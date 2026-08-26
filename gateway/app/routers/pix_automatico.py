# Pix Automático (BACEN) — débito recorrente autorizado uma vez pelo pagador.
#
# O AGENDAMENTO de cada cobrança do ciclo (>= 2 dias antes do vencimento) fica
# no PRODUTO consumidor — este gateway é interface de consumo (stateless).
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from app.core.vault import Vault, get_vault
from app.providers.bacen_pix import _devedor_simples
from app.registry import (
    _REST_POR_BANCO,
    CaminhoInvalido,
    build_rest_provider,
    credentials_from_header,
    resolver_caminho,
)
from app.routers._capacidades import disponivel, exige_capacidade
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON
from app.core.url_webhook import validar_url_webhook
from app.schemas import (
    TXID_BACEN,
    Banco,
    CobrancaRecorrenteIn,
    Provider,
    RecorrenciaIn,
    SolicitacaoRecorrenciaIn,
)

router = APIRouter(prefix="/pix-automatico", tags=["pix-automatico"])

_CREDS_HEADER = Header(default=None, alias="X-Bank-Credentials",
                       description="Credenciais do banco (JSON base64) — só memória.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

# O txid do cobr é o mesmo da cob/cobv — e a regra valia só lá. Aqui `abc`,
# `COM-HIFEN` e um txid de 40 caracteres iam para o BACEN e voltavam como erro
# dele, com o nome do campo perdido no caminho.
_TXID = Path(pattern=TXID_BACEN,
             description="Txid do BACEN: 26 a 35 caracteres, só letras e dígitos",
             examples=["COBR0000000000000000000042"])
_DATA_RETENTATIVA = Path(
    description="Data da retentativa (YYYY-MM-DD)", examples=["2027-01-10"])
_INICIO = Query(description="Início do período, RFC3339 (ex.: 2026-01-01T00:00:00Z)",
                examples=["2026-01-01T00:00:00Z"])
_FIM = Query(description="Fim do período, RFC3339", examples=["2026-01-31T23:59:59Z"])

# Corpo do PATCH: o BACEN aceita subconjuntos diferentes por jornada, então o
# dict livre é do contrato — o que faltava era a spec DIZER o que cabe ali.
_CORPO_PATCH = {
    "required": True,
    "content": {"application/json": {
        "schema": {"type": "object", "minProperties": 1, "additionalProperties": True,
                   "description": "Campos do PATCH BACEN — subconjunto, não o objeto "
                                  "inteiro. Varia por jornada; veja os exemplos."},
        "examples": {
            "cancelar": {"summary": "Cancelar", "value": {"status": "CANCELADA"}},
            "valor": {"summary": "Alterar o valor do ciclo",
                      "value": {"valor": {"original": "150.00"}}},
        },
    }},
}
_CORPO_WEBHOOKS = {
    "required": True,
    "content": {"application/json": {"schema": {
        "type": "object", "minProperties": 1,
        "description": "Informe ao menos uma das duas URLs (https e alcançável de fora: "
                       "quem chama é o banco).",
        "properties": {
            "url_recorrencia": {"type": "string", "format": "uri",
                                "description": "webhookrec — eventos da recorrência",
                                "example": "https://api.empresa.com.br/webhooks/pixaut/rec"},
            "url_cobranca": {"type": "string", "format": "uri",
                             "description": "webhookcobr — eventos das cobranças do ciclo",
                             "example": "https://api.empresa.com.br/webhooks/pixaut/cobr"},
        },
    }}},
}


def _periodo(inicio: str, fim: str) -> tuple[str, str]:
    """Confere o período antes da ida ao banco, sem reformatar.

    As duas datas eram `str` cruas: `amanha` e `""` seguiam para o BACEN como
    chegaram. A string original é preservada porque o dialeto aceita variações
    de RFC3339 (`Z` e `+00:00`), e normalizar aqui trocaria um problema por
    outro."""
    def parse(rotulo: str, valor: str) -> datetime:
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"{rotulo} deve ser RFC3339 (ex.: 2026-01-01T00:00:00Z); "
                       f"recebido: {valor!r}") from None

    if parse("fim", fim) < parse("inicio", inicio):
        raise HTTPException(
            status_code=422,
            detail=f"fim ({fim}) é anterior a inicio ({inicio}); período invertido "
                   "volta vazio e parece ausência de movimento")
    return inicio, fim


