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
- **Criação responde `201` com `Location`** — `POST /cobranca`, `/pix`,
  `/checkout` e `/bolepix`. O `Location` já vem com `tenant_id`, `provider` e o
  `banco`, então é seguível como está — sem os três, a rota de consulta responde
  `422`. `PUT /pix/lote/{id}` responde **`202`** (o banco enfileira o lote, não o
  cria) e também traz o header. `POST /carne` é a exceção: responde `201` **sem
  `Location`**, porque o carnê não é recurso consultável — cada parcela volta no
  corpo com o próprio id.
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
#      {"id": "pycobranca", "tipo": "offline", "bancos_cnab": [19 bancos]}]}
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
3. `GET /credenciais` responde **o que está guardado** sob o token — sem o
   segredo, e com o token mascarado (ele é exibido uma única vez e o servidor
   não consegue recuperá-lo);
4. `DELETE /credenciais` revoga.

### `GET /credenciais` — quando a integração para de funcionar

O certificado mTLS dos bancos vale **um ano** e não tem renovação in-place:
vence, e toda chamada passa a falhar no handshake de uma vez, sem nada no código
ter mudado. Era risco de operação sem nenhuma visibilidade — o material entrava
cifrado no cofre e ninguém mais olhava.

```json
{
  "token": "bapi_********",
  "tenant_id": "empresa_123",
  "certificado": {
    "situacao": "ok",
    "titular": "MSDOBRASILLTDA05230380000174-baas-api-sandbox.c6bank.info",
    "emissor": "baas-api-sandbox.c6bank.info Issuing CA",
    "valido_ate": "2027-08-21",
    "dias_restantes": 360,
    "cnpj": "05230380000174",
    "par_confere": true
  }
}
```

| Campo | Para que serve |
|---|---|
| `situacao` | `ok` · `expirando` (30 dias ou menos) · `expirado` · `ilegivel` |
| `titular` | **Qual** certificado está em uso. O ambiente está no *host* dentro do CN: `baas-api-sandbox` é sandbox, `baas-api` é produção |
| `cnpj` | Extraído do CN, para conferir num olhar que é a empresa certa |
| `par_confere` | A chave privada é a **deste** certificado? `false` é o erro clássico da troca — `.crt` novo com `.key` antiga —, que no handshake vira uma mensagem de TLS que não aponta o par trocado |

O metadado é **derivado e não reconstrói nada**: certificado, chave privada e
`client_secret` nunca saem. É a regra do `core/vault.py`.

