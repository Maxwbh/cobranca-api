from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from app.core.vault import Vault, get_vault
from app.registry import (_SLUG_ENGINE, build_provider, credentials_from_header,
                          resolver_caminho)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER as _PROVIDER
from app.schemas import Banco, CobrancaIn, CobrancaOut, Provider

router = APIRouter(prefix="/cobranca", tags=["cobranca"])

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

_CONTA_DOC = ("Conta no banco, quando a consulta exige. O Sicoob identifica o boleto por "
              "numeroCliente + codigoModalidade + nossoNumero; o C6 identifica só pelo id "
              "e ignora estes campos.")
_NUMERO_CLIENTE = Query(default=None, description=_CONTA_DOC)
_CODIGO_MODALIDADE = Query(default=None, description=_CONTA_DOC)



def _header_creds(value: str | None) -> dict | None:
    try:
        return credentials_from_header(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=CobrancaOut, status_code=201,
             responses={201: {"headers": {"Location": _LOCATION}}})
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
    # 201 é o que o resto da API já faz (bolepix, checkout, credenciais, Pix
    # Automático); estas rotas só herdaram o default do FastAPI. O `Location`
    # completo — com tenant_id e provider — é o que separa 201 útil de 201
    # cosmético: sem os dois a consulta responde 422, e um Location que não se
    # segue não vale o header.
    #
    # Não é 202: o 202 afirma que ainda não há recurso, e aqui já há id e linha
    # digitável. A aprovação assíncrona da CIP no C6 é dita no `status`
    # (registrado|pendente), que é onde ela pertence.
    if out.id:
        response.headers["Location"] = _location(
            f"/cobranca/{out.id}", body.tenant_id, body.provider)
    return out


def _location(caminho: str, tenant_id: str, provider: Provider, **extra: str) -> str:
    """Location que o cliente consegue seguir: as rotas de consulta exigem
    tenant_id e provider, então omiti-los devolveria 422 a quem confia no header."""
    params = {"tenant_id": tenant_id, "provider": getattr(provider, "value", provider), **extra}
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
    cobranca_id: str, tenant_id: str, provider: Provider = _PROVIDER,
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


@router.get("/{cobranca_id}/pdf", response_model=CobrancaOut)
def pdf(
    cobranca_id: str, tenant_id: str, provider: Provider = _PROVIDER,
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
    cobranca_id: str, campos: dict, tenant_id: str, provider: Provider = _PROVIDER,
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
    cobranca_id: str, tenant_id: str, provider: Provider = _PROVIDER,
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