def _campos_do_patch(campos: dict) -> dict:
    """PATCH sem campo nenhum é no-op — e ia para o banco assim mesmo."""
    if not campos:
        raise HTTPException(status_code=422,
                            detail="informe ao menos um campo para alterar")
    return campos


def _provider(tenant_id, provider, account_config, vault, credentials, banco=None):
    try:
        return build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                   account_config=account_config, vault=vault,
                                   credentials=credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _creds_get(credentials, authorization, tenant_id, provider, banco=None):
    try:
        explicit = credentials_from_header(credentials)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return resolve_request_credentials(authorization=authorization, explicit=explicit,
                                       tenant_id=tenant_id, provider=provider, banco=banco)


# Quem oferece Pix Automático é quem herda o mixin BACEN — perguntado à classe,
# não a uma lista escrita à mão, que envelheceria no primeiro provider novo.
#
# Herdar o mixin, porém, prova só que temos o DIALETO. Que o banco exponha
# `rec`/`solicrec` é outra afirmação, e é do sandbox que ela vem: C6 (15 casos
# em 4 jornadas) e Sicoob (`PA_01`) confirmados; o **Inter** não. Mandar o
# integrador para um banco não confirmado é o mesmo defeito, com a agravante de
# ser uma sugestão nossa.
_COM_PIX_AUTOMATICO = sorted(
    b.value for b, klass in _REST_POR_BANCO.items()
    if disponivel(klass, "criar_recorrencia", b.value))
_ALTERNATIVA = ("Pix Automático exige o dialeto BACEN de recorrência, confirmado "
                f"nestes bancos: {', '.join(_COM_PIX_AUTOMATICO)}")


def _cap(provider_obj, metodo: str, provider: Provider, banco: Banco | None):
    """Método do Pix Automático, ou 422 dizendo quais bancos o oferecem.

    O banco que não herda o mixin BACEN não tem o método; chamá-lo direto
    levantava `AttributeError` dentro do handler e o consumidor recebia **500**
    — o serviço se acusando de defeito onde há fronteira de capacidade do banco.
    Foi o que o Itaú devolveu nas quinze rotas daqui.
    """
    try:
        _, alvo = resolver_caminho(provider, banco, {})
    except CaminhoInvalido:
        alvo = provider  # combinação inválida: o erro dela vem do _provider()
    return exige_capacidade(provider_obj, metodo, alvo,
                            recurso="Pix Automático", alternativa=_ALTERNATIVA)


# --- recorrências ------------------------------------------------------------------


@router.post("/recorrencias", response_model=dict, status_code=201)
def criar_recorrencia(body: RecorrenciaIn, authorization: str | None = _AUTH_HEADER,
                      vault: Vault = Depends(get_vault)) -> dict:
    """Cria a recorrência (rec). O pagador autoriza via app (solicrec) ou QR (loc)."""
    rec = body.recorrencia
    if bool(rec.valor_fixo) == bool(rec.valor_minimo):
        raise HTTPException(status_code=422,
                            detail="informe exatamente um: valor_fixo (valorRec) ou valor_minimo")
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)

    vinculo = {"contrato": rec.contrato, "devedor": _devedor_simples(rec.devedor)}
    if rec.objeto:
        vinculo["objeto"] = rec.objeto
    calendario = {"dataInicial": rec.data_inicial.isoformat(), "periodicidade": rec.periodicidade}
    if rec.data_final:
        calendario["dataFinal"] = rec.data_final.isoformat()
    valor = ({"valorRec": f"{rec.valor_fixo:.2f}"} if rec.valor_fixo
             else {"valorMinimoRecebedor": f"{rec.valor_minimo:.2f}"})
    payload = {"vinculo": vinculo, "calendario": calendario, "valor": valor,
               "politicaRetentativa": rec.politica_retentativa}
    if rec.loc is not None:
        payload["loc"] = rec.loc
    if rec.txid_ativacao:
        payload["ativacao"] = {"dadosJornada": {"txid": rec.txid_ativacao}}
    if rec.extras:
        payload.update(rec.extras)
    return _cap(p, "criar_recorrencia", body.provider, body.banco)(payload)


@router.get("/recorrencias", response_model=dict)
def listar_recorrencias(tenant_id: str, inicio: str = _INICIO, fim: str = _FIM,
                        provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                        credentials: str | None = _CREDS_HEADER,
                        authorization: str | None = _AUTH_HEADER,
                        vault: Vault = Depends(get_vault)) -> dict:
    """Lista recorrências do período (RFC3339)."""
    inicio, fim = _periodo(inicio, fim)
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "listar_recorrencias", provider, banco)(inicio=inicio, fim=fim)