O mesmo bloco volta no `POST /credenciais`, que é onde o erro custa menos:
carregar o certificado do ambiente errado só aparecia no primeiro handshake,
horas depois.

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
#    "pix_copia_cola": null, "pix_vinculado": null, "pdf_base64": null, "raw": {...}}
```

> **`pix_vinculado` — o QR liquida o título?** `true` é **Bolepix**: QR dinâmico
> registrado no banco, e pagar por ele dá baixa. `false` é QR **avulso**, montado
> a partir de `chave_pix` no caminho `off`: credita a chave e deixa o título **em
> aberto**, com risco de segunda cobrança ou de protesto de boleto já pago.
> `null` quando o boleto não tem PIX.
>
> O caminho `on` sempre devolve `true` — o EMV vem do banco. No `off` depende do
> que você mandou: `pix_copia_cola` (o EMV do banco) dá `true`, `chave_pix` dá
> `false`. É assim que se fecha o ciclo entre os dois: registre no `on`, pegue o
> `pix_copia_cola` da resposta e renderize o PDF no `off` com o QR que dá baixa.

> ⚠️ **`201` não quer dizer "deu certo" no caminho `off`.** Falha de validação
> da engine volta como **`201` com `status: "erro"`** e os motivos em
> `raw.validation_errors` — não como `4xx`:
>
> ```json
> {"id": null, "status": "erro", "linha_digitavel": null,
>  "raw": {"validation_errors": ["cedente é obrigatório"]}}
> ```
>
> É o mesmo envelope do sucesso, e quem checa só o código HTTP dá o boleto por
> emitido. **Cheque `status`**, sempre. (No caminho `on` o erro do banco vira
> `4xx`/`5xx` de verdade — veja "Erro que veio do banco".)

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

### `GET /cobrancas?tenant_id=&provider=inter&inicio=&fim=`
Os boletos do período — a coleção que a API não sabia devolver. Antes, quem
precisava da lista guardava os ids da emissão e paginava por conta própria, ou
caía no arquivo de retorno.

| Parâmetro | Para que serve |
|---|---|
| `inicio`, `fim` | Período (obrigatórios). Máximo **90 dias**, e período invertido é `422` — no banco ele volta lista vazia, que se lê como "não houve movimento" |
| `pagina`, `tamanho` | `pagina` começa em **1**, como no resto da API (o Inter conta de 0 e o gateway converte); `tamanho` até 1000, default 50 |
| `situacao` | `RECEBIDO`, `A_RECEBER`, `MARCADO_RECEBIDO`, `ATRASADO`, `CANCELADO`, `EXPIRADO`, `FALHA_EMISSAO`, `EM_PROCESSAMENTO`, `PROTESTO` |
| `tipo_cobranca` | `SIMPLES`, `PARCELADO`, `RECORRENTE` |
| `filtrar_data_por` | `VENCIMENTO` (default), `EMISSAO`, `PAGAMENTO` |
| `ordenar_por` / `tipo_ordenacao` | Campo de ordenação e `ASC`/`DESC` |
| `seu_numero`, `pagador`, `documento_pagador` | Busca pelo identificador da emissão ou pelo pagador |

Valor fora dessas listas para **aqui**, com `422` dizendo quais valem: mandado
ao banco, ele responde `400` genérico, que parece falha da integração.

O corpo é passthrough, com os nomes do banco (`totalPaginas`, `totalElementos`,
`cobrancas[]`).

### `GET /cobrancas/sumario?tenant_id=&provider=inter&inicio=&fim=`
Os totais do período por situação — "quanto está em aberto" sem baixar a
coleção inteira para somar no cliente. Mesmos filtros da coleção, **sem**
paginação e sem ordenação (o banco não as aceita aqui). Os totais vêm em
`sumario`: o Inter devolve array na raiz, e array na raiz não tem onde crescer.

> **Só o Inter publica coleção e sumário.** C6 e Sicoob tratam um título por
> vez; nesses bancos a rota responde `422` dizendo quem oferece. No caminho
> offline não há coleção: o estado vem do arquivo de retorno
> (`POST /api/retorno`) ou do OFX.

---

## 📚 Carnê

### `POST /carne`
Registra N parcelas no provider e monta o carnê 3-vias A4 (PDF) na engine.
Corpo: `{tenant_id, provider, banco, account_config, parcelas: [Cobranca...],
credentials?}` → **`201`** com `{carne_pdf_base64, cobrancas: [...]}`. Aceita
`Authorization: Bearer bapi_...` como as demais.

**Sem `Location`**: o carnê não é recurso consultável — é o PDF mais as N
cobranças, e cada uma volta no corpo com o próprio id.

**O `account_config` carrega os dois lados.** Com `provider=on` as parcelas são
registradas pela API do banco e o PDF é desenhado pela engine — que precisa dos
campos dela (`cedente`, `documento_cedente`, `carteira`, `convenio`,
`conta_corrente`) **além** dos do banco. Faltando algum, a resposta é `422`
dizendo qual, antes de registrar qualquer parcela.

**Cada parcela precisa de identificador próprio** (`seu_numero` ou
`nosso_numero`). Duas com o mesmo são o mesmo título duas vezes: uma sai impressa
em duplicata e a outra some do bloco — nunca é cobrada. Responde `422`.

**Teto de 200 parcelas** (`LOTE_MAX_ITENS`), o mesmo de `/api/render/carne` e
`/api/boleto/multi` — acima disso, `413`.

`bank` é redundante e **opcional**: o layout vem do `banco`. Se enviado e
divergente, `422` — carnê com a marca de um banco e parcelas registradas em
outro não é pagável. Banco sem layout na engine (Inter) também é `422`: não há
como desenhar o carnê, e desenhá-lo como outro banco seria pior.

**Nada é recusado depois do registro.** Tudo que dá para conferir — teto,
duplicata, banco, dados de cada parcela — é conferido antes da primeira ida ao
banco. Se ainda assim a montagem falhar, o `422` lista os ids das parcelas que
já foram registradas e continuam válidas.

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

**A chave Pix também é obrigatória** (`bolepix.chave_pix` ou
`account_config.chave_pix`). Sem ela o banco emite boleto **sem o segmento
Pix** — um "Bolepix" que não é bolepix, e nada avisaria. Boleto puro é
`POST /cobranca`, que existe em todos os bancos.

O `external_reference_id` é conferido contra `^[A-Z0-9]{26}$` **antes** de ir ao
banco, tanto no corpo quanto no caminho das consultas. **Omitido, é gerado
aqui** — e volta em `id` e no header `Location`. É o único identificador de
consulta do Bolepix: sem guardá-lo, o boleto não se acha mais.

### `GET /bolepix/{ext_ref}` · `GET /bolepix/{ext_ref}/pdf` · `DELETE /bolepix/{ext_ref}`
Consulta, PDF (base64) e cancelamento (**409** enquanto a CIP processa).

---

## 💳 Checkout — link de pagamento com cartão (C6)

Cria um link hospedado pelo banco. O pagador abre a `url`, digita o cartão **no
domínio do C6** e volta pela `redirect_url`. Crédito ou débito, parcelado, e
Pix no mesmo link se quiser.

**Nenhum dado de cartão passa por esta API.** `save_card` e checkout
transparente **não existem no schema** — corpo com esses campos responde `422`
e não chega ao banco, tanto dentro de `checkout` quanto no nível de cima. É
decisão de produto, e o PAN ficar no domínio do banco mantém o escopo PCI-DSS
lá. O `422` de campo recusado **não devolve o valor enviado**: o nome do campo
basta para corrigir, e devolver o resto sairia daqui para o log de quem chamou.

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
| `valor` | — | **maior que zero**; `0` e negativo respondem `422` daqui |
| `tipo` | `credito` | `credito` \| `debito` |
| `parcelas` | `1` | **teto** oferecido ao pagador — ele escolhe abaixo, salvo `parcelas_fixas`. Repassado ao banco como veio; ver "política de parcelamento" abaixo |
| `juros_por` | `loja` | quem paga o juro: `loja` (BY_SELLER) ou `emissor`. Com `parcelas > 1` o campo é obrigatório — anulá-lo responde `422` daqui, não `400` do banco |
| `pix` | `false` | oferece Pix no mesmo link; o QR é gerado pelo banco |
| `expira_em` | 7 dias (banco) | ISO 8601 |
| `redirect_url` | — | precisa começar com `http://` ou `https://`. Quem publica essa URL é o banco, na página dele, na frente de quem está digitando o cartão — esquema não navegável responde `422` |
| `pagador` | — | se enviado, o endereço exige `street`, `number` (**numérico**), `city`, `state`, `zip_code` |

