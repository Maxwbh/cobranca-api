# Processamento em Lote e Assíncrono (jobs)

> **Status:** implementado — lote síncrono resiliente, `/jobs/boletos`,
> artefatos em disco, `/jobs/cnab/remessas` com sublotes, webhook de conclusão e
> métricas. Falta a **Fase 5** (worker externo), no fim desta página.
> **Origem:** contrato [pyCobrança doc 12 — Processamento em Lote e Assíncrono](https://github.com/Maxwbh/pyCobranca/blob/455f60ce356db9e6ba8212653ee0d146cebaed62/docs/12-processamento-lote.md),
> que atribui **toda a orquestração assíncrona ao serviço REST** (esta API);
> a engine permanece de domínio puro (sem HTTP, fila ou storage).
> A pyCobrança removeu essa página — a orquestração nunca foi dela, e o que
> sobrou virou [19 — Integração](https://github.com/Maxwbh/pyCobranca/blob/main/docs/19-integracao.md)
> e [20 — Superfície pública](https://github.com/Maxwbh/pyCobranca/blob/main/docs/20-superficie-publica.md).
> O link acima é permanente (aponta para o commit em que a página existia), e
> **este documento passa a ser a referência do contrato** para esta API.
>
> Este documento já foi o plano de entrega, com uma seção por fase. As fases
> viraram código e o relato delas saiu: o que fica é o **contrato** e a
> **superfície**, que é o que o `ARCHITECTURE.md` e o próprio código apontam
> daqui.

## 1. O contrato da doc 12 × o que temos

| Exigência | Estado |
|---|:--:|
| Divisão engine × serviço (regra bancária na pyCobrança; HTTP/auth/tenant aqui) | ✅ |
| Engine testável sem infraestrutura | ✅ (117 testes, sem rede) |
| Erros determinísticos por item | ✅ `DadosInvalidos` → `validation_errors` |
| **Falha de um item não cancela o lote** | ✅ |
| Limite de tamanho do lote | ✅ `LOTE_MAX_ITENS` / `JOB_MAX_ITENS`, default 200 → **413** |
| Agrupamento CNAB determinístico | ✅ `agrupar_sublotes` — função pura; 1 arquivo por sublote |
| Não devolver base64 em lote | ✅ jobs entregam **referências** (href/hash); base64 só no `/api/boleto/multi` síncrono via `include_data` |
| `202 Accepted` + `job_id` | ✅ |
| Estados de job/item, tentativas | ✅ job: `received`→`processing`→`completed`\|`partially_completed`\|`failed`; item: `pending`→`completed`\|`failed` |
| Idempotência (`idempotency_key`, `external_id`) | ✅ `Idempotency-Key` por tenant devolve o mesmo job; `external_id` = `item_id` |
| Manifesto + artefatos (zip, hash, expiração) | ✅ `/artifacts`, `sha256`, `bytes`, `expira_em` |
| Webhook de conclusão | ✅ push HMAC ao consumidor do tenant, mesmo canal dos eventos de banco |
| Métricas por job | ✅ `duracao_ms`, `ms_por_item` no job e no evento |
| Concorrência/filas separadas, timeout por item | ❌ **Fase 5** |

## 2. Desenho

```
POST /jobs/boletos ──► valida envelope ──► 202 {job_id}
                            │
                            ▼  (BackgroundTasks)
                    [fila de jobs]───► itens ──► engine pyCobrança
                            │                        │
                            ▼                        ▼
                    estado + manifesto        artefatos (PDF/CNAB)
                            │                        │
   GET /jobs/.../items ◄────┘        GET /jobs/.../artifacts ◄──┘
                            └────► webhook de conclusão (HMAC)
```

**Princípio:** mesma engine, mesmos contratos de item — o job só orquestra.

**Execução:** `BackgroundTasks` do FastAPI, sem Redis nem worker externo (cabe
no free tier). **Persistência:** `core/job_store.py` — Postgres/Supabase (schema
`boleto_api`) se houver DSN, senão SQLite (`JOB_DB_PATH`, default = o mesmo
arquivo do cofre).

## 3. Antes dos jobs: o lote síncrono resiliente

`POST /api/boleto/multi` não é tudo-ou-nada:

- cada item vira registro com `item_id` (de `external_id`/`seu_numero`/
  `numero_documento`/índice), `status` (`completed`\|`failed`) e `errors`;
- o PDF sai com os itens válidos; as falhas vão em `X-Boletos-Failed`,
  `X-Boletos-Errors` e `X-Batch-Status: partially_completed`
  (`include_data=true` devolve `{status, total, completed, failed, boletos, erros}`);
- **400 só quando nenhum item é válido**; **413** acima de `LOTE_MAX_ITENS`.

Cobre até ~200 itens sem infraestrutura nova. Acima disso — ou com PDF pesado e
carnê longo — é a camada de jobs. Números medidos em
[`scripts/README.md`](https://github.com/Maxwbh/cobranca-api/blob/main/scripts/README.md#benchmark_lotepy--tempo-de-resposta-do-lote-offline).

## 4. Superfície

### Boletos

| Endpoint | Comportamento |
|---|---|
| `POST /jobs/boletos` | **202** `{job_id, status: received, recebidos, self, items}`; **413** acima de `JOB_MAX_ITENS`; **422** sem `tenant_id`/`boletos`; `Idempotency-Key` repetida → **200** com o mesmo `job_id` e `idempotent_replay: true` |
| `GET /jobs/boletos/{job_id}?tenant_id=` | estado + `total`/`completed`/`failed` + timestamps + `meta` |
| `GET /jobs/boletos/{job_id}/items` | itens paginados (`limite`≤500, `offset`), filtro `status` |
| `GET /jobs/boletos/{job_id}/items/{item_id}` | item + resultado (dados do boleto) ou `errors` |
| `GET /jobs/boletos/{job_id}/artifacts` | manifesto: `arquivos[]` (nome, `bytes`, `sha256`, `href`), `consolidado` (zip), `expira_em`, `retencao_dias`; **410** se expirado; **404** enquanto processa |
| `GET .../artifacts/items/{nome}.pdf` | PDF do item |
| `GET .../artifacts/{nome}.zip\|manifest.json\|errors.json` | consolidado / manifesto / relatório de erros |

### CNAB

| Endpoint | Comportamento |
|---|---|
| `POST /jobs/cnab/remessas` | **202** `{job_id, titulos, sublotes[{sublote_id, chave, quantidade}], self, files}`; 413/422 e `Idempotency-Key` como nos boletos |
| `GET /jobs/cnab/remessas/{job_id}` | estado + `sublotes`/`completed`/`failed` |
| `GET /jobs/cnab/remessas/{job_id}/files` | manifesto: 1 arquivo por sublote (`nome`, `bytes`, `sha256`, `registros`, `chave`) + `consolidado` e `total_registros` |
| `GET /jobs/cnab/remessas/{job_id}/files/{nome}` | download do `.rem`, do `.zip` ou do manifesto |

`/jobs/cnab/retornos` (parsing de retorno em lote) segue **pendente** — mesmo
padrão, entra quando houver demanda real.

## 5. Decisões que continuam valendo

- **Agrupamento CNAB é função pura e determinística.** Chave = (banco, layout,
  convênio, carteira, conta, agência, variação, pix). **Nunca mistura
  incompatíveis** — misturar geraria arquivo que o banco recusa, ou pior, aceita
  errado. Sublote inválido não derruba o job: os demais arquivos ficam
  disponíveis e dá para reprocessar só o que falhou.
- **Artefato é imutável e auditável.** Cada `.rem` é gravado em
  `ARTIFACT_DIR/<job_id>/files/` com `sha256` e contagem de registros.
- **Disco é efêmero no Render.** `ARTIFACT_TTL_DIAS=7` por padrão, e o
  consumidor deve baixar logo após a conclusão; o disco some a cada deploy.
  Storage remoto (S3/Supabase) é Fase 5.
- **Path traversal responde 404**, com nomes sanitizados e verificação de
  contenção; isolamento por `tenant_id` em todas as rotas (job de outro tenant
  → 404).
- **Falha no push não altera o estado do job.** Consumidor fora do ar é
  capturado e ignorado, com teste dedicado — o job continua `completed`. Retry
  e DLQ ficam para a Fase 5.

**Eventos de conclusão:** `job.boletos.<status>` e `job.cnab_remessas.<status>`
(`completed` \| `partially_completed` \| `failed`), assinados em
`X-Signature: sha256=…` para `SUB__<tenant>__URL/SECRET` (fallback global
`EVENT_WEBHOOK_URL/SECRET`). Sem callback configurado → no-op.

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

## 6. Critérios de aceite

- [x] `POST /jobs/boletos` responde **202** com `job_id`
- [x] Item inválido não derruba o job → `partially_completed`
- [x] `Idempotency-Key` repetida devolve o **mesmo** `job_id`
- [x] Estado persistido sobrevive a nova instância do store (teste dedicado)
- [x] Isolamento por `tenant_id` (job de outro tenant → 404)
- [x] Manifesto com `sha256` e tamanho por artefato; download não usa base64
- [x] CNAB: bancos/carteiras/convênios diferentes geram **arquivos separados**
- [x] Cobertura: 9 testes de jobs + `BC-068..073` na coleção Postman

## 7. Fase 5 — o que falta

O que está aberto tem uma coisa em comum: **exige infraestrutura paga**, e por
isso não entrou junto.

| Item | Por que ainda não |
|---|---|
| Worker externo e filas separadas | `BackgroundTasks` morre com o processo; um worker exige Redis ou serviço dedicado |
| Timeout por item | só faz sentido com worker que possa matar a tarefa |
| Limites por tenant (quota, concorrência) | depende de fila para ter o que limitar |
| Retry/DLQ do push de conclusão | hoje a falha é ignorada; a fila de saída já existe para eventos de banco e serviria de base |
| Storage remoto de artefatos (S3/Supabase) | tira a dependência do disco efêmero e permite TTL maior |
