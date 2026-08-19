# Extrato da conta PJ — movimentações do período.
#
# A resposta é **crua do banco**: C6 (`/v1/statement/`), Sicoob (conta-corrente
# v4, mensal) e Inter (`/banking/v2/extrato`) devolvem shapes diferentes, e
# normalizá-los aqui inventaria um formato que nenhum dos três tem. O que esta
# rota unifica é a CHAMADA — mesmo par de datas, mesma autenticação, mesmo 422
# para quem não oferece.
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._capacidades import exige_capacidade
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON
from app.schemas import Banco, Provider

router = APIRouter(prefix="/extrato", tags=["extrato"])

_CREDS_HEADER = Header(default=None, alias="X-Bank-Credentials",
                       description="Credenciais do banco (JSON base64) — só memória.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

_ALTERNATIVA = ("extrato existe no banco que oferece a API de conta — hoje C6, Sicoob e "
                "Inter; use `banco=c6|sicoob|inter`. O caminho offline não tem conta para "
                "extrair: concilie pelo arquivo de retorno (`POST /api/retorno`) ou pelo "
                "OFX do internet banking (`POST /api/ofx/parse`)")

_TENANT = Query(description="Identificador do tenant (resolve as credenciais)")
_START = Query(description="Data inicial (YYYY-MM-DD)", examples=["2026-01-01"])
_END = Query(description="Data final (YYYY-MM-DD). No Sicoob a API é MENSAL: as duas datas "
                         "precisam cair no mesmo mês, senão 422.",
             examples=["2026-01-31"])
_CONTA = Query(default=None, ge=1,
               description="Número da conta corrente — usado pelo Sicoob, que exige a conta "
                           "na consulta. Omitido, vai `0`, que é o que a rota mandava sempre "
                           "por não ter onde receber o valor.")

# A resposta é repassada como veio do banco: o schema descreve isso e dá o
# exemplo de cada um, em vez de prometer um formato único que não existe.
_RESPOSTA = {
    "type": "object",
    "description": "Resposta CRUA do banco — o shape é o dele, não desta API. "
                   "Os três diferem; veja os exemplos.",
    "additionalProperties": True,
}
_EXEMPLOS = {
    "c6": {"summary": "C6 — /v1/statement/",
           "value": {"transactions": [
               {"id": "TX1", "amount": 1500.0, "type": "CREDIT",
                "date": "2026-01-15", "description": "LIQUIDACAO BOLETO"}]}},
    "sicoob": {"summary": "Sicoob — conta-corrente v4 (mensal)",
               "value": {"resultado": {"saldoAtual": "1500.00", "transacoes": [
                   {"tipo": "CREDITO", "valor": "1500.00", "data": "15/01/2026",
                    "descricao": "LIQUIDACAO COBRANCA"}]}}},
    "inter": {"summary": "Inter — /banking/v2/extrato",
              "value": {"transacoes": [
                  {"cpmf": "", "dataEntrada": "2026-01-15", "tipoTransacao": "PIX",
                   "tipoOperacao": "C", "valor": "1500.00", "titulo": "Pix recebido",
                   "descricao": "PIX RECEBIDO"}]}},
}


@router.get("", response_model=dict,
            responses={200: {"content": {"application/json": {"schema": _RESPOSTA,
                                                              "examples": _EXEMPLOS}}}})
def consultar(
    tenant_id: str = _TENANT,
    start_date: date = _START,
    end_date: date = _END,
    provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    numero_conta: int | None = _CONTA,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict[str, Any]:
    """Movimentações da conta no período. Resposta crua do banco (shape dele).

    Bancos com extrato: C6, Sicoob e Inter — `GET /bancos` diz quais nesta
    instalação. Quem não oferece responde `422`, não `500`."""
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail=f"end_date ({end_date}) é anterior a start_date ({start_date}); "
                   "período invertido volta vazio e parece ausência de movimento")
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(authorization=authorization, explicit=explicit,
                                        tenant_id=tenant_id, provider=provider, banco=banco)
    conta = {"numeroContaCorrente": numero_conta} if numero_conta is not None else {}
    try:
        p = build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                account_config=conta, vault=vault, credentials=creds)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    consultar_extrato = exige_capacidade(p, "extrato", banco or provider,
                                         recurso="extrato de conta",
                                         alternativa=_ALTERNATIVA)
    try:
        return consultar_extrato(start_date=start_date.isoformat(),
                                 end_date=end_date.isoformat())
    except ValueError as e:  # regra do banco: ex. extrato Sicoob multi-mês
        raise HTTPException(status_code=422, detail=str(e)) from e