Responde **201** com `{id, url, status, expira_em}` e o header `Location`
apontando para `GET /checkout/{id}` já com `tenant_id`, `provider` e `banco`.
A `url` do corpo é o que se manda ao cliente; o `Location` é para consultar.

**Mande `Idempotency-Key` se houver botão humano na frente disto.** Sem a chave,
duplo clique cria **dois links para a mesma venda** — e nada impede o pagador de
pagar os dois. Com a chave, o reenvio devolve o mesmo link sem tocar no banco:

```bash
curl -X POST .../checkout -H 'Idempotency-Key: venda-42' -d @pedido.json
```

A chave vale por tenant. Reusá-la com outro pedido responde `422` — uma chave
identifica **uma** requisição, e devolver o link errado seria pior que recusar.
Pedido aqui é o `checkout` **mais o destino** (`provider` e `banco`): a mesma
chave apontada para outro banco é pedido novo, não reenvio. Sem o header, o
comportamento é o de sempre.

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
Movimentações da conta PJ no período. **C6, Sicoob e Inter** — outro banco
responde `422` apontando para o retorno CNAB ou o OFX, não `500`.

**A resposta é crua do banco.** Os três shapes são diferentes de verdade
(`transactions` no C6, `resultado.transacoes` no Sicoob, `transacoes` no Inter),
e normalizá-los aqui inventaria um formato que nenhum deles tem — o Swagger traz
um exemplo de cada. O que esta rota unifica é a **chamada**: mesmo par de datas,
mesma autenticação, mesmo erro para quem não oferece.

| Parâmetro | Observação |
|---|---|
| `start_date`, `end_date` | `YYYY-MM-DD`, conferidos aqui. `end_date` anterior a `start_date` é `422` — invertido o banco devolve lista vazia, que se lê como "não houve movimento" |
| `numero_conta` | conta corrente, **usada pelo Sicoob**. Omitido vai `0` — que era o que a rota mandava sempre, por não ter onde receber o valor |
| `banco=sicoob` | a API dele é **mensal**: as duas datas no mesmo mês, senão `422` com a regra dita. Limite do banco, não desta rota |

### `POST /config/webhook-banco`
Registra no banco a URL que receberá notificações
(`{tenant_id, provider, banco, url, service: BANK_SLIP|CHECKOUT}`); `GET`/`DELETE`
com `?service=` consultam/removem. **C6 e Inter** — outro banco responde `422`
apontando para `/config/webhook-pix` ou para a consulta ativa.