@router.get("/recorrencias/{id_rec}", response_model=dict)
def consultar_recorrencia(id_rec: str, tenant_id: str, txid: str | None = None,
                          provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                          credentials: str | None = _CREDS_HEADER,
                          authorization: str | None = _AUTH_HEADER,
                          vault: Vault = Depends(get_vault)) -> dict:
    """Consulta a recorrência (opcionalmente por txid da jornada)."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "consultar_recorrencia", provider, banco)(id_rec, txid=txid)


@router.patch("/recorrencias/{id_rec}", response_model=dict, openapi_extra={'requestBody': _CORPO_PATCH})
def revisar_recorrencia(id_rec: str, campos: dict, tenant_id: str,
                        provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                        credentials: str | None = _CREDS_HEADER,
                        authorization: str | None = _AUTH_HEADER,
                        vault: Vault = Depends(get_vault)) -> dict:
    """Gestão (Jornada 4): alteração ou cancelamento (ex.: {"status": "CANCELADA"})."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "revisar_recorrencia", provider, banco)(id_rec, _campos_do_patch(campos))


# --- solicitação de confirmação (Jornada 1) ------------------------------------------


@router.post("/solicitacoes", response_model=dict, status_code=201)
def criar_solicitacao(body: SolicitacaoRecorrenciaIn, authorization: str | None = _AUTH_HEADER,
                      vault: Vault = Depends(get_vault)) -> dict:
    """solicrec: envia o pedido de autorização ao app do banco do pagador (Jornada 1)."""
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    return _cap(p, "criar_solicitacao_recorrencia", body.provider, body.banco)(body.dados)


@router.get("/solicitacoes/{id_solic}", response_model=dict)
def consultar_solicitacao(id_solic: str, tenant_id: str, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                          credentials: str | None = _CREDS_HEADER,
                          authorization: str | None = _AUTH_HEADER,
                          vault: Vault = Depends(get_vault)) -> dict:
    """Consulta a solicitação de autorização."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "consultar_solicitacao_recorrencia", provider, banco)(id_solic)


@router.patch("/solicitacoes/{id_solic}", response_model=dict, openapi_extra={'requestBody': _CORPO_PATCH})
def revisar_solicitacao(id_solic: str, campos: dict, tenant_id: str,
                        provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                        credentials: str | None = _CREDS_HEADER,
                        authorization: str | None = _AUTH_HEADER,
                        vault: Vault = Depends(get_vault)) -> dict:
    """Revisa/cancela a solicitação de autorização (PATCH BACEN)."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "revisar_solicitacao_recorrencia", provider, banco)(
        id_solic, _campos_do_patch(campos))


# --- locations (QR de adesão — Jornada 2) --------------------------------------------


@router.post("/locations", response_model=dict, status_code=201)
def criar_location(tenant_id: str, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                   credentials: str | None = _CREDS_HEADER,
                   authorization: str | None = _AUTH_HEADER,
                   vault: Vault = Depends(get_vault)) -> dict:
    """Cria a location do QR de adesão da recorrência (Jornada 2)."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "criar_location_recorrencia", provider, banco)()


@router.get("/locations/{loc_id}", response_model=dict)
def consultar_location(loc_id: str, tenant_id: str, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                       credentials: str | None = _CREDS_HEADER,
                       authorization: str | None = _AUTH_HEADER,
                       vault: Vault = Depends(get_vault)) -> dict:
    """Consulta a location (payload do QR)."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "consultar_location_recorrencia", provider, banco)(loc_id)


