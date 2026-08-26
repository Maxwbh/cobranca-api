---
title: Serviços online por banco — os 18 do catálogo offline
description: Catálogo completo de serviços online de cada uma das 18 instituições do caminho offline — boleto, Pix, extrato, pagamentos, webhook — com o que cabe no produto e o que não cabe.
---

# Serviços online, banco a banco

O caminho `off` atende 19 bancos por CNAB. **Quais deles poderiam ser `on`?**
Esta página responde uma por uma: primeiro o resumo, depois o catálogo completo
de cada instituição, com o que cabe no produto e o que não cabe.

<div class="faixa-stats" aria-label="Resumo do levantamento">
  <div><strong>18</strong><span>bancos no catálogo offline</span></div>
  <div><strong>14</strong><span>com API REST de boleto</span></div>
  <div><strong>15</strong><span>com API de Pix cobrança</span></div>
  <div><strong>3</strong><span>sem caminho online</span></div>
</div>

Não é roadmap — é levantamento: o que a instituição publica hoje, com a fonte, e
o que falta para virar provider. Como cada afirmação foi apurada — e o que
deliberadamente **não** valeu como evidência — está em
[Método](#método-e-o-que-cada-evidência-vale), no fim. O caminho `on` existe para quatro instituições
(C6, Sicoob, Inter, Itaú), das quais três estão nesta lista: o Inter não tem
layout na engine, e por isso não é um dos 18.

## A tabela

Legenda: ✅ API REST · ⚠️ existe, com ressalva · ⛔ não oferece · 🔒 documentação
fechada (só com gerente/convênio).

| # | Banco | Boleto registrado | Pix cobrança | Portal do desenvolvedor |
|---|---|---|---|---|
| 001 | Banco do Brasil | ✅ API Cobrança | ✅ | `developers.bb.com.br` |
| 004 | Banco do Nordeste | ⛔ **só CNAB 400** | ✅ API Pix | credencial pelo internet banking |
| 021 | Banestes | ✅ API Cobrança | ✅ API Pix Cobrança | `desenvolvedores.banestes.com.br` *(respondeu)* |
| 033 | Santander | ✅ registro instantâneo | ✅ Pix para cobrança | `developer.santander.com.br` |
| 041 | Banrisul | ✅ API Cobrança de Títulos | ✅ API Pix | `developers.banrisul.com.br` *(respondeu)* |
| 070 | BRB | ✅ API Banking (registro automático) | ✅ boleto híbrido | sem portal público; credencial pelo gerente |
| 085 | Ailos | ✅ API de Cobrança Bancária | ✅ API Pix QR Code | pela cooperativa (Viacredi e demais) |
| 097 | CrediSIS | ⚠️ emissão por API com token | 🔒 | sem portal público localizado |
| 104 | Caixa | ⚠️ **WebService XML/SOAP** (SIGCB) | ✅ API Pix (+ Pix Automático) | `desenvolvedores.caixa.gov.br` |
| 136 | Unicred | ✅ Boleto + Pix numa integração | ✅ | `developer.unicred.com.br/api-portal` *(respondeu)* |
| 237 | Bradesco | ✅ Registro Online de Boletos | ✅ API Pix | `developers.bradesco.com.br` |
| 336 | **C6 Bank** | ✅ **integrado e homologado** | ✅ | `developers.c6bank.com.br` |
| 341 | **Itaú** | ✅ (provider esqueleto) | ✅ | `devportal.itau.com.br` *(respondeu)* |
| 399 | HSBC | ⛔ | ⛔ | — |
| 422 | Safra | 🔒 API existe, doc fechada | 🔒 | sem portal público; via gerente/Cash |
| 745 | Citibank | ⛔ **arquivo (Cash Management)** | ⛔ | portal corporativo, não de API |
| 748 | Sicredi | ✅ | ✅ API Pix | `developer.sicredi.com.br` *(respondeu)* |
| 756 | **Sicoob** | ✅ **integrado** | ✅ | `developers.sicoob.com.br` *(respondeu)* |

**Contagem:** boleto registrado por API REST em **14 dos 18**; Caixa tem, mas em
SOAP; Banco do Nordeste, Citibank e HSBC não têm. Pix cobrança em **15 dos 18**.

## As quatro exceções, que são o achado

Três bancos do catálogo **não** têm caminho online de boleto, e o motivo é
diferente em cada um — o que importa, porque só um deles é lacuna de produto:

- **Banco do Nordeste (004)** — tem API Pix, e **só CNAB 400** para boleto. É a
  única lacuna de verdade: banco vivo, cliente ativo, e a cobrança registrada
  continua por arquivo. Se alguém pedir BNB online, a resposta hoje é Pix.
- **Citibank (745)** — a cobrança é por transmissão de arquivo no Cash
  Management. Não é atraso: o varejo dele saiu do Brasil (vendido ao Itaú) e o
  que restou é banco de atacado, onde arquivo é o padrão do cliente. Também é o
  único dos 18 que não publica **nenhuma** família de pagamento no Open Finance.
- **HSBC (399)** — não existe mais como banco no Brasil: foi incorporado pelo
  Bradesco em 2016. O código 399 sobrevive como **layout CNAB legado**, e é só
  por isso que a engine o mantém. Não há portal, API ou convênio novo a pedir.

E uma quarta, de natureza diferente:

- **Caixa (104)** — tem cobrança online, mas em **WebService XML/SOAP**
  (`barramento.caixa.gov.br/sibar`, SIGCB), não REST. Um provider aqui não
  reaproveita o `OAuthMtlsClient`: é outro transporte, outro envelope e outra
  liberação (a `X-API-KEY` sai por chamado, não é self-service). O Pix, esse
  sim, é REST BACEN como todos.

## Catálogo completo, banco a banco

A tabela acima responde "dá para emitir?". Esta seção responde "o que mais tem
lá dentro?" — porque a decisão de escrever um provider não se toma só pelo
boleto: extrato e webhook mudam o que a API entrega em conciliação, e o resto do
catálogo é o que **não** entramos, pela
[régua de escopo](roadmap-providers.md#princípio-de-escopo-o-que-não-entra-em-provider-nenhum).

Os bancos estão agrupados por **como se chega neles**, que é o que decide a
ordem da fila. Dentro de cada grupo, por código.

Legenda: ✅ cabe e é usado hoje · 🔜 cabe e não está feito · ⛔ fora de escopo.

### ✅ Já integrados

<p class="chips"><span class="chip chip-on">C6 Bank · 336</span><span class="chip chip-on">Itaú · 341</span><span class="chip chip-on">Sicoob · 756</span></p>

Provider REST escrito e no catálogo. O Itaú entra aqui com ressalva: existe, e está desligado por flag até o payload fechar.

<details markdown="1">
<summary>Ver os 3 — catálogo de serviços</summary>

#### 336 · C6 Bank — [página própria](c6-rest.md) · **integrado**

Dez serviços catalogados (`C6-S01`…`C6-S10`): boleto ✅ · Pix ✅ · Bolepix ✅ ·
Pix Automático ✅ · webhooks ✅ · extrato ✅ · recebíveis de cartão ✅ ·
checkout ✅ · pagamentos/DDA ⛔. É o banco com a maior superfície usada.

#### 341 · Itaú — [página própria](itau-rest.md)

STS com **certificado dinâmico** e token de 5 min · cash management v2:
emissão 🔜, instrução (alterar/baixar/protestar) 🔜, consulta 🔜.
Credencial de cobrança **não é self-service** — sai por gerente/OfficerCash.
Não devolve PDF: quem renderiza é a engine.

#### 756 · Sicoob — [página própria](sicoob-rest.md) · **integrado**

Treze serviços catalogados (`SIC-S01`…`SIC-S13`): boleto ✅ · Pix ✅ ·
Pix Automático ✅ · extrato ✅ · saldo 🔜 · alteração de pagador 🔜 ·
**negativação** 🔜 · **protesto** 🔜 · movimentação (retorno por API) 🔜 ·
pagamentos ⛔ · SPB/poupança ⛔ · Open Finance ⛔.

</details>

### 🎯 Self-service — portal público e credencial sem intermediário

<p class="chips"><span class="chip">Banco do Brasil · 001</span><span class="chip">Banestes · 021</span><span class="chip">Banrisul · 041</span><span class="chip">Unicred · 136</span><span class="chip">Sicredi · 748</span></p>

Dá para começar hoje, sem pedir nada a ninguém: portal aberto, sandbox documentada, credencial na hora. É daqui que sai o próximo provider.

<details markdown="1">
<summary>Ver os 5 — catálogo de serviços</summary>

#### 001 · Banco do Brasil — [página própria](banco-do-brasil-rest.md)

Cobrança (boleto híbrido com Pix) 🔜 · Pix BACEN 🔜 · Pix Automático 🔜 ·
Arrecadação integrada ao Pix 🔜 · Extratos 🔜 · Pagamentos em lote ⛔.
Portal self-service com sandbox; exige **convênio de cobrança ativo**.

#### 021 · Banestes

Portal (respondeu): **Pix Cobrança** 🔜 · **Pix Arrecadação** 🔜 ·
**Pix Automático** 🔜 · Open Finance — Iniciação de Pagamentos ⛔ (é saída) ·
Catálogo de Risco (Pilar 3) ⛔ (dado regulatório, não cobrança).
A **cobrança de boleto existe fora do portal principal**, em
`dev.apps.banestes.b.br/docs/cobranca` (respondeu) — quem procurar só no portal
conclui, errado, que o banco não tem boleto por API.

#### 041 · Banrisul

Catálogo publicado com **cinco** APIs: **Pix** 🔜 · **Cobrança de Títulos**
(emitir, alterar, consultar, acompanhar; boleto tradicional ou híbrido) 🔜 ·
CORBAN Digital (pagar boletos e tributos) ⛔ · Consignado INSS ⛔ ·
Consignado RS ⛔. Portal lançado em 2025; sandbox liberada por e-mail.

#### 136 · Unicred

Marketplace de APIs com sandbox e homologação obrigatória antes da produção.
**Boleto + Pix numa única integração** 🔜 (registro em até 5 minutos, sem
arquivo). Autenticação por `client_id` + `access_token` no header. O catálogo
detalhado exige login no portal.

#### 748 · Sicredi

Pix 🔜 · **Cobrança Bancária v3 com webhook** 🔜 · Conta Corrente — extrato e
saldo 🔜 · Consentimento 🔜 · Multipag ⛔ · Conta Salário ⛔ · TED ⛔ ·
Pagamentos ⛔ · Investimentos ⛔ · Poupança ⛔.
mTLS nas APIs de maior criticidade (Pix, Multipag, Conta Salário, extrato e
saldo). A contratação e a liberação são feitas **pela cooperativa**, não pelo
portal.

</details>

### 🕓 Portal público, liberação burocrática

<p class="chips"><span class="chip">Santander · 033</span><span class="chip">Caixa · 104</span><span class="chip">Bradesco · 237</span></p>

A documentação existe e é boa; o custo está no certificado ICP-Brasil (Bradesco, Santander), no chamado para liberar chave (Caixa) e na homologação por tipo de operação.

<details markdown="1">
<summary>Ver os 3 — catálogo de serviços</summary>

#### 033 · Santander

Cobrança/boleto com **registro instantâneo** 🔜 · Pix para cobrança 🔜 ·
Webhook de notificação 🔜 · Workspaces (agrupamento de credencial) 🔜 ·
Extrato e saldo — via Open Finance consentido 🔜 · Boletos eletrônicos (contas a
pagar da empresa) ⛔ · Pagamentos de contas e tributos ⛔.
Certificado digital `.pem` carregado no portal; `client_id` + `client_secret`.

#### 104 · Caixa

Cobrança — registro por **WebService XML/SOAP** (SIGCB) e CNAB, instruções e
protesto ⚠️🔜 · Pix — QR dinâmico e estático, cobrança imediata, webhook,
devoluções 🔜 · **Pix Automático com convênio próprio** 🔜 · Extratos 🔜 ·
FGTS, GRF e tributos federais/estaduais/municipais ⛔ (arrecadação e pagamento).
`X-API-KEY` liberada por chamado — não é self-service.

#### 237 · Bradesco

Portal com **mais de 120 APIs**. O que toca o produto: emissão de boletos 🔜 ·
Pix, geração e recebimento 🔜 · saldos e extratos 🔜 · **conciliação bancária**
🔜 · notificações 🔜. Fora: pagamento de contas e tributos ⛔, transferências ⛔,
análise de crédito ⛔. mTLS com certificado **A1 ICP-Brasil**; sandbox aberta
inclusive para quem não é cliente.

</details>

### 🔒 Sem porta pública — credencial pelo gerente

<p class="chips"><span class="chip">BRB · 070</span><span class="chip">Ailos · 085</span><span class="chip">CrediSIS · 097</span><span class="chip">Safra · 422</span></p>

A API existe — há ERP integrado com todas —, mas o contrato sai por gerente. Não dá para começar pelo portal: começa pelo cliente que já tem o convênio.

<details markdown="1">
<summary>Ver os 4 — catálogo de serviços</summary>

#### 070 · BRB

Boleto por **API Banking (registro automático)** 🔜, ao lado de CNAB 240 e 400 ·
boleto híbrido com QR Pix 🔜. Sem portal público: credencial pelo gerente.

#### 085 · Ailos

API de **Cobrança Bancária** do sistema (transmissão instantânea, status
`REGISTRADO` na hora) 🔜 · **API Pix Cobrança** 🔜 (documentação em PDF, v3.4,
publicada pelas próprias cooperativas) · **Bolepix** 🔜.
Adesão em *Convênios – Cobrança → Integração por API*. Índices de busca citam um
portal `developer.ailos.coop.br` no mesmo padrão de URL de Banestes e Sicredi
(mesmo fornecedor de portal), mas **o host não resolve** hoje — o caminho
prático é pela cooperativa.

#### 097 · CrediSIS

Emissão de boleto por API, autenticada por **token entregue pelo gerente** 🔜.
Sem portal público e sem contrato publicado: o que se sabe vem de ERPs
integrados.

#### 422 · Safra

API de Cobrança (boleto) 🔒🔜 · API Pix 🔒🔜 (`client_id` + `client_secret` +
certificado digital) · saldo e extrato 🔒 · pagamentos e transferências ⛔ ·
DDA ⛔ · adquirência TEF ⛔.
Documentação **não é pública** — sai por gerente/Cash. Ressalva conhecida: a
resposta da emissão **não traz o EMV**, então o QR do híbrido tem de vir de
outro lugar.

</details>

### ⛔ Sem caminho online de boleto

<p class="chips"><span class="chip">Banco do Nordeste · 004</span><span class="chip">HSBC · 399</span><span class="chip">Citibank · 745</span></p>

Três motivos diferentes, e só um é lacuna de produto. Vale ler a seção das exceções acima antes de tratar os três como iguais.

<details markdown="1">
<summary>Ver os 3 — catálogo de serviços</summary>

#### 004 · Banco do Nordeste

API Pix 🔜 — cobrança imediata, cobrança com vencimento (desconto, juros, multa),
**cobrança em lote**, devoluções e conciliação. Boleto ⛔: só CNAB 400.
Credencial sai pelo internet banking, não por portal.

#### 399 · HSBC

Nada. Não existe como banco no Brasil desde 2016.

#### 745 · Citibank

Cash Management por **transmissão de arquivo**: cobrança e pagamentos. Sem API
pública de cobrança, e sem nenhuma família de pagamento no Open Finance.

</details>

## O que o catálogo completo mostra e a tabela não mostrava

- **Negativação e protesto são a lacuna transversal.** Aparecem no Sicoob
  (`SIC-S11`, `SIC-S12`), no Itaú (instrução) e na Caixa, e a API não expõe
  nenhum dos dois. É régua de recebimento, não pagamento — cabe no escopo, e é
  a maior superfície de cobrança que existe nos bancos e não existe aqui.
- **Extrato existe em quase todos, saldo quase nunca é usado.** `GET /extrato`
  cobre C6, Sicoob e Inter; BB, Bradesco, Santander, Sicredi, Safra e Caixa
  também têm. Saldo aparece separado em Sicoob, Inter e Sicredi e continua sem
  rota — a mesma pendência anotada em `SIC-S06`/`INT-S09`.
- **Webhook é regra, não exceção.** Sicredi, Santander, Bradesco e Banrisul
  publicam notificação própria, como C6 e Inter. Um provider novo já nasce
  podendo alimentar o `POST /webhooks/{banco}` que existe.
- **Arrecadação é um produto à parte** (BB, Banestes, Caixa): guias e tributos
  com QR, que não são boleto de cobrança e hoje não têm lugar no contrato.

## O que isso muda para a fila de providers

O princípio de esforço do [roadmap](roadmap-providers.md) se confirma banco a
banco: **Pix é o barato** (dialeto BACEN, só `PIX_BASE` + auth) e **o boleto
registrado é o trabalho**, porque o payload é proprietário em todos eles.

Três grupos, por custo real:

1. **Self-service, contrato aberto** — Banco do Brasil, Sicredi, Banrisul,
   Banestes, Unicred. Portal público, sandbox documentada, credencial sem
   intermediário comercial. É daqui que sai o próximo provider com menos
   fricção.
2. **Portal público, liberação burocrática** — Bradesco, Santander, Caixa. A
   documentação existe, mas depende de certificado ICP-Brasil (Bradesco,
   Santander) ou de chamado para liberar chave (Caixa).
3. **Sem porta pública** — Safra, BRB, Ailos, CrediSIS. A API existe (há ERP
   integrado com todas), mas a documentação sai por gerente. Levantar essas
   exige o cliente já ter o convênio — não dá para começar pelo portal.

Nada disto está planejado; está levantado. Quando uma linha virar decisão, ela
ganha página própria, como as que já existem para
[C6](c6-rest.md), [Sicoob](sicoob-rest.md), [Inter](inter-rest.md),
[Itaú](itau-rest.md) e [Banco do Brasil](banco-do-brasil-rest.md).

## Método, e o que cada evidência vale

| Fonte | O que prova | O que não prova |
|---|---|---|
| Portal público do banco | que o produto existe e o contrato é documentado | que a conta do cliente tem o convênio |
| Diretório do Open Finance (`DeveloperPortalUri`) | a URL que o **próprio banco** declarou | que o portal está no ar |
| Documentação de ERPs e integradores | que alguém integrou de fato | a versão atual do contrato |

**O que deliberadamente não entrou como evidência: bater HTTP no portal.** Foi
tentado e o resultado é ruído — Santander e C6 responderam `403`, Banco do
Brasil e Bradesco falharam no TLS, Caixa deu `504`, e nenhum desses bancos está
fora do ar: é WAF recusando datacenter. Um roteiro que lesse isso como "portal
indisponível" reprovaria justamente os bancos que já integramos. Onde a coluna
diz *respondeu*, foi `200` verificado; onde não diz, a evidência é documental.

Um sinal, porém, é limpo: **o nome do host resolver ou não**. WAF recusa
requisição, não apaga registro de DNS. Foi assim que se separou "portal existe e
me bloqueou" de "portal não existe sob esse nome" — o caso do Ailos, citado em
índices de busca num endereço que hoje não resolve.

## Ressalvas honestas

- **Nenhum destes contratos foi exercido.** Isto é levantamento documental; o
  que está exercido contra o banco é C6, Sicoob e Inter, na
  [homologação](../homologacao/README.md).
- **Documentação fechada é o normal, não a exceção.** Safra, BRB, Ailos e
  CrediSIS não publicam contrato — o que se sabe deles vem de integradores e de
  ERPs, e pode estar defasado em relação à versão que o banco entrega hoje.
- **Cooperativa é sistema, não banco único.** Ailos, CrediSIS, Sicredi, Sicoob e
  Unicred têm centrais e singulares; o convênio é com a singular e a API é da
  central. Um provider serve todas as cooperativas da mesma central — o que
  torna esse grupo desproporcionalmente barato por cliente atendido.
