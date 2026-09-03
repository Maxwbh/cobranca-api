from __future__ import annotations

import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.vault import Vault, get_vault
from app.registry import (_SLUG_ENGINE, build_provider, credentials_from_header,
                          resolver_caminho)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER as _PROVIDER, TENANT as _TENANT
from app.schemas import Banco, CobrancaIn, CobrancaOut, Provider, Status

router = APIRouter(prefix="/cobranca", tags=["cobranca"])

# O `Location` só serve a quem sabe que ele existe: o FastAPI não documenta
# header setado em tempo de execução, então o Swagger dizia 201 sem dizer para
# onde ir. Declarado aqui para aparecer no contrato.
_LOCATION = {
    "description": "URL de consulta do recurso criado, já com tenant_id, provider e banco",
    "schema": {"type": "string"},
}


_CREDS_HEADER = Header(
    default=None,
    alias="X-Bank-Credentials",
    description="Credenciais do banco (JSON em base64) — só memória, nunca persistidas. Fallback: cofre VAULT__*.",
)
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

_CONTA_DOC = ("Conta no banco, quando a consulta exige. O Sicoob identifica o boleto por "
              "numeroCliente + codigoModalidade + nossoNumero; o C6 identifica só pelo id "
              "e ignora estes campos.")
_NUMERO_CLIENTE = Query(default=None, description=_CONTA_DOC)
_CODIGO_MODALIDADE = Query(default=None, description=_CONTA_DOC)



def _flag(nome: str, default: bool = False) -> bool:
    bruto = os.environ.get(nome)
    return default if bruto is None else bruto.strip().lower() in ("1", "true", "yes", "on")


def _erro_vira_http(out: CobrancaOut) -> JSONResponse | None:
    """`status: "erro"` como `422`, sob `COBRANCA_ERRO_HTTP=1`.

    `201 Created` é a afirmação mais forte que o HTTP tem de "criei o recurso", e
    a rota a usava para dizer que NÃO criou: dados recusados pela engine voltam
    `201` com `status: "erro"` e `id: null`. Quem faz `raise_for_status()` — o
    idiomático em qualquer cliente — dá o boleto por emitido.

    Que é defeito, e não estilo, fica claro na comparação interna: a MESMA
    violação (carteira 999 no BB) responde `400` em `GET /api/boleto/validate` e
    em `POST /api/render/boleto`, e `422` quando é o banco que a detecta e
    devolve `400`. Só aqui ela passa por sucesso — o mesmo erro com três códigos,
    conforme quem o percebeu.

    Mudar o default é quebra de contrato para quem já trata `status`, e a doc
    ensina o comportamento atual em três lugares. Então entra como a casa faz
    com contrato: flag com default compatível hoje (`WEBHOOK_ALLOW_UNAUTHENTICATED`
    e `WEBHOOK_CONFIRM` são o precedente), default novo na 3.0.0.

    O CORPO não muda — só o código. Quem migrar continua lendo
    `raw.validation_errors` no mesmo lugar.
    """
    if out.status is not Status.erro or not _flag("COBRANCA_ERRO_HTTP"):
        return None
    return JSONResponse(status_code=422, content=jsonable_encoder(out))


def _header_creds(value: str | None) -> dict | None:
    try:
        return credentials_from_header(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=CobrancaOut, status_code=201,
             summary="Registrar cobrança (boleto)",
             responses={201: {"headers": {"Location": _LOCATION},
                              "description": "Cobrança registrada. **Cheque `status`**: por "
                                             "compatibilidade, dados recusados pela engine "
                                             "também respondem `201`, com `status: \"erro\"`, "
                                             "`id: null` e sem `Location`. "
                                             "`COBRANCA_ERRO_HTTP=1` faz esse caso responder "
                                             "`422`, que passa a ser o default na 3.0.0."}})
