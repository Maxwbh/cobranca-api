from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.clients import engine
from app.core import pycob
from app.core.vault import Vault, get_vault
from app.providers.offline_engine import _to_engine_payload
from app.registry import _SLUG_ENGINE, build_provider, resolver_caminho
from app.routers._credentials import resolve_request_credentials
from app.routers.offline import LOTE_MAX
from app.schemas import Banco, CarneIn, CarneOut

router = APIRouter(prefix="/carne", tags=["carne"])

_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")
_RESP_413 = {413: {"description": f"Lote acima de {LOTE_MAX} parcelas"}}


# 201 acompanha as demais rotas de criação da API. Sem `Location`: o carnê não
# é recurso consultável — é o PDF montado mais as N cobranças, e cada uma já
# volta no corpo com o próprio id. Apontar para um único /carne/{id} seria
# inventar um recurso que não existe.
@router.post("", response_model=CarneOut, status_code=201, responses=_RESP_413,
             summary="Gerar carnê")
def gerar_carne(body: CarneIn, authorization: str | None = _AUTH_HEADER,
                vault: Vault = Depends(get_vault)) -> CarneOut:
    """Registra N parcelas no provider e monta o carnê (3-vias A4) no engine.

    Bancos registram cobranças individuais; o PDF de carnê é montado
    in-process pela engine pyCobrança. Quando o banco devolve um nosso_numero
    registrado, ele é repassado ao render para o carnê bater com a cobrança.

    **Tudo que dá para recusar é recusado ANTES do registro**: lote acima do
    teto, parcela duplicada, banco sem layout e dado que a engine não desenha.
    Depois do primeiro `registrar` existe boleto no banco, e um erro ali deixa
    títulos vivos que a resposta não menciona.
    """
    _caminho, banco = resolver_caminho(body.provider, body.banco, body.account_config)
    slug = _slug_do_carne(banco, body.bank)

    previa = [_to_engine_payload(p, body.account_config, slug) for p in body.parcelas]
    _recusar_lote_grande(previa)
    _recusar_duplicados(previa)
    _recusar_dados_invalidos(slug, previa)

    creds = resolve_request_credentials(
        authorization=authorization, explicit=body.credentials,
        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco,
    )
    provider = build_provider(
        provider=body.provider, banco=body.banco, tenant_id=body.tenant_id,
        account_config=body.account_config, vault=vault, credentials=creds,
    )

    cobrancas = [provider.registrar(p) for p in body.parcelas]

    boletos = []
    for data, cob in zip(previa, cobrancas):
        if cob.id:  # usa o nosso_numero registrado pelo banco, se houver
            data = dict(data, nosso_numero=cob.id)
        boletos.append(data)

    try:
        rendered = engine.render_carne(slug, boletos)
    except pycob.DadosInvalidos as e:
        raise _erro_com_o_que_ja_existe(e.erros, cobrancas) from e
    _conferir_itens(rendered, cobrancas)
    return CarneOut(carne_pdf_base64=rendered.get("pdf_base64"), cobrancas=cobrancas)


def _slug_do_carne(banco: Banco, bank: str | None) -> str:
    """Slug do layout que desenha o carnê — derivado do `banco`, não do texto.

    `bank` é o mesmo fato escrito duas vezes, e o único efeito de aceitá-lo sem
    conferir era deixar os dois discordarem: parcelas registradas num banco e
    carnê desenhado como outro, com `201`. Boleto assim não é pagável, e nada
    acusava. Segue aceito por compatibilidade — precisa concordar."""
    canonico = _SLUG_ENGINE.get(banco)
    if canonico is None:
        disponiveis = ", ".join(sorted(b.value for b in _SLUG_ENGINE))
        raise HTTPException(
            status_code=422,
            detail=f"a engine não tem layout de boleto para '{banco.value}', então não há "
                   f"como desenhar o carnê; bancos com carnê: {disponiveis}")
    if bank and bank != canonico:
        raise HTTPException(
            status_code=422,
            detail=f"`bank` ('{bank}') não é o layout de `banco` ('{banco.value}', que "
                   f"desenha como '{canonico}'): o carnê sairia com a marca de um banco e "
                   "as parcelas registradas em outro. Omita `bank` — ele vem do `banco`")
    return canonico


