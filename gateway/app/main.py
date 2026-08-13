from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.vault import CredentialNotFound
from app.registry import CaminhoInvalido
from app.core.swagger_tema import pagina_swagger
from app.providers.c6 import ProcessamentoPendente
from app.routers import (
    bancos, bolepix, carne, checkout, cobranca, conciliacao, credenciais,
                         extrato, jobs, offline, pix, pix_automatico, webhook_banco,
                         webhooks)

# Portais oficiais (linkados nas descrições — o Swagger UI renderiza markdown)
_DOC_C6 = "https://developers.c6bank.com.br"
_DOC_SICOOB = "https://developers.sicoob.com.br/portal/"
_DOC_BACEN_PIX = "https://bacen.github.io/pix-api/"
_DOC_INTER = "https://developers.bancointer.com.br/"
_DOC_REPO = "https://github.com/Maxwbh/cobranca-api/tree/main/docs/development"

TAGS = [
    {"name": "bancos",
     "description": "Catálogo de bancos: caminhos (`on`/`off`) de cada um, capacidades reais (introspecção), "
                    "o que **esta instalação** faz (`registrado_pronto`, `fallback_offline`) e o esquema de "
                    "credenciais por banco. "
                    f"Catálogo completo de serviços por banco (incl. não implementados): [docs do repositório]({_DOC_REPO})."},
    {"name": "credenciais",
     "description": "Tokenização zero-knowledge: cadastre as credenciais do banco UMA vez e use o token `bapi_` nas demais chamadas. "
                    "**O mecanismo é um só; o esquema de campos é de cada banco** — C6 e Sicoob entregam "
                    "PKCS12 (`pfx_base64` + `pfx_password`), o Inter entrega `.crt` + `.key` "
                    "(`cert_pem` + `key_pem`, aceitos em PEM cru ou base64). Integrar banco novo não muda "
                    "nada do lado do consumidor: o esquema vigente sai em `GET /bancos`."},
    {"name": "cobranca",
     "description": "Boleto: emitir, consultar, alterar, PDF e baixar. `provider=on` vai à API do banco, "
                    "`provider=off` emite pela engine pyCobrança; `banco` diz qual instituição. "
                    f"Docs oficiais: [C6 Boleto]({_DOC_C6}/apis/bankslip) · [Sicoob Cobrança v3]({_DOC_SICOOB}) · "
                    f"[Inter Cobrança v3]({_DOC_INTER}).\n\n"
                    "**Alterar (`PUT`) hoje só existe no C6** — no Sicoob e no Inter o caminho é "
                    "baixar e reemitir, e a rota responde `422` dizendo isso.\n\n"
                    "**PDF nem sempre vem do banco.** C6 e Inter devolvem em base64; o **Itaú "
                    "não devolve** — a API dele responde linha digitável e código de barras, e o "
                    "PDF sai da engine (`POST /api/render/boleto`, `bank=itau`), com **os dados "
                    "que o banco registrou**. O código de barras é determinístico: renderizar com "
                    "um nosso número diferente do registrado gera um boleto que não concilia — "
                    "confira a linha digitável antes de entregar ao pagador.\n\n"
                    "`GET /bancos` responde a matriz exata, por introspecção."},
    {"name": "carne",
     "description": "Carnê 3-vias A4 (registra N parcelas e monta o PDF na engine pyCobrança)."},
    {"name": "pix",
     "description": "Pix BACEN: cob/cobv, revisão, listas, lote e Pix RECEBIDOS (conciliação). Dialeto idêntico em todos os bancos — "
                    f"[spec BACEN]({_DOC_BACEN_PIX}). Docs oficiais: [C6 Pix]({_DOC_C6}/apis/pix) · "
                    f"[Sicoob]({_DOC_SICOOB}) · [Inter]({_DOC_INTER})."},
    {"name": "bolepix",
     "description": "Boleto híbrido online com QR Pix EVP embutido (exclusivo C6, /v2/bank_slips). "
                    f"Doc oficial: [C6 Bolepix]({_DOC_C6}/apis/bolepix)."},
    {"name": "checkout",
     "description": "Link de pagamento com **cartão** (crédito/débito, parcelado) e, opcionalmente, Pix no mesmo link. "
                    "**Modo link apenas:** o pagador digita o cartão na página do banco — nenhum dado de cartão passa por esta API, "
                    "e por isso `save_card` e checkout transparente não existem no schema. Existe no banco que oferece a "
                    f"funcionalidade (hoje o C6). Doc oficial: [C6 Checkout]({_DOC_C6}/apis/checkout)."},
    {"name": "pix-automatico",
     "description": "Débito recorrente via Pix (BACEN): recorrência, autorização do pagador, cobranças do ciclo e retentativa. "
                    "O agendamento de cada cobrança fica no produto consumidor. "
                    f"Docs: [spec BACEN]({_DOC_BACEN_PIX}) · [C6 Pix Automático]({_DOC_C6}/apis/pix-automatico)."},
    {"name": "conciliacao",
     "description": "Recebíveis e transações C6 Pay (extrato da adquirência). "
                    f"Doc oficial: [C6 Pay statements]({_DOC_C6}/apis/c6pay-statements)."},
    {"name": "extrato",
     "description": "Extrato da conta PJ (C6 /v1/statement; Sicoob conta-corrente v4 — mensal; Inter /banking/v2/extrato). "
                    f"Docs oficiais: [C6 Extrato]({_DOC_C6}/apis/statement) · [Sicoob]({_DOC_SICOOB}) · [Inter]({_DOC_INTER})."},
    {"name": "config",
     "description": "Configurações NO banco: URL de webhook (boleto e Pix por chave). "
                    "Cadastro de webhook de boleto no **C6** e no **Inter**; o Sicoob não expõe a rota "
                    "(responde `422`). O de Pix por chave é BACEN, igual em todos. "
                    f"Docs oficiais: [C6 Notificações]({_DOC_C6}/apis/notifications) · [Inter]({_DOC_INTER}) · "
                    f"[webhook Pix BACEN]({_DOC_BACEN_PIX})."},
    {"name": "jobs",
     "description": "Processamento em **lote assíncrono**: `202 Accepted` + `job_id`, itens "
                    "rastreáveis e estado persistido. A falha de um item não cancela o job "
                    "(`partially_completed`). Idempotência por `Idempotency-Key`. Boletos e **CNAB com sublotes determinísticos**; artefatos (PDF/`.rem`/zip) com `sha256` e expiração; **webhook de conclusão** assinado (HMAC) e métricas por job."},
    {"name": "webhooks",
     "description": "ENTRADA de notificações dos bancos → evento normalizado → push assinado (HMAC) ao consumidor dono do tenant."},
    {"name": "health", "description": "Sonda de disponibilidade."},
]

