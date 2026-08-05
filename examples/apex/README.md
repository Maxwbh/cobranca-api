# Oracle APEX — boletos, lotes e cartão

Páginas APEX que consomem a **Cobranca-API** via `APEX_WEB_SERVICE` — sem
dependência externa, sem PL/SQL de baixo nível e sem travar a sessão.

## Arquivos

| Arquivo | O quê |
|---|---|
| [`apex_boleto.sql`](./apex_boleto.sql) | Página de emissão: process On Submit, **download do PDF** e **preview em iframe** |
| [`apex_lote_job.sql`](./apex_lote_job.sql) | Fechamento em **lote**: cria o job, AJAX Callback de progresso, report de itens e botão "baixar zip" |
| [`apex_checkout.sql`](./apex_checkout.sql) | **Link de pagamento com cartão** (+ Pix no mesmo link): cria o link, acompanha o status e recebe o webhook em ORDS |
| [`../oracle/`](../oracle/) | Pacote PL/SQL `COBRANCA_API` (para uso fora do APEX) e setup de ACL |

## Setup (5 minutos)

1. **ACL de rede** — ver [`../oracle/acl_setup.sql`](../oracle/acl_setup.sql).
   No **Autonomous Database** a wallet já vem pronta; basta a ACL do host.
2. **Application Item** `G_COBRANCA_API_URL` = `https://SEU-SERVICO.onrender.com`
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

## Página 3 — cartão (`apex_checkout.sql`)

O caso de balcão: cobrar na hora, na tela, sem maquininha. `POST /checkout` com
`pix: true` devolve **um link que aceita cartão e Pix**, e o QR sai do banco.

**Não existe campo de cartão nesta página, de propósito.** O PAN é digitado no
domínio do banco e o escopo PCI-DSS fica lá — pôr o número no APEX trocaria o
assunto de integração para certificação.

| Componente | Tipo | O que faz |
|---|---|---|
| Process `CRIAR_LINK` | On Submit → PL/SQL | `POST /checkout` com `Idempotency-Key`; grava `checkout_id` e `url` na venda |
| Application Process `ATUALIZAR_CHECKOUT` | On Demand | `GET /checkout/{id}` — o Dynamic Action (timer 5s) lê `{status}` |
| Region "Pagar" | PL/SQL Dynamic Content | Botão para a `url` + `div` para o QR |
| Process `CANCELAR` | On Submit → PL/SQL | `DELETE /checkout/{id}` |

O que separa isto de um POST comum:

- **`Idempotency-Key` derivada da venda** (`'venda-' || :P30_VENDA_ID`), não de
  `SYSTIMESTAMP`. Duplo clique em botão de APEX não é hipótese; sem a chave ele
  cria **dois links para a mesma venda**, e nada impede o pagador de pagar os
  dois. Reenvio com a mesma chave devolve o mesmo link, sem tocar no banco.
- **A baixa sai do `liquidado` que o banco devolve**, não do `redirect_url`. O
  retorno traz o navegador de volta; quem confirma pagamento é a consulta.
  Confiar no retorno do browser é confiar no cliente.
- **Desligue o timer quando o status sair de `pendente`** — senão a página fica
  consultando o banco para sempre.

### Tela fechada: webhook em vez de polling

O timer resolve enquanto a tela está aberta. Para o pagador que paga o link três
horas depois, o caminho é o webhook: cadastre com `service: CHECKOUT` em
`POST /config/webhook-banco` e aponte `SUB__<tenant>__URL` para um handler ORDS.
A seção 6 do arquivo traz o handler, e o essencial dele é:

- **valide o `X-Signature` antes de olhar o corpo** — sem isso, quem descobrir a
  URL posta `{"status":"liquidado"}` e baixa a sua venda de graça;
- **`confirmado = true`** significa que o gateway reconsultou o banco e ele
  confirmou. `null` é "ninguém verificou"; trate como aviso, não como baixa;
- **responda 2xx quando processar** — a API re-tenta com backoff enquanto não
  receber 2xx, e a reentrega do mesmo evento já chega deduplicada.

## Report de itens direto em SQL

Com `JSON_TABLE` dá para exibir os itens do job num Interactive Report comum —
o exemplo está comentado no fim do `apex_lote_job.sql`. Alternativa nativa:
**Web Source Module** apontando para `/jobs/boletos/{job_id}/items`.

## Boas práticas

- Guarde a URL da API num **Application Item**, nunca fixa na página.
- Rotas online (`/cobranca`, `/pix`, `/checkout`) exigem o token `bapi_` —
  guarde em item protegido de aplicação, nunca em item de página.
- Para volumes acima de 200 títulos, crie **vários jobs** (o limite é por job).
- Mande `Idempotency-Key` em **todo POST que nasce de um botão**. Vale para
  `/jobs` e para `/checkout`; a chave sai do domínio (competência, venda), nunca
  do relógio.