### `PUT /config/webhook-pix`
Webhook BACEN **por chave**: o banco chama a URL quando um Pix cai naquela chave.
Corpo `{tenant_id, provider, banco, chave, url, credentials?}`; `GET`/`DELETE`
com `?chave=` consultam/removem. **C6, Sicoob e Inter** (dialeto BACEN).

> **A `url` é conferida antes de ir ao banco.** Quem a chama é o **banco**, de
> fora, pela internet pública — então ela precisa ser `https` e ter destino
> alcançável. `http://localhost`, `10.x`, `169.254.169.254` e afins eram aceitos
> com `200`, e o cadastro *parecia* feito: o cliente só descobria que não recebia
> notificação quando um pagamento se perdia. `http://` é recusado por outro
> motivo — o evento leva valor, pagador e id da cobrança no corpo.
>
> Em homologação com túnel local, `WEBHOOK_URL_PERMITE_LOCAL=1` libera os dois.

As seis respostas são **cruas do banco** (confirmação no formato dele).

---

## 📊 Conciliação (C6 Pay)

### `GET /conciliacao/recebiveis` · `GET /conciliacao/transacoes`
Query: `tenant_id`, `start_date`, `end_date`, `provider=on`, `banco=c6`,
`page` (default 1, mínimo 1), `size` (default 50, de 1 a 100).

```bash
curl "http://localhost:8000/conciliacao/recebiveis?tenant_id=empresa_123&provider=on&banco=c6&start_date=2026-07-01&end_date=2026-07-31" \
  -H 'Authorization: Bearer bapi_kJx...'
# 200 → {"page": 1, "last_page": 3, "total_items": 120, "items": [{...}]}
```

**As datas são conferidas aqui, não pelo banco.** `YYYY-MM-DD`, janela de no
máximo **60 dias** (limite do C6) e `end_date` não anterior a `start_date` —
fora disso, `422` antes da ida à rede. O período invertido é o que mais importa
recusar: o banco responde **lista vazia**, e quem chama lê isso como "não houve
movimento no período".

**Só o C6 oferece** (C6 Pay). Outro banco responde `422` dizendo isso — antes
respondia `500`. Para o caminho offline, a conciliação é pelo arquivo de retorno
(`POST /api/retorno`) ou pelo OFX (`POST /api/ofx/parse`).

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

**O `{banco}` é `c6`, `sicoob` ou `inter`, em minúsculas.** Qualquer outra coisa
— incluindo `C6` — responde `422`, e não `200`. A diferença importa: `200` diz ao
banco "recebi, pode parar de reentregar", então um slug errado na URL cadastrada
transformava toda notificação em pagamento perdido em silêncio. O corpo também
precisa ser um objeto JSON não vazio: `"texto"` e `[1,2,3]` davam `500`, e o
banco reentregava em loop um payload que nunca ia funcionar.

### `GET /health`
`{"status": "ok"}`.

---

## 🔁 Pix Automático (BACEN) — `on` apenas

Débito recorrente autorizado **uma vez** pelo pagador. O dialeto é o do BACEN
(`rec`, `solicrec`, `locrec`, `cobr`), igual em todo PSP, e o gateway o
implementa uma vez só — para um banco novo custa o prefixo e a autenticação.

Quem oferece: **C6, Sicoob e Inter**. O **Itaú não** — as rotas respondem `422`
nomeando quem oferece. O que cada banco de fato respondeu está em
[pix-automatico.md](../development/pix-automatico.md).

| Método | Rota | Jornada |
|---|---|---|
| `POST` | `/pix-automatico/recorrencias` | cria a recorrência (`rec`) |
| `GET` | `/pix-automatico/recorrencias` | lista do período (RFC3339) |
| `GET` · `PATCH` | `/pix-automatico/recorrencias/{id_rec}` | consulta · altera/cancela (J4) |
| `POST` | `/pix-automatico/solicitacoes` | pede autorização no app do pagador (J1) |
| `GET` · `PATCH` | `/pix-automatico/solicitacoes/{id_solic}` | consulta · revisa/cancela |
| `POST` | `/pix-automatico/locations` | location do QR de adesão (J2) |
| `GET` | `/pix-automatico/locations/{loc_id}` | payload do QR |
| `DELETE` | `/pix-automatico/locations/{loc_id}/recorrencia` | desvincula (invalida o QR) |
| `PUT` | `/pix-automatico/cobrancas/{txid}` | agenda a cobrança do ciclo (J3) |
| `GET` | `/pix-automatico/cobrancas` | lista do período |
| `GET` · `PATCH` | `/pix-automatico/cobrancas/{txid}` | consulta · revisa/cancela |
| `POST` | `/pix-automatico/cobrancas/{txid}/retentativa/{data}` | retentativa pós-vencimento |
| `PUT` | `/pix-automatico/config/webhooks` | `webhookrec` e/ou `webhookcobr` |

