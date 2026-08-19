# Superfície OFFLINE /api/* — NATIVA (engine pyCobranca, in-process).
#
# Nova Versão 100% Python: substitui o proxy para o Banking Core BrCobrança
# (Ruby), cuja conexão foi DESCONTINUADA.
# mesmos paths, campos, headers X-* e formatos de erro.
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.core import pycob
from app.core.swagger_tema import pagina_swagger

router = APIRouter(tags=["offline"])

# Limite de itens por lote síncrono (pyCobrança doc 12 — acima disso, jobs).
LOTE_MAX = int(os.environ.get("LOTE_MAX_ITENS", "200"))

#: Teto por header JSON. `X-Boletos-Info` carrega metadados de CADA item e cresce
#: ~300 B por boleto (medido em scripts/benchmark_lote.py): 100 itens ~30 KB,
#: 200 ~60 KB, 500 ~150 KB.
#:
#: O default 8 KB e o que passa em QUALQUER lugar: e o limite por linha do nginx
#: (large_client_header_buffers) e cabe no ALB (16 KB) e no http.client (64 KB).
#: Na pratica: ate ~27 boletos o detalhe vem no header; acima disso ele e
#: truncado e sinalizado, e o detalhe sai por `include_data=true` — sem limite.
#: Os contadores (`X-Boletos-Count`, `X-Boletos-Failed`, `X-Batch-Status`) sao
#: pequenos e vem SEMPRE.
HEADER_JSON_MAX = int(os.environ.get("HEADER_JSON_MAX_BYTES", str(8 * 1024)))

