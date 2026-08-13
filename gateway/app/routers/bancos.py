# Catálogo de bancos/providers do gateway — descoberta programática.
#
# As capacidades são INTROSPECTADAS das classes de provider (método sobrescrito
# = capacidade real), então este endpoint nunca fica defasado do código.
from __future__ import annotations

from fastapi import APIRouter

from app.providers.base import BankProvider
from app.providers.offline_engine import PyCobrancaProvider
from app.providers.c6 import C6Provider
from app.providers.inter import InterProvider
from app.providers.itau import ItauProvider
from app.providers.sicoob import SicoobProvider
from app.registry import _REST_POR_BANCO, _SLUG_ENGINE, registered_ready
from app.schemas import Banco

router = APIRouter(prefix="/bancos", tags=["bancos"])

# método do provider -> capacidade exposta
_CAPACIDADES = {
    "registrar": "boleto",
    "alterar": "boleto_alteracao",
    "pdf": "boleto_pdf",
    "baixar": "boleto_baixa",
    "criar_pix": "pix",
    "revisar_pix": "pix_revisao",
    "criar_lote_cobv": "pix_lote",
    "listar_pix_recebidos": "pix_recebidos",
    "configurar_webhook_pix": "webhook_pix_por_chave",
    "criar_recorrencia": "pix_automatico",
    "criar_bolepix": "bolepix",
    # O catálogo é como o consumidor DESCOBRE o que cada banco faz. Sem esta
    # linha, quem consultava /bancos não tinha como saber que existe link de
    # pagamento com cartão — a rota existia e era invisível.
    "criar_checkout": "checkout_cartao",
    "extrato": "extrato",
    "listar_recebiveis": "conciliacao_cartao",
    "cadastrar_webhook": "webhook_banco",
}

# Mecanismo de autenticação DA API — único para todos os bancos:
# 1. POST /credenciais recebe os parâmetros DO BANCO (esquema próprio de cada um),
#    processa e armazena cifrado (zero-knowledge) → devolve token bapi_;
# 2. as demais chamadas autenticam com `Authorization: Bearer bapi_...` — a API
#    valida o token e usa as credenciais do banco por dentro.
_MECANISMO_API = {
    "cadastro": "POST /credenciais {tenant_id, provider, credentials:{<esquema do banco>}} -> token bapi_ (única vez)",
    "uso": "Authorization: Bearer bapi_... nas demais chamadas (a API valida e decifra em memória)",
    "revogacao": "DELETE /credenciais (com o Bearer)",
    "alternativas": [
        "credentials no corpo (POSTs) ou header X-Bank-Credentials (GET/DELETE) — stateless",
        "cofre VAULT__<tenant>__<provider>__* (env, fallback)",
    ],
}

# Esquema de credenciais PRÓPRIO de cada banco (conteúdo do campo `credentials`)
_ESQUEMA_C6 = {
    "client_id": "obrigatório (portal C6)",
    "client_secret": "obrigatório",
    "pfx_base64": "certificado mTLS do portal (PKCS12 em base64) — obrigatório",
    "pfx_password": "senha do certificado",
}
_ESQUEMA_SICOOB = {
    "client_id": "obrigatório (portal Sicoob; vai também no header de toda request)",
    "access_token": "sandbox: token estático do portal (dispensa OAuth/mTLS)",
    "client_secret": "produção: OAuth client_credentials com scopes",
    "pfx_base64": "produção: certificado mTLS/e-CNPJ (PKCS12 em base64)",
    "pfx_password": "senha do certificado",
    "scopes": "opcional (lista; default do provider)",
}

_ESQUEMA_INTER = {
    "client_id": "obrigatório (aplicação no Internet Banking do Inter)",
    "client_secret": "obrigatório",
    "cert_pem": "certificado da aplicação (.crt em PEM ou base64) — é o que o Inter entrega",
    "key_pem": "chave privada (.key em PEM ou base64)",
    "pfx_base64": "alternativa ao par acima: o mesmo material em PKCS12/base64",
    "pfx_password": "senha do certificado, quando houver",
    "conta_corrente": "obrigatório quando a aplicação enxerga mais de uma conta (header x-conta-corrente)",
    "scopes": "opcional (lista; default do provider)",
}

_ESQUEMA_ITAU = {
    "client_id": "obrigatório (credencial da aplicação; cobrança sai por gerente/OfficerCash)",
    "client_secret": "obrigatório (o definitivo, devolvido junto com o certificado)",
    "cert_pem": "certificado dinâmico assinado pelo Itaú (.crt em PEM ou base64)",
    "key_pem": "chave privada gerada no CSR (.key em PEM ou base64)",
    "pfx_base64": "alternativa ao par acima: o mesmo material em PKCS12/base64",
    "pfx_password": "senha do certificado, quando houver",
    "scopes": "opcional (lista; default do provider)",
}


# 18 bancos suportados pelo caminho offline (engine pyCobrança / CNAB).
# Derivado do mapa que o roteador realmente usa: lista escrita à mão aqui já
# significaria catálogo dizendo uma coisa e `provider=off` fazendo outra.
_BANCOS_CNAB = sorted(_SLUG_ENGINE.values())

