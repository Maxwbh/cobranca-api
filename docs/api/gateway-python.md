# Cobranca-API Gateway (Python) — Referência da API

> Gateway de cobrança multi-banco (`gateway/`, FastAPI). A versão corrente é a
> que `app.version` declara — não a repetimos aqui, porque cópia de número é a
> primeira coisa a envelhecer.
>
> **A fonte é a app, não este arquivo.** Com o serviço no ar, `GET /docs`
> (Swagger) e `GET /openapi.json` refletem o código em execução; este guia
> explica o *porquê* e o fluxo, que a spec não conta. Divergiu? a spec está
> certa.
>
> Não confundir com a superfície **offline** (`/api/*`, engine pyCobrança
> in-process — ver [docs/openapi.yaml](../openapi.yaml)). Papéis em
> [separacao-3-produtos.md](../development/separacao-3-produtos.md).

## Conceitos

- **`tenant_id`** — escopo de cada conta/cliente (multi-tenant).
- **`provider`** — o **caminho**, e só ele: `on` = API REST do banco (OAuth2 +
  mTLS, exige credencial); `off` (default; **vazio/omitido** equivale) = CNAB
  offline pela engine pyCobrança, 100% Python, sem rede e sem convênio. Pix e
  conciliação só existem `on` (senão **422**).
- **`banco`** — a **instituição**: `c6`, `sicoob`, `inter`, `itau`,
  `banco_brasil`… Trocar de mundo é trocar o `provider`; o `banco` fica. No
  caminho `off` o banco também pode continuar vindo em `account_config.bank`,
  como sempre veio.

  > Os dois eixos eram um campo só, e o preço aparecia na borda: "qual banco"
  > vivia no `provider` quando online e dentro do `account_config` quando
  > offline — não havia como dizer *"esse banco, pelo outro caminho"*.
  >
  > **O nome do banco no `provider` continua aceito** (`provider=c6` =
  > `provider=on&banco=c6`): há integração em produção e roteiro de homologação
  > já enviado ao banco com esses payloads. O apelido sai na 3.0.0.
  >
  > Combinação que não existe falha alto, com a lista de quem tem:
  > `provider=on&banco=bradesco` → `422` (não há API REST do Bradesco aqui);
  > `provider=off&banco=inter` → `422` (a engine não tem o layout 077, e cair em
  > outro banco emitiria boleto registrado no lugar errado).
- **Criação responde `201` com `Location`** — `POST /cobranca`, `/carne`,
  `/pix` e `/checkout`. O `Location` já vem com `tenant_id` e `provider`, então
  é seguível como está. `PUT /pix/lote/{id}` responde **`202`**: o banco
  enfileira o lote, não o cria.
- **Credenciais** (ordem de precedência):
  1. `Authorization: Bearer bapi_...` — token do `/credenciais` (recomendado);
  2. `credentials` no corpo (POSTs) ou header `X-Bank-Credentials`
     (JSON base64, GET/DELETE) — stateless, só memória;
  3. cofre do servidor `VAULT__<tenant>__<banco>__*` (env, fallback) — a chave
     é o **banco** (`VAULT__empresa_123__C6__CLIENT_ID`), não o caminho.

## 🏦 Descoberta: `GET /bancos`

Lista os bancos, os **caminhos** de cada um, suas **capacidades reais**
(introspectadas do código — nunca desatualiza) e o contrato único de
autenticação:

```bash
curl http://localhost:8000/bancos
# → {"caminhos": {"on": "API do banco...", "off": "engine pyCobrança..."},
#    "autenticacao_api": {...},
#    "bancos": [
#      {"id": "c6", "codigo_banco": "336", "tipo": "rest",
#       "caminhos": ["on", "off"], "registrado_pronto": true,
#       "fallback_offline": "banco_c6", "caminho_efetivo": "on",
#       "flag": "C6_REGISTERED_READY",
#       "capacidades": ["boleto", "boleto_alteracao", "boleto_baixa", "boleto_pdf",
#                       "bolepix", "checkout_cartao", "conciliacao_cartao", "extrato",
#                       "pix", "pix_automatico", "pix_lote", "pix_recebidos",
#                       "pix_revisao", "webhook_banco", "webhook_pix_por_chave"]},
#      {"id": "sicoob", "codigo_banco": "756", "tipo": "rest", ...},
#      {"id": "inter",  "codigo_banco": "077", "tipo": "rest",
#       "caminhos": ["on"], "fallback_offline": null, ...},
#      {"id": "pycobranca", "tipo": "offline", "bancos_cnab": [18 bancos]}]}
```

**`capacidades` fala do banco; os quatro campos novos falam desta instalação.**
São perguntas diferentes: "o C6 emite boleto registrado?" e "este container vai
emitir pelo C6?". Enquanto `<BANCO>_REGISTERED_READY` estiver desligado, o
caminho `on` é **rebaixado para a engine** — `registrado_pronto: false` e
`caminho_efetivo: "off"` dizem isso antes de o integrador descobrir pelo boleto.
`fallback_offline: null` (Inter) significa que não há para onde cair.

