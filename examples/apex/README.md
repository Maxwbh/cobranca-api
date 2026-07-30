# Oracle APEX — emissão de boletos e lotes

Páginas APEX que consomem a **Cobranca-API** via `APEX_WEB_SERVICE` — sem
dependência externa, sem PL/SQL de baixo nível e sem travar a sessão.

## Arquivos

| Arquivo | O quê |
|---|---|
| [`apex_boleto.sql`](./apex_boleto.sql) | Página de emissão: process On Submit, **download do PDF** e **preview em iframe** |
| [`apex_lote_job.sql`](./apex_lote_job.sql) | Fechamento em **lote**: cria o job, AJAX Callback de progresso, report de itens e botão "baixar zip" |
| [`../oracle/`](../oracle/) | Pacote PL/SQL `COBRANCA_API` (para uso fora do APEX) e setup de ACL |

## Setup (5 minutos)

1. **ACL de rede** — ver [`../oracle/acl_setup.sql`](../oracle/acl_setup.sql).
   No **Autonomous Database** a wallet já vem pronta; basta a ACL do host.
2. **Application Item** `G_COBRANCA_API_URL` = `https://boleto-cnab-api.onrender.com`
   (e `G_TENANT_ID` se for usar as rotas online/lote).
3. Cole os blocos dos arquivos nos Processes/Regions indicados nos comentários.

## Página 1 — emitir boleto (`apex_boleto.sql`)

| Componente | Tipo | O que faz |
|---|---|---|
| Process `EMITIR` | On Submit → PL/SQL | Chama `/api/boleto/data` (linha digitável) e `/api/boleto` (PDF via `make_rest_request_b`), grava o BLOB |
| Application Process `BAIXAR_BOLETO` | On Demand | Serve o PDF com `WPG_DOCLOAD.download_file` |
| Region "Preview" | PL/SQL Dynamic Content | `<iframe>` apontando para o Application Process |

Os itens de página esperados (`P10_AGENCIA`, `P10_CONTA`, …) estão nomeados no
próprio script — renomeie conforme a sua aplicação.

## Página 2 — lote assíncrono (`apex_lote_job.sql`)

O padrão importante aqui: **não bloquear a sessão do APEX**. A página cria o
job (resposta em ~1s, HTTP **202**) e um **Dynamic Action com timer** consulta o
progresso:

```
[Botão Emitir] → Process cria o job → :P20_JOB_ID
        ↓
[Dynamic Action: timer 3s] → AJAX Callback ATUALIZAR_JOB → {status, completed, failed}
        ↓
[Report de itens]  +  [Botão "Baixar todos" → zip consolidado]
```

Detalhes que evitam retrabalho:

- **Idempotência**: o header `Idempotency-Key` (ex.: `apex-202607`) faz o
  reenvio devolver **o mesmo job** — proteção contra duplo clique e reprocesso.
- **Falha isolada**: item inválido não derruba o lote; o job termina como
  `partially_completed` e `/items?status=failed` lista só os problemáticos.
- **Sem base64**: os PDFs saem por download (`/artifacts`), com `sha256` no
  manifesto — o JSON não carrega binário.

## Report de itens direto em SQL

Com `JSON_TABLE` dá para exibir os itens do job num Interactive Report comum —
o exemplo está comentado no fim do `apex_lote_job.sql`. Alternativa nativa:
**Web Source Module** apontando para `/jobs/boletos/{job_id}/items`.

## Boas práticas

- Guarde a URL da API num **Application Item**, nunca fixa na página.
- Rotas online (`/cobranca`, `/pix`) exigem o token `bapi_` — guarde em item
  protegido de aplicação, nunca em item de página.
- Para volumes acima de 200 títulos, crie **vários jobs** (o limite é por job).
