# Jobs de lote (assíncrono) — Fase 1 do plano-jobs-lote.md.
#
# Contrato pyCobrança doc 12: recepção síncrona curta (202 + job_id),
# processamento em background por item (falha de um item não cancela o lote),
# consulta do job e dos itens. Estado persistido (sobrevive a restart).
from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from app.core import artifacts as art
from app.core import job_store as js
from app.core import pycob
from app.core.forwarder import forward_event
from app.core.subscriptions import resolve_callback

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: Teto de itens por job (doc 12 sugere 200 como referência inicial).
JOB_MAX_ITENS = int(os.environ.get("JOB_MAX_ITENS", "200"))


# --- documentacao OpenAPI dos POSTs -------------------------------------------
# Os dois handlers leem `await request.json()` (dict cru) para preservar o
# contrato flexivel de item da doc 12. O efeito colateral e que o FastAPI NAO
# consegue gerar o requestBody: o Swagger mostrava os endpoints sem corpo, e o
# consumidor nao tinha como saber o que enviar. `openapi_extra` declara o schema
# SEM mexer na validacao em runtime.

_ITEM_BOLETO = {
    "type": "object",
    "description": "Campos do boleto (mesmos de /api/boleto) + `bank` e, "
                   "opcionalmente, `external_id` para idempotência por item.",
    "required": ["bank"],
    "properties": {
        "bank": {"type": "string", "example": "sicoob"},
        "external_id": {"type": "string",
                        "description": "Idempotência por item: repetir não duplica.",
                        "example": "PED-2026-0001"},
        "valor": {"type": "number", "example": 150.0},
        "cedente": {"type": "string"}, "documento_cedente": {"type": "string"},
        "sacado": {"type": "string"}, "sacado_documento": {"type": "string"},
        "agencia": {"type": "string"}, "conta_corrente": {"type": "string"},
        "convenio": {"type": "string"}, "carteira": {"type": "string"},
        "nosso_numero": {"type": "string"},
        "data_vencimento": {"type": "string", "format": "date"},
    },
    "additionalProperties": True,
}

_CORPO_JOB_BOLETOS = {
    "required": True,
    "content": {"application/json": {"schema": {
        "type": "object",
        "required": ["tenant_id", "boletos"],
        "properties": {
            "tenant_id": {"type": "string", "example": "empresa_hml"},
            "boletos": {"type": "array", "minItems": 1, "maxItems": JOB_MAX_ITENS,
                        "items": _ITEM_BOLETO},
            # `carne` saiu do enum: o job renderiza UM PDF por item, e carnê é
            # 3 boletos numa página. Era opção impossível por construção,
            # oferecida no contrato. Para carnê use POST /api/render/carne.
            "template": {"type": "string", "enum": list(pycob.MODELOS_BOLETO),
                         "default": "moderno"},
        },
    }}},
}

_CORPO_JOB_REMESSAS = {
    "required": True,
    "content": {"application/json": {"schema": {
        "type": "object",
        "required": ["tenant_id", "titulos"],
        "properties": {
            "tenant_id": {"type": "string", "example": "empresa_hml"},
            "titulos": {
                "type": "array", "minItems": 1, "maxItems": JOB_MAX_ITENS,
                "description": "Cada título traz o cabeçalho da remessa e seus "
                               "`pagamentos`. Títulos incompatíveis viram sublotes "
                               "separados (um arquivo CNAB cada).",
                "items": {
                    "type": "object",
                    "required": ["bank", "cnab_type"],
                    "properties": {
                        "bank": {"type": "string", "example": "sicoob"},
                        "cnab_type": {"type": "string", "enum": ["cnab240", "cnab400"]},
                        "pix": {"type": "boolean", "default": False},
                        "pagamentos": {"type": "array", "items": {"type": "object"}},
                    },
                    "additionalProperties": True,
                },
            },
        },
    }}},
}

#: 413 e 404 nao sao inferidos pelo FastAPI (vem de JSONResponse/HTTPException).
_RESP_413 = {413: {"description": f"Acima de JOB_MAX_ITENS (default {JOB_MAX_ITENS}) — "
                                  "divida o volume em jobs menores."}}