@router.delete("/locations/{loc_id}/recorrencia", response_model=dict)
def desvincular_location(loc_id: str, tenant_id: str, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                         credentials: str | None = _CREDS_HEADER,
                         authorization: str | None = _AUTH_HEADER,
                         vault: Vault = Depends(get_vault)) -> dict:
    """Desvincula a recorrência da location (invalida o QR)."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "desvincular_location_recorrencia", provider, banco)(loc_id)


# --- cobranças do ciclo (cobr — Jornada 3) --------------------------------------------


@router.put("/cobrancas/{txid}", response_model=dict, status_code=201)
def criar_cobranca(body: CobrancaRecorrenteIn, txid: str = _TXID,
                   authorization: str | None = _AUTH_HEADER,
                   vault: Vault = Depends(get_vault)) -> dict:
    """Agenda a cobrança do ciclo (>= 2 dias antes do vencimento — regra BACEN)."""
    creds = resolve_request_credentials(authorization=authorization, explicit=body.credentials,
                                        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco)
    p = _provider(body.tenant_id, body.provider, body.account_config, vault, creds,
                  banco=body.banco)
    c = body.cobranca
    payload = {
        "idRec": c.id_rec,
        "calendario": {"dataDeVencimento": c.data_vencimento.isoformat()},
        "valor": {"original": f"{c.valor:.2f}"},
    }
    if c.info_adicional:
        payload["infoAdicional"] = c.info_adicional
    if c.extras:
        payload.update(c.extras)
    return _cap(p, "criar_cobranca_recorrente", body.provider, body.banco)(txid, payload)


@router.get("/cobrancas", response_model=dict)
def listar_cobrancas(tenant_id: str, inicio: str = _INICIO, fim: str = _FIM,
                     provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                     credentials: str | None = _CREDS_HEADER,
                     authorization: str | None = _AUTH_HEADER,
                     vault: Vault = Depends(get_vault)) -> dict:
    """Lista cobranças do ciclo no período (RFC3339)."""
    inicio, fim = _periodo(inicio, fim)
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "listar_cobrancas_recorrentes", provider, banco)(inicio=inicio, fim=fim)


@router.get("/cobrancas/{txid}", response_model=dict)
def consultar_cobranca(tenant_id: str, txid: str = _TXID, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                       credentials: str | None = _CREDS_HEADER,
                       authorization: str | None = _AUTH_HEADER,
                       vault: Vault = Depends(get_vault)) -> dict:
    """Consulta uma cobrança do ciclo (cobr) pelo txid."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "consultar_cobranca_recorrente", provider, banco)(txid)


@router.patch("/cobrancas/{txid}", response_model=dict, openapi_extra={'requestBody': _CORPO_PATCH})
def revisar_cobranca(campos: dict, tenant_id: str, txid: str = _TXID, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                     credentials: str | None = _CREDS_HEADER,
                     authorization: str | None = _AUTH_HEADER,
                     vault: Vault = Depends(get_vault)) -> dict:
    """Revisa a cobrança do ciclo (PATCH BACEN) — ex.: cancelamento antes da liquidação."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "revisar_cobranca_recorrente", provider, banco)(
        txid, _campos_do_patch(campos))


@router.post("/cobrancas/{txid}/retentativa/{data}", response_model=dict, status_code=201)
def retentar_cobranca(tenant_id: str, txid: str = _TXID, data: date = _DATA_RETENTATIVA, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                      credentials: str | None = _CREDS_HEADER,
                      authorization: str | None = _AUTH_HEADER,
                      vault: Vault = Depends(get_vault)) -> dict:
    """Retentativa de liquidação para a data (YYYY-MM-DD) — pós vencimento não pago."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    return _cap(p, "retentar_cobranca_recorrente", provider, banco)(txid, data.isoformat())


# --- webhooks do Pix Automático ---------------------------------------------------------


@router.put("/config/webhooks", response_model=dict,
            openapi_extra={"requestBody": _CORPO_WEBHOOKS})
def configurar_webhooks(body: dict, tenant_id: str, provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
                        credentials: str | None = _CREDS_HEADER,
                        authorization: str | None = _AUTH_HEADER,
                        vault: Vault = Depends(get_vault)) -> dict:
    """Configura webhookrec e/ou webhookcobr: {"url_recorrencia": ..., "url_cobranca": ...}."""
    creds = _creds_get(credentials, authorization, tenant_id, provider, banco)
    p = _provider(tenant_id, provider, {}, vault, creds, banco=banco)
    out: dict = {}
    # Mesma regra do /config/webhook-*: quem chama essa URL é o BANCO, de fora.
    # Aqui ela era repassada crua — `javascript:`, `localhost` e IP interno
    # entravam com 200, e a notificação do débito nunca chegaria.
    for campo, metodo, chave in (("url_recorrencia", "configurar_webhook_recorrencia", "webhookrec"),
                                 ("url_cobranca", "configurar_webhook_cobranca_recorrente", "webhookcobr")):
        url = body.get(campo)
        if not url:
            continue
        try:
            url = validar_url_webhook(url)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"{campo}: {e}") from None
        out[chave] = _cap(p, metodo, provider, banco)(url)
    if not out:
        raise HTTPException(status_code=422, detail="informe url_recorrencia e/ou url_cobranca")
    return out