Antes de chamar qualquer operação, o sistema consumidor pode checar se o banco
do tenant suporta a capacidade. Nem todo banco faz tudo, e as diferenças são
reais:

| Capacidade | C6 (336) | Sicoob (756) | Inter (077) | Itaú (341) ² |
|---|:--:|:--:|:--:|:--:|
| Boleto — emitir, consultar, baixar | ✅ | ✅ | ✅ | ✅ |
| Boleto — **PDF pela API do banco** | ✅ | ✅ | ✅ | **—** |
| Boleto — **alterar** (`PUT /cobranca/{id}`) | ✅ | — | — | ✅ |
| Pix BACEN — cob/cobv, lote, revisão, recebidos | ✅ | ✅ | ✅ | — |
| Pix Automático | ✅ | ✅ | ✅ ¹ | — |
| Extrato da conta PJ | ✅ | ✅ | ✅ | — |
| Webhook **cadastrado no banco** | ✅ | — | ✅ | — |
| Bolepix (boleto com QR EVP) | ✅ | — | — | — |
| Checkout de cartão | ✅ | — | — | — |
| Conciliação de adquirência (C6 Pay) | ✅ | — | — | — |

² **Itaú é esqueleto**, desligado por padrão (`ITAU_REGISTERED_READY`): sem a
flag, `provider=itau` emite pela engine offline, que tem o layout 341. Pix e
webhook ficam de fora até o contrato ser confirmado — ver
[itau-rest.md](../development/itau-rest.md).

¹ O dialeto é BACEN e o provider o implementa, mas o **produto precisa estar
habilitado na conta**: na homologação o sandbox do Inter respondeu que a conta
não tem Pix Automático contratado. Capacidade declarada ≠ produto liberado.

A tabela acima é reprodução; a **fonte é o `GET /bancos`**, que introspecta as
classes de provider e por isso não envelhece. Pedir o que o banco não tem
responde **422 dizendo para onde ir**, não 500.


> **PDF nem sempre vem do banco.** C6, Sicoob e Inter devolvem o PDF em base64
> na própria API. O **Itaú não devolve** — a API dele responde linha digitável e
> código de barras. Quando o banco não fornece, `GET /cobranca/{id}/pdf` responde
> `422` **com o caminho pronto**: renderizar pela engine em
> `POST /api/render/boleto`, com o `bank` do banco e **os dados que o banco
> registrou**.
>
> A ressalva não é formalidade. O código de barras é **determinístico** — função
> de banco, vencimento, valor, agência/conta/carteira e nosso número —, então
> renderizar com um nosso número diferente do registrado produz um boleto que o
> pagador paga e ninguém concilia. **Compare a linha digitável calculada pela
> engine com a que o banco devolveu antes de entregar.**

## 🔐 Autenticação — mecanismo único da API, esquema próprio por banco

O **mecanismo da API é o mesmo para todos os bancos** (é ele que o consumidor
integra uma única vez):

1. `POST /credenciais` **recebe os parâmetros do banco** (cada banco tem o seu
   esquema), processa e **armazena cifrado** (zero-knowledge) → devolve o token
   `bapi_` (única vez);
2. **Todas as demais chamadas** autenticam com `Authorization: Bearer bapi_...`
   — a API valida o token e usa as credenciais do banco internamente;
3. `DELETE /credenciais` revoga.

O **esquema de credenciais é próprio de cada banco** — o campo `credentials` é
livre e o `GET /bancos` documenta o esquema vigente:

| Banco | `credentials` (esquema próprio) |
|---|---|
| **C6** | `client_id`, `client_secret`, `pfx_base64`, `pfx_password` (mTLS obrigatório) |
| **Sicoob** | `client_id` + `access_token` (sandbox) · `client_id`, `client_secret`, `pfx_base64`, `pfx_password`, `scopes?` (produção) |
| **Inter** | `client_id`, `client_secret`, `cert_pem` + `key_pem`, `conta_corrente?`, `scopes?` |

> **O Inter entrega `.crt` + `.key`, não PKCS12.** Os dois campos aceitam PEM cru
> ou base64 do mesmo material — quem baixou do portal cola o arquivo e segue.
> `pfx_base64`/`pfx_password` continuam valendo como alternativa, para quem já
> converteu. Exigir a conversão seria obrigar a rodar `openssl` antes da primeira
> chamada, por nada.
>
> `conta_corrente` só é necessário quando a aplicação enxerga **mais de uma**
> conta — vira o header `x-conta-corrente`. Mandá-lo vazio é pior que omitir:
> foi exatamente isso que fez o Sicoob recusar toda consulta com
> `numeroCliente=`.

> Banco novo com outro esquema? O consumidor não muda nada: continua enviando o
> dict de credenciais daquele banco no `POST /credenciais` e usando o `bapi_`.