#: Teto por arquivo enviado. As quatro rotas de upload faziam `await ler()` do
#: arquivo INTEIRO para a memória, sem olhar o tamanho: um POST grande derruba o
#: processo antes de qualquer validação. O teto vem antes da leitura útil e
#: responde 413, que é o mesmo código do lote acima de LOTE_MAX.
UPLOAD_MAX = int(os.environ.get("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))

#: Vocabulário do enum que a spec publicada já declara para `include_data` e
#: `pix`. O código aceitava só `"true"` e tratava TODO o resto como `false` —
#: `include_data=1` respondia 200 com o PDF binário, quando o chamador pediu
#: JSON. Parâmetro fora do enum é erro do chamador, não um `false` silencioso.
_BOOL_ACEITOS = {"true": True, "false": False}


class ParametroInvalido(pycob.DadosInvalidos):
    """Erro de parâmetro do chamador — o router traduz para 400."""


def _bool_param(nome: str, valor: str) -> bool:
    escolhido = _BOOL_ACEITOS.get((valor or "").strip().lower())
    if escolhido is None:
        raise ParametroInvalido(
            [f"`{nome}` deve ser 'true' ou 'false'; recebido: {valor!r}"])
    return escolhido


async def _ler_upload(arquivo: Any, campo: str) -> bytes:
    """Lê o arquivo enviado, com teto e sem aceitar vazio."""
    dados = await arquivo.read()
    if len(dados) > UPLOAD_MAX:
        raise ArquivoGrandeDemais(campo, len(dados))
    if not dados:
        raise ParametroInvalido([f"`{campo}`: arquivo vazio"])
    return dados


class ArquivoGrandeDemais(Exception):
    def __init__(self, campo: str, tamanho: int) -> None:
        super().__init__(campo)
        self.campo = campo
        self.tamanho = tamanho

    def resposta(self) -> JSONResponse:
        return JSONResponse(status_code=413, content={
            "error": f"Arquivo acima do limite de {UPLOAD_MAX} bytes",
            "campo": self.campo, "recebidos": self.tamanho,
            "hint": "divida o arquivo (o teto vem de UPLOAD_MAX_BYTES)"})


def _json_cabecalho(valor: list[dict[str, Any]], flag: str,
                    cab: dict[str, str]) -> str:
    """Serializa em header; se nao couber, devolve `[]` e sinaliza a truncagem.

    Sem isto o lote grande sai com header impossivel de ler. Truncando, o PDF
    continua entregue e o cliente sabe onde buscar o detalhe: `include_data=true`
    devolve os mesmos dados NO CORPO, sem limite de tamanho.
    """
    txt = json.dumps(valor)  # ensure_ascii: header é latin-1
    if len(txt.encode("latin-1", "replace")) <= HEADER_JSON_MAX:
        return txt
    cab[flag] = "true"
    cab.setdefault("X-Boletos-Detalhe", "use include_data=true (metadados no corpo)")
    return "[]"


def _spec_path() -> Path:
    # repo (dev) e imagem (produção: COPY docs/openapi.yaml /docs/)
    for p in (Path(__file__).resolve().parents[3] / "docs" / "openapi.yaml",
              Path("/docs/openapi.yaml")):
        if p.exists():
            return p
    return Path("/docs/openapi.yaml")


_SPEC = _spec_path()

#: A spec offline é escrita à mão e servida em três formas (`/api/openapi.json`,
#: `/api/openapi.yaml`, `/api/docs`). Ler e parsear 75 KB de YAML A CADA chamada
#: custava ~150 ms — trinta vezes o resto da superfície, e é justamente o que o
#: Swagger da própria API busca ao abrir.
#:
#: A chave é o mtime, não "carregou uma vez": em produção o arquivo não muda e
#: o custo vira um `stat`; em desenvolvimento, editar o YAML e recarregar a
#: página continua mostrando a edição, sem reiniciar o processo.
_cache_spec: tuple[float, bytes, dict[str, Any], str] | None = None


class SpecAusente(HTTPException):
    """Doc offline sem o arquivo → 503 dizendo ONDE ele foi procurado.

    `docs/openapi.yaml` é asset de RUNTIME, copiado para a imagem — já ficou de
    fora por causa do `.dockerignore`, e as três rotas passaram a responder
    "Internal Server Error". 500 anônimo manda procurar no lugar errado (a
    aplicação); o caminho no corpo aponta para o empacotamento, que é onde o
    defeito está. 503 porque a API segue inteira: só a documentação caiu.

    Herda de `HTTPException` em vez de virar um handler próprio no `main`: o
    handler casa por classe, e `importlib.reload` deste módulo — que os testes
    do carnê fazem para reler `LOTE_MAX_ITENS` — cria uma classe NOVA que o
    handler antigo não reconhece. O erro voltaria a ser 500, e só na suíte
    inteira. Pendurar no `HTTPException` resolve pela MRO.
    """

    def __init__(self, detalhe: str) -> None:
        super().__init__(status_code=503, detail=(
            f"{detalhe}. O arquivo é asset de RUNTIME: confira o COPY do"
            " Dockerfile e as exceções do .dockerignore"))


def _carregar_spec() -> tuple[bytes, dict[str, Any], str]:
    """Bytes crus, árvore JSON e ETag da spec offline.

    Devolve o YAML **cru** junto com a árvore porque `/api/openapi.yaml` promete
    o arquivo byte a byte: reserializar traria outro texto, com outra ordem e
    outros comentários.
    """
    global _cache_spec
    try:
        mtime = _SPEC.stat().st_mtime
    except OSError as e:
        # Já aconteceu em produção: o `.dockerignore` excluiu o YAML da imagem e
        # as três rotas passaram a responder "Internal Server Error", sem dizer
        # o que faltava. O caminho procurado é a informação que resolve.
        raise SpecAusente(f"spec offline não encontrada em {_SPEC}") from e

    if _cache_spec is None or _cache_spec[0] != mtime:
        cru = _SPEC.read_bytes()
        arvore = yaml.safe_load(cru.decode("utf-8"))
        # Sem `default=str`: converter em silêncio faria `/api/openapi.json` e
        # `/api/openapi.yaml` responderem coisas diferentes para o mesmo campo
        # (data não quotada vira texto num e segue data no outro). Quem barra
        # isso antes de subir é o CI; aqui é a segunda linha, e ela nomeia o
        # campo em vez de deixar um TypeError anônimo subir.
        try:
            json.dumps(arvore)
        except TypeError as e:
            raise SpecAusente(
                f"{_SPEC} tem valor que o JSON não expressa ({e}) — quote-o no"
                " YAML, senão /api/openapi.json e /api/openapi.yaml divergem") from e
        _cache_spec = (mtime, cru, arvore, hashlib.sha256(cru).hexdigest()[:32])
    return _cache_spec[1], _cache_spec[2], _cache_spec[3]


def _resposta_condicional(request: Request, etag: str) -> Response | None:
    """304 quando o navegador já tem esta versão — o Swagger reabre muito."""
    if request.headers.get("if-none-match") == f'"{etag}"':
        return Response(status_code=304, headers=_cabecalhos_spec(etag))
    return None


def _cabecalhos_spec(etag: str) -> dict[str, str]:
    return {"ETag": f'"{etag}"', "Cache-Control": "no-cache"}


def _erro_validacao(e: pycob.DadosInvalidos) -> JSONResponse:
    return JSONResponse(status_code=400, content={
        "error": "Dados do boleto inválidos",
        "validation_errors": e.erros,
        "hint": "Verifique se todos os campos obrigatórios estão preenchidos",
    })


# JSON válido não é payload válido: `"texto"`, `123` e `[]` passam pelo
# `json.loads` e só explodem lá dentro, quando a engine chama `.get()` no que
# achava ser um objeto — `AttributeError`, 500, "Internal Server Error" para
# quem só errou a FORMA do corpo. O parse já respondia 400 nesse caso; a forma
# não era conferida em lugar nenhum.
_NOME_JSON = {dict: "objeto", list: "lista", str: "texto", bool: "booleano",
              int: "número", float: "número", type(None): "null"}


def _tipo_json(valor: Any) -> str:
    return _NOME_JSON.get(type(valor), type(valor).__name__)


def _objeto(valor: Any, campo: str) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise pycob.DadosInvalidos(
            [f"`{campo}` deve ser um objeto JSON — recebi {_tipo_json(valor)}"])
    return valor


def _lista_de_objetos(valor: Any, campo: str) -> list[dict[str, Any]]:
    if not isinstance(valor, list):
        raise pycob.DadosInvalidos(
            [f"`{campo}` deve ser uma lista JSON — recebi {_tipo_json(valor)}"])
    # Só os primeiros: lote de 200 itens de tipo errado não vira 200 linhas de erro.
    ruins = [i for i, item in enumerate(valor) if not isinstance(item, dict)][:5]
    if ruins:
        raise pycob.DadosInvalidos(
            [f"`{campo}[{i}]` deve ser um objeto JSON — recebi {_tipo_json(valor[i])}"
             for i in ruins])
    return valor


def _data_param(data: str) -> dict[str, Any]:
    try:
        valores = json.loads(data)
    except json.JSONDecodeError as e:
        raise pycob.DadosInvalidos([f"JSON inválido no parâmetro data: {e}"]) from e
    return _objeto(valores, "data")


# ------------------------------------------------------------------ saúde/meta
@router.get("/api/health", include_in_schema=False)
def api_health() -> dict[str, str]:
    from datetime import datetime, timezone

    return {"status": "OK", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/api/info", include_in_schema=False)
def api_info() -> dict[str, Any]:
    return {
        "name": "Cobranca-API — Offline (pyCobranca)",
        "version": pycob.versao(),
        "engine": "pycobranca",
        "supported_banks": pycob.bancos_suportados(),
        "formats": ["pdf"],
        "cnab": ["cnab240", "cnab400"],
    }


@router.get("/api/metadata", include_in_schema=False)
def api_metadata(request: Request) -> dict[str, Any]:
    return {
        "api": {"name": "Cobranca-API — Offline (pyCobranca)",
                 "version": request.app.version, "engine": "python"},
        "pycobranca": {"version": pycob.versao(),
                        "repository": "https://github.com/Maxwbh/pyCobranca"},
        "endpoints": {
            "health": "GET /api/health", "info": "GET /api/info",
            "metadata": "GET /api/metadata", "bancos": "GET /api/bancos",
            "boleto_validate": "GET /api/boleto/validate",
            "boleto_data": "GET /api/boleto/data",
            "boleto_nosso_numero": "GET /api/boleto/nosso_numero",
            "boleto": "GET /api/boleto", "boleto_multi": "POST /api/boleto/multi",
            "remessa": "POST /api/remessa", "retorno": "POST /api/retorno",
            "ofx_parse": "POST /api/ofx/parse",
            "render_boleto": "POST /api/render/boleto",
            "render_carne": "POST /api/render/carne",
            "render_fatura": "POST /api/render/fatura",
            "render_remessa": "POST /api/render/remessa",
        },
    }


@router.get("/api/bancos", include_in_schema=False)
def api_bancos() -> dict[str, Any]:
    bancos = []
    for slug in pycob.bancos_suportados():
        codigo = pycob.CODIGO_POR_SLUG[slug]
        remessas = sorted({t for (b, t, _p) in pycob._REMESSAS if b == slug})
        pix = any(p for (b, _t, p) in pycob._REMESSAS if b == slug)
        bancos.append({"slug": slug, "codigo": codigo, "boleto": True,
                        "cnab": remessas, "pix_remessa": pix})
    return {"total": len(bancos), "bancos": bancos, "engine": "pycobranca"}


# ------------------------------------------------------------------ boleto
@router.get("/api/boleto/validate", include_in_schema=False)
def boleto_validate(bank: str, data: str) -> Any:
    try:
        pycob.validar(bank, _data_param(data))
    except pycob.DadosInvalidos as e:
        return JSONResponse(status_code=400, content={
            "valid": False, "validation_errors": e.erros,
            "hint": "Corrija os erros de validação antes de gerar o boleto"})
    return {"valid": True, "message": "Dados do boleto são válidos"}


@router.get("/api/boleto/data", include_in_schema=False)
def boleto_data(bank: str, data: str) -> Any:
    try:
        return pycob.dados_boleto(bank, _data_param(data))
    except pycob.DadosInvalidos as e:
        return _erro_validacao(e)


@router.get("/api/boleto/nosso_numero", include_in_schema=False)
def boleto_nosso_numero(bank: str, data: str) -> Any:
    try:
        d = pycob.dados_boleto(bank, _data_param(data))
    except pycob.DadosInvalidos as e:
        return _erro_validacao(e)
    return {k: d[k] for k in ("bank", "nosso_numero", "nosso_numero_formatado", "nosso_numero_dv")}


#: Modelos aceitos no lote. `carne` (3 vias por A4) só existe aqui e em
#: `/api/render/carne`; os demais vêm da engine, para não haver duas listas.
_TEMPLATES_LOTE = ("carne", *sorted(pycob.MODELOS_BOLETO))


def _headers_boleto(d: dict[str, Any]) -> dict[str, str]:
    return {
        "X-Nosso-Numero": d["nosso_numero"],
        "X-Nosso-Numero-Formatado": d["nosso_numero_formatado"],
        "X-Nosso-Numero-DV": d["nosso_numero_dv"],
        "X-Codigo-Barras": d["codigo_barras"],
        "X-Linha-Digitavel": d["linha_digitavel"],
    }


@router.get("/api/boleto", include_in_schema=False)
def boleto(bank: str, data: str, type: str = "pdf",
           include_data: str = "false", template: str = "moderno") -> Any:
    if type != "pdf":
        return JSONResponse(status_code=400, content={
            "error": f"Formato '{type}' descontinuado — a engine pyCobranca gera PDF",
            # Lista plana como em todo o resto da superfície. Aqui era o único
            # lugar que devolvia objeto-por-campo: quem itera `validation_errors`
            # esperando mensagens recebia a string "type".
            "validation_errors": ["`type` deve ser 'pdf'"]})
    try:
        detalhar = _bool_param("include_data", include_data)
        valores = _data_param(data)
        info = pycob.dados_boleto(bank, valores)
        pdf = pycob.pdf_boleto(bank, valores, template)
    except pycob.DadosInvalidos as e:
        return _erro_validacao(e)
    if detalhar:
        return {**info, "content_base64": base64.b64encode(pdf).decode(),
                "content_type": "application/pdf", "filename": f"boleto-{bank}.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=boleto-{bank}.pdf",
        **_headers_boleto(info)})


@router.post("/api/boleto/multi", include_in_schema=False)
async def boleto_multi(data: UploadFile = File(...), type: str = "pdf",
                       include_data: str = "false", template: str = "moderno") -> Any:
    if type != "pdf":
        return JSONResponse(status_code=400, content={
            "error": f"Formato '{type}' descontinuado — a engine pyCobranca gera PDF",
            "validation_errors": ["`type` deve ser 'pdf'"]})
    # `pdf_multi` cai em `moderno` quando não reconhece o modelo. Silêncio aqui
    # é pior que erro: o irmão `GET /api/boleto` responde 400 para o mesmo
    # valor, então `template=modrno` saía 200 com o lote no modelo errado e
    # ninguém tinha como saber. Quem valida é a rota — o teto de qualidade da
    # engine é gerar o PDF, não conferir o contrato REST.
    if template not in _TEMPLATES_LOTE:
        return JSONResponse(status_code=400, content={
            "error": "Dados do boleto inválidos",
            "validation_errors": [f"template '{template}' inválido"
                                  f" (use: {', '.join(_TEMPLATES_LOTE)})"]})
    try:
        detalhar = _bool_param("include_data", include_data)
        boletos = _lista_de_objetos(json.loads(await _ler_upload(data, "data")), "data")
        if len(boletos) > LOTE_MAX:
            return JSONResponse(status_code=413, content={
                "error": f"Lote acima do limite de {LOTE_MAX} itens",
                "recebidos": len(boletos),
                "hint": "divida o lote (processamento assíncrono: ver docs/development/plano-jobs-lote.md)"})
        # Dois itens com o mesmo identificador são o MESMO título emitido duas
        # vezes: o PDF sai com a duplicata impressa e o título sobrescrito nunca
        # é cobrado — some do lote em silêncio. O `pdf_multi` já calculava isso
        # e o resultado era descartado aqui.
        repetidos = pycob.duplicados(boletos)
        if repetidos:
            return JSONResponse(status_code=422, content={
                "error": "Itens com identificador duplicado no lote",
                "hint": "o item_id vem de external_id, seu_numero ou numero_documento —"
                        " cada item precisa de um valor distinto",
                "duplicados": repetidos})
        pdf, itens = pycob.pdf_multi(boletos, template=template)
    except ArquivoGrandeDemais as e:
        return e.resposta()
    except (json.JSONDecodeError, pycob.DadosInvalidos) as e:
        erros = e.erros if isinstance(e, pycob.DadosInvalidos) else [str(e)]
        return JSONResponse(status_code=400, content={
            "error": "Boleto(s) com erros de validação", "validation_errors": erros})
    ok = [i for i in itens if i["status"] == "completed"]
    falhas = [i for i in itens if i["status"] == "failed"]
    resumo = {"total": len(itens), "completed": len(ok), "failed": len(falhas),
              "status": "partially_completed" if falhas else "completed"}
    if detalhar:
        return {**resumo, "boletos": ok, "erros": falhas,
                "content_base64": base64.b64encode(pdf).decode(),
                "content_type": "application/pdf", "filename": "boletos-multi.pdf"}
    cab = {"Content-Disposition": "attachment; filename=boletos-multi.pdf",
           "X-Boletos-Count": str(len(ok)),
           "X-Boletos-Failed": str(len(falhas)),
           "X-Batch-Status": resumo["status"]}
    cab["X-Boletos-Info"] = _json_cabecalho(ok, "X-Boletos-Info-Truncado", cab)
    cab["X-Boletos-Errors"] = _json_cabecalho(falhas, "X-Boletos-Errors-Truncado", cab) \
        if falhas else "[]"
    return Response(content=pdf, media_type="application/pdf", headers=cab)


# ------------------------------------------------------------------ CNAB
@router.post("/api/remessa", include_in_schema=False)
async def remessa(bank: str, type: str, data: UploadFile = File(...),
                  pix: str = "false") -> Any:
    try:
        com_pix = _bool_param("pix", pix)
        valores = _objeto(json.loads(await _ler_upload(data, "data")), "data")
        conteudo = pycob.gerar_remessa(bank, type, valores, pix=com_pix)
    except ArquivoGrandeDemais as e:
        return e.resposta()
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={
            "error": "Erro ao gerar remessa", "validation_errors": [f"JSON inválido: {e}"]})
    except pycob.DadosInvalidos as e:
        return JSONResponse(status_code=400, content={
            "error": "Erro ao gerar remessa", "validation_errors": e.erros})
    sufixo = "-pix" if com_pix else ""
    return Response(content=conteudo, media_type="text/plain", headers={
        "Content-Disposition": f"attachment; filename=remessa-{bank}-{type}{sufixo}.rem"})


@router.post("/api/retorno", include_in_schema=False)
async def retorno(bank: str, type: str, data: UploadFile = File(...)) -> Any:
    try:
        return pycob.parse_retorno(await _ler_upload(data, "data"), layout_hint=type)
    except ArquivoGrandeDemais as e:
        return e.resposta()
    except pycob.DadosInvalidos as e:
        # `validation_errors` é a chave canônica em toda a superfície; esta rota
        # era a única com `details`, e quem escreve um handler genérico de erro
        # tinha de conhecer as duas. A antiga fica como alias.
        return JSONResponse(status_code=400, content={
            "error": "Erro ao processar retorno",
            "validation_errors": e.erros, "details": e.erros})


# ------------------------------------------------------------------ OFX
@router.post("/api/ofx/parse", include_in_schema=False)
async def ofx_parse(file: UploadFile = File(...), somente_creditos: str = Form("false")) -> Any:
    """Extrato OFX (v1 SGML e v2 XML) lido pela engine.

    O `nosso_numero` sai do memo com regra POR BANCO (`extrair_nosso_numero`),
    não com regex genérico: cada banco formata o memo do seu jeito.
    """
    try:
        so_creditos = _bool_param("somente_creditos", somente_creditos)
        raw = await _ler_upload(file, "file")
        extrato = pycob.ler_ofx(raw, somente_creditos=so_creditos)
    except ArquivoGrandeDemais as e:
        return e.resposta()
    except pycob.DadosInvalidos as e:
        # arquivo invalido = 400. Bug inesperado NAO vira 400 falso: sobe a 500.
        # `error` acompanha o resto da superfície; `erro` fica como alias.
        return JSONResponse(status_code=400, content={
            "error": "Arquivo OFX inválido", "erro": "Arquivo OFX inválido",
            "validation_errors": e.erros})

    def _direcao(t) -> str:
        """Crédito ou débito — pelo TRNTYPE do arquivo, não pelo sinal.

        A engine **normaliza o valor para positivo** e guarda a direção em
        `tipo` (o TRNTYPE do OFX). Deduzir do sinal, como se fazia aqui, dava
        `credito` para TUDO: o `-350,50` de um pagamento chegava como `350,50`,
        entrava na soma de créditos e `total_debitos` ficava eternamente `0`.
        Num extrato de conciliação isso conta dinheiro que saiu como dinheiro
        que entrou.

        O sinal continua valendo como segunda opinião: arquivo que preserve o
        negativo é débito mesmo que o TRNTYPE não diga.
        """
        if t.valor < 0 or str(getattr(t, "tipo", "") or "").upper() == "DEBIT":
            return "debito"
        return "credito"

    transacoes = [{
        "tipo": _direcao(t),
        "valor": abs(float(t.valor)),
        "data": t.data.isoformat() if t.data else None,
        "memo": (t.memo or "").strip(),
        "id": t.fitid or None,
        "nosso_numero": t.nosso_numero_extraido,
    } for t in extrato.transacoes]

    creditos = sum(x["valor"] for x in transacoes if x["tipo"] == "credito")
    debitos = sum(x["valor"] for x in transacoes if x["tipo"] == "debito")
    datas = [t["data"] for t in transacoes if t["data"]]
    corpo = {
        "banco": {"org": extrato.org, "fid": extrato.fid},
        "conta": {"agencia": extrato.agencia, "numero": extrato.conta_numero,
                   "tipo": extrato.conta_tipo},
        "periodo": {"inicio": min(datas) if datas else None,
                     "fim": max(datas) if datas else None},
        "saldo": {"valor": float(extrato.saldo_valor) if extrato.saldo_valor is not None else None,
                   "data": extrato.saldo_data.isoformat() if extrato.saldo_data else None},
        "transacoes": transacoes,
        "resumo": {"total_creditos": round(creditos, 2), "total_debitos": round(debitos, 2),
                    "quantidade": len(transacoes)},
    }
    return JSONResponse(status_code=201, content=corpo)


# ------------------------------------------------------------------ render/* (compat interna)
@router.post("/api/render/boleto", include_in_schema=False)
async def render_boleto(body: dict) -> Any:
    try:
        bank, valores = body.get("bank", ""), _objeto(body.get("data") or {}, "data")
        # `template` nao era nem declarado aqui: o irmao GET /api/boleto aceita,
        # entao quem migrava de um para o outro perdia a escolha do modelo em
        # silencio. Os dois caminhos passam a se comportar igual.
        info = pycob.dados_boleto(bank, valores)
        pdf = pycob.pdf_boleto(bank, valores, body.get("template", "moderno"))
    except pycob.DadosInvalidos as e:
        return _erro_validacao(e)
    return {"nosso_numero": info["nosso_numero"], "linha_digitavel": info["linha_digitavel"],
            "codigo_barras": info["codigo_barras"], "pdf_base64": base64.b64encode(pdf).decode()}


@router.post("/api/render/carne", include_in_schema=False)
async def render_carne(body: dict) -> Any:
    try:
        itens = _lista_de_objetos(body.get("boletos") or [], "boletos")
    except pycob.DadosInvalidos as e:
        return JSONResponse(status_code=400, content={"error": "Falha ao gerar carnê",
                                                       "validation_errors": e.erros})
    bank = body.get("bank")
    boletos = [dict(b, bank=b.get("bank") or bank) for b in itens]
    # O teto valia só para /api/boleto/multi. Como o carnê renderiza pelo mesmo
    # `pdf_multi`, e de forma síncrona, dava para passar do limite trocando de
    # endpoint — sem nenhum teto, um lote grande vai direto ao OOM em vez de
    # receber o 413 barato.
    if len(boletos) > LOTE_MAX:
        return JSONResponse(status_code=413, content={
            "error": f"Lote acima do limite de {LOTE_MAX} itens",
            "recebidos": len(boletos),
            "hint": "divida o lote (processamento assíncrono: ver docs/development/plano-jobs-lote.md)"})

    # Dois itens com o mesmo identificador são o MESMO título emitido duas
    # vezes: no carnê a parcela sai impressa em duplicata e a que foi
    # sobrescrita nunca é cobrada — some do bloco em silêncio. O `pdf_multi` já
    # calculava isso e o resultado era descartado aqui.
    repetidos = pycob.duplicados(boletos)
    if repetidos:
        return JSONResponse(status_code=422, content={
            "error": "Itens com identificador duplicado no lote",
            "hint": "o item_id vem de external_id, seu_numero ou numero_documento —"
                    " cada item precisa de um valor distinto",
            "duplicados": repetidos})

    try:
        pdf, _ = pycob.pdf_multi(boletos, template="carne")
    except pycob.DadosInvalidos as e:
        return JSONResponse(status_code=400, content={"error": "Falha ao gerar carnê",
                                                       "validation_errors": e.erros})
    return {"pdf_base64": base64.b64encode(pdf).decode()}


@router.post("/api/render/fatura", include_in_schema=False)
async def render_fatura(body: dict) -> Any:
    """Fatura: corpo livre (itens/blocos) no topo + boleto de pagamento abaixo.

    Passthrough para o engine (`render_fatura_pdf`): o gateway não soma nem
    calcula nada — o `valor` do boleto e os totais vêm no payload da aplicação.
    Superfície REST dos níveis 1 e 2 (`itens` e `fatura.blocos`).

    O nível 3 (`fatura.desenhar`) é um callback Python que recebe a tela do PDF
    — não trafega por JSON. Em vez de repassar um valor inútil ao engine (que
    falharia lá dentro), a rota recusa explicitamente: o que a API não consegue
    fazer, ela não finge fazer.
    """
    fatura_body = body.get("fatura")
    if isinstance(fatura_body, dict) and "desenhar" in fatura_body:
        return JSONResponse(status_code=400, content={
            "error": "Nível 3 (fatura.desenhar) não é suportado via REST",
            "hint": "`desenhar` é um callback Python (recebe a tela do PDF) e não "
                    "trafega por JSON. Use o nível 1 (`itens`) ou o nível 2 "
                    "(`fatura.blocos`); para arte livre, chame a engine pyCobrança "
                    "in-process na própria aplicação."})

    try:
        corpo: dict[str, Any] = {}
        if body.get("itens") is not None:
            corpo["itens"] = _lista_de_objetos(body["itens"], "itens")
        if fatura_body is not None:
            corpo["fatura"] = _objeto(fatura_body, "fatura")

        bank, data = body.get("bank", ""), _objeto(body.get("data") or {}, "data")
        info = pycob.dados_boleto(bank, data)
        pdf = pycob.pdf_fatura(bank, data, corpo or None)
    except pycob.DadosInvalidos as e:
        return _erro_validacao(e)

    return {"nosso_numero": info["nosso_numero"], "linha_digitavel": info["linha_digitavel"],
            "codigo_barras": info["codigo_barras"], "pdf_base64": base64.b64encode(pdf).decode()}


@router.post("/api/render/remessa", include_in_schema=False)
async def render_remessa(body: dict) -> Any:
    try:
        conteudo = pycob.gerar_remessa(body.get("bank", ""), body.get("type", ""),
                                        _objeto(body.get("data") or {}, "data"),
                                        pix=bool(body.get("pix")))
    except pycob.DadosInvalidos as e:
        return JSONResponse(status_code=400, content={"error": "Erro ao gerar remessa",
                                                       "validation_errors": e.erros})
    return {"cnab": conteudo}


# ------------------------------------------------------------------ docs offline
@router.get("/api/openapi.json", include_in_schema=False)
def api_openapi_json(request: Request) -> Response:
    _, arvore, etag = _carregar_spec()
    return _resposta_condicional(request, etag) or JSONResponse(
        content=arvore, headers=_cabecalhos_spec(etag))


@router.get("/api/openapi.yaml", include_in_schema=False)
def api_openapi_yaml(request: Request) -> Response:
    cru, _, etag = _carregar_spec()
    return _resposta_condicional(request, etag) or Response(
        content=cru, media_type="application/yaml; charset=utf-8",
        headers=_cabecalhos_spec(etag))


@router.get("/api/docs", include_in_schema=False)
def api_docs(request: Request) -> HTMLResponse:
    # A página só existe para exibir a spec: sem ela, um 200 entregaria um
    # Swagger que nunca carrega e o operador ficaria olhando tela em branco.
    _carregar_spec()
    return HTMLResponse(pagina_swagger(
        titulo="Cobranca-API — Offline (Swagger)",
        superficie="Offline · pyCobrança",
        pill="18 bancos · sem convênio",
        detalhe=f"v{request.app.version} · pycobranca {pycob.versao()}",
        links=[("pyCobranca", "https://github.com/Maxwbh/pyCobranca", False),
               ("Gateway REST →", "/docs", True)],
        spec_url="/api/openapi.json",
    ))