app = FastAPI(
    title="Cobranca-API",
    version="2.2.0",
    docs_url=None,  # /docs customizado abaixo (tema visual da plataforma)
    # `contact` e `license_info` saem no cabeçalho do Swagger e no openapi.json —
    # é o "quem mantém isto" para quem chega pela demo sem passar pelo GitHub.
    contact={
        "name": "Maxwell da Silva Oliveira — M&S do Brasil LTDA",
        "url": "https://msbrasil.inf.br",
        "email": "maxwbh@gmail.com",
    },
    license_info={"name": "MIT", "url": "https://github.com/Maxwbh/cobranca-api/blob/main/LICENSE"},
    openapi_tags=TAGS,
    description=(
        "Serviço único de cobrança **100% Python** — **3 bancos ON** "
        "(**C6** 336 · **Sicoob** 756 · **Inter** 077) **e 18 OFF** pela engine "
        "[pyCobrança](https://github.com/Maxwbh/pyCobranca) embutida.\n\n"
        "**Dois eixos, dois campos:** `provider` é o **caminho** — `on` (API do "
        "banco) ou `off` (engine pyCobrança) — e `banco` é a **instituição** "
        "(`c6`, `sicoob`, `itau`, `banco_brasil`…). Trocar de caminho é trocar "
        "`provider`; o `banco` fica. O nome do banco no `provider` (`provider=c6`) "
        "segue aceito como **apelido legado** e sai na 3.0.0.\n\n"
        "**Nem todo banco faz tudo** — e isso é dado, não parágrafo: `GET /bancos` "
        "devolve as capacidades por **introspecção das classes de provider**, então "
        "não há como a lista envelhecer. Ele diz também o que **esta instalação** "
        "faz com cada banco (`registrado_pronto`, `fallback_offline`, "
        "`caminho_efetivo`) — capacidade do banco e caminho da instalação são "
        "coisas diferentes. Pedir ao banco algo que ele não oferece "
        "responde `422` dizendo **para onde ir**, nunca `500`.\n\n"
        "**Superfície offline (`/api/*`):** boleto/CNAB/OFX de **18 bancos** sem banco online, gerada "
        "**nativamente** pela pyCobrança no próprio processo (sem sidecar) e sem "
        "autenticação — doc própria em [**Swagger Offline → `/api/docs`**](/api/docs) "
        "([spec](/api/openapi.yaml)).\n\n"
        "**Produto standalone** consumido por múltiplos sistemas; escopo por `tenant_id`. "
        "**Instalação em uma linha** — imagem pronta publicada a cada release: "
        "`docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest`. "
        "Documentação completa: [maxwbh.github.io/cobranca-api](https://maxwbh.github.io/cobranca-api/).\n\n"
        "### Emissão em lote — qual caminho usar\n\n"
        "| Volume | Caminho | O que devolve |\n"
        "|---|---|---|\n"
        "| até **200** | `POST /api/boleto/multi` | **um PDF** com o lote (síncrono) |\n"
        "| até **200** | `POST /jobs/boletos` | **202 + `job_id`**: artefatos, estado e webhook |\n"
        "| acima de 200 | dividir em jobs de até 200 | ambos respondem **413** acima do teto |\n\n"
        "`LOTE_MAX_ITENS` e `JOB_MAX_ITENS` (default **200**) limitam os **dois** "
        "caminhos. O limite protege **memória** — o PDF do lote é montado em RAM —, "
        "não tempo: o custo por boleto é o mesmo lote a lote.\n\n"
        "**Referência medida** (HML, free tier, engine offline): ~**65 ms por "
        "boleto**, estável de 50 a 200 itens — 100 boletos ≈ 7 s, 200 ≈ 14 s. O "
        "job **não é mais rápido** (mesma engine, `BackgroundTasks` no mesmo "
        "processo): ele devolve em ~0,4 s em vez de segurar a conexão, e entrega "
        "estado consultável, artefatos com `sha256` e webhook de conclusão.\n\n"
        "**Push de eventos (saída, não é um path desta API):** ao receber o webhook do "
        "banco, o gateway envia o evento normalizado (`WebhookEvent`) por `POST` ao "
        "consumidor dono do tenant, assinado em `X-Signature: sha256=<hmac_sha256(secret, "
        "raw_body)>`. Destino por tenant via `SUB__<tenant>__URL/SECRET`, com fallback "
        "global `EVENT_WEBHOOK_URL/SECRET`.\n\n"
        "**Respostas `dict` (passthrough):** rotas Pix/Pix Automático/extrato/conciliação "
        "devolvem o corpo do banco como veio (padrão BACEN/documentação do banco), sem "
        "re-tipagem — o contrato é o do banco; o gateway normaliza autenticação, "
        "multi-tenant e erros.\n\n"
        "### Como testar (serviço único)\n\n"
        "```bash\n"
        "# 1. As duas superfícies na mesma URL\n"
        "curl {base}/health          # gateway\n"
        "curl {base}/api/health      # engine offline (pyCobrança)\n\n"
        "# 2. Boleto offline em PDF (sem credencial)\n"
        "curl -G {base}/api/boleto --data-urlencode 'bank=banco_brasil' \\\n"
        "  --data-urlencode 'type=pdf' --data-urlencode 'data={...json do boleto...}' -o boleto.pdf\n\n"
        "# 3. Cobrança registrada (após POST /credenciais -> token bapi_)\n"
        "curl -X POST {base}/cobranca -H 'Authorization: Bearer bapi_...' \\\n"
        "  -H 'Content-Type: application/json' -d '{...CobrancaIn...}'\n"
        "```\n\n"
        "---\n\n"
        "**Documentação oficial dos bancos:** "
        f"[C6 Bank]({_DOC_C6}) · [Sicoob]({_DOC_SICOOB}) · [Pix BACEN]({_DOC_BACEN_PIX}) — "
        f"guias de integração por banco (incl. catálogo de serviços): [repositório]({_DOC_REPO})."
    ),
)

