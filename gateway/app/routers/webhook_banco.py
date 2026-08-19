# Cadastro do webhook NO BANCO (C6 /v1/webhooks) — o banco passa a notificar a
# URL informada (ex.: a rota /webhooks/{banco}/{tenant} deste gateway).
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._capacidades import exige_capacidade
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON
from app.schemas import (Banco, Provider, ServicoWebhook, WebhookBancoIn,
                         WebhookPixIn)

router = APIRouter(prefix="/config/webhook-banco", tags=["config"])

_CREDS_HEADER = Header(default=None, alias="X-Bank-Credentials",
                       description="Credenciais do banco (JSON base64) — só memória.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

_ALT_BANCO = ("cadastro de webhook no banco existe em quem oferece a API — hoje C6 e Inter; "
              "use `banco=c6|inter`. Para Pix, o caminho é `/config/webhook-pix` (BACEN, "
              "por chave). Sem isso, receba pela consulta ativa (`GET /cobranca/{id}`)")
_ALT_PIX = ("webhook Pix por chave é do dialeto BACEN — hoje C6, Sicoob e Inter; use "
            "`banco=c6|sicoob|inter`. Para boleto, o caminho é `/config/webhook-banco`")

_SERVICE = Query(default=ServicoWebhook.bank_slip,
                 description="O que o banco notifica: `BANK_SLIP` (boleto) ou `CHECKOUT` (cartão)")
_CHAVE = Query(description="Chave Pix do recebedor", examples=["financeiro@empresa.com.br"])

# As seis respostas são repassadas COMO O BANCO MANDOU — confirmação do cadastro,
# no formato dele. O schema diz isso em vez de prometer "objeto qualquer".
_RESP_DO_BANCO = {200: {"content": {"application/json": {"schema": {
    "type": "object", "additionalProperties": True,
    "description": "Confirmação CRUA do banco — o shape é o dele, não desta API."}}}}}


def _provider(tenant_id, provider, vault, credentials, banco=None):
    try:
        return build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                   account_config={}, vault=vault, credentials=credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=dict, responses=_RESP_DO_BANCO)
def cadastrar(body: WebhookBancoIn, authorization: str | None = _AUTH_HEADER,
              vault: Vault = Depends(get_vault)) -> dict:
    """Registra a URL de notificação no banco (service: BANK_SLIP | CHECKOUT)."""
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, vault, creds, banco=body.banco)
    return exige_capacidade(p, "cadastrar_webhook", body.banco or body.provider,
                            recurso="cadastro de webhook no banco",
                            alternativa=_ALT_BANCO)(url=body.url, service=body.service.value)


@router.get("", response_model=dict, responses=_RESP_DO_BANCO)
def consultar(tenant_id: str, service: ServicoWebhook = _SERVICE,
              provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
              credentials: str | None = _CREDS_HEADER,
              authorization: str | None = _AUTH_HEADER,
              vault: Vault = Depends(get_vault)) -> dict:
    """Consulta o webhook cadastrado no banco para o service."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, vault, creds, banco=banco)
    return exige_capacidade(p, "consultar_webhook", banco or provider,
                            recurso="cadastro de webhook no banco",
                            alternativa=_ALT_BANCO)(service=service.value)


@router.delete("", response_model=dict, responses=_RESP_DO_BANCO)
def remover(tenant_id: str, service: ServicoWebhook = _SERVICE,
            provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
            credentials: str | None = _CREDS_HEADER,
            authorization: str | None = _AUTH_HEADER,
            vault: Vault = Depends(get_vault)) -> dict:
    """Remove o webhook do service no banco."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, vault, creds, banco=banco)
    return exige_capacidade(p, "remover_webhook", banco or provider,
                            recurso="cadastro de webhook no banco",
                            alternativa=_ALT_BANCO)(service=service.value)


# --- webhook Pix BACEN por CHAVE (P_06) — banco chama a URL quando o Pix cai -----

pix_router = APIRouter(prefix="/config/webhook-pix", tags=["config"])


@pix_router.put("", response_model=dict, responses=_RESP_DO_BANCO)
def configurar_pix(body: WebhookPixIn, authorization: str | None = _AUTH_HEADER,
                   vault: Vault = Depends(get_vault)) -> dict:
    """Configura o webhook BACEN da chave — o banco chama a URL quando um Pix cai nela."""
    creds = resolve_request_credentials(authorization=authorization,
                                        explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider,
                                        banco=body.banco)
    p = _provider(body.tenant_id, body.provider, vault, creds, banco=body.banco)
    configurar = exige_capacidade(p, "configurar_webhook_pix", body.banco or body.provider,
                                  recurso="webhook Pix por chave", alternativa=_ALT_PIX)
    return configurar(body.chave, body.url)


@pix_router.get("", response_model=dict, responses=_RESP_DO_BANCO)
def consultar_pix(tenant_id: str, chave: str = _CHAVE,
                  provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                  credentials: str | None = _CREDS_HEADER,
                  authorization: str | None = _AUTH_HEADER,
                  vault: Vault = Depends(get_vault)) -> dict:
    """Consulta o webhook BACEN cadastrado para a chave Pix."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, vault, creds, banco=banco)
    return exige_capacidade(p, "consultar_webhook_pix", banco or provider,
                            recurso="webhook Pix por chave", alternativa=_ALT_PIX)(chave)


@pix_router.delete("", response_model=dict, responses=_RESP_DO_BANCO)
def remover_pix(tenant_id: str, chave: str = _CHAVE,
                provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                credentials: str | None = _CREDS_HEADER,
                authorization: str | None = _AUTH_HEADER,
                vault: Vault = Depends(get_vault)) -> dict:
    """Remove o webhook BACEN da chave Pix."""
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    p = _provider(tenant_id, provider, vault, creds, banco=banco)
    return exige_capacidade(p, "remover_webhook_pix", banco or provider,
                            recurso="webhook Pix por chave", alternativa=_ALT_PIX)(chave)