## Códigos de erro comuns

| Código | Quando |
|---|---|
| 401 | token `bapi_` inválido/revogado; webhook com token errado |
| 403 | token de outro tenant/provider |
| 422 | contrato inválido (provider offline em rota REST, chave Pix ausente, header malformado) |
| 424 | tenant sem credenciais (nem request, nem token, nem cofre) |
| 409 | registro em processamento no banco (CIP) — re-tente em instantes |

### Erro que veio do banco

O status do banco é **traduzido** para o que o chamador precisa fazer. Em todos
os casos o corpo traz `upstream` com o status, a URL e a resposta original do
banco — traduzir a faixa não custa o diagnóstico.

| Banco responde | A API responde | O que fazer |
|---|---|---|
| `400`, `422` | **`422`** | corrigir o payload — re-tentar igual não resolve |
| `401`, `403` | **`424`** | corrigir as credenciais do banco |
| `404` | **`404`** | o recurso não existe no banco |
| `405` | **`422`** | operação não suportada para esse recurso |
| `409` | **`409`** | conflito: já existe, ou o estado não permite |
| `429` | **`429`** | respeitar o `Retry-After` (repassado quando o banco envia) |
| `5xx` e demais | **`502`** | falha do banco — re-tentar com backoff |
| rede/timeout | **`504`** | banco indisponível |

> **Uma exceção à tabela:** erro no endpoint de **token** é sempre `424`,
> qualquer que seja o status devolvido. O Inter responde `400` a
> `client_credentials` inválido, e traduzir aquilo como "o banco recusou os
> dados enviados" manda quem integra caçar defeito no payload quando o problema
> é a credencial.

Todos esses códigos estão **declarados no OpenAPI** das rotas que falam com o
banco — não é preciso descobri-los em produção. Rotas que não saem do processo
(`/bancos`, `/health`) não os declaram, justamente para não ensinar o
integrador a tratar erro que nunca chega.

---

## 🔑 Credenciais (tokenização)

### `POST /credenciais`
Cadastra credenciais do banco e devolve um **token opaco** (única vez).
Zero-knowledge: cifradas com AES-256-GCM cuja chave é derivada **do próprio
token** (HKDF-SHA256) — o servidor guarda só o SHA-256 do token e não decifra
sozinho. Storage: Postgres/Supabase (`SUPABASE_DB_URL`/`DATABASE_URL`, schema
próprio `boleto_api`) ou SQLite local.

```bash
curl -X POST http://localhost:8000/credenciais \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "empresa_123",
    "provider": "c6",
    "credentials": {
      "client_id": "...", "client_secret": "...",
      "pfx_base64": "...", "pfx_password": "..."
    }
  }'
# 201 → {"token": "bapi_kJx...", "tenant_id": "empresa_123", "provider": "c6"}
#   guarde o token: ele não é recuperável (o servidor não o armazena)
```

### `DELETE /credenciais`
Revoga o token **imediatamente** (apaga o registro cifrado).

```bash
curl -X DELETE http://localhost:8000/credenciais \
  -H 'Authorization: Bearer bapi_kJx...'
# 204 | 401 se o token não existir
```

---

## 🧾 Cobrança (boleto)

### `POST /cobranca`
Registra a cobrança. Com `provider=on&banco=c6` (e `C6_REGISTERED_READY=true`)
usa a API REST do banco; senão renderiza offline na engine pyCobrança, no mesmo
processo. `provider=off&banco=<qualquer um dos 18>` vai direto à engine.

```jsonc
{"provider": "on",  "banco": "c6"}     // API do C6
{"provider": "off", "banco": "c6"}     // mesmo banco, boleto pela engine
{"provider": "c6"}                     // apelido legado do primeiro (sai na 3.0.0)
```

> **`provider=inter` não tem esse fallback, de propósito.** A engine offline não
> tem o layout do 077: cair nela emitiria um boleto **registrado no banco
> errado** — falha silenciosa e cara. Sem credencial do Inter a rota responde
> `424`.

```bash
curl -X POST http://localhost:8000/cobranca \
  -H 'Authorization: Bearer bapi_kJx...' \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "empresa_123",
    "provider": "c6",
    "account_config": {"billing_scheme": "21"},
    "cobranca": {
      "valor": "1500.00",
      "vencimento": "2026-08-31",
      "seu_numero": "FAT001",
      "nosso_numero": "123",
      "pagador": {
        "nome": "José da Silva",
        "documento": "12345678901",
        "endereco": {"street": "Av. Nove de Julho", "number": 123,
                     "city": "São Paulo", "state": "SP", "zip_code": "01000000"}
      }
    }
  }'
# 201 Created
# Location: /cobranca/01J3...?tenant_id=empresa_123&provider=c6
# → {"id": "01J3...", "status": "registrado",
#    "linha_digitavel": "33690.00009 ...", "codigo_barras": "3369...",
#    "pix_copia_cola": null, "pdf_base64": null, "raw": {...}}
```