_openapi_original = app.openapi

# --- Erros na spec -------------------------------------------------------------
#
# Os erros de banco NÃO nascem nas assinaturas das rotas: vêm dos exception
# handlers abaixo (`ProcessamentoPendente`, `httpx.HTTPStatusError`,
# `httpx.RequestError`, `CredentialNotFound`). O FastAPI não os enxerga, então a
# spec declarava só `200/201/422` — e quem integra descobria o `409` da CIP e o
# `424` de credencial em produção, não no Swagger.
#
# Declarar num pós-processamento único, e não `responses=` rota a rota, é o que
# mantém spec e handler casados: a lista mora ao lado do `ERRO_UPSTREAM` que a
# produz, e rota nova entra documentada sem ninguém lembrar de copiar o bloco.

_ERRO_UPSTREAM = "ErroDoBanco"
_ERRO_SIMPLES = "Erro"

_SCHEMAS_DE_ERRO: dict[str, dict] = {
    _ERRO_SIMPLES: {
        "title": "Erro",
        "type": "object",
        "properties": {"detail": {"type": "string"}},
        "required": ["detail"],
    },
    _ERRO_UPSTREAM: {
        "title": "Erro do banco",
        "description": "O status do banco é traduzido para o que o chamador precisa "
                       "fazer, mas o original vai inteiro em `upstream` — traduzir a "
                       "faixa não pode custar o diagnóstico.",
        "type": "object",
        "properties": {
            "detail": {"type": "string", "description": "O que houve, em uma frase."},
            "upstream": {
                "type": "object",
                "description": "A resposta do banco, como veio.",
                "properties": {
                    "status": {"type": "integer", "description": "Status HTTP do banco."},
                    "url": {"type": "string", "description": "Endpoint do banco chamado."},
                    "body": {"description": "Corpo do banco (JSON, ou texto truncado em 500)."},
                },
            },
        },
        "required": ["detail"],
    },
}


