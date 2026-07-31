# Estudo — link de pagamento com cartão (C6 e Sicoob)

> Estudo de caso. **Nada disto está implementado.** O documento existe para que a
> decisão seja tomada com os fatos na mesa, e para que a pergunta não precise ser
> refeita daqui a seis meses.

## Contexto

O **Consumidor da API** — o terceiro produto da separação, que vive fora deste
repositório ([separacao-3-produtos.md](./separacao-3-produtos.md)) — quer
oferecer **três formas de pagamento**: boleto, Pix e link de cartão. O link é
enviado ao cliente, que paga em crédito ou débito.

Boleto e Pix já existem aqui, nos dois bancos. A pergunta é o que falta para o
terceiro.

## Resposta curta

| Banco | Tem API de link de pagamento? |
|---|---|
| **C6** | **Sim** — API Checkout v1.1.5, no mesmo host e na mesma autenticação que o projeto já usa |
| **Sicoob** | **Não** — cartão é da Sipag, adquirente do grupo, sem API pública |

A capacidade nasceria **assimétrica**, como já acontece com o Bolepix. O
`exige_capacidade` já trata isso: `provider=sicoob` recebe `422` dizendo para
onde ir, em vez de `500`.

---

## C6 — API Checkout

O portal do desenvolvedor é uma SPA, mas publica os specs OpenAPI em
`/yamls/<api>.yaml`. O do Checkout tem 54 KB e declara:

```
POST   /v1/checkouts/                    criar   → devolve a URL do link
POST   /v1/checkouts/authorize           autorizar
GET    /v1/checkouts/{id}                consultar
PUT    /v1/checkouts/{id}/capture        capturar
PUT    /v1/checkouts/{id}/cancel         cancelar
GET    /v1/checkouts/generate/public-key chave pública (checkout transparente)
GET    /v1/checkouts/sdk-doc             documentação do SDK
```

**Servidores:** `baas-api-sandbox.c6bank.info` e `baas-api.c6bank.info` — os
mesmos do boleto e do Bolepix. Mesma OAuth + mTLS, mesmo certificado, mesmo
cofre de credenciais. Não é integração nova: é rota nova sobre o
`OAuthMtlsClient` que já existe.

### Configuração do cartão

| Campo | Valores | Efeito |
|---|---|---|
| `type` | `DEBIT`, `CREDIT` | tipo da transação |
| `installments` | inteiro | máximo de parcelas; `>1` exige `interest_type` |
| `interest_type` | `BY_SELLER`, `BY_ISSUER` | **quem paga os juros** — parcelado loja ou emissor |
| `capture` | booleano | captura automática (default) ou posterior |
| `authenticate` | `REQUIRED`, `OPTIONAL`, `NOT_REQUIRED` | autenticação pelo emissor |
| `recurrent` | booleano | sinaliza recorrência; melhora aprovação |
| `save_card` | booleano | tokeniza; o token volta na resposta |
| `soft_descriptor` | texto | o que aparece na fatura do portador |

O mesmo checkout aceita **Pix** no mesmo objeto (`payment.pix.key`, com `AUTO`
gerando o QR) — ou seja, um único link pode oferecer cartão e Pix.

### Ciclo de vida

```
CREATED → IN PROGRESS → AUTHORIZED, CONFIRMATION PENDING
        → CONFIRMATION REQUESTED → PAID
```

Terminais: `PAID`, `DECLINED`, `CANCELLED`, `EXPIRED`, `ERROR`.

Expiração default de **7 dias** quando `expiration_date_time` é omitido; sem
pagamento, o status vira `EXPIRED` sozinho.

### Link ou transparente — e por que isso decide a arquitetura

São dois modos:

- **Link** — o C6 devolve `url` (`https://checkout.c6bank.info/{id}`), você
  encaminha o pagador, e ele volta pela `redirect_url`.
- **Transparente** — SDK e chave pública; o cartão é digitado na **sua** página
  e cifrado antes de sair.

Para enviar o link ao cliente, só o primeiro serve — e ele tem uma propriedade
que vale mais que a conveniência: **nenhum dado de cartão passa por esta API nem
pelo Consumidor da API**. O PAN é digitado no domínio do C6, e o escopo
PCI-DSS fica com o banco. O transparente inverte isso, e aí a discussão deixa de
ser sobre um endpoint e passa a ser sobre certificação.

**Recomendação: modo link.**

### Notificação — metade já existe

O spec do Checkout **não tem webhook**: zero ocorrências de `webhook`,
`callback` ou `notification` nos 54 KB. A notificação vem pela API de webhooks
genérica do C6 — e essa o projeto **já fala**:

```python
# gateway/app/providers/c6.py
def cadastrar_webhook(self, *, url: str, service: str) -> dict[str, Any]:
    """Registra a URL de notificação no banco (service: BANK_SLIP | CHECKOUT)."""
```