> **`registrado` não é `liquidado`.** O status normalizado tem seis valores —
> `registrado | pendente | liquidado | baixado | expirado | erro` — e vale igual
> nos três bancos. Duas traduções foram decisão de produto, não tradução literal:
> no Inter, `MARCADO_RECEBIDO` (baixa manual do beneficiário) vira **`liquidado`**,
> porque a pergunta de quem consome é "posso liberar?"; e `PROTESTO` vira
> **`registrado`**, porque o título segue em aberto — criar um sétimo status
> obrigaria todo consumidor a tratar um caso que só um banco tem. O valor cru do
> banco fica sempre em `raw`.

### `GET /cobranca/{id}?tenant_id=&provider=`
Consulta o status normalizado (`registrado|pendente|liquidado|baixado|expirado|erro`).

### `GET /cobranca/{id}/pdf?tenant_id=&provider=`
PDF do boleto registrado, em `pdf_base64`. Provider offline → 422.

### `PUT /cobranca/{id}?tenant_id=&provider=`
Altera boleto emitido — corpo com os campos C6 (`amount`, `due_date`,
`discount`, `interest`, `fine`). **Só o C6 oferece alteração**; Sicoob e Inter
respondem `422` apontando o caminho (baixar e reemitir). Registro em
processamento na CIP → **409** (re-tente em instantes).

### `DELETE /cobranca/{id}?tenant_id=&provider=`
Baixa/cancela. O verbo muda por banco e o gateway absorve: C6 `PUT
/bank_slips/{id}/cancel`, Inter `POST /cobrancas/{id}/cancelar` com
`motivoCancelamento` obrigatório.

> Nas rotas GET/DELETE, credenciais via `Authorization: Bearer bapi_...` ou
> header `X-Bank-Credentials: <base64(JSON)>`.
>
> **Sicoob e Inter identificam a conta, não só o boleto.** Passe
> `numero_cliente`/`codigo_modalidade` (Sicoob) na query quando a credencial não
> os traz; sem isso o banco recusa a leitura. O C6 não expõe esse problema
> porque identifica pelo id — foi por isso que ele passou despercebido até a
> homologação do Sicoob.

---

## 📚 Carnê

### `POST /carne`
Registra N parcelas no provider e monta o carnê 3-vias A4 (PDF) na engine.
Corpo: `{tenant_id, provider, account_config, bank, parcelas: [Cobranca...],
credentials?}` → **`201`** com `{carne_pdf_base64, cobrancas: [...]}`.

---

## ⚡ Pix dinâmico (BACEN) — só providers REST

### `POST /pix` — cob imediata
```bash
curl -X POST http://localhost:8000/pix \
  -H 'Authorization: Bearer bapi_kJx...' \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "empresa_123",
    "provider": "c6",
    "account_config": {"chave_pix": "financeiro@empresa.com"},
    "pix": {"valor": "97.50", "expiracao_segundos": 3600, "descricao": "Pedido 42"}
  }'
# 201 Created
# Location: /pix/9d36b84f...?tenant_id=empresa_123&provider=c6
# → {"txid": "9d36b84f...", "status": "registrado", "valor": "97.50",
#    "expira_em": "2026-08-04T15:00:00Z",
#    "pix_copia_cola": "00020126...", "location": "pix.example.com/qr/..."}
```

> `expira_em` é **derivado** do `calendario` do banco: `criacao + expiracao`
> (cob) ou `dataDeVencimento + validadeAposVencimento` (cobv). Prazo absurdo
> vindo do banco devolve `null` em vez de derrubar a rota — o mock do Sicoob
> mandou 1.025.541.278 dias e virava `500`.

### `POST /pix` — cobv (com vencimento)
Inclua `data_vencimento`, `txid` (26–35 alfanuméricos) e `devedor` **com
endereço** (`logradouro/cidade/uf/cep` — exigência BACEN):

```json
"pix": {
  "valor": "150.00", "txid": "FATURA2026080100000000000001",
  "data_vencimento": "2026-08-31", "validade_apos_vencimento": 30,
  "devedor": {"nome": "José", "documento": "12345678901",
              "endereco": {"logradouro": "Rua X, 1", "cidade": "Recife",
                           "uf": "PE", "cep": "50000000"}}
}
```

### `GET /pix/{txid}?tenant_id=&provider=c6[&vencimento=true]`
Status: `ATIVA→registrado`, `CONCLUIDA→liquidado`, `REMOVIDA_*→baixado`.
`vencimento=true` consulta cobv.

### `PATCH /pix/{txid}?tenant_id=[&vencimento=true]`
Revisa a cobrança (BACEN): corpo com `valor`, `solicitacaoPagador`, `calendario`…

### `GET /pix?tenant_id=&inicio=&fim=[&vencimento=true]`
Lista cobranças do período (RFC3339: `2026-07-15T00:00:00Z`).