def _recusar_lote_grande(boletos: list[dict[str, Any]]) -> None:
    """Mesmo teto de `/api/render/carne` e `/api/boleto/multi`.

    O carnê do gateway renderiza pelo mesmo `pdf_multi` e de forma síncrona: sem
    teto, o lote grande vai ao OOM (e, no caminho ON, depois de N idas ao banco)
    em vez de receber o 413 barato."""
    if len(boletos) > LOTE_MAX:
        raise HTTPException(
            status_code=413,
            detail=f"Lote acima do limite de {LOTE_MAX} parcelas; recebidas "
                   f"{len(boletos)}. Divida o carnê (processamento assíncrono: ver "
                   "docs/development/plano-jobs-lote.md)")


def _recusar_duplicados(boletos: list[dict[str, Any]]) -> None:
    """Duas parcelas com o mesmo identificador são o MESMO título duas vezes: no
    carnê uma sai impressa em duplicata e a sobrescrita some do bloco — nunca é
    cobrada. `/api/render/carne` já recusava; por aqui passava com `201`."""
    repetidos = pycob.duplicados(boletos)
    if repetidos:
        onde = "; ".join(f"{d['item_id']} nos índices {d['indices']}" for d in repetidos)
        raise HTTPException(
            status_code=422,
            detail="parcelas com identificador duplicado no carnê: " + onde
                   + ". O identificador vem de seu_numero ou nosso_numero — cada"
                     " parcela precisa do seu")


def _recusar_dados_invalidos(slug: str, boletos: list[dict[str, Any]]) -> None:
    """Valida cada parcela ANTES de registrar qualquer uma.

    A engine descarta o item inválido e monta o carnê com o resto: 12 parcelas
    entravam, 11 saíam desenhadas, e a resposta era `201` — o pagador não recebe
    o boleto de uma parcela que continua sendo cobrada. Aqui a recusa vem antes
    da primeira ida ao banco, com o índice e o motivo de cada parcela."""
    erros = []
    for i, data in enumerate(boletos):
        try:
            pycob.validar(slug, data)
        except pycob.DadosInvalidos as e:
            erros.extend(f"parcela {i}: {erro}" for erro in e.erros)
    if erros:
        raise HTTPException(status_code=422, detail="; ".join(erros))


def _conferir_itens(rendered: dict[str, Any], cobrancas: list) -> None:
    """Rede de segurança: item que a engine reprovou no render não pode sumir.

    `_recusar_dados_invalidos` roda antes e deveria ter pego. Se ainda assim um
    item falhar aqui, as parcelas JÁ estão registradas — e a resposta precisa
    dizer isso em vez de devolver um PDF menor que o pedido."""
    falhas = [i for i in rendered.get("itens") or [] if i.get("status") == "failed"]
    if falhas:
        motivos = "; ".join(f"{i.get('item_id')}: {'; '.join(i.get('errors') or [])}"
                            for i in falhas)
        raise _erro_com_o_que_ja_existe([motivos], cobrancas)


def _erro_com_o_que_ja_existe(erros: list[str], cobrancas: list) -> HTTPException:
    registrados = [c.id for c in cobrancas if getattr(c, "id", None)]
    detalhe = "falha ao montar o carnê: " + "; ".join(erros)
    if registrados:
        detalhe += (". As parcelas JÁ foram registradas no banco e continuam válidas: "
                    + ", ".join(registrados) + " — baixe-as se for refazer o carnê")
    return HTTPException(status_code=422, detail=detalhe)
