# Estudo — link de pagamento com cartão (C6 e Sicoob)

> Estudo de caso. **Nada disto está implementado.** O documento existe para que a
> decisão seja tomada com os fatos na mesa, e para que a pergunta não precise ser
> refeita daqui a seis meses.
>
> **As decisões de produto já foram tomadas** — juros `BY_SELLER`, baixa na
> aprovação, nenhum dado de cartão do nosso lado, e cartão só no C6. Estão em
> [Decisões tomadas](#decisões-tomadas), com o que cada uma fecha e o que cada
> uma custa. Nenhuma pergunta segue em aberto; o que falta é implementar.

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

A capacidade nasce **assimétrica**, como já acontece com o Bolepix — e a
[decisão 4](#decisões-tomadas) diz que fica assim: cartão **somente no banco que
tem**. O `exige_capacidade` já trata o caso: `provider=sicoob` recebe `422`
dizendo para onde ir, em vez de `500`.

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
| `interest_type` | `BY_SELLER`, `BY_ISSUER` | **quem paga os juros** — parcelado loja ou emissor; decidido: `BY_SELLER` |
| `capture` | booleano | captura automática (default) ou posterior |
| `authenticate` | `REQUIRED`, `OPTIONAL`, `NOT_REQUIRED` | autenticação pelo emissor |
| `recurrent` | booleano | sinaliza recorrência; melhora aprovação |
| `save_card` | booleano | tokeniza; o token volta na resposta |
| `soft_descriptor` | texto | o que aparece na fatura do portador |

O mesmo checkout aceita **Pix** no mesmo objeto (`payment.pix.key`, com `AUTO`
gerando o QR) — ou seja, um único link pode oferecer cartão e Pix.

**`interest_type` é `BY_SELLER`, por contrato de cliente** ([decisão
1](#decisões-tomadas)) — valor decidido, mas não constante desta API: o default
é `BY_SELLER` e o contrato pode dizer outra coisa. Isso tem uma consequência de
desenho, e ela vale mesmo que nenhum contrato divirja: esta API **não
guarda configuração comercial de cliente**. O `credential_store` cifra
credencial por `(tenant, provider)` e nada além disso; encargos de boleto já
chegam **no corpo da requisição** (`multa`, `juros` e `desconto` em
`schemas.py:59-73`, repassados ao banco na forma dele). `interest_type` e
`installments` seguem a mesma regra: **campos do payload**, com o Consumidor da
API resolvendo-os a partir do contrato antes de chamar. A API continua sem
estado de negócio.

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

**Decisão: modo link, e só ele** ([decisão 3](#decisões-tomadas)). Nem esta API
nem o Consumidor gravam dado de cartão — nem em trânsito, nem tokenizado. Isso
promove o parágrafo acima de recomendação a **restrição**: o checkout
transparente fica fora do escopo em definitivo, e `save_card` também. Tokenizar
significa guardar um token que **é** um meio de pagamento; a decisão de não
gravar dado de cartão não distingue PAN de token.

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

**E não é só o receptor.** O banco notifica *esta API*, não o Consumidor —
ele nem conhece o Consumidor. O caminho completo já está montado: o receptor
normaliza o evento, `subscriptions.resolve_callback(tenant_id)` descobre qual
consumidor é dono daquele tenant, e `forwarder.forward_event` reenvia por POST
assinado com **HMAC-SHA256** (`X-Signature: sha256=…`, validado com
`hmac.compare_digest` do outro lado). Nenhuma dessas três peças precisa ser
escrita para o cartão funcionar; muda só o `service` no cadastro.

Vale corrigir aqui um desenho intuitivo e errado: *banco → Consumidor* não
acontece. É *banco → Cobrança-API → Consumidor*, e o segundo salto é o que
entrega o evento já normalizado e assinado.

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

**Isto está decidido e não entra:** cartão existe somente no banco que tem
([decisão 4](#decisões-tomadas)). A seção acima permanece porque a pergunta vai
voltar — e quando voltar, o `404` em sete rotas do sandbox e os três subdomínios
que não resolvem já estão medidos, com data.

---

## Desenho proposto (se for adiante)

Espelhando o `/bolepix`, que resolve o mesmo formato de problema:

```
POST   /checkout        → {id, url, status, expira_em}
GET    /checkout/{id}   → status normalizado
DELETE /checkout/{id}   → cancela
```

O corpo do `POST` carrega o que o contrato do cliente definiu — `parcelas` e
`juros_por` (`loja` → `BY_SELLER`, `emissor` → `BY_ISSUER`, default `loja`), no
mesmo espírito de `multa`/`juros`/`desconto` do boleto: a API traduz para a
forma do banco e não guarda nada. O default cobre a decisão 1 sem obrigar todo
chamador a repeti-la; `parcelas > 1` continua exigindo o campo explícito do lado
do C6, e essa validação é `422` daqui, não `400` do banco — a mesma regra que o
endereço do Bolepix passou a seguir.

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

**Checkout transparente e `save_card`.** Trazem dado de cartão para dentro —
o primeiro como PAN, o segundo como token. Fora de escopo por decisão, não por
esforço. Ver acima.

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
host).

**Decisão: a baixa acontece em `PAID`** ([decisão 2](#decisões-tomadas)) — na
aprovação do cartão, não na liquidação do recebível. A API de Recebíveis fica
**fora do escopo**, e o mapeamento da seção anterior (`PAID` → `liquidado`) é o
comportamento final desta API, não um estágio.

**Onde a regra mora:** no Consumidor da API. Esta API entrega `liquidado` e
para aí — não existe baixa aqui para acontecer cedo ou tarde, porque contrato e
parcela não são conceitos deste lado. Isso importa para ler o resto desta seção:
o que segue não são pendências da API, são coisas que o Consumidor e quem opera
o financeiro precisam saber.

O que a decisão **não** resolve, e precisa ficar visível para quem opera: a
conciliação bancária passa a divergir da baixa por até 30 dias no crédito. No
boleto e no Pix, `liquidado` e extrato batem no mesmo dia; no cartão, não. Quem
concilia por extrato vai ver parcela baixada sem crédito correspondente, e isso
é **esperado** — não é erro de integração. Se um dia essa divergência precisar
ser fechada por dentro, a porta é a API de Recebíveis; a decisão de hoje é que
ela não abre agora.

**A decisão 1 acrescenta uma segunda divergência, e essa não é de prazo.** Com
`BY_SELLER`, o juro do parcelamento sai do repasse — some-se a isso o MDR, e o
crédito que entra é **menor** que o valor baixado, não só mais tarde. Quem
concilia cartão está comparando duas grandezas que não são a mesma: a parcela
fecha por `valor`, o extrato traz `valor − juros − taxas`, em D+30. No boleto,
`valor` baixado e `valor` creditado coincidem. Nenhuma das duas diferenças é
defeito; as duas precisam estar escritas antes de alguém abrir chamado.

## O que nenhuma API resolve

- **Habilitação comercial** do C6 Pay como adquirente — é contrato, não
  credencial.
- **Taxas** por bandeira, modalidade e parcelamento.
- **Chargeback**: não aparece em nenhum dos specs consultados.

## Decisões tomadas

As perguntas em aberto da primeira versão deste estudo foram respondidas. O que
segue é decisão de produto, não implementação — **nada disto foi codificado.**

Duas delas dizem a mesma coisa por caminhos diferentes: **a regra é do
Consumidor da API, não desta API.** Nem o juro do parcelamento nem a baixa da
parcela viram comportamento daqui. Esta API traduz — recebe o que o chamador
mandou, fala com o banco, normaliza o status de volta — e não guarda regra de
negócio de cliente nenhum. Vale a pena reler as decisões 1 e 2 com isso em
mente: as duas movem responsabilidade para fora, não para dentro.

**1. Os juros do parcelamento são do lojista — `BY_SELLER`, e quem configura é o
Consumidor da API.** O valor chega **no payload**, como os encargos do boleto já
chegam, com `BY_SELLER` de default. Quem decide é o chamador, a partir do
contrato que ele tem com o cliente dele; esta API nem conhece esse contrato. Não
nasce tabela de configuração comercial aqui — ver [Configuração do
cartão](#configuração-do-cartão).

O que `BY_SELLER` significa em dinheiro: o portador paga `valor / parcelas` sem
acréscimo, e o juro do parcelamento sai do repasse ao lojista. `BY_ISSUER`
inverteria — o emissor cobraria o juro do portador e o lojista receberia cheio,
ao custo de o cliente final ver um valor maior que o da parcela. A escolha
protege o valor que o pagador vê, e cobra por isso no caixa. A consequência
combinada com a decisão 2 está em [O ponto que não é
endpoint](#o-ponto-que-não-é-endpoint).

**2. A parcela é quitada na aprovação do cartão — e essa regra é do Consumidor
da API.** A fronteira importa: **esta API não dá baixa em nada.** Ela não conhece
contrato nem parcela; o que ela faz é traduzir `PAID` para `liquidado` e
devolver. Quem decide que `liquidado` quita a parcela é o Consumidor, e é lá que
a regra mora — do mesmo jeito que já mora hoje para boleto e Pix.

O ganho é justamente esse: o Consumidor trata as três formas de pagamento com a
mesma verificação de `status == liquidado`, sem um ramo especial para cartão. E
a API de Recebíveis C6 Pay sai do escopo por consequência — se a baixa não
depende da liquidação do recebível, não há por que trazer essa consulta para
dentro. O custo aceito está em [O ponto que não é
endpoint](#o-ponto-que-não-é-endpoint).

**3. Nem a API nem o Consumidor gravam informação de cartão.** Isto fecha a
escolha de arquitetura: **modo link**, sem checkout transparente e sem
`save_card`. O PAN é digitado no domínio do C6 e o escopo PCI-DSS fica com o
banco — não por conveniência, mas porque a alternativa muda o assunto de
integração para certificação. Ver [Link ou
transparente](#link-ou-transparente--e-por-que-isso-decide-a-arquitetura).

**4. Cartão existe somente no banco que tem — C6.** Cartão pelo Sicoob **não é
requisito**. A capacidade nasce assimétrica e assim permanece: `provider=sicoob`
recebe `422` do `exige_capacidade` dizendo para onde ir, exatamente como já
acontece com o Bolepix. Integrar a Sipag como terceiro provider **não entra no
escopo** — não por ser inviável, mas por não ser pedido.

Isto encerra a lista: nenhuma pergunta deste estudo segue em aberto.

O que a decisão custa, para ficar dito: cliente atendido só pelo Sicoob não tem
a terceira forma de pagamento. Boleto e Pix continuam nos dois bancos; o link de
cartão, não. Se um dia virar requisito, a [decisão 3](#decisões-tomadas)
permanece válida e vira o critério de seleção — a Sipag só serviria se
oferecesse link hospedado, porque integração que exija cartão no nosso domínio
já está descartada.

## De quem é cada configuração

As decisões 1 e 2 puxaram a fronteira para um lugar específico. Vale varrer o
resto do Checkout com o mesmo critério, antes de a implementação decidir por
omissão: **se o valor muda de cliente para cliente, ele é do Consumidor da API e
viaja na requisição; se é da integração, é daqui.**

O precedente já existe e não é novo: `account_config` é descrito no schema como
*"blob por provider, não unificado de propósito"*, e até credencial pode vir no
request. Esta API já é um tradutor configurado por chamada.

### Do Consumidor da API — vai no corpo da requisição

| Campo do Checkout | Por que é dele |
|---|---|
| `installments` — parcelas | Até quantas vezes cada cliente pode parcelar é política comercial, e muda por contrato |
| `interest_type` — `juros_por` | [Decisão 1](#decisões-tomadas). Default `loja` |
| `type` — `CREDIT`/`DEBIT` | Aceitar débito, crédito ou os dois é oferta dele |
| `expiration_date_time` — `expira_em` | O banco usa 7 dias quando omitido; amarrar ao vencimento da parcela é regra de cobrança, e cobrança é dele |
| `redirect_url` | Para onde o pagador volta depois de pagar — é página do Consumidor. Esta API não tem para onde mandar |
| `soft_descriptor` | O nome que aparece na fatura do portador é a marca do lojista, não a nossa |
| `recurrent` | Só o Consumidor sabe se aquela cobrança faz parte de um contrato recorrente |
| Pix no mesmo link (`payment.pix.key`) | Um link pode oferecer cartão **e** Pix. Oferecer ou não é decisão de produto dele |
| URL do webhook | **Já funciona assim hoje** — `POST /webhooks/banco` registra a URL por tenant, com `service: CHECKOUT` |

`authenticate` (`REQUIRED`/`OPTIONAL`/`NOT_REQUIRED`) fica na mesma coluna, com
uma ressalva: é apetite de risco — autenticação do emissor derruba fraude e
derruba conversão junto —, mas o contrato com a adquirente pode impor um piso.
Expor como campo do Consumidor está certo; assumir que ele escolhe livremente,
não.

### Desta API — não é configurável por quem chama

Credenciais e seu cofre; qual provider tem a capacidade; o mapeamento de status
para o enum normalizado; as validações que recusam antes de chamar o banco
(endereço do pagador, `parcelas > 1` sem `juros_por`); e a tradução de erro do
banco em `4xx`/`5xx`. Nada disso muda por cliente — muda por integração.

### O que o Consumidor **não** pode configurar

Esta é a lista que precisa virar código, não parágrafo:

- **`save_card` e o checkout transparente.** A [decisão 3](#decisões-tomadas) só
  é real se o campo **não existir** no schema. Se o corpo for repassado ao banco
  sem filtro, basta um chamador mandar `save_card: true` para o token entrar no
  fluxo — e a decisão de não guardar dado de cartão terá sido revogada por um
  cliente, sem ninguém revisar. Documentar não segura isso; ausência de campo,
  sim.
- **`capture` em duas fases.** Fora de escopo: cobrança de parcela captura na
  hora. Deixar exposto convida a um estado "autorizado mas não capturado" que
  nenhum status normalizado representa.
- **`provider` para cartão.** Só o C6 tem ([decisão 4](#decisões-tomadas)); o
  resto é `422` do `exige_capacidade`, não campo de configuração.

O critério que separa as duas últimas seções: **configuração é o que varia sem
mudar o desenho.** Quando mudar o valor mudaria o que a API garante — que dado
de cartão não passa por aqui, que todo status cabe no enum — não é configuração,
é decisão, e decisão mora no código.
