# Pix dinâmico (cob/cobv BACEN) — só providers REST; o caminho offline não emite Pix.
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.vault import Vault, get_vault
from app.registry import build_rest_provider, credentials_from_header
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON
from app.schemas import (
    Banco,
    LoteCobvIn,
    LoteCobvRevisaoIn,
    PixCobrancaIn,
    PixCobrancaOut,
    Provider,
)

router = APIRouter(prefix="/pix", tags=["pix"])

# O `Location` só serve a quem sabe que ele existe: o FastAPI não documenta
# header setado em tempo de execução, então o Swagger dizia 201 sem dizer para
# onde ir. Declarado aqui para aparecer no contrato.
_LOCATION = {
    "description": "URL de consulta do recurso criado, já com tenant_id e provider",
    "schema": {"type": "string"},
}


_CREDS_HEADER = Header(
    default=None,
    alias="X-Bank-Credentials",
    description="Credenciais do banco (JSON em base64) — só memória, nunca persistidas. Fallback: cofre VAULT__*.",
)
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")


def _provider(tenant_id: str, provider: Provider, account_config: dict, vault: Vault,
              credentials: dict | None = None, banco: Banco | None = None):
    try:
        return build_rest_provider(
            provider=provider, banco=banco, tenant_id=tenant_id,
            account_config=account_config, vault=vault, credentials=credentials,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=PixCobrancaOut, status_code=201,
             responses={201: {"headers": {"Location": _LOCATION}}})