def _resposta(descricao: str, schema: str = _ERRO_UPSTREAM) -> dict:
    return {"description": descricao,
            "content": {"application/json": {
                "schema": {"$ref": f"#/components/schemas/{schema}"}}}}


# Ordem e texto seguem a tabela de `ERRO_UPSTREAM` — se um mudar, o outro tem de
# mudar junto, e ficam lado a lado para que a divergência salte aos olhos.
_RESPOSTAS_DO_BANCO: dict[str, dict] = {
    "404": _resposta("Recurso não encontrado no banco."),
    "409": _resposta(
        "Conflito no banco: já existe, ou o estado não permite. Inclui o **registro "
        "assíncrono na CIP ainda em curso** (`ProcessamentoPendente`) — nesse caso "
        "é transitório e a mesma chamada funciona em instantes."),
    "424": _resposta(
        "Credenciais: ausentes no cofre para o par tenant/**banco** (a credencial é "
        "da instituição, não do caminho), ou rejeitadas "
        "pelo banco. Todo erro no endpoint de **token** responde `424`, qualquer "
        "que seja o status do banco — o Inter, por exemplo, devolve `400` para "
        "`client_credentials` inválido, e chamar aquilo de payload inválido manda "
        "procurar defeito no lugar errado."),
    "429": _resposta(
        "Limite de requisições do banco atingido. O `Retry-After` é repassado "
        "quando o banco o envia."),
    "502": _resposta("Falha do banco (`5xx` ou status não mapeado) — re-tentar com backoff."),
    "504": _resposta("Banco indisponível ou tempo esgotado (rede/timeout)."),
}

# Tags cujas rotas realmente saem para o banco. As de fora respondem sem cruzar a
# rede: `bancos` é introspecção do código, `credenciais` só cifra e guarda,
# `health` é sonda — e `webhooks` é ENTRADA do banco, não chamada a ele.
_TAGS_QUE_FALAM_COM_O_BANCO = {
    "cobranca", "carne", "pix", "bolepix", "checkout", "pix-automatico",
    "conciliacao", "extrato", "config", "jobs",
}

# O `422` gerado pelo FastAPI cobre só a validação do corpo. A mesma faixa carrega
# outros dois casos, de corpos diferentes, e omiti-los faz o integrador tratar
# `422` como "erro meu de schema" quando pode ser o banco ou o catálogo.
_422_AMPLIADO = (
    "Três origens, distinguíveis pelo corpo:\n\n"
    "1. **Validação do contrato** (`detail` em lista) — o corpo ou a query não "
    "batem com o schema;\n"
    "2. **Capacidade ausente** (`detail` em texto) — o banco não oferece a "
    "operação; a mensagem diz para onde ir. Confira em `GET /bancos`;\n"
    "3. **O banco recusou os dados** (`400`/`422`/`405` no upstream) — traz "
    "`upstream` com a resposta original. Re-tentar igual não resolve."
)