# Os dois eixos, ditos onde o consumidor descobre a API. O `provider` virou o
# CAMINHO e o `banco` a INSTITUIÇÃO; sem isto no catálogo, a mudança só
# apareceria lendo o Swagger campo a campo.
_CAMINHOS = {
    "on": "API do banco (OAuth2 + mTLS). Exige credencial e homologação.",
    "off": "engine pyCobrança no próprio processo (CNAB/boleto). Sem rede, sem convênio.",
    "uso": "provider=on|off + banco=<id>. Ex.: provider=on&banco=c6",
    "legado": ("nome do banco no `provider` (`provider=c6`) segue aceito como apelido "
               "de `on`+`banco`; sai na 3.0.0"),
}


def _capacidades(klass: type) -> list[str]:
    caps = []
    for metodo, capacidade in _CAPACIDADES.items():
        impl = getattr(klass, metodo, None)
        base = getattr(BankProvider, metodo, None)
        if impl is not None and impl is not base:  # sobrescrito = suportado de fato
            caps.append(capacidade)
    return sorted(caps)


def _caminho_do_banco(banco: Banco) -> dict:
    """O que ESTA instalação faz com o banco — não o que o banco sabe fazer.

    `capacidades` responde pela API do banco; não respondia pela instalação. Com
    `<BANCO>_REGISTERED_READY` desligado, `provider=on` é rebaixado para a
    engine em silêncio, e quem consultava o catálogo via "boleto" e concluía
    "registrado no banco". Estes dois campos são a diferença entre as duas
    frases.
    """
    pronto = registered_ready(banco)
    fallback = _SLUG_ENGINE.get(banco)
    return {
        "caminhos": (["on"] if banco in _REST_POR_BANCO else []) + (["off"] if fallback else []),
        "registrado_pronto": pronto,
        "fallback_offline": fallback,
        "caminho_efetivo": "on" if pronto else ("off" if fallback else "on"),
        "flag": f"{banco.value.upper()}_REGISTERED_READY",
    }


@router.get("", response_model=dict)
def listar() -> dict:
    """Bancos disponíveis, caminho (on/off) de cada um, capacidades reais e como autenticar."""
    return {
        "caminhos": _CAMINHOS,
        "autenticacao_api": _MECANISMO_API,
        "bancos": [
            {
                **_caminho_do_banco(Banco.c6),
                "id": "c6",
                "nome": "C6 Bank",
                "codigo_banco": "336",
                "tipo": "rest",
                "capacidades": _capacidades(C6Provider),
                "credentials": _ESQUEMA_C6,
                "sandbox": "https://baas-api-sandbox.c6bank.info (seg-sex 7h-23h; mTLS + OAuth)",
                "documentacao": "docs/development/c6-rest.md",
            },
            {
                **_caminho_do_banco(Banco.sicoob),
                "id": "sicoob",
                "nome": "Sicoob",
                "codigo_banco": "756",
                "tipo": "rest",
                "capacidades": _capacidades(SicoobProvider),
                "credentials": _ESQUEMA_SICOOB,
                "sandbox": "https://sandbox.sicoob.com.br/sicoob/sandbox (token estático do portal)",
                "documentacao": "docs/development/sicoob-rest.md",
            },
            {
                **_caminho_do_banco(Banco.inter),
                "id": "inter",
                "nome": "Banco Inter",
                "codigo_banco": "077",
                "tipo": "rest",
                "capacidades": _capacidades(InterProvider),
                "credentials": _ESQUEMA_INTER,
                "sandbox": "https://cdpj-sandbox.partners.uatinter.co (OAuth + mTLS)",
                "documentacao": "docs/development/inter-rest.md",
                "observacao": ("sem fallback offline: a engine pyCobrança não tem o layout do "
                               "077, e cair em outro banco emitiria boleto errado"),
            },
            {
                **_caminho_do_banco(Banco.itau),
                "id": "itau",
                "nome": "Itaú Unibanco",
                "codigo_banco": "341",
                "tipo": "rest",
                "capacidades": _capacidades(ItauProvider),
                "credentials": _ESQUEMA_ITAU,
                "sandbox": "sem mTLS e fora do OAuth 2.0 — o dialeto do sandbox NÃO é o de produção",
                "documentacao": "docs/development/itau-rest.md",
                "observacao": ("ESQUELETO: paths e payload ainda não confirmados (catálogo exige "
                               "login) e o provider fica desligado até ITAU_REGISTERED_READY — "
                               "sem a flag, provider=itau emite pela engine, que tem o layout 341. "
                               "O banco não devolve PDF: quem renderiza é a engine"),
            },
            {
                "caminhos": ["off"],
                "id": "pycobranca",
                "nome": "Offline/CNAB (engine pyCobrança — 100% Python)",
                "codigo_banco": None,
                "tipo": "offline",
                "capacidades": _capacidades(PyCobrancaProvider) + ["carne", "remessa_cnab", "retorno_cnab"],
                "bancos_cnab": _BANCOS_CNAB,
                "observacao": ("default quando `provider` vem vazio/omitido; "
                                "não requer credenciais de banco"),
                "documentacao": "docs/development/separacao-3-produtos.md",
            },
        ],
    }