`schemas.py` já expõe `service: "BANK_SLIP" | "CHECKOUT"` no `POST
/webhooks/banco`, e o receptor `/webhooks/{banco}/{tenant_id}` já existe.

Sem isso, o link viraria polling — e um contrato com 36 parcelas em aberto
viraria polling em 36 recursos.

### Armadilha já conhecida

O `payer.address` do Checkout exige **`street`, `number`, `city`, `state`,
`zip_code`**, com `number` **numérico**. É a mesma pegadinha do Bolepix: endereço
ausente vira `400` do banco, e `number` como string também. O `_payer`
centralizado e a validação de endereço já cobrem os dois casos.

---

## Sicoob — não há equivalente

O catálogo do sandbox do Sicoob tem dez APIs:

```
cobranca-bancaria/v3          conta-corrente/v4       pix/api/v2
cobranca-bancaria-pagamentos  convenios-pagamentos/v2 pix-pagamentos/v2
investimentos/v2              poupanca/v3             spb/v2
payments/v2/itp (Open Finance)
```

Nenhuma trata de cartão. Sondando o sandbox em `/checkout`, `/checkouts`,
`/cartoes`, `/cards`, `/link-pagamento`, `/adquirencia` e `/ecommerce`: **`404`
em todos**. O catálogo autenticado do portal (`/portal-developers/v2/apis`)
responde `401`, então não dá para enumerar de fora — mas a lista do sandbox é a
mesma que o portal publica.

A adquirência do Sicoob é a **Sipag**, criada em 2014, e ela **tem** link de
pagamento, e-commerce e cobrança recorrente — como produto. O que não existe é
porta de entrada programática pública: `developers.sipag.com.br`,
`docs.sipag.com.br` e `desenvolvedores.sipag.com.br` **não resolvem**. O site
publica um guia de boas práticas de segurança do link de pagamento em PDF, o que
confirma que o produto é operado por painel, não por API.

**Consequência prática:** cartão pelo Sicoob significaria integrar com a Sipag
como um **terceiro provider** — outro contrato, outras credenciais, outro
mecanismo de autenticação, e possivelmente sem sandbox. Não é "mais um método no
provider Sicoob".

---

## Desenho proposto (se for adiante)

Espelhando o `/bolepix`, que resolve o mesmo formato de problema:

```
POST   /checkout        → {id, url, status, expira_em}
GET    /checkout/{id}   → status normalizado
DELETE /checkout/{id}   → cancela
```

Exclusivo do C6, via `exige_capacidade`. Mapeamento para o `Status` normalizado,
que **cabe inteiro** — nenhum status novo:

| C6 | Projeto |
|---|---|
| `CREATED`, `IN PROGRESS`, `AUTHORIZED…`, `CONFIRMATION REQUESTED` | `pendente` |
| `PAID` | `liquidado` |
| `CANCELLED` | `baixado` |
| `EXPIRED` | `expirado` |
| `DECLINED`, `ERROR` | `erro` |

O Consumidor da API trata as três formas de pagamento com o mesmo
`status == liquidado`.

### O que deixaria de fora

**Captura em duas fases** (`authorize` → `capture`). Serve para reservar valor e
capturar depois — típico de e-commerce com estoque. Cobrança de parcela captura
na hora.

**Checkout transparente.** Traz dado de cartão para dentro. Ver acima.

**Recebíveis.** Ver a próxima seção.

### Esforço

Um método no provider, um router de três rotas, schema, mapeamento de status e
testes — mesmo molde do `/bolepix`. O webhook não custa nada: já está pronto.

---

## O ponto que não é endpoint

**Status `PAID` não é dinheiro na conta.** O checkout vira `PAID` quando a
transação é aprovada; crédito liquida em D+30, ou antes se houver antecipação.

Se o Consumidor da API baixar a parcela em `PAID`, o contrato fecha correto —
mas a **conciliação bancária não bate no mesmo dia**, como bate no boleto e no
Pix. São dois eventos distintos que no boleto acontecem juntos.

Isso é outra API: `Transações e Recebíveis C6 Pay`
(`GET /v1/c6pay/statement/receivables` e `/transactions`, spec de 18 KB, mesmo
host). É decisão de produto se ela entra ou se a baixa em `PAID` basta.

## O que nenhuma API resolve

- **Habilitação comercial** do C6 Pay como adquirente — é contrato, não
  credencial.
- **Taxas** por bandeira, modalidade e parcelamento.
- **Chargeback**: não aparece em nenhum dos specs consultados.

## Perguntas em aberto

1. `interest_type` é `BY_SELLER` ou `BY_ISSUER`? Muda quanto entra no caixa.
2. A baixa acontece em `PAID` ou só na liquidação do recebível?
3. Cartão pelo Sicoob é requisito, ou C6-só é aceitável? Se for requisito, é
   projeto de integração com a Sipag, não extensão deste provider.
