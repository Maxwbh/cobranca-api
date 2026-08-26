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
from app.routers._capacidades import disponivel, implementa, nao_confirmadas
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
    # Três rotas públicas que o catálogo não mencionava, e que DISCRIMINAM:
    # `GET /pix/{txid}` não existe no Itaú, `GET /conciliacao/transacoes` só no
    # C6, e sem `normalizar_webhook` o `POST /webhooks/{banco}` não entende a
    # notificação daquele banco. É o mesmo argumento do `checkout_cartao` acima
    # — a rota existia e era invisível.
    "consultar_pix": "pix_consulta",
    "listar_transacoes": "conciliacao_transacoes",
    "normalizar_webhook": "webhook_entrada",
}

# `consultar` fica DE FORA de propósito, e o motivo é o limite do método: a
# introspecção lê "sobrescrito = suporta", e o provider offline sobrescreve
# `consultar` para devolver `pendente` com a dica "conciliar via retorno/OFX".
# Sobrescrever ali é honestidade, não capacidade — anunciar faria o consumidor
# esperar consulta de status onde não há estado para consultar.

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


# Os 19 bancos do caminho offline (engine pyCobrança / CNAB). Eram 18 até a
# 1.1.1 implementar o Inter (077).
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


def _capacidades(klass: type, banco: str | None = None) -> list[str]:
    # Mesmo critério que o `exige_capacidade` aplica na requisição — uma função
    # só, para o catálogo não voltar a discordar do que a rota faz.
    #
    # `banco` entra porque capacidade herdada de mixin não é a mesma coisa que
    # capacidade confirmada no banco: o Inter herda o dialeto de Pix Automático
    # e ninguém verificou se o banco expõe as rotas. Ver `_NAO_CONFIRMADO`.
    return sorted(cap for metodo, cap in _CAPACIDADES.items()
                  if disponivel(klass, metodo, banco))


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
        # Capacidade cujo dialeto o provider herda e que ninguém confirmou NESTE
        # banco: some de `capacidades` e aparece aqui, com a variável que a
        # libera. Sai vazio quando não há nenhuma — que é o caso hoje. Fica em
        # `_caminho_do_banco` porque vale para todos, e pendurar na entrada de um
        # banco só foi o que fez o campo faltar nos outros três.
        "capacidades_nao_confirmadas": nao_confirmadas(banco.value),
    }