### Lote de cobv
`PUT /pix/lote/{id}` (corpo: `{descricao, cobrancas:[{txid, valor,
data_vencimento, devedor…}]}`) · **`PATCH /pix/lote/{id}`** · `GET /pix/lote/{id}`
· `GET /pix/lotes?inicio=&fim=`.

O `PUT` responde **`202`**, não `201`: o banco devolve *"lote solicitado para
criação"* — ele enfileira, e o resultado se lê no `GET`. Prometer `201` seria
dizer que o recurso já existe.

O `PATCH` **revisa** as cobranças do lote: só as que vão no corpo mudam, as
demais ficam como estão. Mesma forma de item do `PUT`, **sem `descricao`** — o
PATCH do BACEN carrega apenas `cobsv`, e mandar `descricao` aqui é `422` em vez
de silêncio. Vale para qualquer provider de dialeto BACEN (C6, Sicoob, Inter).

---

## 🧾⚡ Bolepix — boleto híbrido online (C6 v2)

### `POST /bolepix`
Emite boleto **com QR Pix EVP embutido**, direto no banco (idempotente por
`external_reference_id`, 26 chars A-Z0-9 — gerado se omitido):

```bash
curl -X POST http://localhost:8000/bolepix \
  -H 'Authorization: Bearer bapi_kJx...' -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "empresa_123", "provider": "c6",
    "account_config": {"chave_pix": "<chave EVP>", "billing_scheme": "21"},
    "bolepix": {
      "valor": "99.90", "vencimento": "2026-08-31", "descricao": "Pedido 42",
      "pagador": {"nome": "José", "documento": "12345678901",
                  "endereco": {"address": "Av. Nove de Julho, 100",
                               "neighborhood": "Centro", "city": "São Paulo",
                               "state": "SP", "zip_code": "01000000"}}
    }
  }'
# 201 → linha digitável + código de barras + pix_copia_cola (QR EVP)
```

O `endereco` do pagador é **obrigatório** no Bolepix: o `/v2` do C6 exige
`city`, `state` e `zip_code` (aliases `cidade`, `uf`, `cep`). Faltando qualquer
um, a API responde **`422`** dizendo qual campo falta, sem chamar o banco.

### `GET /bolepix/{ext_ref}` · `GET /bolepix/{ext_ref}/pdf` · `DELETE /bolepix/{ext_ref}`
Consulta, PDF (base64) e cancelamento (**409** enquanto a CIP processa).

---

## 💳 Checkout — link de pagamento com cartão (C6)

Cria um link hospedado pelo banco. O pagador abre a `url`, digita o cartão **no
domínio do C6** e volta pela `redirect_url`. Crédito ou débito, parcelado, e
Pix no mesmo link se quiser.

**Nenhum dado de cartão passa por esta API.** `save_card` e checkout
transparente **não existem no schema** — corpo com esses campos responde `422`
e não chega ao banco. É decisão de produto, e o PAN ficar no domínio do banco
mantém o escopo PCI-DSS lá.

### `POST /checkout`

```json
{
  "tenant_id": "empresa1", "provider": "c6",
  "checkout": {
    "valor": "150.00",
    "tipo": "credito",
    "parcelas": 6,
    "juros_por": "loja",
    "pix": true,
    "descricao": "Pedido 42",
    "redirect_url": "https://sua-loja.com.br/retorno"
  }
}
```

| Campo | Default | Observação |
|---|---|---|
| `tipo` | `credito` | `credito` \| `debito` |
| `parcelas` | `1` | **teto** oferecido ao pagador — ele escolhe abaixo, salvo `parcelas_fixas`. Repassado ao banco como veio; ver "política de parcelamento" abaixo |
| `juros_por` | `loja` | quem paga o juro: `loja` (BY_SELLER) ou `emissor`. Com `parcelas > 1` o campo é obrigatório — anulá-lo responde `422` daqui, não `400` do banco |
| `pix` | `false` | oferece Pix no mesmo link; o QR é gerado pelo banco |
| `expira_em` | 7 dias (banco) | ISO 8601 |
| `pagador` | — | se enviado, o endereço exige `street`, `number` (**numérico**), `city`, `state`, `zip_code` |

Responde **201** com `{id, url, status, expira_em}`. A `url` é o que se manda
ao cliente.

**Mande `Idempotency-Key` se houver botão humano na frente disto.** Sem a chave,
duplo clique cria **dois links para a mesma venda** — e nada impede o pagador de
pagar os dois. Com a chave, o reenvio devolve o mesmo link sem tocar no banco:

```bash
curl -X POST .../checkout -H 'Idempotency-Key: venda-42' -d @pedido.json
```

A chave vale por tenant. Reusá-la com um `checkout` diferente responde `422` —
uma chave identifica **uma** requisição, e devolver o link errado seria pior que
recusar. Sem o header, o comportamento é o de sempre.

#### Política de parcelamento — de quem é cada parte

