from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.vault import CredentialNotFound
from app.providers.c6 import ProcessamentoPendente
from app.routers import (bancos, bolepix, carne, cobranca, conciliacao, credenciais,
                         extrato, jobs, offline, pix, pix_automatico, webhook_banco,
                         webhooks)

# Portais oficiais (linkados nas descrições — o Swagger UI renderiza markdown)
_DOC_C6 = "https://developers.c6bank.com.br"
_DOC_SICOOB = "https://developers.sicoob.com.br/portal/"
_DOC_BACEN_PIX = "https://bacen.github.io/pix-api/"
_DOC_REPO = "https://github.com/Maxwbh/cobranca-api/tree/main/docs/development"

TAGS = [
    {"name": "bancos",
     "description": "Catálogo de bancos, capacidades reais (introspecção) e esquema de credenciais por banco. "
                    f"Catálogo completo de serviços por banco (incl. não implementados): [docs do repositório]({_DOC_REPO})."},
    {"name": "credenciais",
     "description": "Tokenização zero-knowledge: cadastre as credenciais do banco UMA vez e use o token `bapi_` nas demais chamadas. "
                    "O esquema de campos de cada banco está em `GET /bancos`."},
    {"name": "cobranca",
     "description": "Boleto: emitir, consultar, alterar, PDF e baixar — REST (banco) ou offline via pyCobrança, conforme `provider`. "
                    f"Docs oficiais: [C6 Boleto]({_DOC_C6}/apis/bankslip) · [Sicoob Cobrança v3]({_DOC_SICOOB})."},
    {"name": "carne",
     "description": "Carnê 3-vias A4 (registra N parcelas e monta o PDF na engine pyCobrança)."},
    {"name": "pix",
     "description": "Pix BACEN: cob/cobv, revisão, listas, lote e Pix RECEBIDOS (conciliação). Dialeto idêntico em todos os bancos — "
                    f"[spec BACEN]({_DOC_BACEN_PIX}). Docs oficiais: [C6 Pix]({_DOC_C6}/apis/pix) · [Sicoob]({_DOC_SICOOB})."},
    {"name": "bolepix",
     "description": "Boleto híbrido online com QR Pix EVP embutido (exclusivo C6, /v2/bank_slips). "
                    f"Doc oficial: [C6 Bolepix]({_DOC_C6}/apis/bolepix)."},
    {"name": "pix-automatico",
     "description": "Débito recorrente via Pix (BACEN): recorrência, autorização do pagador, cobranças do ciclo e retentativa. "
                    "O agendamento de cada cobrança fica no produto consumidor. "
                    f"Docs: [spec BACEN]({_DOC_BACEN_PIX}) · [C6 Pix Automático]({_DOC_C6}/apis/pix-automatico)."},
    {"name": "conciliacao",
     "description": "Recebíveis e transações C6 Pay (extrato da adquirência). "
                    f"Doc oficial: [C6 Pay statements]({_DOC_C6}/apis/c6pay-statements)."},
    {"name": "extrato",
     "description": "Extrato da conta PJ (C6 /v1/statement; Sicoob conta-corrente v4 — mensal). "
                    f"Docs oficiais: [C6 Extrato]({_DOC_C6}/apis/statement) · [Sicoob]({_DOC_SICOOB})."},
    {"name": "config",
     "description": "Configurações NO banco: URL de webhook (boleto e Pix por chave). "
                    f"Docs oficiais: [C6 Notificações]({_DOC_C6}/apis/notifications) · [webhook Pix BACEN]({_DOC_BACEN_PIX})."},
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
    version="2.0.0",
    docs_url=None,  # /docs customizado abaixo (tema visual da plataforma)
    openapi_tags=TAGS,
    description=(
        "Serviço único de cobrança **100% Python**: gateway multi-banco (C6/Sicoob) + "
        "engine [pyCobrança](https://github.com/Maxwbh/pyCobranca) embutida.\n\n"
        "**Superfície offline (`/api/*`):** boleto/CNAB/OFX sem banco online, gerada "
        "**nativamente** pela pyCobrança no próprio processo (sem sidecar) e sem "
        "autenticação — doc própria em [**Swagger Offline → `/api/docs`**](/api/docs) "
        "([spec](/api/openapi.yaml)).\n\n"
        "**Produto standalone** consumido por múltiplos sistemas; escopo por `tenant_id`.\n\n"
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


def _openapi_com_external_docs() -> dict:
    schema = _openapi_original()
    schema["externalDocs"] = {
        "description": "Documentação do projeto (guias por banco, roadmap, testes)",
        "url": _DOC_REPO,
    }
    return schema


app.openapi = _openapi_com_external_docs

app.include_router(bancos.router)
app.include_router(credenciais.router)
app.include_router(cobranca.router)
app.include_router(carne.router)
app.include_router(jobs.router)
app.include_router(pix.router)
app.include_router(bolepix.router)
app.include_router(conciliacao.router)
app.include_router(extrato.router)
app.include_router(pix_automatico.router)
app.include_router(webhook_banco.router)
app.include_router(webhook_banco.pix_router)
app.include_router(webhooks.router)
# Catch-all /api/* por último (convenção; rotas tipadas ficam na raiz, sem colisão).
app.include_router(offline.router)


@app.exception_handler(ProcessamentoPendente)
async def _processamento_pendente(request: Request, exc: ProcessamentoPendente) -> JSONResponse:
    # Registro assincrono na CIP ainda em curso — o chamador re-tenta.
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPStatusError)
async def _erro_do_banco(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """Erro HTTP vindo do BANCO (upstream) — nunca 500 genérico.

    401/403 do banco = credencial inválida/sem permissão para o produto → 424
    (dependência falhou, o chamador precisa corrigir as credenciais);
    demais status → 502 (bad gateway), preservando status e corpo do banco.
    """
    upstream = exc.response.status_code
    try:
        detalhe = exc.response.json()
    except ValueError:
        detalhe = (exc.response.text or "")[:500]
    status = 424 if upstream in (401, 403) else 502
    return JSONResponse(status_code=status, content={
        "detail": ("credenciais do banco rejeitadas (401/403 no upstream)"
                    if status == 424 else "erro na API do banco"),
        "upstream": {"status": upstream, "url": str(exc.request.url), "body": detalhe},
    })


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
    # Tenant/provider não provisionado no cofre — erro de configuração, não 500.
    return JSONResponse(
        status_code=424,
        content={"detail": "credenciais do tenant/provider ausentes no cofre"},
    )


_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Cobranca-API — Gateway (Swagger)</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <link rel="icon" type="image/png" href="https://unpkg.com/swagger-ui-dist@5/favicon-32x32.png">
  <style>
    /* Tema Tech Innovation: #0F172A grafite · #1E40AF azul · #06B6D4 ciano */
    body { margin: 0; }
    .cob-topbar { background: linear-gradient(120deg, #0F172A 0%, #1E40AF 70%, #3B5A82 100%);
                  padding: 14px 28px; color: #fff; border-bottom: 4px solid #06B6D4;
                  display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
    .cob-topbar h1 { margin: 0; font: 700 20px 'Segoe UI', sans-serif; letter-spacing: .3px; }
    .cob-topbar .surface { color: #06B6D4; font: 600 13px 'Segoe UI', sans-serif;
                           text-transform: uppercase; letter-spacing: 1px; }
    .cob-topbar small { color: #cbd5e1; font: 12px 'Segoe UI', sans-serif; }
    .cob-topbar a { color: #fff; font: 600 13px 'Segoe UI', sans-serif;
                    margin-left: auto; text-decoration: none; border: 1px solid #06B6D4;
                    border-radius: 6px; padding: 5px 12px; }
    .cob-topbar a:hover { background: #06B6D4; color: #0F172A; }
    .swagger-ui .topbar { display: none; }
    .swagger-ui .info .title { color: #0F172A; }
    .swagger-ui .info a { color: #1E40AF; }
    .swagger-ui .btn.authorize, .swagger-ui .btn.authorize svg { color: #1E40AF; fill: #1E40AF; }
    .swagger-ui .btn.authorize { border-color: #1E40AF; }
    .swagger-ui .scheme-container { background: #F8FAFC; box-shadow: none; }
    .swagger-ui .opblock-tag { color: #0F172A; border-bottom: 1px solid #E2E8F0; }
    .cob-topbar .cob-mark { align-self: center; flex: none; }
    .cob-topbar .pill { background: rgba(6,182,212,.15); border: 1px solid #06B6D4;
              color: #a5f3fc; font: 600 11px 'Segoe UI', sans-serif;
              border-radius: 999px; padding: 3px 10px; letter-spacing: .4px; }
    .cob-topbar .links { margin-left: auto; display: flex; gap: 8px; align-self: center; }
    .cob-topbar .links a { margin-left: 0; }
    @media (max-width: 640px) {
      .cob-topbar { padding: 10px 14px; gap: 8px; }
      .cob-topbar h1 { font-size: 17px; }
      .cob-topbar small, .cob-topbar .pill { display: none; }
      .cob-topbar .links { margin-left: 0; width: 100%; }
      .cob-topbar .links a { flex: 1; text-align: center; }
    }
  </style>
</head>
<body>
  <div class="cob-topbar">
    <svg class="cob-mark" width="26" height="26" viewBox="0 0 52 52" aria-hidden="true"><g transform="translate(26,26) rotate(45)"><rect x="-20" y="-20" width="40" height="40" rx="8" fill="none" stroke="#06B6D4" stroke-width="5"/><rect x="-7" y="-7" width="14" height="14" rx="3" fill="#06B6D4"/></g></svg>
    <h1>Cobranca-API</h1>
    <span class="surface">Gateway REST &middot; multi-banco</span>
    <span class="pill">100% Python &middot; FastAPI + pyCobran&ccedil;a</span>
    <small>v__VERSION__ &middot; C6 &middot; Sicoob &middot; Pix BACEN &middot; pyCobrança</small>
    <div class="links">
      <a href="https://github.com/Maxwbh/cobranca-api" target="_blank" rel="noopener">GitHub</a>
      <a href="/api/docs">Offline / pyCobrança &rarr;</a>
    </div>
  </div>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis],
        tryItOutEnabled: true,
        validatorUrl: null,
      });
    };
  </script>
</body>
</html>"""


@app.get("/docs", include_in_schema=False)
def swagger_ui() -> HTMLResponse:
    """Swagger UI do gateway com a identidade visual da plataforma."""
    return HTMLResponse(_SWAGGER_HTML.replace("__VERSION__", app.version))


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Sonda de disponibilidade do gateway (não toca nos bancos)."""
    return {"status": "ok"}