# A resposta é HETEROGÊNEA de propósito: o registro do `pycobranca` traz
# `bancos_cnab` e não tem `flag` nem `codigo_banco`. Modelo Pydantic único
# forçaria campos opcionais em todo mundo e diria menos, não mais — então o
# schema é escrito aqui, descrevendo o que cada campo DECIDE. Um teste compara
# estas chaves com as que a rota devolve, para a descrição não envelhecer.
_SCHEMA_BANCO = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "Valor aceito em `banco` (e no `provider` legado).",
               "example": "c6"},
        "nome": {"type": "string", "example": "C6 Bank"},
        "codigo_banco": {"type": "string", "nullable": True,
                         "description": "COMPE. `null` no registro da engine, que não é um banco.",
                         "example": "336"},
        "tipo": {"type": "string", "enum": ["rest", "offline"]},
        "caminhos": {"type": "array", "items": {"type": "string", "enum": ["on", "off"]},
                     "description": "Caminhos que ESTE banco tem. O Inter só tem `on`: "
                                    "não há layout offline dele, e cair na engine emitiria "
                                    "um boleto de outro banco.",
                     "example": ["on", "off"]},
        "registrado_pronto": {"type": "boolean",
                              "description": "A flag desta instalação está ligada."},
        "caminho_efetivo": {"type": "string", "enum": ["on", "off"],
                            "description": "**O que acontece de fato** ao pedir `provider=on` "
                                           "agora. Com a flag desligada e havendo fallback, "
                                           "vira `off` — a chamada responde `201` sem ter "
                                           "passado pelo banco."},
        "fallback_offline": {"type": "string", "nullable": True,
                             "description": "Slug da engine usado quando o `on` é rebaixado.",
                             "example": "banco_c6"},
        "flag": {"type": "string", "description": "Variável de ambiente que liga o caminho `on`.",
                 "example": "C6_REGISTERED_READY"},
        "capacidades": {"type": "array", "items": {"type": "string"},
                        "description": "Introspectadas das classes de provider — método "
                                       "sobrescrito = capacidade real, então a lista não "
                                       "envelhece com o código. Capacidade herdada de mixin "
                                       "só entra aqui depois de CONFIRMADA no banco; até lá "
                                       "aparece em `capacidades_nao_confirmadas`.",
                        "example": ["boleto", "pix", "pix_consulta", "webhook_entrada"]},
        "capacidades_nao_confirmadas": {
            "type": "object", "additionalProperties": {"type": "string"},
            "description": "`capacidade -> variável que a libera`. O provider tem o "
                           "dialeto e ninguém confirmou que ESTE banco expõe as rotas — "
                           "dizer que ele não oferece seria outra afirmação sem lastro. "
                           "Confirme com credencial real e ligue a variável.",
            "example": {"pix_automatico": "INTER_PIX_AUTOMATICO_READY"}},
        "credentials": {"type": "object",
                        "description": "Esquema de credenciais DESTE banco, para o "
                                       "`POST /credenciais`. O mecanismo é um só; os campos "
                                       "são de cada instituição."},
        "bancos_cnab": {"type": "array", "items": {"type": "string"},
                        "description": "Só no registro da engine: os 18 slugs do catálogo offline."},
        "observacao": {"type": "string",
                       "description": "Só no registro da engine: quando ela entra sem ninguém pedir."},
        "sandbox": {"type": "string"},
        "documentacao": {"type": "string", "example": "docs/development/c6-rest.md"},
    },
    "required": ["id", "nome", "tipo", "caminhos", "capacidades"],
}

_SCHEMA_CATALOGO = {
    "type": "object",
    "properties": {
        "caminhos": {"type": "object", "description": "O que `on` e `off` significam, e o apelido legado."},
        "autenticacao_api": {"type": "object", "description": "Como autenticar — igual para todos os bancos."},
        "bancos": {"type": "array", "items": _SCHEMA_BANCO},
    },
    "required": ["caminhos", "autenticacao_api", "bancos"],
}


@router.get(
    "",
    response_model=dict,
    summary="Catálogo de bancos desta instalação",
    responses={200: {"content": {"application/json": {"schema": _SCHEMA_CATALOGO}}}},
)
def listar() -> dict:
    """Bancos disponíveis, caminho (on/off) de cada um, capacidades reais e como autenticar.

    É a rota para onde o resto da documentação manda quem precisa da matriz
    exata — e ela respondia com `summary: "Listar"` e schema "objeto qualquer".
    Os campos que decidem integração estão descritos no schema da resposta.
    """
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
                "capacidades": _capacidades(C6Provider, "c6"),
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
                "capacidades": _capacidades(SicoobProvider, "sicoob"),
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
                "capacidades": _capacidades(InterProvider, "inter"),
                "credentials": _ESQUEMA_INTER,
                "sandbox": "https://cdpj-sandbox.partners.uatinter.co (OAuth + mTLS)",
                "documentacao": "docs/development/inter-rest.md",
                "observacao": ("existe nos dois caminhos desde a pyCobrança 1.1.1, que "
                               "implementou o layout 077 — o fallback offline cai no "
                               "layout DO PRÓPRIO Inter. Só a carteira 110 no boleto"),
            },
            {
                **_caminho_do_banco(Banco.itau),
                "id": "itau",
                "nome": "Itaú Unibanco",
                "codigo_banco": "341",
                "tipo": "rest",
                "capacidades": _capacidades(ItauProvider, "itau"),
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