| Regra | Quem resolve |
|---|---|
| **Valor mínimo de parcela** (ex.: R$ 100) | **A aplicação que consome.** Não existe campo para isso, e não vai existir |
| **Teto de parcelas da loja** (ex.: até 3x) | **A aplicação que consome**, mandando o número já calculado em `parcelas` |
| Teto de parcelas do banco | O **banco**, que recusa o que não aceita |
| Quem paga o juro | Você, em `juros_por` — repassado como `interest_type` |

A API **não valida** `parcelas` além de `>= 1`: o valor vai ao banco como veio.
Isso é decisão, não omissão — replicar aqui o teto do banco criaria uma segunda
fonte de verdade que envelhece, e no dia em que o banco ampliar o limite a nossa
cópia recusaria um parcelamento válido.

Com valor mínimo de parcela, o cálculo é de quem chama, antes do POST:

```sql
-- 3x, com parcela mínima de R$ 100 — a política é da loja, não da API
p_parcelas => GREATEST(1, LEAST(3, FLOOR(l_valor / 100)))
```

| Venda | `parcelas` enviado | O pagador vê |
|---|---|---|
| R$ 300,00 | 3 | 3 × R$ 100,00 |
| R$ 250,00 | 2 | 2 × R$ 125,00 |
| R$ 90,00 | 1 | à vista |

Mandar `parcelas: 3` fixo numa venda de R$ 90 ofereceria 3 × R$ 30 ao pagador —
**violando a política da própria loja, e o banco não vai barrar isso por você.**

Se o número enviado passar do que o banco aceita, a resposta é **`422`** com o
motivo original dele em `upstream` — o caminho é reenviar com outra
configuração, não há estado a desfazer (o link não chegou a ser criado).

Nada disto vale para `juros_por`: esse é obrigatório quando `parcelas > 1`, e
anulá-lo é `422` **daqui**, sem chamar o banco.

### `GET /checkout/{id}` · `DELETE /checkout/{id}`

Consulta e cancelamento. Status normalizado igual ao resto da API:

| C6 | Aqui |
|---|---|
| `CREATED`, `IN PROGRESS`, `AUTHORIZED…`, `CONFIRMATION REQUESTED`, `CANCELLATION REQUESTED` | `pendente` |
| `PAID` | `liquidado` |
| `CANCELLED` | `baixado` |
| `EXPIRED` | `expirado` |
| `DECLINED`, `ERROR` | `erro` |

> `DECLINED` é `erro`, não `baixado`: cartão recusado não encerrou a cobrança —
> o link se esgotou, a dívida não. Quem decide que segue em aberto é o
> consumidor da API, que é quem conhece contrato e parcela.

**Notificação:** o checkout não tem callback próprio. Cadastre a URL com
`service: CHECKOUT` em `POST /config/webhook-banco` — o evento chega em
`/webhooks/c6/<tenant>` e é repassado assinado, como o do boleto, com
`event: "checkout.atualizado"` e o mesmo status normalizado da tabela acima.
Use a rota **com tenant**: é a única em que o `liquidado` é reconsultado no
banco antes de seguir para você.

**Provider que não oferece link hospedado responde `422`** dizendo para onde ir.
Hoje só o C6 oferece.

