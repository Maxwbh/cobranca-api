# Conciliação online (C6 Pay statement) — recebíveis e transações por período.
#
# Períodos de até 60 dias por requisição (limite da API do C6).
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._capacidades import (
    exige_capacidade,
    exige_capacidade_antes_da_credencial,
)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON, TENANT as _TENANT
from app.schemas import Banco, ConciliacaoOut, Provider

router = APIRouter(prefix="/conciliacao", tags=["conciliacao"])

_CREDS_HEADER = Header(
    default=None,
    alias="X-Bank-Credentials",
    description="Credenciais do banco (JSON em base64) — só memória, nunca persistidas. Fallback: cofre VAULT__*.",
)
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

# Limite da API do C6, que é quem oferece a conciliação — e a rota só existe
# para quem a oferece, então não há segunda fonte de verdade a envelhecer. A
# janela vinha escrita na descrição do parâmetro e não valia em lugar nenhum:
# um ano de período ia inteiro para o banco e voltava como erro dele.
JANELA_MAX_DIAS = 60

# Conciliação de adquirência é do C6 (C6 Pay). Chamar em quem não implementa
# levantava AttributeError -> 500 "Internal Server Error" em 21 bytes, no
# caminho que o `GET /bancos` já descrevia como exclusivo.
_ALTERNATIVA = ("conciliação de adquirência existe no banco que oferece a funcionalidade — "
                "hoje o C6 (C6 Pay); use `banco=c6`. Para o caminho offline, concilie pelo "
                "arquivo de retorno (`POST /api/retorno`) ou pelo OFX (`POST /api/ofx/parse`)")

_START = Query(description="Data inicial (YYYY-MM-DD)", examples=["2026-01-01"])
_END = Query(description=f"Data final (YYYY-MM-DD; no máximo {JANELA_MAX_DIAS} dias após a inicial)",
             examples=["2026-01-31"])
_PAGE = Query(default=1, ge=1, description="Página, a partir de 1")
_SIZE = Query(default=50, ge=1, le=100, description="Itens por página (1 a 100)")


def _periodo(start_date: date, end_date: date) -> tuple[str, str]:
    """Confere o período ANTES da ida ao banco e devolve no formato dele.

    Datas eram `str` livres: `amanha`, `""` e `2026-13-45` seguiam para a API do
    C6 tal como chegaram. E período invertido é o erro mais silencioso dos três,
    porque o banco costuma responder lista vazia — que quem chama lê como
    'não houve movimento no período'."""
    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail=f"end_date ({end_date}) é anterior a start_date ({start_date}); "
                   "período invertido volta vazio e parece ausência de movimento")
    dias = (end_date - start_date).days
    if dias > JANELA_MAX_DIAS:
        raise HTTPException(
            status_code=422,
            detail=f"período de {dias} dias acima do máximo de {JANELA_MAX_DIAS}; "
                   "divida a consulta em janelas menores")
    return start_date.isoformat(), end_date.isoformat()


def _provider(tenant_id: str, provider: Provider, banco: Banco | None, vault: Vault,
              credentials_header: str | None, authorization: str | None):
    try:
        explicit = credentials_from_header(credentials_header)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(
        authorization=authorization, explicit=explicit,
        tenant_id=tenant_id, provider=provider, banco=banco,
    )
    try:
        return build_rest_provider(
            provider=provider, banco=banco, tenant_id=tenant_id, account_config={}, vault=vault,
            credentials=creds,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/recebiveis", response_model=ConciliacaoOut)
def recebiveis(
    tenant_id: str = _TENANT,
    start_date: date = _START,
    end_date: date = _END,
    provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    page: int = _PAGE,
    size: int = _SIZE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> ConciliacaoOut:
    """Recebíveis C6 Pay do período (paginado; máx. 60 dias por consulta)."""
    inicio, fim = _periodo(start_date, end_date)
    exige_capacidade_antes_da_credencial(provider, banco, None, "listar_recebiveis",
                                         recurso="conciliação de recebíveis",
                                         alternativa=_ALTERNATIVA)
    p = _provider(tenant_id, provider, banco, vault, credentials, authorization)
    listar = exige_capacidade(p, "listar_recebiveis", banco or provider,
                              recurso="conciliação de recebíveis",
                              alternativa=_ALTERNATIVA)
    return listar(start_date=inicio, end_date=fim, page=page, size=size)


@router.get("/transacoes", response_model=ConciliacaoOut)
def transacoes(
    tenant_id: str = _TENANT,
    start_date: date = _START,
    end_date: date = _END,
    provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    page: int = _PAGE,
    size: int = _SIZE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> ConciliacaoOut:
    """Transações C6 Pay do período (paginado; máx. 60 dias por consulta)."""
    inicio, fim = _periodo(start_date, end_date)
    exige_capacidade_antes_da_credencial(provider, banco, None, "listar_transacoes",
                                         recurso="conciliação de transações",
                                         alternativa=_ALTERNATIVA)
    p = _provider(tenant_id, provider, banco, vault, credentials, authorization)
    listar = exige_capacidade(p, "listar_transacoes", banco or provider,
                              recurso="conciliação de transações",
                              alternativa=_ALTERNATIVA)
    return listar(start_date=inicio, end_date=fim, page=page, size=size)
