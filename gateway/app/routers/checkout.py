# Checkout — link de pagamento com cartão (C6 /v1/checkouts).
#
# MODO LINK, e só ele: o banco devolve uma `url`, o pagador digita o cartão no
# domínio DELE e o escopo PCI-DSS fica lá. Checkout transparente (`/authorize`,
# `/generate/public-key`) e captura em duas fases (`/{id}/capture`) existem no
# spec do C6 e NÃO são expostos — decisão de produto, não limitação técnica.
#
# `save_card` cai pelo `extra="forbid"` do schema: a decisão de não guardar dado
# de cartão só é real se o campo não existir, porque corpo repassado sem filtro
# revoga decisão sem ninguém revisar.
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.idempotency import (
    ConflitoDeIdempotencia,
    get_idempotency_store,
    impressao,
)
from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._capacidades import (
    exige_capacidade,
    exige_capacidade_antes_da_credencial,
)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON, TENANT as _TENANT
from app.schemas import (
    Autenticacao,
    Banco,
    CheckoutIn,
    CheckoutOut,
    JurosPor,
    Pagador,
    Provider,
    TipoCartao,
)

router = APIRouter(prefix="/checkout", tags=["checkout"])

_CREDS_HEADER = Header(default=None, alias="X-Bank-Credentials",
                       description="Credenciais do banco (JSON base64) — só memória.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")
_IDEMPOTENCIA_HEADER = Header(
    default=None, alias="Idempotency-Key",
    description="Reenvio com a mesma chave devolve O MESMO link, sem criar outro no "
                "banco. Mesma chave com outro pedido — corpo, provider ou banco "
                "diferentes — é 422.")
_LOCATION = {
    "description": "URL de consulta do link criado, já com tenant_id, provider e banco",
    "schema": {"type": "string"},
}

# Cartão existe onde a instituição OFERECE link hospedado. Hoje, o C6.
_ALTERNATIVA = ("link de pagamento existe no banco que oferece a funcionalidade — "
                "hoje o C6 (/v1/checkouts); use `banco=c6`")

_TIPO = {TipoCartao.credito: "CREDIT", TipoCartao.debito: "DEBIT"}
_JUROS = {JurosPor.loja: "BY_SELLER", JurosPor.emissor: "BY_ISSUER"}
_AUTENTICACAO = {
    Autenticacao.obrigatoria: "REQUIRED",
    Autenticacao.opcional: "OPTIONAL",
    Autenticacao.nao_exigida: "NOT_REQUIRED",
}

# O C6 exige o endereço completo do pagador quando `payer` é enviado, com
# `number` NUMÉRICO. É a mesma pegadinha do Bolepix: sem isso o banco responde
# 400, e o gateway devolvia 502 — erro de servidor para payload que dava para
# recusar aqui, dizendo qual campo falta.
ENDERECO_OBRIGATORIO = {
    "street": "street (ou logradouro)",
    "number": "number (ou numero)",
    "city": "city (ou cidade)",
    "state": "state (ou uf)",
    "zip_code": "zip_code (ou cep)",
}


def _provider(tenant_id, provider, account_config, vault, credentials, banco=None):
    try:
        return build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                   account_config=account_config, vault=vault,
                                   credentials=credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _payer_checkout(pagador: Pagador) -> dict:
    end = pagador.endereco or {}
    address = {
        "street": end.get("street") or end.get("logradouro"),
        "number": end.get("number") or end.get("numero"),
        "complement": end.get("complement") or end.get("complemento"),
        "city": end.get("city") or end.get("cidade"),
        "state": end.get("state") or end.get("uf"),
        "zip_code": end.get("zip_code") or end.get("cep"),
    }
    faltando = [rotulo for campo, rotulo in ENDERECO_OBRIGATORIO.items() if not address.get(campo)]
    if faltando:
        raise HTTPException(
            status_code=422,
            detail="checkout exige endereço do pagador; faltando: "
                   + ", ".join(f"pagador.endereco.{r}" for r in faltando),
        )
    try:
        address["number"] = int(address["number"])
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="pagador.endereco.number deve ser numérico (o C6 recusa texto)",
        ) from None
    payer = {"name": pagador.nome, "tax_id": pagador.documento,
             "address": {k: v for k, v in address.items() if v is not None}}
    if end.get("email"):
        payer["email"] = end["email"]
    if end.get("phone_number") or end.get("telefone"):
        payer["phone_number"] = end.get("phone_number") or end.get("telefone")
    return payer


@router.post("", response_model=CheckoutOut, status_code=201,
             responses={201: {"headers": {"Location": _LOCATION}}})