def registrar(
    body: CobrancaIn,
    response: Response,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> CobrancaOut:
    """Registra a cobrança (boleto). Dois eixos: `provider` diz o **caminho** —
    `on` = API REST do banco, `off` (default) = CNAB offline pela engine
    pyCobrança — e `banco` diz a **instituição** (`c6`, `sicoob`, `itau`…).

    O nome do banco no `provider` (`provider=c6`) segue aceito como apelido de
    `on` + `banco`, e sai na 3.0.0. Resposta normalizada, igual nos dois
    caminhos. Combinação que não existe responde `422` dizendo quais existem.
    """
    creds = resolve_request_credentials(
        authorization=authorization, explicit=body.credentials,
        tenant_id=body.tenant_id, provider=body.provider, banco=body.banco,
    )
    provider = build_provider(
        provider=body.provider, banco=body.banco, tenant_id=body.tenant_id,
        account_config=body.account_config, vault=vault, credentials=creds,
    )
    out = provider.registrar(body.cobranca)
    recusa = _erro_vira_http(out)
    if recusa is not None:
        return recusa
    # 201 é o que o resto da API já faz (bolepix, checkout, credenciais, Pix
    # Automático); estas rotas só herdaram o default do FastAPI. O `Location`
    # completo — com tenant_id, provider E BANCO — é o que separa 201 útil de
    # 201 cosmético: sem os três a consulta responde 422, e um Location que não
    # se segue não vale o header.
    #
    # Não é 202: o 202 afirma que ainda não há recurso, e aqui já há id e linha
    # digitável. A aprovação assíncrona da CIP no C6 é dita no `status`
    # (registrado|pendente), que é onde ela pertence.
    if out.id:
        response.headers["Location"] = _location(
            f"/cobranca/{out.id}", body.tenant_id, body.provider, body.banco)
    return out


def _location(caminho: str, tenant_id: str, provider: Provider,
              banco: Banco | None = None, **extra: str) -> str:
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


def _conta(numero_cliente: int | None, codigo_modalidade: int | None) -> dict:
    """Configuração de conta nas rotas sem corpo.

    As quatro rotas de leitura/baixa montavam o provider com `account_config={}`,
    e no Sicoob isso significa `numeroCliente` VAZIO: consultar, imprimir ou
    baixar boleto respondia 400 do banco, sempre. O C6 nunca expôs a falha
    porque identifica o boleto só pelo id — foi o roteiro do Sicoob que achou.
    """
    return {k: v for k, v in {"numeroCliente": numero_cliente,
                              "codigoModalidade": codigo_modalidade}.items() if v is not None}


@router.get("/{cobranca_id}", response_model=CobrancaOut)
def consultar(
    cobranca_id: str, tenant_id: str = _TENANT, provider: Provider = _PROVIDER,
    banco: Banco | None = _BANCO,
    numero_cliente: int | None = _NUMERO_CLIENTE,
    codigo_modalidade: int | None = _CODIGO_MODALIDADE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> CobrancaOut:
    """Consulta o status normalizado do boleto (registrado|pendente|liquidado|baixado)."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=_header_creds(credentials),
        tenant_id=tenant_id, provider=provider, banco=banco,
    )
    p = build_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                       account_config=_conta(numero_cliente, codigo_modalidade),
                       vault=vault, credentials=creds)
    return p.consultar(cobranca_id)


@router.get("/{cobranca_id}/pdf", response_model=CobrancaOut, summary="PDF do boleto")
def pdf(
    cobranca_id: str, tenant_id: str = _TENANT, provider: Provider = _PROVIDER,
    banco: Banco | None = _BANCO,
    numero_cliente: int | None = _NUMERO_CLIENTE,
    codigo_modalidade: int | None = _CODIGO_MODALIDADE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> CobrancaOut:
    """PDF do boleto registrado — **quando o banco fornece**.

    C6, Sicoob e Inter devolvem o PDF em base64. O **Itaú não**: a API dele responde
    linha digitável e código de barras, e o desenho é renderizar pela engine,
    que já tem o layout 341. Nesse caso a rota responde `422` dizendo o caminho
    exato — `POST /api/render/boleto` com `bank` do banco e **os dados que o
    banco registrou**.

    A ressalva do `422` não é formalidade: o código de barras é determinístico,
    então renderizar com um nosso número diferente do registrado produz um
    boleto que ninguém concilia. Confira a linha digitável calculada contra a
    que o banco devolveu antes de entregar ao pagador.
    """
    creds = resolve_request_credentials(
        authorization=authorization, explicit=_header_creds(credentials),
        tenant_id=tenant_id, provider=provider, banco=banco,
    )
    p = build_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                       account_config=_conta(numero_cliente, codigo_modalidade),
                       vault=vault, credentials=creds)
    try:
        return p.pdf(cobranca_id)
    except NotImplementedError as e:
        # "Não fornece" sozinho manda o integrador procurar defeito onde não há.
        # Quando o banco TEM layout na engine (Itaú, por exemplo), o PDF existe
        # — só vem do caminho offline, e a mensagem entrega o slug pronto.
        #
        # O slug sai do BANCO resolvido, não do `provider`: com o modelo novo
        # (`provider=on&banco=itau`) o `provider` não nomeia banco nenhum, e
        # procurar por ele devolveria a mensagem genérica justo em quem tem
        # layout.
        _, alvo = resolver_caminho(provider, banco, {})
        slug = _SLUG_ENGINE.get(alvo)
        alternativa = (
            f"renderize pela engine: POST /api/render/boleto com bank='{slug}' e os "
            "dados que o banco registrou (confira a linha digitável calculada "
            "contra a que o banco devolveu antes de entregar ao pagador)"
            if slug else
            "não há layout offline para este banco; use o PDF do próprio banco quando houver"
        )
        raise HTTPException(
            status_code=422,
            detail=f"banco '{alvo.value}' não devolve PDF na API; {alternativa}",
        ) from e


@router.put("/{cobranca_id}", response_model=CobrancaOut)
def alterar(
    cobranca_id: str, campos: dict, tenant_id: str = _TENANT, provider: Provider = _PROVIDER,
    banco: Banco | None = _BANCO,
    numero_cliente: int | None = _NUMERO_CLIENTE,
    codigo_modalidade: int | None = _CODIGO_MODALIDADE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> CobrancaOut:
    """Altera boleto emitido (amount, due_date, discount, interest, fine)."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=_header_creds(credentials),
        tenant_id=tenant_id, provider=provider, banco=banco,
    )
    p = build_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                       account_config=_conta(numero_cliente, codigo_modalidade),
                       vault=vault, credentials=creds)
    try:
        return p.alterar(cobranca_id, campos)
    except NotImplementedError as e:
        raise HTTPException(status_code=422, detail="este banco não suporta alteração online; baixe e reemita") from e


@router.delete("/{cobranca_id}", response_model=CobrancaOut)
def baixar(
    cobranca_id: str, tenant_id: str = _TENANT, provider: Provider = _PROVIDER,
    banco: Banco | None = _BANCO,
    numero_cliente: int | None = _NUMERO_CLIENTE,
    codigo_modalidade: int | None = _CODIGO_MODALIDADE,
    credentials: str | None = _CREDS_HEADER,
    authorization: str | None = _AUTH_HEADER,
    vault: Vault = Depends(get_vault),
) -> CobrancaOut:
    """Baixa/cancela o boleto (409 enquanto a CIP processa o registro)."""
    creds = resolve_request_credentials(
        authorization=authorization, explicit=_header_creds(credentials),
        tenant_id=tenant_id, provider=provider, banco=banco,
    )
    p = build_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                       account_config=_conta(numero_cliente, codigo_modalidade),
                       vault=vault, credentials=creds)
    return p.baixar(cobranca_id)