**Oracle:** página pronta em
[`examples/apex/apex_checkout.sql`](https://github.com/Maxwbh/cobranca-api/blob/main/examples/apex/apex_checkout.sql)
(criar link, acompanhar status, handler ORDS do webhook) e
`cobranca_api.criar_checkout` no
[pacote PL/SQL](https://github.com/Maxwbh/cobranca-api/blob/main/examples/oracle/cobranca_api_pkg.sql).

---

## 🏦 Extrato e configuração

### `GET /extrato?tenant_id=&start_date=&end_date=`
Movimentações da conta PJ no período.

### `POST /config/webhook-banco`
Registra no banco a URL que receberá notificações
(`{tenant_id, provider, url, service: BANK_SLIP|CHECKOUT}`); `GET`/`DELETE`
com `?service=` consultam/removem.

---

## 📊 Conciliação (C6 Pay)

### `GET /conciliacao/recebiveis` · `GET /conciliacao/transacoes`
Query: `tenant_id`, `start_date`, `end_date` (máx. 60 dias), `provider=c6`,
`page` (default 1), `size` (default 50, máx. 100).

```bash
curl "http://localhost:8000/conciliacao/recebiveis?tenant_id=empresa_123&start_date=2026-07-01&end_date=2026-07-31" \
  -H 'Authorization: Bearer bapi_kJx...'
# 200 → {"page": 1, "last_page": 3, "total_items": 120, "items": [{...}]}
```

---

## 🔔 Webhooks (entrada) e push de eventos (saída)

### `POST /webhooks/{banco}` · `POST /webhooks/{banco}/{tenant_id}`
URL que você cadastra **no banco**. Exige `WEBHOOK_TOKEN__<BANCO>` configurado e
`?token=...` (ou header `x-webhook-token`) — sem token configurado, ou token
divergente, **401**. Os bancos não assinam o payload; o token de rota é a prova
de origem, e sem ela qualquer um forjaria um `liquidado`.

O evento é normalizado (`WebhookEvent`) e **empurrado por POST assinado**
(`X-Signature: sha256=<hmac_sha256(secret, body)>`) ao consumidor dono do
tenant (`SUB__<tenant>__URL/SECRET`) ou ao destino global
(`EVENT_WEBHOOK_URL/SECRET`). Se o push não sair de primeira, o evento fica em
fila e é re-tentado com backoff — a resposta traz `pendente_de_entrega: true`.

Três campos do `WebhookEvent` que valem ler antes de integrar:

| Campo | O que diz |
|---|---|
| `event` | `"duplicado"` quando o banco reentregou algo que já passou — ignore |
| `confirmado` | `true` o banco confirmou o `liquidado`; `false` ele discordou e o `status` aqui é o **dele**; `null` não foi possível perguntar |
| `pendente_de_entrega` | `true` quando o push falhou e vai ser re-tentado |

A confirmação só acontece na rota **com tenant** — o cofre de credenciais é por
tenant, e sem credencial não há como perguntar ao banco.

### `GET /health`
`{"status": "ok"}`.

---

## 🚀 Exemplos de utilização por banco

O fluxo é o MESMO para qualquer banco — muda apenas `provider`, as credenciais
e o `account_config`. Copie e ajuste.

### C6 Bank (336) — produção/sandbox mTLS

```bash
GW=http://localhost:8000

# 1. Cadastra credenciais UMA vez → token
TOKEN=$(curl -s -X POST $GW/credenciais -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "c6",
  "credentials": {"client_id": "<uuid do portal>", "client_secret": "<secret>",
                   "pfx_base64": "<base64 do .pfx>", "pfx_password": "<senha>"}
}' | jq -r .token)

# 2. Boleto registrado (carteira 21 sandbox / 15 produção)
curl -s -X POST $GW/cobranca -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "c6",
  "account_config": {"billing_scheme": "21"},
  "cobranca": {"valor": "1500.00", "vencimento": "2026-08-31", "seu_numero": "FAT001",
    "pagador": {"nome": "José da Silva", "documento": "12345678901",
      "endereco": {"street": "Av. Nove de Julho", "number": 123,
                   "city": "São Paulo", "state": "SP", "zip_code": "01000000"}}}}'

# 3. Bolepix (boleto + QR Pix EVP embutido) — exclusivo C6
curl -s -X POST $GW/bolepix -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "c6",
  "account_config": {"chave_pix": "<chave EVP>", "billing_scheme": "21"},
  "bolepix": {"valor": "99.90", "vencimento": "2026-08-31", "descricao": "Pedido 42",
    "pagador": {"nome": "José", "documento": "12345678901",
      "endereco": {"address": "Av. Nove de Julho, 100", "neighborhood": "Centro",
                   "city": "São Paulo", "state": "SP", "zip_code": "01000000"}}}}'

# 4. Pix imediato + conciliação de recebidos
curl -s -X POST $GW/pix -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"tenant_id": "empresa_123", "provider": "c6",
       "account_config": {"chave_pix": "<chave>"}, "pix": {"valor": "97.50"}}'
curl -s "$GW/pix/recebidos?tenant_id=empresa_123&provider=c6&inicio=2026-07-01T00:00:00Z&fim=2026-07-31T23:59:59Z" \
  -H "Authorization: Bearer $TOKEN"
```

### Sicoob (756) — sandbox com token estático (sem mTLS)

```bash
# 1. Credenciais do sandbox = client_id + access_token do portal (só isso!)
TOKEN=$(curl -s -X POST $GW/credenciais -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "sicoob",
  "credentials": {"client_id": "<client_id do portal>",
                   "access_token": "<token estático do portal>"}
}' | jq -r .token)
# produção: troque access_token por client_secret + pfx_base64/pfx_password
# e aponte SICOOB_BASE_URL para https://api.sicoob.com.br

# 2. Boleto v3 (numeroCliente/codigoModalidade da cooperativa)
curl -s -X POST $GW/cobranca -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "sicoob",
  "account_config": {"numeroCliente": 25546454, "codigoModalidade": 1},
  "cobranca": {"valor": "156.23", "vencimento": "2026-08-31", "seu_numero": "FAT001",
    "pagador": {"nome": "Marcelo dos Santos", "documento": "98765432185",
      "endereco": {"endereco": "Rua 87 Quadra 1", "bairro": "Setor Central",
                   "cidade": "Luziânia", "uf": "GO", "cep": "72360000"}}}}'
# resposta pode trazer pix_copia_cola (boleto híbrido, se a conta tem chave Pix)

# 3. Pix e conciliação — MESMAS chamadas do C6, só muda provider=sicoob
curl -s -X POST $GW/pix -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"tenant_id": "empresa_123", "provider": "sicoob",
       "account_config": {"chave_pix": "<chave>"}, "pix": {"valor": "10.00"}}'

# 4. Extrato conta-corrente (mensal no Sicoob)
curl -s "$GW/extrato?tenant_id=empresa_123&provider=sicoob&start_date=2026-07-01&end_date=2026-07-31" \
  -H "Authorization: Bearer $TOKEN"
```

### Banco Inter (077) — sandbox com certificado PEM

```bash
# 1. Credenciais: o Inter entrega .crt + .key, não .pfx — cole os arquivos
TOKEN=$(curl -s -X POST $GW/credenciais -H 'Content-Type: application/json' -d "$(jq -n \
  --rawfile crt Inter_API_Certificado.crt --rawfile key Inter_API_Chave.key '{
  tenant_id: "empresa_123", provider: "inter",
  credentials: {client_id: "<uuid da aplicação>", client_secret: "<secret>",
                cert_pem: $crt, key_pem: $key}}')" | jq -r .token)

# 2. Boleto com QR Pix no MESMO documento (default: formasRecebimento BOLETO_PIX)
curl -s -X POST $GW/cobranca -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "inter",
  "cobranca": {"valor": "150.00", "vencimento": "2026-12-31", "seu_numero": "PED-1",
    "pagador": {"nome": "João da Silva", "documento": "12345678909",
      "endereco": {"logradouro": "Rua Presidente Kennedy", "numero": "126A",
                   "bairro": "Centro", "cidade": "Sete Lagoas",
                   "uf": "MG", "cep": "35700000"}}}}'
# 201 → id (codigoSolicitacao), linha_digitavel, codigo_barras e pix_copia_cola

# 3. Baixar: no Inter o motivo é obrigatório, e o gateway o preenche
curl -s -X DELETE "$GW/cobranca/<codigoSolicitacao>?tenant_id=empresa_123&provider=inter" \
  -H "Authorization: Bearer $TOKEN"

# 4. Extrato Banking v2 — mesma rota dos outros bancos
curl -s "$GW/extrato?tenant_id=empresa_123&provider=inter&start_date=2026-07-01&end_date=2026-07-31" \
  -H "Authorization: Bearer $TOKEN"
```

> **Boleto puro é opt-in.** O default do gateway é `BOLETO_PIX` (o híbrido).
> Pedindo `account_config: {"formas_recebimento": "BOLETO"}` o Inter devolve
> `pix: null` — verificado no sandbox. Defaultar em `BOLETO` perderia em
> silêncio justamente o QR que motiva escolher o banco.

### Pix Automático (débito recorrente) — mesmo dialeto em todos os bancos

```bash
# 1. Cria a recorrência (contrato de cobrança mensal)
curl -s -X POST $GW/pix-automatico/recorrencias -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "c6",
  "recorrencia": {"contrato": "CT-2026-001", "objeto": "Aluguel Apto 101",
    "devedor": {"nome": "José", "documento": "12345678901"},
    "periodicidade": "MENSAL", "data_inicial": "2026-08-01",
    "valor_fixo": "1500.00", "politica_retentativa": "PERMITE_3R_7D"}}'
# → idRec; o pagador autoriza pelo app (POST /solicitacoes) ou QR (POST /locations)

# 2. A cada ciclo, o SEU sistema agenda a parcela (>= 2 dias antes do vencimento)
curl -s -X PUT $GW/pix-automatico/cobrancas/TXID2026080100000000000001 \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123", "provider": "c6",
  "cobranca": {"id_rec": "<idRec>", "valor": "1500.00", "data_vencimento": "2026-08-05"}}'
# no vencimento o banco debita sozinho; o webhook avisa liquidação/falha
```

### Boleto offline (CNAB, 18 bancos) — sem credenciais de banco

```bash
# provider omitido/vazio → engine pyCobrança (Ruby); bancos: GET /bancos
curl -s -X POST $GW/cobranca -H 'Content-Type: application/json' -d '{
  "tenant_id": "empresa_123",
  "account_config": {"bank": "itau", "agencia": "0810", "conta_corrente": "53678",
                      "carteira": "175", "convenio": "12345"},
  "cobranca": {"valor": "100.00", "vencimento": "2026-08-31", "nosso_numero": "123",
    "pagador": {"nome": "José", "documento": "12345678901"}}}'
```

## Fluxo típico de integração

```text
1. POST /credenciais            → guarda o bapi_ (por tenant+banco)
2. POST /cobranca | POST /pix   → emite (Bearer bapi_)
3. Banco notifica /webhooks/c6/{tenant} → push assinado ao seu sistema
4. GET /conciliacao/recebiveis  → bate o financeiro
5. DELETE /credenciais          → rotação/revogação quando precisar
```

Configuração completa (envs) no [guia de deploy](../deploy.md);
detalhes do C6 em [c6-rest.md](../development/c6-rest.md).
