# C6 Bank — Integração REST (boleto, Pix, conciliação)

> Implementada no gateway Python (`gateway`), provider `c6`.
> Integração irmã: [sicoob-rest.md](./sicoob-rest.md) — o Pix compartilha o
> mesmo código BACEN (`app/providers/bacen_pix.py`).
> Specs oficiais: seção [Onde baixar a documentação oficial](#onde-baixar-a-documentação-oficial).

## Onde baixar a documentação oficial

> As specs e documentos do C6 **não são versionados aqui** (são material oficial,
> baixável no portal e sujeito a atualização pelo banco). Baixe direto na fonte.

**Portal:** https://developers.c6bank.com.br/ · **Erros:** https://developers.c6bank.com.br/apis/errors

### APIs (OpenAPI / referência)

| Documento | Baixar em |
|---|---|
| Autenticação (mTLS + OAuth) | https://developers.c6bank.com.br/apis/auth |
| Boleto bancário (`/v1/bank_slips`) | https://developers.c6bank.com.br/apis/bankslip |
| Pix (BACEN — `/v2/pix`) | https://developers.c6bank.com.br/apis/pix |
| Bolepix (boleto híbrido — `/v2/bank_slips`) | https://developers.c6bank.com.br/apis/bolepix |
| Pix Automático (`/rec`, `/solicrec`, `/cobr`) | https://developers.c6bank.com.br/apis/pix-automatico |
| Notificações / Webhooks (`/v1/webhooks`) | https://developers.c6bank.com.br/apis/notifications |
| Transações e Recebíveis — C6 Pay (`/v1/c6pay/statement`) | https://developers.c6bank.com.br/apis/c6pay-statements |
| Extrato (`/v1/statement`) | https://developers.c6bank.com.br/apis/statement |
| Checkout — cartão/Pix (`/v1/checkouts`) | https://developers.c6bank.com.br/apis/checkout |
| Agendamento de Pagamentos / DDA | https://developers.c6bank.com.br/apis/schedule-payments |

### Homologação e outros

| Documento | Baixar em |
|---|---|
| **Roteiro de Testes — C6 Developers v3.0** (`.docx`) | https://developers.c6bank.com.br/get-started (etapa 4) · [link direto](https://developers.c6bank.com.br/test-scripts/Roteiro%20de%20Testes%20-%20C6%20Developers%20v3.0.docx) |
| Release Notes | https://developers.c6bank.com.br/ (seção *Release Notes*) |
| Layout CNAB 400 (cobrança) | Portal C6 / gerente da conta (documento de cobrança registrada) |

### Como a integração usa essas specs

O mapeamento contrato-a-contrato (extraído destas specs e **validado no sandbox**)
está documentado em [`../c6-rest.md`](./c6-rest.md). Sequência de integração:
`autenticação → boleto/pix → bolepix → conciliação (C6 Pay) → notificações`.

## Serviços do banco × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).

| ID | Serviço no portal C6 | O que faz | Status | Uso na Cobranca-API |
|---|---|---|:---:|---|
| C6-S01 | Autenticação (mTLS + OAuth) | Token de acesso às APIs | ✅ | Interno (`OAuthMtlsClient`) — transparente p/ o consumidor |
| C6-S02 | Boleto Bancário (`/v1/bank_slips`) | Emitir/consultar/alterar/baixar boleto registrado + PDF | ✅ | `POST/GET/PUT/DELETE /cobranca`, `GET /cobranca/{id}/pdf` |
| C6-S03 | Pix (BACEN `/v2/pix`) | Cob imediata, cobv, lote, revisão, Pix recebidos, devoluções, webhook por chave | ✅ | `/pix/*`, `/config/webhook-pix` |
| C6-S04 | Bolepix (`/v2/bank_slips`) | Boleto híbrido com QR Pix EVP | ✅ | `/bolepix/*` |
| C6-S05 | Pix Automático (`/rec`, `/solicrec`, `/cobr`) | Débito recorrente via Pix | ✅ | `/pix-automatico/*` (agendamento no produto consumidor) |
| C6-S06 | Notificações / Webhooks (`/v1/webhooks`) | Avisos de pagamento/baixa de boleto | ✅ | `/config/webhook-banco` (config) + `POST /webhooks/c6[/{tenant}]` (entrada) |
| C6-S07 | Extrato (`/v1/statement`) | Movimentações da conta PJ | ✅ | `GET /extrato` |
| C6-S08 | Transações e Recebíveis — C6 Pay | Extrato da adquirência (cartão) | ✅ | `GET /conciliacao/recebiveis\|transacoes` |
| C6-S09 | Checkout (cartão/Pix) | Página de pagamento hospedada | ⛔ | Sem previsão (decisão de produto) |
| C6-S10 | Agendamento de Pagamentos / DDA | Pagar contas/boletos (saída de dinheiro) | ⛔ | Fora de escopo — o produto é **cobrança** (entrada), não pagamento |

## Roteamento de provider

| `provider` no request | Caminho |
|---|---|
| `c6` | API REST do C6 (mTLS + OAuth) |
| vazio / omitido / `pycobranca` | engine pyCobrança (CNAB offline, in-process) |

- **Boleto** tem os dois modos. Enquanto `C6_REGISTERED_READY` não for `true`
  (pós-homologação), `provider=c6` **cai automaticamente no CNAB** (fallback).
- **Pix dinâmico** e **conciliação** só existem no REST → `provider=pycobranca`
  nessas rotas responde **422**.

## ⏰ Janela de disponibilidade do sandbox (trava de horário)

> O **sandbox do C6 opera em janela de horário**. Fora dela, o `POST /v1/auth`
> responde **403 Forbidden** — não é credencial inválida nem erro da API.

Como isso aparece na Cobranca-API:

| Camada | Comportamento fora da janela |
|---|---|
| Gateway | `424` com `upstream.status: 403` e a URL do banco (nunca 500) |
| Regressão Postman | Pastas do C6 (cobrança REST, Pix, Bolepix, Pix Automático, extrato, conciliação) tolerando `424` — ver `postman/README.md` |
| Caminho offline (`/api/*`, jobs, CNAB) | **Não afetado** — não depende do banco |

**Ao validar**: rode a regressão dentro da janela de atendimento do sandbox;
fora dela, o resultado esperado é `424` nas rotas online. Confirme o horário
vigente com o time do C6 (varia por ambiente e pode mudar sem aviso).

## Autenticação no banco (mTLS + OAuth)

- **mTLS obrigatório** (certificado do portal, PKCS12) + OAuth
  `client_credentials` em `POST /v1/auth`.
- Sandbox: `https://baas-api-sandbox.c6bank.info` — **seg–sex, 7h–23h**.
- Produção: `https://baas-api.c6bank.info` (exige conta PJ homologada; MEI não).

## Superfície (C6 → gateway)

| Operação | C6 | Endpoint do gateway |
|---|---|---|
| Emitir boleto | `POST /v1/bank_slips/` | `POST /cobranca` |
| Consultar boleto | `GET /v1/bank_slips/{id}` | `GET /cobranca/{id}` |
| PDF do boleto | `GET /{id}` (`base64_pdf_file`) | `GET /cobranca/{id}/pdf` |
| Cancelar boleto | `PUT /v1/bank_slips/{id}/cancel` (204) | `DELETE /cobranca/{id}` |
| Pix cob imediata | `POST /v2/pix/cob` · `PUT /cob/{txid}` | `POST /pix` (txid opcional) |
| Pix cobv (vencimento) | `PUT /v2/pix/cobv/{txid}` | `POST /pix` (com `data_vencimento`) |
| Consultar Pix | `GET /v2/pix/cob{v}/{txid}` | `GET /pix/{txid}[?vencimento=true]` |
| Revisar Pix | `PATCH /v2/pix/cob{v}/{txid}` | `PATCH /pix/{txid}` |
| Listar Pix | `GET /v2/pix/cob{v}?inicio&fim` | `GET /pix` |
| Lote de cobv | `PUT/PATCH/GET /v2/pix/lotecobv/{id}` | `/pix/lote/{id}`, `/pix/lotes` |
| Bolepix (híbrido) | `/v2/bank_slips` (ext_ref 26 chars, Pix EVP) | `POST/GET/DELETE /bolepix` |
| Extrato PJ | `GET /v1/statement/` | `GET /extrato` |
| Alterar boleto | `PUT /v1/bank_slips/{id}` | `PUT /cobranca/{id}` |
| Webhook no banco | `POST/GET/DELETE /v1/webhooks/` | `/config/webhook-banco` |
| Recebíveis | `GET /v1/c6pay/statement/receivables` | `GET /conciliacao/recebiveis` |
| Transações | `GET /v1/c6pay/statement/transactions` | `GET /conciliacao/transacoes` |
| Notificações (status) | webhook do banco | `POST /webhooks/c6[/{tenant}]` |

## Pix Automático, recebidos e webhook por chave (BACEN, compartilhado)

Implementados no dialeto BACEN compartilhado (`bacen_pix.py`) — valem para C6 e
Sicoob: **Pix Automático** (`/pix-automatico/*`: rec, solicrec, locrec, cobr,
retentativa, webhookrec/cobr — o agendamento de cada cobrança fica no produto
consumidor), **Pix recebidos** (`/pix/recebidos`, devoluções) e **webhook por
chave** (`/config/webhook-pix`).

## Particularidades do banco — mapeamentos

**Boleto** (`bank_slip_create_request`): `seu_numero → external_reference_id`
(`^[a-zA-Z0-9]{1,10}$`, único), `valor → amount`, `vencimento → due_date`,
`nosso_numero → our_number` (`^\d{1,10}$`), `pagador → payer{name, tax_id,
address{street, number, city, state, zip_code}}` (endereço obrigatório),
`multa/juros/desconto → fine/interest/discount`. Carteira via `billing_scheme`:
**21 = sandbox, 15 = produção** (env `C6_BILLING_SCHEME` ou `account_config`).

**Status boleto**: `CREATED→registrado`, `PAID→liquidado`, `CANCELLED→baixado`.
**Status Pix (BACEN)**: `ATIVA→registrado`, `CONCLUIDA→liquidado`,
`REMOVIDA_*→baixado`.

## Autenticação da API (token `bapi_`)

Cada banco tem seu **próprio esquema** de credenciais, mas o mecanismo da API é
o mesmo: `POST /credenciais` recebe os parâmetros deste banco, armazena cifrado
(zero-knowledge) e devolve o token `bapi_`; as demais chamadas validam pelo
`Authorization: Bearer bapi_...`. Esquema vigente por banco: `GET /bancos`.

## Credenciais — token (recomendado), no request, ou cofre (fallback)

**1. Tokenização (recomendado)** — cadastre uma vez, use o token:

```
POST /credenciais  {tenant_id, provider, credentials}
  → 201 {"token": "bapi_..."}        # exibido UMA única vez

# demais rotas:
Authorization: Bearer bapi_...

DELETE /credenciais  (com o Bearer)  # revogação imediata
```

Zero-knowledge: as credenciais ficam cifradas (AES-256-GCM) com chave
**derivada do próprio token** (HKDF-SHA256) — o servidor guarda só o SHA-256
do token para lookup e **não consegue decifrar sozinho**; um vazamento do
banco entrega blobs inúteis. Backend: **Postgres/Supabase** se
`SUPABASE_DB_URL` (ou `DATABASE_URL`) estiver no ambiente; senão **SQLite**
local (`CREDENTIAL_DB_PATH`, default `credentials.db`). No Render Free o disco
é efêmero — após um deploy o token retorna 401 e o consumidor recadastra
(1 chamada). Token de outro tenant/provider → 403.

**Supabase — schema próprio, fora do `public`:** a tabela vive em
`boleto_api.credential_tokens` (schema criado automaticamente; nome via
`CREDENTIAL_DB_SCHEMA`). O `public` do Supabase é exposto pela API
auto-gerada (PostgREST) — o schema dedicado mantém as credenciais **fora
dessa superfície**. Não adicione `boleto_api` aos "Exposed schemas" do
PostgREST (Settings → API) e ele fica acessível apenas pela connection
string do banco.

**2. Credenciais no request** (stateless, nada armazenado):

- **POSTs** (`/cobranca`, `/pix`, `/carne`): campo `credentials` no corpo —
  `{"client_id", "client_secret", "pfx_base64", "pfx_password"}`.
- **GET/DELETE** (`/cobranca/{id}`, `/pix/{txid}`, `/conciliacao/*`): header
  `X-Bank-Credentials` com o mesmo JSON codificado em base64.

**3. Cofre no ambiente (fallback)** — usado só quando o request não traz nem
Bearer nem `credentials`:

```
VAULT__<tenant>__c6__client_id
VAULT__<tenant>__c6__client_secret
VAULT__<tenant>__c6__pfx_base64      # certificado mTLS (PKCS12 em base64)
VAULT__<tenant>__c6__pfx_password
```

Chave Pix por conta em `account_config.chave_pix` (ou por cobrança em
`pix.chave`).

## Webhook

O C6 chama a URL cadastrada a cada mudança de status. Cadastre com token:
`https://…/webhooks/c6/<tenant>?token=<segredo>` e configure
`WEBHOOK_TOKEN__C6=<segredo>` (validação em tempo constante; sem a env, aceita
sem validar). O evento normalizado é encaminhado ao consumidor dono do tenant
com HMAC (`X-Signature`), como nos demais bancos.

## Ambiente / envs

| Env | Default | Uso |
|---|---|---|
| `C6_BASE_URL` | `https://baas-api-sandbox.c6bank.info` | trocar p/ produção |
| `C6_AUTH_URL` | `{C6_BASE_URL}/v1/auth` | endpoint OAuth |
| `C6_BILLING_SCHEME` | `21` | carteira (15 em produção) |
| `C6_REGISTERED_READY` | `false` | liga boleto REST (senão CNAB) |
| `C6_PARTNER_NAME` / `C6_PARTNER_VERSION` | `boleto-api` / — | headers `partner-software-*` |
| `WEBHOOK_TOKEN__C6` | — | token do webhook de entrada |

## Testes

- `pytest` (mock): `tests/test_cobranca_c6.py`, `test_pix_c6.py`,
  `test_conciliacao_c6.py`, `test_webhooks.py`.
- E2E sandbox (`tests/test_sandbox_c6.py`): roda só com `C6_SANDBOX_CLIENT_ID`
  / `C6_SANDBOX_CLIENT_SECRET` (+ `C6_SANDBOX_PFX_*`, `C6_SANDBOX_CHAVE_PIX`)
  no ambiente, dentro da janela do sandbox.

## Validado no sandbox real (roteiro v3.0)

- Boleto: emitir (simples/juros+multa/desconto), alterar, consultar, PDF e
  cancelar — o **registro é assíncrono (CIP)**: cancelamentos no intervalo
  respondem 400/422; o provider re-tenta (`C6_CIP_RETRIES`/`C6_CIP_WAIT_SECONDS`)
  e devolve **409** se seguir pendente.
- Pix: cob (com/sem txid), cobv, PATCH de revisão, consultas e listas —
  ✔ confirmado: `pixCopiaECola` **vem no corpo** da resposta.
- Bolepix: criar (idempotente por `external_reference_id`), consultar, PDF.
- Extrato, recebíveis/transações e cadastro de webhook no banco.
- Indisponível no sandbox à época: `lotecobv` (502 do lado do banco).

## Pendências

1. Mecanismo de autenticidade do webhook (hoje: token na URL).
2. Shape fino de `receivables/transactions` (tipagem passthrough).
3. Enviar o roteiro preenchido a homologacaoapi@c6bank.com e, aprovado,
   ligar `C6_REGISTERED_READY=true` + carteira 15 + `C6_BASE_URL` de produção.