_RESP_404 = {404: {"description": "Job não encontrado para o tenant."}}


def _store() -> js.JobStore:
    return js.get_job_store()


def _notificar_conclusao(job_id: str, tenant_id: str, tipo: str, job: dict[str, Any],
                         manifesto: dict[str, Any] | None) -> None:
    """Push assinado (HMAC) ao consumidor dono do tenant — mesmo canal dos
    eventos de banco. No-op se o tenant não tem callback configurado."""
    destino = resolve_callback(tenant_id)
    if not destino:
        return
    url, secret = destino
    evento = {
        "event": f"job.{tipo}.{job.get('status')}",
        "job_id": job_id,
        "tenant_id": tenant_id,
        "tipo": tipo,
        "status": job.get("status"),
        "total": job.get("total"),
        "completed": job.get("completed"),
        "failed": job.get("failed"),
        "duracao_ms": job.get("duracao_ms"),
        "self": f"/jobs/{'cnab/remessas' if tipo == 'cnab_remessas' else 'boletos'}/{job_id}",
    }
    if manifesto:
        evento["artifacts"] = {
            "arquivos": len(manifesto.get("arquivos", [])),
            "consolidado": (manifesto.get("consolidado") or {}).get("href"),
            "expira_em": manifesto.get("expira_em"),
        }
    try:
        forward_event(evento, url=url, secret=secret)
    except Exception:  # noqa: BLE001 — push nunca derruba o job
        pass


def _metricas(job: dict[str, Any], inicio: float) -> dict[str, Any]:
    """Métricas por job (doc 12): duração total e média por item."""
    duracao_ms = int((time.monotonic() - inicio) * 1000)
    total = max(int(job.get("total") or 0), 1)
    return {"duracao_ms": duracao_ms, "ms_por_item": round(duracao_ms / total, 1)}


def _item_id(item: dict[str, Any], indice: int) -> str:
    """Delega para a derivação central — antes era uma terceira cópia."""
    return pycob.item_id(item, indice)