> **O agendamento do ciclo é seu, não da API.** A regra BACEN manda criar a
> `cobr` **pelo menos 2 dias antes** do vencimento; este gateway é interface de
> consumo (stateless) e não roda cron. Quem agenda é o produto que chama.
>
> A API recusa `data_vencimento` **no passado** — não existe agendar para
> ontem. Os 2 dias de antecedência ficam como aviso e não como trava: não está
> claro se o BACEN conta dia corrido ou útil, e travar errado impediria um
> agendamento que o banco aceita.
>
> `valor_fixo` (`valorRec`) e `valor_minimo` (`valorMinimoRecebedor`) são
> **mutuamente exclusivos** — mandar os dois, ou nenhum, é `422`.

**Conferido antes de ir ao banco:** o `txid` da `cobr` segue o padrão BACEN
(`^[a-zA-Z0-9]{26,35}$`, o mesmo da cob/cobv), `inicio`/`fim` das listagens
precisam ser RFC3339 e não podem estar invertidos, a `{data}` da retentativa
precisa ser data, e o `PATCH` precisa de ao menos um campo. A URL do
`/config/webhooks` segue a mesma regra do `/config/webhook-*` — https e
alcançável de fora, porque quem a chama é o banco.

## 💸 Pix recebidos e devolução — `on` apenas

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/pix/recebidos?inicio=&fim=` | Pix creditados no período |
| `GET` | `/pix/recebidos/{e2eid}` | um Pix pelo end-to-end id |
| `PUT` | `/pix/recebidos/{e2eid}/devolucao/{id}` | solicita devolução |
| `GET` | `/pix/recebidos/{e2eid}/devolucao/{id}` | status da devolução |

## 📦 Jobs em lote (assíncrono)

Para volume acima do que o síncrono aguenta. Responde **`202`** com `job_id`;
os artefatos saem por **referência** (href + `sha256`), nunca em base64.
Contrato e limites em [plano-jobs-lote.md](../development/plano-jobs-lote.md).

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/jobs/boletos` | **202** + `job_id`; `Idempotency-Key` repetida devolve o mesmo |
| `GET` | `/jobs/boletos/{job_id}` | estado, contadores e métricas |
| `GET` | `/jobs/boletos/{job_id}/items` | itens paginados (`limite` 1–500, `offset`≥0, filtro `status`: `pending`\|`completed`\|`failed`) |
| `GET` | `/jobs/boletos/{job_id}/items/{item_id}` | um item, com resultado ou `errors` |
| `GET` | `/jobs/boletos/{job_id}/artifacts` | manifesto (nome, bytes, `sha256`, href, `expira_em`) |
| `GET` | `/jobs/boletos/{job_id}/artifacts/items/{nome}` | PDF de um item |
| `GET` | `/jobs/boletos/{job_id}/artifacts/{nome}` | zip · `manifest.json` · `errors.json` |
| `POST` | `/jobs/cnab/remessas` | **202** + sublotes determinísticos |
| `GET` | `/jobs/cnab/remessas/{job_id}` | estado e sublotes |
| `GET` | `/jobs/cnab/remessas/{job_id}/files` | manifesto: 1 arquivo por sublote |
| `GET` | `/jobs/cnab/remessas/{job_id}/files/{nome}` | download do `.rem`, do zip ou do manifesto |

> Item inválido **não derruba o lote**: o job termina `partially_completed` e os
> demais artefatos ficam disponíveis.

**Todo link da resposta é seguível como está.** `self`, `items`, `artifacts`,
`files` e os `href` do manifesto já vêm com `tenant_id` — as rotas de consulta e
download exigem, porque é ele que separa os clientes, e o link sem ele respondia
`422`. Basta seguir o que a resposta oferece, sem remontar URL.

As rotas de artefato respondem **`410`** quando a retenção vence
(`retencao_dias` no manifesto) — diferente do `404` de "nunca existiu".

## 🔔 Configuração de webhook no banco

| Método | Rota | O que faz |
|---|---|---|
| `POST` · `GET` · `DELETE` | `/config/webhook-banco` | webhook de boleto (C6, Inter) |
| `PUT` · `GET` · `DELETE` | `/config/webhook-pix` | webhook Pix **por chave** (BACEN) |

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

### Boleto offline (CNAB, 19 bancos) — sem credenciais de banco

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
