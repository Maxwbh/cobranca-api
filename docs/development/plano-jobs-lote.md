# Plano — Processamento em Lote e Assíncrono (jobs)

> **Status:** Fases 0 (quick-win), **1 (jobs/BackgroundTasks)**, **2 (artefatos em disco)**
> **3 (CNAB com sublotes)** e **4 (webhook + métricas)** IMPLEMENTADAS; Fase 5 em aberto.
> **Origem:** contrato [pyCobrança doc 12 — Processamento em Lote e Assíncrono](https://github.com/Maxwbh/pyCobranca/blob/main/docs/12-processamento-lote.md),
> que atribui **toda a orquestração assíncrona ao serviço REST** (esta API);
> a engine permanece de domínio puro (sem HTTP, fila ou storage).

---

## 1. Validação do contrato (o que a doc 12 exige × o que temos)

| Exigência | Estado |
|---|:--:|
| Divisão engine × serviço (regra bancária na pyCobrança; HTTP/auth/tenant aqui) | ✅ |
| Engine testável sem infraestrutura | ✅ (117 testes, sem rede) |
| Erros determinísticos por item | ✅ `DadosInvalidos` → `validation_errors` |
| **Falha de um item não cancela o lote** | ✅ **quick-win (§2)** |
| Limite de tamanho do lote | ✅ **quick-win** (`LOTE_MAX_ITENS`, default 200 → 413) |
| Agrupamento CNAB determinístico | ✅ **Fase 3** (`agrupar_sublotes` — função pura por banco/layout/convênio/carteira/conta/agência/variação/pix; 1 arquivo por sublote) |
| Não devolver base64 em lote | ✅ jobs entregam **referências** (href/hash); base64 só no `/api/boleto/multi` síncrono via `include_data` |
| `202 Accepted` + `job_id` | ✅ **Fase 1** |
| Endpoints `/jobs/*` | ✅ boletos + artifacts + **CNAB remessas** (Fases 1–3); `/jobs/cnab/retornos` fica para depois |
| Estados de job/item, tentativas | ✅ **Fase 1** (job: received→processing→completed\|partially_completed\|failed; item: pending→completed\|failed) |
| Idempotência (`idempotency_key`, `external_id`) | ✅ **Fase 1** (`Idempotency-Key` por tenant devolve o mesmo job; `external_id` = `item_id`) |
| Manifesto + artefatos (zip, hash, expiração) | ✅ **Fase 2** (`/artifacts`, `sha256`, `bytes`, `expira_em`, zip com PDFs+manifesto+erros) |
| Webhook de conclusão | ✅ **Fase 4** (push HMAC ao consumidor do tenant, mesmo canal dos eventos de banco) |
| Métricas por job | ✅ **Fase 4** (`duracao_ms`, `ms_por_item` no job e no evento) |
| Concorrência/filas separadas, timeout por item | ❌ (Fase 5) |

## 2. Quick-win entregue (síncrono resiliente)

`POST /api/boleto/multi` deixou de ser tudo-ou-nada:

- Cada item vira registro com `item_id` (de `external_id`/`seu_numero`/
  `numero_documento`/índice), `status` (`completed`|`failed`) e `errors`.
- O PDF sai com os itens válidos; falhas vão em `X-Boletos-Failed`,
  `X-Boletos-Errors` e `X-Batch-Status: partially_completed`
  (`include_data=true` devolve `{status, total, completed, failed, boletos, erros}`).
- **400 apenas quando nenhum item é válido**; **413** acima de `LOTE_MAX_ITENS` (200).

Cobre a faixa até ~200 itens sem infraestrutura nova. **Acima disso** (ou com
PDF pesado/carnê longo) vale a camada de jobs abaixo.

## 3. Arquitetura proposta (jobs)

```
POST /jobs/boletos ──► valida envelope ──► 202 {job_id}
                            │
                            ▼  (worker)
                    [fila de jobs]───► itens ──► engine pyCobrança
                            │                        │
                            ▼                        ▼
                    estado + manifesto        artefatos (PDF/CNAB)
                            │                        │
   GET /jobs/.../items ◄────┘        GET /jobs/.../artifacts ◄──┘
                            └────► webhook de conclusão (HMAC, como hoje)
```

**Princípio:** mesma engine, mesmos contratos de item — o job só orquestra.

### 3.1 Endpoints (conforme doc 12)

| Método | Path | Retorno |
|---|---|---|
| POST | `/jobs/boletos` | 202 `{job_id, recebidos, status, self}` |
| GET | `/jobs/boletos/{job_id}` | estado + contadores + manifesto resumido |
| GET | `/jobs/boletos/{job_id}/items` | itens paginados (filtro por `status`) |
| GET | `/jobs/boletos/{job_id}/items/{item_id}` | item + erros + artefato |
| GET | `/jobs/boletos/{job_id}/artifacts` | manifesto de artefatos (PDF/zip, hash, tamanho, expiração) |
| POST | `/jobs/cnab/remessas` · GET `{job_id}` · GET `{job_id}/files` | remessa em lote com **sublotes** |
| POST | `/jobs/cnab/retornos` · GET `{job_id}` | parsing de retorno em lote |

### 3.2 Estados

Job: `received → validating → processing → completed | partially_completed | failed`
Item: `pending → validating → rendering → completed | failed | skipped`

### 3.3 Persistência

Reaproveita o backend já existente do cofre (`core/credential_store.py`):
**Postgres/Supabase quando `SUPABASE_DB_URL`/`DATABASE_URL` existir, senão SQLite**
— mesmo schema isolado (`boleto_api`). Tabelas: `job`, `job_item`, `job_artifact`.
Escopo por `tenant_id` (idem às demais rotas) e auth pelo token `bapi_`.

### 3.4 Execução

- **Fase A (sem dependência nova):** `BackgroundTasks` do FastAPI + trava por
  job no banco. Atende o free tier e não exige Redis.
- **Fase B (escala):** worker externo (RQ/Celery/arq) com **fila separada para
  PDF** (CPU-intensivo), limites por tenant e retry com backoff só para falhas
  transitórias. A interface REST não muda entre A e B.

### 3.5 Artefatos

PDF por item + consolidado `.zip` (PDFs + `manifest.json` + `errors.json`),
com `sha256`, tamanho e expiração. Storage plugável: disco (`/app/data/jobs`,
já é volume gravável) na Fase A; S3/GCS compatível na Fase B — **nunca base64
no JSON de lote**, conforme a doc 12.

### 3.6 Idempotência

- Header `Idempotency-Key` por tenant → job já existente é retornado (não recria).
- `external_id` por item → dedupe dentro do job e chave de reprocessamento.
- Reprocessar = nova tentativa do item, preservando histórico.

### 3.7 CNAB — sublotes determinísticos

`POST /jobs/cnab/remessas` agrupa por **(banco, layout, convênio, carteira,
conta)**; cada grupo vira um arquivo; nunca mistura incompatíveis; valida
header/trailer antes de publicar; permite reprocessar só o sublote com erro.
(A separação hoje inexistente vira função pura em `core/pycob.py`, testável.)

## 4. Fases de entrega

| Fase | Escopo | Depende de |
|---|---|---|
| **0 — feito** | Lote síncrono resiliente + limite (§2) | — |
| **1** | `/jobs/boletos` (POST/GET/items) com BackgroundTasks + persistência + estados + idempotência | nada novo |
| **2 — feito** | Artefatos (PDF por item + zip + manifesto/hashes/expiração) e `/artifacts` | disco (`ARTIFACT_DIR`) |
| **3 — feito** | `/jobs/cnab/remessas` com sublotes determinísticos + `/files` + download | Fase 1 |
| **4 — feito** | Webhook de conclusão (push HMAC existente) + métricas por job | Fase 1 |
| **5** | Worker externo + filas separadas + limites por tenant | Redis/serviço pago |

## 5. Critérios de aceite

- [x] `POST /jobs/boletos` responde **202** com `job_id` (processamento em background)
- [x] Item inválido não derruba o job → `partially_completed`
- [x] `Idempotency-Key` repetida devolve o **mesmo** `job_id`
- [x] Estado persistido sobrevive a nova instância do store (teste dedicado)
- [x] Isolamento por `tenant_id` (job de outro tenant → 404)
- [x] Manifesto com `sha256` e tamanho por artefato; download não usa base64
- [x] CNAB: títulos de bancos/carteiras/convênios diferentes geram **arquivos separados**
- [x] Cobertura: 9 testes de jobs (estado, idempotência, tenant, limites) + BC-068..073 na coleção Postman

## 6. Decisões em aberto

| # | Decisão | Opções |
|---|---|---|
| 1 | Escopo da 1ª entrega | (a) só Fase 1 (boletos) · (b) Fases 1+3 (boletos e CNAB juntos) |
| 2 | Execução | (a) BackgroundTasks (sem infra, cabe no free tier) · (b) já ir para worker externo |
| 3 | Storage de artefatos | (a) disco do container (efêmero no Render) · (b) S3/Supabase Storage desde o início |
| 4 | Limite síncrono | manter 200 no `/api/boleto/multi` ou baixar (ex. 50) e empurrar o resto para jobs |


---

## 7. Fase 1 — o que ficou implementado

| Endpoint | Comportamento |
|---|---|
| `POST /jobs/boletos` | **202** `{job_id, status: received, recebidos, self, items}`; **413** acima de `JOB_MAX_ITENS` (200); **422** sem `tenant_id`/`boletos`; com `Idempotency-Key` repetida → **200** com o mesmo `job_id` e `idempotent_replay: true` |
| `GET /jobs/boletos/{job_id}?tenant_id=` | estado + `total`/`completed`/`failed` + timestamps + `meta` |
| `GET /jobs/boletos/{job_id}/items` | itens paginados (`limite`≤500, `offset`), filtro `status` |
| `GET /jobs/boletos/{job_id}/items/{item_id}` | item + resultado (dados do boleto) ou `errors` |

- **Execução:** `BackgroundTasks` do FastAPI — sem Redis/worker externo, cabe no free tier.
- **Persistência:** `core/job_store.py` — Postgres/Supabase (schema `boleto_api`) se houver
  DSN, senão SQLite (`JOB_DB_PATH`, default = mesmo arquivo do cofre).
## 8. Fase 2 — artefatos em disco

| Endpoint | Retorno |
|---|---|
| `GET /jobs/boletos/{job_id}/artifacts` | manifesto: `arquivos[]` (nome, `bytes`, `sha256`, `href`), `consolidado` (zip), `expira_em`, `retencao_dias`; **410** se expirado; **404** enquanto o job processa |
| `GET /jobs/boletos/{job_id}/artifacts/items/{nome}.pdf` | PDF do item |
| `GET /jobs/boletos/{job_id}/artifacts/{nome}.zip\|manifest.json\|errors.json` | consolidado / manifesto / relatório de erros |

- **Layout:** `ARTIFACT_DIR/<job_id>/{items/*.pdf, manifest.json, errors.json, boletos-<job_id>.zip}`
  (default `/app/data/jobs`, `ARTIFACT_TTL_DIAS=7`).
- **Segurança:** nomes sanitizados + verificação de contenção do path
  (path traversal → 404) e isolamento por `tenant_id` em todas as rotas.
- **Efemeridade (Render free):** o disco some a cada deploy — a retenção é
  curta e o consumidor deve baixar logo após a conclusão. Storage remoto
  (S3/Supabase) fica para a Fase 5 (decisão §6.3 em aberto).
- **Fase 3 (próxima):** `/jobs/cnab/remessas` com sublotes determinísticos.


## 9. Fase 3 — CNAB em lote com sublotes

| Endpoint | Retorno |
|---|---|
| `POST /jobs/cnab/remessas` | **202** `{job_id, titulos, sublotes[{sublote_id, chave, quantidade}], self, files}`; 413/422 e `Idempotency-Key` como nos boletos |
| `GET /jobs/cnab/remessas/{job_id}` | estado + `sublotes`/`completed`/`failed` |
| `GET /jobs/cnab/remessas/{job_id}/files` | manifesto: 1 arquivo por sublote com `nome`, `bytes`, `sha256`, `registros`, `chave` + `consolidado` (zip) e `total_registros` |
| `GET /jobs/cnab/remessas/{job_id}/files/{nome}` | download do `.rem`, do `.zip` ou do manifesto |

- **Agrupamento** (`core/pycob.agrupar_sublotes`, função pura): chave =
  (banco, layout, convênio, carteira, conta, agência, variação, pix).
  **Nunca mistura incompatíveis**; determinístico (teste dedicado).
- **Falha isolada:** sublote inválido não derruba o job → `partially_completed`;
  os demais arquivos ficam disponíveis (permite reprocessar só o que falhou).
- **Auditoria:** cada `.rem` é gravado imutável em `ARTIFACT_DIR/<job_id>/files/`,
  com `sha256` e contagem de registros no manifesto.
- **Pendente:** `/jobs/cnab/retornos` (parsing de retorno em lote) — mesmo
  padrão, entra quando houver demanda real.


## 10. Fase 4 — webhook de conclusão e métricas

**Push de conclusão** (mesmo canal dos eventos de banco — `forwarder` + `subscriptions`):
ao terminar o job, o serviço envia `POST` assinado em `X-Signature: sha256=…`
ao consumidor **dono do tenant** (`SUB__<tenant>__URL/SECRET`, com fallback
global `EVENT_WEBHOOK_URL/SECRET`). Sem callback configurado → **no-op**.

```json
{
  "event": "job.boletos.partially_completed",
  "job_id": "job_...", "tenant_id": "empresa1", "tipo": "boletos",
  "status": "partially_completed", "total": 2, "completed": 1, "failed": 1,
  "duracao_ms": 812,
  "self": "/jobs/boletos/job_...",
  "artifacts": {"arquivos": 1, "consolidado": "/jobs/.../boletos-job_....zip",
                 "expira_em": "..."}
}
```

Eventos: `job.boletos.<status>` e `job.cnab_remessas.<status>`
(`completed` | `partially_completed` | `failed`).

**Métricas por job** (`duracao_ms`, `ms_por_item`) persistidas em `meta.metricas`
e expostas no `GET` do job e no próprio evento.

**Garantia:** falha no push (consumidor fora do ar) **não altera o estado do
job** — é capturada e ignorada, com teste dedicado. Retry/DLQ fica para a Fase 5.