# O token `bapi_` não aparece na assinatura das rotas (as credenciais são
# resolvidas na dependência, e o header é só UM dos três caminhos). Sem declarar
# aqui, o Swagger não mostra o botão **Authorize** — e quem clica em "Try it out"
# numa rota de banco não tem onde colar o token.
_SEGURANCA = "TokenBapi"
_ESQUEMA_SEGURANCA = {
    _SEGURANCA: {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "bapi_",
        "description": (
            "Token opaco devolvido por `POST /credenciais` — `Authorization: "
            "Bearer bapi_...`.\n\n"
            "**É opcional**, e a spec diz isso: as credenciais do banco podem vir "
            "no corpo (`credentials`), no header `X-Bank-Credentials` ou do cofre "
            "do servidor (`VAULT__<tenant>__<banco>__*` — a chave é o banco, não o "
            "caminho). Sem nenhuma das três, "
            "a rota responde `424`."
        ),
    }
}
# `{}` na lista = "também funciona sem" — declarar só o esquema diria que o token
# é obrigatório, o que seria mentira nas outras duas formas de credencial.
_SEGURANCA_OPCIONAL = [{}, {_SEGURANCA: []}]


def _openapi_enriquecido() -> dict:
    """Acrescenta à spec o que o FastAPI não tem como saber sozinho."""
    schema = _openapi_original()
    schema["externalDocs"] = {
        "description": "Documentação do projeto (guias por banco, roadmap, testes)",
        "url": _DOC_REPO,
    }
    schema.setdefault("components", {}).setdefault("schemas", {}).update(_SCHEMAS_DE_ERRO)
    schema["components"].setdefault("securitySchemes", {}).update(_ESQUEMA_SEGURANCA)

    for operacoes in schema["paths"].values():
        for operacao in operacoes.values():
            if not isinstance(operacao, dict):
                continue
            respostas = operacao.setdefault("responses", {})
            tags = set(operacao.get("tags") or ())
            if tags & _TAGS_QUE_FALAM_COM_O_BANCO:
                for status, corpo in _RESPOSTAS_DO_BANCO.items():
                    respostas.setdefault(status, corpo)
                if "422" in respostas:
                    respostas["422"]["description"] = _422_AMPLIADO
                operacao.setdefault("security", _SEGURANCA_OPCIONAL)
            if tags & {"credenciais", "webhooks"}:
                respostas.setdefault("401", _resposta(
                    "Token inválido, revogado ou de outro tenant.", _ERRO_SIMPLES))
    return schema


app.openapi = _openapi_enriquecido

app.include_router(bancos.router)
app.include_router(credenciais.router)
app.include_router(cobranca.router)
app.include_router(carne.router)
app.include_router(jobs.router)
app.include_router(pix.router)
app.include_router(bolepix.router)
app.include_router(checkout.router)
app.include_router(conciliacao.router)
app.include_router(extrato.router)
app.include_router(pix_automatico.router)
app.include_router(webhook_banco.router)
app.include_router(webhook_banco.pix_router)
app.include_router(webhooks.router)
# Catch-all /api/* por último (convenção; rotas tipadas ficam na raiz, sem colisão).
app.include_router(offline.router)


