# Cobranca-API — Gateway (Python/FastAPI)

Gateway de cobrança multi-banco e **porta única da plataforma**, **100% Python**:
serve as rotas REST online (C6, Sicoob, Inter) na raiz e a superfície offline em `/api/*`,
gerada **nativamente** pela engine [pyCobrança](https://github.com/Maxwbh/pyCobranca)
dentro do próprio processo (sem sidecar, sem proxy HTTP).

> **v2.0.0 — serviço único, 100% Python.** A engine offline roda embutida
> ([pyCobrança](https://github.com/Maxwbh/pyCobranca)): um processo, uma imagem,
> nenhum sidecar.

**Serviço único — como rodar igual produção:**
```bash
docker compose up --build   # (na raiz do repo)
# http://localhost:8000/docs      (gateway)  ·  /health
# http://localhost:8000/api/docs  (Core)     ·  /api/health
```

## ⚠️ Dois "API" — não confundir (colisão de nome)

| | Produto | Repo / dir | Papel | Versão |
|---|---|---|---|---|
| **Este** | **Cobranca-API** (serviço) | `gateway/` | providers C6/Sicoob/Inter, cofre, webhook, conciliação | FastAPI `version` em `app/main.py` |
| Outro | **pyCobrança** (engine) | biblioteca Python (pip) | boleto/CNAB/OFX/PIX-QR — chamada in-process por `app/core/pycob.py` | `pycobranca.__version__` |

- A engine offline é a biblioteca [pyCobrança](https://github.com/Maxwbh/pyCobranca)
  (Python puro), consumida **in-process**; não há processo/serviço separado.
  Ver [separação em 3 produtos](../docs/development/separacao-3-produtos.md).
- **Versionamento independente:** a engine pyCobrança versiona no repositório
  dela; este projeto versiona o serviço na própria app FastAPI
  (`app.version`). Nenhum release acopla os dois — a versão da engine em uso
  aparece em `GET /api/metadata`.

## Por que a engine é uma biblioteca (e não um serviço)
- No caminho **registrado** (C6, Sicoob, Inter) o **banco devolve** linha digitável/PDF/QR →
  o serviço só orquestra OAuth+mTLS+JSON. **Não usa a engine.**
- No caminho **offline/CNAB/carnê** (18 bancos) → `core/pycob.py` chama a engine
  **pyCobrança** no próprio processo (sem HTTP, sem sidecar).

Um processo, uma imagem, um deploy. À medida que a adoção da API registrada
cresce, o caminho offline passa a ser usado só onde não há API do banco.

## Estrutura
```
app/
  schemas.py              # contrato canônico (pydantic) — estável p/ os consumidores
  registry.py             # roteia provider + resolve credencial no cofre
  core/
    vault.py              # cofre de credenciais por tenant (stateful) — INTERFACE
    subscriptions.py      # registro de assinantes (callback por tenant) — multi-sistema
    forwarder.py          # push assinado (HMAC) do evento ao consumidor
    credential_store.py   # store dos tokens bapi_ (Postgres/Supabase ou SQLite; zero-knowledge)
  clients/
    oauth_mtls.py         # OAuth2 client_credentials sobre mTLS (PKCS12), scopes, headers
    engine.py             # acesso à engine pyCobrança (render boleto/carnê, in-process)
  providers/
    base.py               # interface BankProvider
    bacen_pix.py          # mixin Pix BACEN (cob/cobv/lote) — compartilhado C6+Sicoob
    offline_engine.py     # PyCobrancaProvider (offline/CNAB, in-process)
    c6.py                 # C6 (336): boleto, Pix (mixin), Bolepix, extrato, webhooks
    sicoob.py             # Sicoob (756): Cobrança v3, Pix (mixin), boleto híbrido
  routers/
    bancos.py             # GET /bancos (catálogo com capacidades por introspecção)
    _credentials.py       # resolução de credenciais do request (Bearer > corpo/header > cofre)
    credenciais.py        # POST/DELETE /credenciais (tokenização — chave derivada do token)
    cobranca.py           # POST /cobranca, GET/DELETE /cobranca/{id}, GET /cobranca/{id}/pdf
    carne.py              # POST /carne (registra N parcelas + carnê 3-vias)
    pix.py                # /pix: cob/cobv, PATCH revisao, listas e lote (BACEN) — só REST
    bolepix.py            # /bolepix: boleto híbrido online com Pix EVP (C6 v2)
    pix_automatico.py     # /pix-automatico: rec, solicrec, locrec, cobr (BACEN)
    conciliacao.py        # GET /conciliacao/recebiveis|transacoes (C6 Pay)
    extrato.py            # GET /extrato (movimentações da conta PJ)
    webhook_banco.py      # /config/webhook-banco: registra a URL de notificação NO banco
    webhooks.py           # POST /webhooks/{banco} e /webhooks/{banco}/{tenant_id}
```

## Endpoints
| Método | Rota | O que faz |
|---|---|---|
| GET | `/bancos` | Catálogo de bancos, **capacidades reais** (introspecção) e contrato de autenticação |
| POST | `/credenciais` | Cadastra credenciais do banco → devolve **token** (`bapi_...`, única vez) |
| DELETE | `/credenciais` | Revoga o token imediatamente |
| POST | `/cobranca` | Registra cobrança no provider (por tenant) → resposta normalizada |
| GET | `/cobranca/{id}` | Consulta status (`?tenant_id=&provider=`) |
| GET | `/cobranca/{id}/pdf` | PDF do boleto registrado (quando o banco fornece) |
| PUT | `/cobranca/{id}` | Altera boleto emitido (valor, vencimento, juros/multa/desconto) |
| DELETE | `/cobranca/{id}` | Baixa/cancela (409 enquanto a CIP processa o registro) |
| POST | `/carne` | Registra N parcelas + monta carnê 3-vias (PDF) |
| POST | `/pix` | Cobrança Pix: cob imediata (com/sem txid) ou cobv (`data_vencimento`) |
| GET | `/pix/{txid}` | Consulta cob (ou cobv com `?vencimento=true`) |
| PATCH | `/pix/{txid}` | Revisa a cobrança (valor, solicitação...) |
| GET | `/pix` | Lista cobranças do período (`inicio`/`fim` RFC3339) |
| PUT | `/pix/lote/{id}` | Cria/atualiza lote de cobv · GET consulta · `/pix/lotes` lista |
| GET | `/pix/recebidos` | **Pix recebidos** (money-in) do período; `/{e2eid}` consulta; `PUT .../devolucao/{id}` devolve |
| POST | `/pix-automatico/recorrencias` | **Pix Automático**: cria a recorrência (autorização única do pagador) |
| GET/PATCH | `/pix-automatico/recorrencias/{idRec}` | Consulta · revisão/cancelamento (Jornada 4) |
| POST | `/pix-automatico/solicitacoes` | solicrec — pedido de autorização no app do pagador (Jornada 1) |
| POST | `/pix-automatico/locations` | QR de adesão (Jornada 2) |
| PUT | `/pix-automatico/cobrancas/{txid}` | Agenda a cobrança do ciclo (≥ 2 dias antes; **agendamento no consumidor**) |
| POST | `/pix-automatico/cobrancas/{txid}/retentativa/{data}` | Retentativa pós-vencimento |
| PUT | `/pix-automatico/config/webhooks` | webhookrec / webhookcobr |
| PUT/GET/DELETE | `/config/webhook-pix` | Webhook BACEN **por chave** (Pix recebido em tempo real) |
| POST | `/bolepix` | Boleto híbrido online (boleto + QR Pix EVP) — C6 v2 |
| GET/DELETE | `/bolepix/{ext_ref}` | Consulta (`/pdf` p/ PDF) e cancela o Bolepix |
| GET | `/extrato` | Extrato de movimentações da conta PJ |
| POST/GET/DELETE | `/config/webhook-banco` | Registra/consulta/remove a URL de notificação no banco |
| GET | `/conciliacao/recebiveis` | Recebíveis por período (C6 Pay) |
| GET | `/conciliacao/transacoes` | Transações por período (C6 Pay) |
| POST | `/webhooks/{banco}` | Recebe webhook do banco → push ao destino **global** |
| POST | `/webhooks/{banco}/{tenant_id}` | Idem, roteando ao consumidor **dono do tenant** |
| GET | `/health` | Health check |

**Roteamento de provider:** `provider=c6|sicoob` → API REST do banco;
vazio/omitido ou `pycobranca` → CNAB offline (engine pyCobrança, in-process).
Pix e conciliação exigem provider REST (422 caso contrário).
 Detalhes do C6 em
[`docs/development/c6-rest.md`](../docs/development/c6-rest.md).

**Autenticação:** o MECANISMO da API é único — `POST /credenciais` recebe os
parâmetros do banco (cada banco tem seu próprio esquema, documentado em
`GET /bancos`), armazena cifrado e devolve o token `bapi_`; as demais chamadas
validam pelo `Authorization: Bearer bapi_...`.

**Credenciais (ordem de precedência):** `Authorization: Bearer bapi_...`
(token do `/credenciais` — zero-knowledge: cifradas com chave derivada do
próprio token; Postgres/Supabase via `SUPABASE_DB_URL`/`DATABASE_URL` em
**schema próprio `boleto_api`**, fora do `public`; senão SQLite local) → `credentials` no corpo / header `X-Bank-Credentials` (só
memória) → cofre `VAULT__*` (env, fallback).

## Referência da API
- **Referência navegável (com exemplos curl):**
  [`docs/api/gateway-python.md`](../docs/api/gateway-python.md).
- **Spec viva:** `GET /openapi.json` da própria API (sempre atual — não versionamos cópia).
- **Swagger ao vivo:** `GET /docs` (e `/openapi.json`) quando a app está rodando.
- **Regenerar** após mudar schemas/rotas:
  ```bash
  PYTHONPATH=. python -c "import json; from app.main import app; \
    open('openapi.json','w').write(json.dumps(app.openapi(), ensure_ascii=False, indent=2)+'\n')"
  ```
- **Push de eventos (saída):** não é um path desta API — o gateway envia o
  `WebhookEvent` por `POST` assinado (`X-Signature`) ao consumidor (ver
  [Multi-sistema](#produto-standalone--acopla-a-qualquer-projeto)).

## Produto standalone — acopla a QUALQUER projeto
A Cobranca-API **não pertence a nenhum consumidor**. Qualquer projeto integra pelo
mesmo contrato (`/cobranca`, `/carne`) e recebe os eventos de pagamento por **push
assinado** (HMAC). Nenhum consumidor é especial — nada no código é específico
de um sistema.

**Multi-sistema (implementado):** cada tenant pertence a um consumidor, que
registra um callback próprio (`subscriptions.resolve_callback`). O banco aponta o
webhook de cada conta para `/webhooks/{banco}/{tenant_id}` e o evento é empurrado
**só ao sistema dono** daquele tenant. Sem tenant na rota, cai no destino global.

```
sistemaA → SUB__sistemaA__URL (Sistema 1)
sistemaB → SUB__sistemaB__URL (Sistema 2)   # eventos roteados por tenant
```

## Fallback — C6/Sicoob ainda não 100%
Enquanto a cobrança **registrada** (API do banco) de C6/Sicoob não está
homologada, o gateway **cai no caminho offline** (engine pyCobrança) — gera o
documento localmente, sem precisar de credencial de banco. Quando homologar,
ligue por banco: `C6_REGISTERED_READY=true` / `SICOOB_REGISTERED_READY=true`.
O roteamento fica em `registry.build_provider`.

> **O Inter está fora desse mecanismo, de propósito.** A engine offline não tem
> o layout do 077: cair nela emitiria um boleto **registrado no banco errado** —
> falha silenciosa, e cara. Sem credencial, `provider=inter` responde `424`.
> `registry._OFFLINE_BANK` não tem entrada para ele, e isso é a decisão, não um
> esquecimento.

## Configuração (env)
| Var | Para quê |
|---|---|
| `C6_REGISTERED_READY` | `true` usa a cobrança registrada do C6; default cai no offline |
| `SICOOB_REGISTERED_READY` | `true` usa a cobrança registrada do Sicoob; default cai no offline |
| `EVENT_WEBHOOK_URL` | webhook do consumidor **global** (push de eventos) |
| `EVENT_WEBHOOK_SECRET` | segredo HMAC do destino global (`X-Signature`) |
| `SUB__<tenant>__URL` | callback **por tenant** (multi-sistema) — sobrepõe o global |
| `SUB__<tenant>__SECRET` | segredo HMAC daquele tenant/consumidor |
| `VAULT__<tenant>__<provider>__*` | **fallback** de credenciais por tenant — o padrão é o consumidor enviar `credentials` no request (corpo nos POSTs; header `X-Bank-Credentials` em GET/DELETE), sem gravar nada no servidor |
| `C6_BASE_URL` / `C6_AUTH_URL` | endpoints do C6 (default: sandbox `baas-api-sandbox.c6bank.info` + `/v1/auth`) |
| `C6_BILLING_SCHEME` | carteira C6: `21` sandbox (default) / `15` produção |
| `WEBHOOK_TOKEN__<BANCO>` | token do webhook de **entrada** (ex.: `WEBHOOK_TOKEN__C6`) — 401 se divergir |
| `SUPABASE_DB_URL` / `DATABASE_URL` | Postgres/Supabase p/ o store de tokens de credencial (senão SQLite) |
| `CREDENTIAL_DB_SCHEMA` | schema Postgres do store — **próprio, fora do `public`** (default `boleto_api`; no Supabase, não expor no PostgREST) |
| `CREDENTIAL_DB_PATH` | caminho do SQLite do store de tokens (default `credentials.db`) |

## Rodar (dev)
```bash
cd gateway
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export EVENT_WEBHOOK_URL=https://meu-consumidor/webhooks/cobranca-api
export EVENT_WEBHOOK_SECRET=troque-isto
uvicorn app.main:app --reload
# http://localhost:8000/docs
```

## Pendências (TODO no código)
- **Sicoob**: fechar paths/payloads/auth-urls reais na homologação (o C6 está
  **validado no sandbox real** — roteiro de homologação v3.0 executado).
- Implementar **Vault** real (KMS/Vault/DB cifrado) — `EnvVault` é só dev.
- Trocar `subscriptions` por **store real** (DB) — `EnvSubscriptions` é só dev.
- **Worker de conciliação** (polling Sicoob) — não incluído neste esqueleto.
- **Retry/fila** no push de eventos (saída) — hoje é best-effort.

> ✅ Já feito: `/api/render/*` in-process; carnê 3-vias; push assinado por
> tenant (multi-sistema); **C6 REST** (boleto registrado, Pix cob/cobv,
> conciliação C6 Pay) com contrato real; token de rota no webhook de entrada
> (`WEBHOOK_TOKEN__<BANCO>`).

> Recomendação: extrair este diretório para um **repo próprio** (`cobranca-api`) quando sair
> do esqueleto. Vive aqui temporariamente para versionar junto da decisão.