def _itens_e_duplicados(
    itens_brutos: list[dict[str, Any]],
    id_de: Callable[[dict[str, Any], int], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Monta os itens do job e denuncia identificadores repetidos.

    `item_id` é a identidade do item na API (`/items/{item_id}`) e metade da
    chave primária de `job_items`. Dois itens com o mesmo identificador não são
    endereçáveis individualmente — e, antes desta checagem, o INSERT estourava
    `IntegrityError` e o cliente recebia **500** sem saber o que corrigir.

    A colisão é fácil de não notar: `_item_id` só cai no índice (sempre único)
    quando o item não traz `external_id`, `seu_numero` nem `numero_documento`.
    Lote real costuma trazer o número do documento — e repeti-lo é plausível.
    """
    itens: list[dict[str, Any]] = []
    primeiro_indice: dict[str, int] = {}
    repetidos: dict[str, list[int]] = {}
    for indice, bruto in enumerate(itens_brutos):
        item_id = id_de(bruto, indice)
        if item_id in primeiro_indice:
            repetidos.setdefault(item_id, [primeiro_indice[item_id]]).append(indice)
        else:
            primeiro_indice[item_id] = indice
        itens.append({"item_id": item_id, "indice": indice})
    duplicados = [{"item_id": k, "indices": v} for k, v in sorted(repetidos.items())]
    return itens, duplicados


def _processar(job_id: str, tenant_id: str, boletos: list[dict[str, Any]],
               template: str) -> None:
    """Worker (BackgroundTasks): renderiza item a item e persiste o resultado."""
    inicio = time.monotonic()
    store = _store()
    store.atualizar_status(job_id, js.JOB_PROCESSING)
    completos = falhos = 0
    for indice, item in enumerate(boletos):
        item_id = _item_id(item, indice)
        bank = item.get("bank") or item.get("banco") or ""
        dados = {k: v for k, v in item.items() if k not in ("bank", "banco", "external_id")}
        try:
            info = pycob.dados_boleto(bank, dados)
            pdf = pycob.pdf_boleto(bank, dados, template)
        except pycob.DadosInvalidos as e:
            falhos += 1
            store.concluir_item(job_id, item_id, js.ITEM_FAILED,
                                {"bank": bank, "errors": e.erros})
            continue
        except Exception as e:  # noqa: BLE001 — item não pode derrubar o job
            falhos += 1
            store.concluir_item(job_id, item_id, js.ITEM_FAILED,
                                {"bank": bank, "errors": [f"erro inesperado: {e}"]})
            continue
        completos += 1
        # Fase 2: PDF vai para o disco; o item guarda a referência (hash/tamanho).
        artefato = art.salvar_item(job_id, item_id, pdf)
        store.concluir_item(job_id, item_id, js.ITEM_COMPLETED,
                            {"bank": bank, **info, "artifact": artefato})
    final = (js.JOB_COMPLETED if not falhos
             else js.JOB_FAILED if not completos else js.JOB_PARTIAL)
    store.atualizar_status(job_id, final, completed=completos, failed=falhos)
    # Manifesto + errors.json + zip consolidado (doc 12: nada de base64 em lote).
    job = store.obter(tenant_id, job_id) or {"tenant_id": tenant_id, "status": final,
                                              "total": len(boletos), "tipo": "boletos"}
    manifesto = art.consolidar(job_id, job, store.itens(job_id, limite=10_000))
    job.update(_metricas(job, inicio))
    store.salvar_metricas(job_id, _metricas(job, inicio))
    _notificar_conclusao(job_id, tenant_id, "boletos", job, manifesto)


@router.post("/boletos", status_code=202,
             openapi_extra={"requestBody": _CORPO_JOB_BOLETOS},
             responses=_RESP_413)
async def criar_job_boletos(
    request: Request,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Cria um job de emissão em lote e responde **202** com o `job_id`.

    Corpo: `{tenant_id, boletos: [...], template?}`. Cada item aceita
    `external_id` (idempotência por item) além dos campos do boleto e `bank`.
    """
    corpo = await request.json()
    tenant_id = corpo.get("tenant_id")
    boletos = corpo.get("boletos") or []
    if not tenant_id:
        raise HTTPException(status_code=422, detail="campo obrigatório: tenant_id")
    if not boletos:
        raise HTTPException(status_code=422, detail="campo obrigatório: boletos (não vazio)")
    if len(boletos) > JOB_MAX_ITENS:
        return JSONResponse(status_code=413, content={
            "error": f"Job acima do limite de {JOB_MAX_ITENS} itens",
            "recebidos": len(boletos)})

    # O template era aceito, gravado em meta e DESCARTADO pelo worker: o job
    # registrava um modelo que nunca foi aplicado. Validar aqui é o que impede
    # o job de rodar inteiro para só então o metadado mentir sobre o resultado.
    template = corpo.get("template", "moderno")
    if template not in pycob.MODELOS_BOLETO:
        extra = (" — carnê é 3 boletos por página e não cabe no job, que gera um"
                 " PDF por item; use POST /api/render/carne") if template == "carne" else ""
        return JSONResponse(status_code=422, content={
            "error": f"template '{template}' inválido",
            "validation_errors": [f"use um de: {', '.join(pycob.MODELOS_BOLETO)}{extra}"]})

    store = _store()
    if idempotency_key:
        existente = store.por_idempotencia(tenant_id, idempotency_key)
        if existente:  # mesma chave -> MESMO job (não recria)
            job = store.obter(tenant_id, existente)
            return JSONResponse(status_code=200, content={
                "job_id": existente, "status": job["status"], "total": job["total"],
                "idempotent_replay": True, "self": f"/jobs/boletos/{existente}"})

    itens, duplicados = _itens_e_duplicados(boletos, _item_id)
    if duplicados:
        return JSONResponse(status_code=422, content={
            "error": "Itens com identificador duplicado no lote",
            "hint": "o item_id vem de external_id, seu_numero ou numero_documento —"
                    " cada item do lote precisa de um valor distinto",
            "duplicados": duplicados})

    job_id = js.novo_job_id()
    store.criar({"job_id": job_id, "tenant_id": tenant_id, "tipo": "boletos",
                 "status": js.JOB_RECEIVED, "total": len(boletos),
                 "idempotency_key": idempotency_key, "criado_em": js.agora(),
                 "meta": {"template": template}}, itens)
    background.add_task(_processar, job_id, tenant_id, boletos, template)
    return {"job_id": job_id, "status": js.JOB_RECEIVED, "recebidos": len(boletos),
            "self": f"/jobs/boletos/{job_id}",
            "items": f"/jobs/boletos/{job_id}/items"}


@router.get("/boletos/{job_id}", responses=_RESP_404)
def consultar_job(job_id: str, tenant_id: str) -> Any:
    """Estado do job + contadores (received/processing/completed/partially_completed/failed)."""
    job = _store().obter(tenant_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    return {
        "job_id": job["job_id"], "tipo": job["tipo"], "status": job["status"],
        "total": job["total"], "completed": job["completed"], "failed": job["failed"],
        "criado_em": job["criado_em"], "atualizado_em": job["atualizado_em"],
        "meta": job["meta"], "metricas": job["meta"].get("metricas"),
        "items": f"/jobs/boletos/{job_id}/items",
    }


@router.get("/boletos/{job_id}/items", responses=_RESP_404)
def listar_itens(job_id: str, tenant_id: str, status: str | None = None,
                 limite: int = Query(default=100, le=500), offset: int = 0) -> Any:
    """Itens do job (paginado; filtro opcional por `status`)."""
    store = _store()
    if not store.obter(tenant_id, job_id):
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    itens = store.itens(job_id, status=status, limite=limite, offset=offset)
    return {"job_id": job_id, "total_retornado": len(itens),
            "limite": limite, "offset": offset, "items": itens}


@router.get("/boletos/{job_id}/items/{item_id}", responses=_RESP_404)
def consultar_item(job_id: str, item_id: str, tenant_id: str) -> Any:
    """Um item do lote: estado, artefato e — se falhou — o erro daquele boleto.

    É por aqui que se investiga um `partially_completed`: o job segue em frente
    quando um item falha, e o motivo fica no item, não no job.
    """
    store = _store()
    if not store.obter(tenant_id, job_id):
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    for item in store.itens(job_id, limite=500):
        if item["item_id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="item não encontrado no job")


# ------------------------------------------------------------------ artefatos
@router.get("/boletos/{job_id}/artifacts", responses=_RESP_404)
def manifesto_artefatos(job_id: str, tenant_id: str) -> Any:
    """Manifesto do job: arquivos, `sha256`, tamanhos, expiração e consolidado `.zip`.

    Contrato doc 12: o lote entrega **referências**, nunca PDFs em base64.
    """
    if not _store().obter(tenant_id, job_id):
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    manifesto = art.ler_manifesto(job_id)
    if not manifesto:
        raise HTTPException(status_code=404,
                            detail="artefatos ainda não disponíveis (job em processamento)")
    if art.expirado(manifesto):
        raise HTTPException(status_code=410, detail="artefatos expirados")
    return manifesto


@router.get("/boletos/{job_id}/artifacts/items/{nome}", responses=_RESP_404)
def baixar_artefato_item(job_id: str, nome: str, tenant_id: str) -> Any:
    """Download do PDF de um item."""
    if not _store().obter(tenant_id, job_id):
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    caminho = art.caminho_artefato(job_id, nome, item=True)
    if not caminho:
        raise HTTPException(status_code=404, detail="artefato não encontrado")
    return FileResponse(caminho, media_type="application/pdf", filename=nome)


@router.get("/boletos/{job_id}/artifacts/{nome}", responses=_RESP_404)
def baixar_artefato(job_id: str, nome: str, tenant_id: str) -> Any:
    """Download do consolidado (`.zip`), do `manifest.json` ou do `errors.json`."""
    if not _store().obter(tenant_id, job_id):
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    caminho = art.caminho_artefato(job_id, nome)
    if not caminho:
        raise HTTPException(status_code=404, detail="artefato não encontrado")
    tipo = "application/zip" if nome.endswith(".zip") else "application/json"
    return FileResponse(caminho, media_type=tipo, filename=nome)


# ------------------------------------------------------------------ CNAB (Fase 3)
def _processar_remessas(job_id: str, tenant_id: str,
                        sublotes: list[dict[str, Any]]) -> None:
    """Worker: gera 1 arquivo CNAB por sublote compatível."""
    inicio = time.monotonic()
    store = _store()
    store.atualizar_status(job_id, js.JOB_PROCESSING)
    completos = falhos = 0
    for sublote in sublotes:
        sid = sublote["sublote_id"]
        try:
            conteudo = pycob.gerar_remessa(sublote["bank"], sublote["cnab_type"],
                                            sublote["dados"], pix=sublote["pix"])
        except pycob.DadosInvalidos as e:
            falhos += 1
            store.concluir_item(job_id, sid, js.ITEM_FAILED,
                                {"chave": sublote["chave"], "errors": e.erros})
            continue
        except Exception as e:  # noqa: BLE001 — sublote não derruba o job
            falhos += 1
            store.concluir_item(job_id, sid, js.ITEM_FAILED,
                                {"chave": sublote["chave"],
                                 "errors": [f"erro inesperado: {e}"]})
            continue
        completos += 1
        artefato = art.salvar_remessa(job_id, sid, conteudo)
        store.concluir_item(job_id, sid, js.ITEM_COMPLETED,
                            {"chave": sublote["chave"], "quantidade": sublote["quantidade"],
                             "artifact": artefato})
    final = (js.JOB_COMPLETED if not falhos
             else js.JOB_FAILED if not completos else js.JOB_PARTIAL)
    store.atualizar_status(job_id, final, completed=completos, failed=falhos)
    job = store.obter(tenant_id, job_id) or {"tenant_id": tenant_id, "status": final,
                                              "total": len(sublotes)}
    manifesto = art.consolidar_remessas(job_id, job, store.itens(job_id, limite=10_000))
    job.update(_metricas(job, inicio))
    store.salvar_metricas(job_id, _metricas(job, inicio))
    _notificar_conclusao(job_id, tenant_id, "cnab_remessas", job, manifesto)


@router.post("/cnab/remessas", status_code=202,
             openapi_extra={"requestBody": _CORPO_JOB_REMESSAS},
             responses=_RESP_413)
async def criar_job_remessas(
    request: Request,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Cria um job de remessa CNAB em lote com **sublotes determinísticos**.

    Corpo: `{tenant_id, titulos: [...]}`. Cada título traz o cabeçalho da
    remessa (`bank`, `cnab_type`, convênio, carteira, conta…) e seus
    `pagamentos`. Títulos **incompatíveis nunca entram no mesmo arquivo** —
    são separados por (banco, layout, convênio, carteira, conta, agência,
    variação, pix), gerando um arquivo CNAB por sublote.
    """
    corpo = await request.json()
    tenant_id = corpo.get("tenant_id")
    titulos = corpo.get("titulos") or []
    if not tenant_id:
        raise HTTPException(status_code=422, detail="campo obrigatório: tenant_id")
    if not titulos:
        raise HTTPException(status_code=422, detail="campo obrigatório: titulos (não vazio)")
    if len(titulos) > JOB_MAX_ITENS:
        return JSONResponse(status_code=413, content={
            "error": f"Job acima do limite de {JOB_MAX_ITENS} títulos",
            "recebidos": len(titulos)})

    store = _store()
    if idempotency_key:
        existente = store.por_idempotencia(tenant_id, idempotency_key)
        if existente:
            job = store.obter(tenant_id, existente)
            return JSONResponse(status_code=200, content={
                "job_id": existente, "status": job["status"], "total": job["total"],
                "idempotent_replay": True, "self": f"/jobs/cnab/remessas/{existente}"})

    sublotes = pycob.agrupar_sublotes(titulos)
    # `sublote_id` sai do agrupamento e deve ser único por construção. A
    # checagem fica como rede: se o agrupamento mudar e passar a repetir, o
    # cliente recebe 422 explicando, em vez de 500 vindo do banco.
    itens, duplicados = _itens_e_duplicados(sublotes, lambda s, _i: str(s["sublote_id"]))
    if duplicados:
        return JSONResponse(status_code=422, content={
            "error": "Sublotes com identificador duplicado",
            "hint": "falha no agrupamento determinístico de títulos — reporte o caso",
            "duplicados": duplicados})

    job_id = js.novo_job_id()
    store.criar({"job_id": job_id, "tenant_id": tenant_id, "tipo": "cnab_remessas",
                 "status": js.JOB_RECEIVED, "total": len(sublotes),
                 "idempotency_key": idempotency_key, "criado_em": js.agora(),
                 "meta": {"titulos": len(titulos), "sublotes": len(sublotes)}}, itens)
    background.add_task(_processar_remessas, job_id, tenant_id, sublotes)
    return {"job_id": job_id, "status": js.JOB_RECEIVED, "titulos": len(titulos),
            "sublotes": [{"sublote_id": s["sublote_id"], "chave": s["chave"],
                          "quantidade": s["quantidade"]} for s in sublotes],
            "self": f"/jobs/cnab/remessas/{job_id}",
            "files": f"/jobs/cnab/remessas/{job_id}/files"}


@router.get("/cnab/remessas/{job_id}", responses=_RESP_404)
def consultar_job_remessas(job_id: str, tenant_id: str) -> Any:
    """Estado do job de remessa e a lista de **sublotes** gerados.

    O lote é dividido por banco/layout/convênio/carteira/conta — um arquivo por
    combinação, porque o banco não aceita remessa misturada. Os arquivos ficam
    em `/jobs/cnab/remessas/{job_id}/files`.
    """
    job = _store().obter(tenant_id, job_id)
    if not job or job["tipo"] != "cnab_remessas":
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    return {"job_id": job["job_id"], "tipo": job["tipo"], "status": job["status"],
            "sublotes": job["total"], "completed": job["completed"],
            "failed": job["failed"], "criado_em": job["criado_em"],
            "atualizado_em": job["atualizado_em"], "meta": job["meta"],
            "metricas": job["meta"].get("metricas"),
            "files": f"/jobs/cnab/remessas/{job_id}/files"}


@router.get("/cnab/remessas/{job_id}/files", responses=_RESP_404)
def listar_arquivos_remessa(job_id: str, tenant_id: str) -> Any:
    """Manifesto dos arquivos CNAB: 1 por sublote, com `sha256`, registros e chave."""
    job = _store().obter(tenant_id, job_id)
    if not job or job["tipo"] != "cnab_remessas":
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    manifesto = art.ler_manifesto(job_id)
    if not manifesto:
        raise HTTPException(status_code=404,
                            detail="arquivos ainda não disponíveis (job em processamento)")
    if art.expirado(manifesto):
        raise HTTPException(status_code=410, detail="arquivos expirados")
    return manifesto


@router.get("/cnab/remessas/{job_id}/files/{nome}", responses=_RESP_404)
def baixar_arquivo_remessa(job_id: str, nome: str, tenant_id: str) -> Any:
    """Download de um arquivo CNAB (`.rem`), do consolidado `.zip` ou do manifesto."""
    job = _store().obter(tenant_id, job_id)
    if not job or job["tipo"] != "cnab_remessas":
        raise HTTPException(status_code=404, detail="job não encontrado para o tenant")
    caminho = art.caminho_arquivo_cnab(job_id, nome)
    if not caminho:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")
    tipo = ("application/zip" if nome.endswith(".zip")
            else "application/json" if nome.endswith(".json") else "text/plain")
    return FileResponse(caminho, media_type=tipo, filename=nome)