@app.exception_handler(CaminhoInvalido)
async def _caminho_invalido(request: Request, exc: CaminhoInvalido) -> JSONResponse:
    """Combinação caminho×banco que não existe → 422 dizendo o que existe.

    Um handler só, e não `try/except` em cada rota: a regra é do roteamento, e
    espalhá-la garantiria que uma rota nova nascesse sem ela — que é como o erro
    vira 500 em produção.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ProcessamentoPendente)
async def _processamento_pendente(request: Request, exc: ProcessamentoPendente) -> JSONResponse:
    # Registro assincrono na CIP ainda em curso — o chamador re-tenta.
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# Tradução do erro do BANCO para o erro do CHAMADOR.
#
# Antes só existiam dois destinos: 401/403 -> 424 e TODO O RESTO -> 502. Isso
# jogava erro do chamador na faixa 5xx: quem mandava payload que o banco recusa
# (400/422) ou pedia recurso inexistente (404) recebia "bad gateway", que diz
# "o upstream falhou" e manda re-tentar -- quando re-tentar igual nunca ia dar
# certo. A regra passa a ser: erro que o chamador conserta responde 4xx; erro do
# banco ou da rede continua 5xx.
#
# O corpo e o status do banco vao em `upstream` em TODOS os casos: traduzir a
# faixa nao pode custar o diagnostico.
ERRO_UPSTREAM: dict[int, tuple[int, str]] = {
    400: (422, "o banco recusou os dados enviados"),
    422: (422, "o banco recusou os dados enviados"),
    401: (424, "credenciais do banco rejeitadas (401/403 no upstream)"),
    403: (424, "credenciais do banco rejeitadas (401/403 no upstream)"),
    404: (404, "recurso não encontrado no banco"),
    405: (422, "operação não suportada pelo banco para este recurso"),
    409: (409, "conflito no banco (registro já existe ou estado não permite)"),
    429: (429, "limite de requisições do banco atingido"),
}


def _eh_endpoint_de_token(url: str) -> bool:
    """Reconhece a URL de autenticação dos providers pelo sufixo do caminho.

    Casar por sufixo e não por host mantém isto válido quando a base muda entre
    sandbox e produção — que é justamente quando o erro aparece.
    """
    caminho = url.split("?", 1)[0].rstrip("/")
    return caminho.endswith(("/token", "/auth", "/oauth/v2/token", "/v1/auth"))


@app.exception_handler(httpx.HTTPStatusError)
async def _erro_do_banco(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """Erro HTTP vindo do BANCO (upstream) — nunca 500 genérico.

    Ver ERRO_UPSTREAM: o que o chamador conserta vira 4xx; 5xx do banco e
    status não mapeado seguem 502 (bad gateway).
    """
    upstream = exc.response.status_code
    try:
        detalhe = exc.response.json()
    except ValueError:
        detalhe = (exc.response.text or "")[:500]
    status, mensagem = ERRO_UPSTREAM.get(upstream, (502, "erro na API do banco"))
    # Erro no endpoint de TOKEN é sempre credencial, qualquer que seja o status.
    # O Inter devolve 400 para client_credentials inválido, e o mapa acima o
    # traduzia como "o banco recusou os dados enviados" — mandando quem integra
    # caçar defeito no payload quando o problema é a credencial.
    if _eh_endpoint_de_token(str(exc.request.url)):
        status, mensagem = 424, "credenciais do banco rejeitadas na autenticação"
    resposta = JSONResponse(status_code=status, content={
        "detail": mensagem,
        "upstream": {"status": upstream, "url": str(exc.request.url), "body": detalhe},
    })
    # 429 sem Retry-After obriga o chamador a chutar o intervalo do backoff.
    if status == 429 and exc.response.headers.get("retry-after"):
        resposta.headers["Retry-After"] = exc.response.headers["retry-after"]
    return resposta


@app.exception_handler(httpx.RequestError)
async def _banco_indisponivel(request: Request, exc: httpx.RequestError) -> JSONResponse:
    """Falha de rede/timeout com o banco → 504, não 500."""
    return JSONResponse(status_code=504, content={
        "detail": "banco indisponível ou tempo esgotado",
        "upstream": {"url": str(exc.request.url) if exc.request else None,
                      "erro": type(exc).__name__},
    })


@app.exception_handler(CredentialNotFound)
async def _credential_not_found(request: Request, exc: CredentialNotFound) -> JSONResponse:
    # Tenant/banco não provisionado no cofre — erro de configuração, não 500.
    return JSONResponse(
        status_code=424,
        content={"detail": "credenciais do tenant/banco ausentes no cofre"},
    )


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    """Swagger UI do gateway com a identidade visual da plataforma."""
    return HTMLResponse(pagina_swagger(
        titulo="Cobranca-API — Gateway (Swagger)",
        superficie="Gateway REST · multi-banco",
        pill="3 bancos ON · 18 OFF",
        detalhe=f"v{app.version} · C6 · Sicoob · Inter · Pix BACEN",
        links=[("GitHub", "https://github.com/Maxwbh/cobranca-api", False),
               ("Offline / pyCobrança →", "/api/docs", True)],
        spec_url="/openapi.json",
    ))


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Sonda de disponibilidade do gateway (não toca nos bancos)."""
    return {"status": "ok"}