def criar(
    body: PixCobrancaIn,
    response: Response,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> PixCobrancaOut:
    """Cria cobrança Pix: cob imediata (default) ou cobv se `data_vencimento`."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=body.credentials,
        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco,
    )
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    try:
        out = p.criar_pix(body.pix)
    except ValueError as e:  # chave/txid/devedor ausentes → erro do chamador
        raise HTTPException(status_code=422, detail=str(e)) from e
    # cob e cobv moram na mesma rota e se distinguem por `vencimento`; sem esse
    # parâmetro o Location de uma cobv apontaria para a cob, que não existe.
    if out.txid:
        extra = {"vencimento": "true"} if body.pix.data_vencimento else {}
        response.headers["Location"] = _location(
            f"/pix/{out.txid}", body.tenant_id, body.provider, body.banco, **extra)
    return out


def _location(caminho: str, tenant_id: str, provider, banco=None, **extra: str) -> str:
    """Location que o cliente consegue seguir.

    As rotas de consulta exigem `tenant_id` e `provider` — e, desde o modelo de
    dois eixos, também o `banco` quando o `provider` é `on`/`off`. O `banco`
    ficou de fora quando o eixo nasceu, e o header passou a apontar para um
    `422`: quebrado exatamente no modelo NOVO, e são no legado (`provider=c6`),
    que carrega o banco no próprio valor e sai na 3.0.0.

    Nada acusava porque nada seguia o header — o teste agora segue.
    """
    params = {"tenant_id": tenant_id, "provider": getattr(provider, "value", provider)}
    if banco is not None:
        params["banco"] = getattr(banco, "value", banco)
    params.update(extra)
    return f"{caminho}?{urlencode(params)}"


def _creds(credentials, authorization, tenant_id, provider, banco=None):
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return resolve_request_credentials(
        authorization=authorization, explicit=explicit,
        tenant_id=tenant_id, provider=provider, banco=banco,
    )


@router.get("", response_model=dict)
def listar(
    tenant_id: str, inicio: str, fim: str,
    vencimento: bool = False, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Lista cobranças do período (RFC3339). `vencimento=true` lista cobv."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.listar_pix(inicio=inicio, fim=fim, vencimento=vencimento)


@router.get("/recebidos", response_model=dict)
def listar_recebidos(
    tenant_id: str, inicio: str, fim: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Pix RECEBIDOS (money-in) no período — conciliação Pix (P_05 BACEN)."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.listar_pix_recebidos(inicio=inicio, fim=fim)


@router.get("/recebidos/{e2eid}", response_model=dict)
def consultar_recebido(
    e2eid: str, tenant_id: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Detalhe de um Pix RECEBIDO pelo e2eid (conciliação money-in)."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.consultar_pix_recebido(e2eid)


@router.put("/recebidos/{e2eid}/devolucao/{devolucao_id}", response_model=dict, status_code=201)
def devolver(
    e2eid: str, devolucao_id: str, body: dict, tenant_id: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Devolução (total/parcial) de um Pix recebido: corpo {"valor": "10.00"}."""
    if not body.get("valor"):
        raise HTTPException(status_code=422, detail="corpo deve conter valor")
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.devolver_pix(e2eid, devolucao_id, str(body["valor"]))


@router.get("/recebidos/{e2eid}/devolucao/{devolucao_id}", response_model=dict,
            summary="Consultar devolução")
def consultar_devolucao(
    e2eid: str, devolucao_id: str, tenant_id: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Consulta uma devolução de Pix recebido."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.consultar_devolucao(e2eid, devolucao_id)


@router.get("/lotes", response_model=dict)
def listar_lotes(
    tenant_id: str, inicio: str, fim: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Lista lotes de cobv do período (RFC3339)."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.listar_lotes_cobv(inicio=inicio, fim=fim)


# 202, e não 201 como as demais rotas de criação: o banco responde "lote
# solicitado para criação", sem corpo — o lote é enfileirado, não criado. É a
# mesma régua que mantém o /cobranca em 201: lá existe id e linha digitável na
# resposta, aqui não existe nada ainda. O `Location` fica, que é justamente o
# uso do 202: dizer onde acompanhar.
@router.put("/lote/{lote_id}", response_model=dict, status_code=202,
            responses={202: {"headers": {"Location": _LOCATION}}})
def criar_lote(
    lote_id: str, body: LoteCobvIn,
    response: Response,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Cria/atualiza lote de cobranças com vencimento (lotecobv BACEN)."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=body.credentials,
        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco,
    )
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    out = p.criar_lote_cobv(lote_id, body.descricao, _cobsv(body))
    response.headers["Location"] = _location(
        f"/pix/lote/{lote_id}", body.tenant_id, body.provider, body.banco)
    return out


def _cobsv(body: LoteCobvIn | LoteCobvRevisaoIn) -> list[dict]:
    """Itens do lote no dialeto BACEN. Compartilhado por criar e revisar: o
    `cobsv` do PATCH tem a mesma forma do PUT, e duas cópias divergiriam no dia
    em que um campo mudasse."""
    from app.providers.c6 import _devedor  # mapeamento canonico -> BACEN

    chave_conta = body.account_config.get("chave_pix")
    itens = []
    for pix in body.cobrancas:
        if not (pix.txid and pix.data_vencimento and pix.devedor):
            raise HTTPException(status_code=422,
                                detail="cada item do lote exige txid, data_vencimento e devedor")
        itens.append({
            "txid": pix.txid,
            "calendario": {"dataDeVencimento": pix.data_vencimento.isoformat(),
                           "validadeAposVencimento": pix.validade_apos_vencimento},
            "devedor": _devedor(pix.devedor),
            "valor": {"original": f"{pix.valor:.2f}"},
            "chave": pix.chave or chave_conta,
        })
    return itens


# PATCH e não PUT: o PUT do BACEN recria o lote inteiro (e exige `descricao`),
# o PATCH revisa as cobranças que vão no corpo. Faltava — `revisar_lote_cobv`
# existia no mixin desde sempre, sem rota, e a homologação do C6 registrou o
# caso P_03_02 como ausente por causa disso. A cobrança individual já tinha o
# seu PATCH (`/pix/{txid}`); a assimetria era o defeito.
@router.patch("/lote/{lote_id}", response_model=dict)
def revisar_lote(
    lote_id: str, body: LoteCobvRevisaoIn,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Revisa cobranças dentro de um lote de cobv (PATCH BACEN `/lotecobv/{id}`).

    Só as cobranças enviadas são revisadas; as demais do lote ficam como estão.
    Vale para qualquer provider de dialeto BACEN — C6, Sicoob e Inter."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=body.credentials,
        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco,
    )
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    return p.revisar_lote_cobv(lote_id, _cobsv(body))


@router.get("/lote/{lote_id}", response_model=dict)
def consultar_lote(
    lote_id: str, tenant_id: str, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> dict:
    """Consulta um lote de cobv pelo id."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.consultar_lote_cobv(lote_id)


@router.get("/{txid}", response_model=PixCobrancaOut)
def consultar(
    txid: str, tenant_id: str, vencimento: bool = False, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> PixCobrancaOut:
    """`vencimento=true` consulta cobv (/cobv/{txid}); default cob."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.consultar_pix(txid, vencimento=vencimento)


@router.patch("/{txid}", response_model=PixCobrancaOut)
def revisar(
    txid: str, campos: dict, tenant_id: str,
    vencimento: bool = False, provider: Provider = _PROVIDER_ON,
    banco: Banco | None = _BANCO,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> PixCobrancaOut:
    """Revisa a cobrança (PATCH BACEN): valor, solicitacaoPagador, calendario..."""
    p = _provider(tenant_id, provider, {}, vault,
                  _creds(credentials, authorization, tenant_id, provider), banco=banco)
    return p.revisar_pix(txid, campos, vencimento=vencimento)