def criar(body: CheckoutIn, response: Response, authorization: str | None = _AUTH_HEADER,
          idempotency_key: str | None = _IDEMPOTENCIA_HEADER,
          vault: Vault = Depends(get_vault)) -> CheckoutOut:
    """Cria o link de pagamento e devolve a `url` para onde mandar o pagador.

    Aceita cartão e, com `pix: true`, Pix no mesmo link. Expira em 7 dias quando
    `expira_em` é omitido (default do banco).

    Mande `Idempotency-Key` se houver botão humano na frente disto: sem a chave,
    duplo clique cria **dois links para a mesma venda**, e nada impede o pagador
    de pagar os dois."""
    # A impressão é do checkout MAIS o destino, não do corpo inteiro:
    # `credentials` pode vir no request e não faz parte da identidade do pedido —
    # o mesmo pedido com a credencial reenviada de outro jeito continua sendo o
    # mesmo pedido. `provider` e `banco` entram porque SÃO identidade: sem eles,
    # a mesma chave enviada a outro banco devolvia o link do primeiro, e o
    # segundo banco nunca era chamado — a venda ia para a instituição errada com
    # 201 e nada acusando.
    marca = impressao(_pedido(body)) if idempotency_key else ""
    if idempotency_key:
        guardada = _replay(body.tenant_id, idempotency_key, marca)
        if guardada is not None:
            return guardada

    # ...e a capacidade antes da CREDENCIAL: sem isto, banco sem o recurso
    # respondia 424 e mandava buscar credencial que não resolveria nada.
    exige_capacidade_antes_da_credencial(body.provider, body.banco, body.account_config,
                                         "criar_checkout", recurso="link de pagamento com cartão",
                                         alternativa=_ALTERNATIVA)
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    # Capacidade ANTES do payload: "este banco não faz link de pagamento" precede
    # "faltou o CEP" — senão um provider sem suporte responderia sobre o campo.
    criar_link = exige_capacidade(p, "criar_checkout", body.provider,
                                  recurso="link de pagamento com cartão",
                                  alternativa=_ALTERNATIVA)
    ck = body.checkout
    card: dict = {"type": _TIPO[ck.tipo], "installments": ck.parcelas}
    if ck.parcelas > 1 and ck.juros_por:
        card["interest_type"] = _JUROS[ck.juros_por]
    if ck.parcelas_fixas is not None:
        card["fixed_installments"] = ck.parcelas_fixas
    if ck.autenticacao is not None:
        card["authenticate"] = _AUTENTICACAO[ck.autenticacao]
    if ck.recorrente is not None:
        card["recurrent"] = ck.recorrente

    payload: dict = {"amount": float(ck.valor), "payment": {"card": card}}
    if ck.pix:
        payload["payment"]["pix"] = {"key": "AUTO"}  # o banco gera o QR
    if ck.descricao:
        payload["description"] = ck.descricao
    if ck.expira_em:
        payload["expiration_date_time"] = ck.expira_em.isoformat()
    if ck.redirect_url:
        payload["redirect_url"] = ck.redirect_url
    if ck.external_reference_id:
        payload["external_reference_id"] = ck.external_reference_id
    if ck.pagador:
        payload["payer"] = _payer_checkout(ck.pagador)

    resultado = criar_link(payload)
    if idempotency_key:
        _guardar(body.tenant_id, idempotency_key, marca, resultado)
    if resultado.id:
        response.headers["Location"] = _location(
            f"/checkout/{resultado.id}", body.tenant_id, body.provider, body.banco)
    return resultado


def _pedido(body: CheckoutIn) -> dict:
    """O que identifica o pedido para fins de idempotência."""
    return {"checkout": body.checkout.model_dump(mode="json"),
            "provider": getattr(body.provider, "value", body.provider),
            "banco": getattr(body.banco, "value", body.banco)}


def _location(caminho: str, tenant_id: str, provider, banco=None) -> str:
    """Location que o cliente consegue seguir.

    `GET /checkout/{id}` exige `tenant_id` e `provider`, e o `banco` junto quando
    o provider é `on`/`off` — o header sem eles apontava para um `422`. Mesma
    correção feita em `/cobranca` e `/pix`; aqui não havia header nenhum, e o
    `201` devolvia um `id` que só o consumidor sabia montar em URL."""
    params = {"tenant_id": tenant_id, "provider": getattr(provider, "value", provider)}
    if banco is not None:
        params["banco"] = getattr(banco, "value", banco)
    return f"{caminho}?{urlencode(params)}"


def _replay(tenant_id: str, chave: str, marca: str) -> CheckoutOut | None:
    """Resposta já guardada para esta chave, ou None se é a primeira vez.

    Store indisponível devolve None (segue e cria): perder a idempotência é ruim,
    mas recusar a venda porque o nosso SQLite tropeçou é pior."""
    try:
        guardada = get_idempotency_store().buscar(tenant_id, "checkout", chave, marca)
    except ConflitoDeIdempotencia:
        raise HTTPException(
            status_code=422,
            detail=f"Idempotency-Key '{chave}' já foi usada neste tenant com outro "
                   "checkout; use uma chave nova para um pedido novo",
        ) from None
    except Exception:  # noqa: BLE001
        return None
    return CheckoutOut(**guardada) if guardada else None


def _guardar(tenant_id: str, chave: str, marca: str, resultado: CheckoutOut) -> None:
    """Nunca levanta: o link JÁ existe no banco a esta altura, e falhar aqui
    esconderia do cliente uma cobrança que foi criada."""
    try:
        get_idempotency_store().guardar(tenant_id, "checkout", chave, marca,
                                        resultado.model_dump(mode="json"))
    except Exception:  # noqa: BLE001
        pass


@router.get("/{checkout_id}", response_model=CheckoutOut)
def consultar(checkout_id: str, tenant_id: str = _TENANT, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
              credentials: str | None = _CREDS_HEADER,
              authorization: str | None = _AUTH_HEADER,
              vault: Vault = Depends(get_vault)) -> CheckoutOut:
    """Status normalizado do link. `PAID` → `liquidado`; `DECLINED`/`ERROR` → `erro`."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return exige_capacidade(p, "consultar_checkout", provider,
                            recurso="link de pagamento com cartão",
                            alternativa=_ALTERNATIVA)(checkout_id)


@router.delete("/{checkout_id}", response_model=CheckoutOut)
def cancelar(checkout_id: str, tenant_id: str = _TENANT, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
             credentials: str | None = _CREDS_HEADER,
             authorization: str | None = _AUTH_HEADER,
             vault: Vault = Depends(get_vault)) -> CheckoutOut:
    """Cancela o link (`CANCELLED` → `baixado`)."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return exige_capacidade(p, "cancelar_checkout", provider,
                            recurso="link de pagamento com cartão",
                            alternativa=_ALTERNATIVA)(checkout_id)
