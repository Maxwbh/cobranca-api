# Bolepix — boleto híbrido online com Pix EVP (C6 /v2/bank_slips).
#
# Schema do v2 difere do boleto v1: external_reference_id ^[A-Z0-9]{26}$ e
# address do pagador unificado (rua+número num campo) + neighborhood.
from __future__ import annotations

import random
import string

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response

from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._capacidades import (
    exige_capacidade,
    exige_capacidade_antes_da_credencial,
)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import (
    BANCO as _BANCO,
    PROVIDER_ON as _PROVIDER_ON,
    TENANT as _TENANT,
)
from app.schemas import (EXTERNAL_REFERENCE_ID, Banco, BolepixIn, CobrancaOut,
                         Pagador, Provider)

router = APIRouter(prefix="/bolepix", tags=["bolepix"])

_CREDS_HEADER = Header(default=None, alias="X-Bank-Credentials",
                       description="Credenciais do banco (JSON base64) — só memória.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

_ALTERNATIVA = ("Bolepix é exclusivo do C6 (/v2/bank_slips) — use `banco=c6`. Boleto sem o "
                "QR Pix é `/cobranca`, que existe em todos")
_EXT_REF = Path(pattern=EXTERNAL_REFERENCE_ID,
                description="Identificador do Bolepix: 26 caracteres, só maiúsculas e dígitos",
                examples=["PEDIDO00000000000000004242"])
_LOCATION = {"description": "URL de consulta do Bolepix criado, com tenant_id, provider e banco",
             "schema": {"type": "string"}}


def _location(ext_ref: str, tenant_id: str, provider, banco=None) -> str:
    params = {"tenant_id": tenant_id, "provider": getattr(provider, "value", provider)}
    if banco is not None:
        params["banco"] = getattr(banco, "value", banco)
    return f"/bolepix/{ext_ref}?{urlencode(params)}"


def _provider(tenant_id, provider, account_config, vault, credentials, banco=None):
    try:
        return build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                   account_config=account_config, vault=vault,
                                   credentials=credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# O /v2 exige city, state e zip_code no endereço do pagador. Sem eles o banco
# responde 400 e o gateway traduzia em 502 — erro de servidor para um payload
# que já dava para recusar aqui, com a mensagem dizendo qual campo falta.
ENDERECO_OBRIGATORIO = {
    "city": ("city", "cidade"),
    "state": ("state", "uf"),
    "zip_code": ("zip_code", "cep"),
}


def _payer_v2(pagador: Pagador) -> dict:
    end = pagador.endereco or {}
    linha = end.get("address")
    if not linha:
        rua = end.get("street") or end.get("logradouro") or ""
        num = end.get("number") or end.get("numero")
        linha = f"{rua}, {num}" if num else rua
    address = {
        "address": linha,
        "neighborhood": end.get("neighborhood") or end.get("bairro"),
        "city": end.get("city") or end.get("cidade"),
        "state": end.get("state") or end.get("uf"),
        "zip_code": end.get("zip_code") or end.get("cep"),
    }
    faltando = [
        f"pagador.endereco.{campo} (ou {alias})"
        for campo, (_, alias) in ENDERECO_OBRIGATORIO.items()
        if not address.get(campo)
    ]
    if faltando:
        raise HTTPException(
            status_code=422,
            detail="Bolepix exige endereço do pagador; faltando: " + ", ".join(faltando),
        )
    payer = {"name": pagador.nome, "tax_id": pagador.documento,
             "address": {k: v for k, v in address.items() if v is not None}}
    if end.get("email"):
        payer["email"] = end["email"]
    return payer


def _novo_ext_ref() -> str:
    return "".join(random.SystemRandom().choices(string.ascii_uppercase + string.digits, k=26))


@router.post("", response_model=CobrancaOut, status_code=201,
             responses={201: {"headers": {"Location": _LOCATION}}})
def criar(body: BolepixIn, response: Response, authorization: str | None = _AUTH_HEADER,
          vault: Vault = Depends(get_vault)) -> CobrancaOut:
    """Emite Bolepix (boleto + QR Pix EVP). Reenvio com o mesmo
    external_reference_id devolve a cobrança existente (idempotente no banco).

    Omitido, o `external_reference_id` é gerado aqui — e volta em `id` e no
    `Location`. É o único identificador de consulta, então perdê-lo é perder o
    boleto."""
    # ...e a capacidade antes da CREDENCIAL: sem isto, banco sem o recurso
    # respondia 424 e mandava buscar credencial que não resolveria nada.
    exige_capacidade_antes_da_credencial(body.provider, body.banco, body.account_config,
                                         "criar_bolepix", recurso="Bolepix",
                                         alternativa=_ALTERNATIVA)
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    # Capacidade ANTES do payload: "este banco não faz Bolepix" precede
    # "faltou o CEP" — senão um provider sem suporte responderia sobre o campo.
    emitir = exige_capacidade(p, "criar_bolepix", body.banco or body.provider,
                              recurso="Bolepix", alternativa=_ALTERNATIVA)
    bp = body.bolepix
    chave = bp.chave_pix or body.account_config.get("chave_pix")
    # Sem chave o banco emite boleto SEM o segmento Pix: um "Bolepix" que não é
    # bolepix, com 201 e nada avisando. É a mesma falha silenciosa do `emv` — o
    # nome do recurso promete o QR, e quem quer boleto puro tem `/cobranca`.
    if not chave:
        raise HTTPException(
            status_code=422,
            detail="chave Pix ausente: campo obrigatório no Bolepix "
                   "(`bolepix.chave_pix` ou `account_config.chave_pix`). Sem ela o banco "
                   "emite boleto SEM QR, que é `POST /cobranca` e vale em todos os bancos")
    ext_ref = bp.external_reference_id or _novo_ext_ref()
    dados = {
        "external_reference_id": ext_ref,
        "amount": float(bp.valor),
        "due_date": bp.vencimento.isoformat(),
        "description": bp.descricao,
        "payer": _payer_v2(bp.pagador),
        "payment_method": {
            "bank_slip": {
                k: v for k, v in {
                    "billing_scheme": body.account_config.get("billing_scheme"),
                    "our_number": bp.nosso_numero,
                    "instructions": bp.instrucoes,
                }.items() if v is not None
            },
        },
    }
    if not dados["payment_method"]["bank_slip"].get("billing_scheme"):
        from app.providers.c6 import C6_BILLING_SCHEME
        dados["payment_method"]["bank_slip"]["billing_scheme"] = C6_BILLING_SCHEME
    if bp.dias_apos_vencimento is not None:
        dados["days_after_due_date"] = bp.dias_apos_vencimento
    dados["payment_method"]["pix"] = {"key": chave, "type": "EVP"}
    out = emitir(dados)
    # O `id` saía da resposta do banco. Quando ela não ecoa o
    # `external_reference_id` — e a de criação é mínima — o identificador
    # GERADO AQUI se perdia, e o boleto ficava inconsultável.
    if not out.id:
        out.id = ext_ref
    # O `Location` segue o id CONFIRMADO pelo banco, não o que mandamos: se os
    # dois divergirem, quem vale é o dele — é lá que a consulta bate.
    response.headers["Location"] = _location(out.id, body.tenant_id, body.provider, body.banco)
    return out


@router.get("/{external_reference_id}", response_model=CobrancaOut)
def consultar(external_reference_id: str = _EXT_REF, *, tenant_id: str = _TENANT, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
              credentials: str | None = _CREDS_HEADER,
              authorization: str | None = _AUTH_HEADER,
              vault: Vault = Depends(get_vault)) -> CobrancaOut:
    """Consulta o Bolepix pelo external_reference_id (26 chars A-Z0-9)."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return exige_capacidade(p, "consultar_bolepix", banco or provider,
                            recurso="Bolepix", alternativa=_ALTERNATIVA)(external_reference_id)


@router.get("/{external_reference_id}/pdf", response_model=CobrancaOut,
            summary="PDF do Bolepix")
def pdf(external_reference_id: str = _EXT_REF, *, tenant_id: str = _TENANT, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
        credentials: str | None = _CREDS_HEADER,
        authorization: str | None = _AUTH_HEADER,
        vault: Vault = Depends(get_vault)) -> CobrancaOut:
    """PDF do Bolepix em base64."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return exige_capacidade(p, "pdf_bolepix", banco or provider,
                            recurso="Bolepix", alternativa=_ALTERNATIVA)(external_reference_id)


@router.delete("/{external_reference_id}", response_model=CobrancaOut)
def cancelar(external_reference_id: str = _EXT_REF, *, tenant_id: str = _TENANT, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
             credentials: str | None = _CREDS_HEADER,
             authorization: str | None = _AUTH_HEADER,
             vault: Vault = Depends(get_vault)) -> CobrancaOut:
    """Cancela o Bolepix (409 enquanto a CIP processa o registro)."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return exige_capacidade(p, "cancelar_bolepix", banco or provider,
                            recurso="Bolepix", alternativa=_ALTERNATIVA)(external_reference_id)
