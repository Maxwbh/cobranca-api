# BTG Pactual (208) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](./roadmap-providers.md).
> Entra por um motivo que nenhum outro banco da fila tem: é o **único outro
> banco** com **link de pagamento hospedado por API** confirmado, além do C6 —
> e com webhook, que o Checkout do C6 não tem.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal do Desenvolvedor | https://developers.empresas.btgpactual.com/ |
| Índice completo das APIs | https://developers.empresas.btgpactual.com/llms.txt |
| Link de Pagamento (guia) | https://developers.empresas.btgpactual.com/docs/link-de-pagamento-1 |
| Link de Pagamento (referência) | https://developers.empresas.btgpactual.com/reference/link-de-pagamento |
| Autenticação (BTG Id) | https://developers.empresas.btgpactual.com/docs (seção BTG Id) |

## Serviços do banco × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).
>
> O ⛔ segue a [régua de escopo](./roadmap-providers.md#princípio-de-escopo-o-que-não-entra-em-provider-nenhum):
> a API é intermediária — não calcula, não confere, não guarda regra de negócio
> de cliente; e o produto é cobrança (entrada), não pagamento (saída).

| ID | Serviço no portal BTG | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| BTG-S01 | BTG Id — OAuth2 (`client_credentials`) | Token de acesso às APIs | 🔜 | Interno (`OAuthMtlsClient`, sem mTLS) |
| BTG-S02 | Cobranças | Criar, listar, atualizar e cancelar cobrança | 🔜 | `POST/GET/PUT/DELETE /cobranca` |
| BTG-S03 | Boletos | Boleto único, **parcelado** ou em lote | 🔜 | `POST /cobranca` (parcelado → avaliar mapeamento) |
| BTG-S04 | Cobranças em Lote | Processamento assíncrono de várias cobranças | 🔜 | `POST /jobs/boletos` (já existe como job) |
| BTG-S05 | **Link de Pagamento** | Página hospedada; boleto + Pix + **cartão de crédito** | 🔜 | Capacidade **cartão** — ver seção abaixo |
| BTG-S06 | Pix Cobrança Dinâmico | QR dinâmico de cobrança | 🔜 | `/pix/*` — **dialeto BACEN a confirmar** (define o esforço) |
| BTG-S07 | Pix Automático | Cobrança recorrente autorizada | 🔜 | `/pix-automatico/*` |
| BTG-S08 | Webhooks | Notificação em tempo real, com reprocessamento | 🔜 | `/config/webhook-banco` + `POST /webhooks/btg[/{tenant}]` |
| BTG-S09 | Extrato e Saldo | Movimentações, saldo, PDF do extrato em base64 | 🔜 | `GET /extrato` |
| BTG-S10 | Guia de Conciliação | Apoio à conciliação de transações | 🔜 | Avaliar — só se for consulta; a API **não concilia** |
| BTG-S11 | Negativação de boletos | Registrar/cancelar negativação em lote | 🔜 | Avaliar — é ação sobre cobrança emitida |
| BTG-S12 | Protesto | Agendar, consultar e cancelar protesto | 🔜 | Avaliar — idem |
| BTG-S13 | Cartões de crédito e faturas | Listar cartões da empresa, consultar faturas | ⛔ | Dado de conta, não de cobrança |
| BTG-S14 | Antecipação de recebíveis de cartão | Antecipar recebível | ⛔ | Operação de crédito — participa do fluxo do dinheiro |
| BTG-S15 | Pagamentos, Transferências, PagFor, Batch | Saída de dinheiro | ⛔ | Fora de escopo — o produto é cobrança (entrada) |
| BTG-S16 | DDA | Autorizar/consultar débito direto | ⛔ | Fora de escopo — saída |
| BTG-S17 | Crédito, consignado, renegociação, solar | Originação e gestão de crédito | ⛔ | Fora de escopo |
| BTG-S18 | Câmbio | Moedas e cotação indicativa | ⛔ | Fora de escopo |
| BTG-S19 | Folha de pagamento | Onboarding e gestão de colaboradores | ⛔ | Fora de escopo |
| BTG-S20 | Open Finance | Compartilhamento de dados | ⛔ | Fora de escopo |
| BTG-S21 | CNAB 240 (SFTP / VAN) | Troca de arquivo por transmissão | ⛔ | Caminho CNAB é da engine — **que não tem o banco 208**; ver nota abaixo |

> **Nota sobre o BTG-S21 — não existe caminho offline para o BTG hoje.** Dizer
> que "o CNAB já é servido pela engine" é verdade sobre a arquitetura e falso
> sobre este banco: o `208` **não está** entre os 18 da pyCobrança (`001`, `004`,
> `021`, `033`, `041`, `070`, `085`, `097`, `104`, `136`, `237`, `336`, `341`,
> `399`, `422`, `745`, `748`, `756`). O BTG só teria a via **registrada por API**.
>
> É implementável: o BTG publica
> [CNAB Febraban 240 posições](https://developers.empresas.btgpactual.com/docs/cnab-febraban-240-posições)
> — segmentos P, Q, R, S, Y, T, U, códigos de movimento e particularidades —, e
> ERPs como Omie e Citel já rodam o `208 [240p]`. Mas a página cobre as
> divergências, **não** o layout completo: faltam posições exatas, nosso número,
> carteira e composição do código de barras, que viriam do manual de cobrança
> pelo gerente.
>
> E o trabalho **não é deste repositório**: banco offline é da engine
> [pyCobrança](https://github.com/Maxwbh/pyCobranca), o segundo dos
> [três produtos](./separacao-3-produtos.md), com versão própria. Seria um PR
> lá; aqui o banco apareceria sozinho no `GET /bancos` na próxima versão da
> engine, sem uma linha de código.

## Link de pagamento — por que este banco entra

O BTG passa nos dois critérios de cartão do
[roadmap](./roadmap-providers.md#cartão--link-de-pagamento-capacidade-não-provider):

- **Restrição dura — modo link:** a criação devolve `linkUrl` (ex.:
  `https://link.btgpactual.com/8d241f83`) e o pagador vai para uma **área não
  logada** do BTG Empresas. O PAN é digitado no domínio do banco; o escopo
  PCI-DSS fica com ele.
- **Critério de entrada:** o BTG **oferece** a funcionalidade. Não é exceção nem
  ampliação de regra — é a regra aplicada.

Meios aceitos no mesmo link: `BANKSLIP`, `IMMEDIATE_QRCODE` (Pix) e
`CREDIT_CARD`. O crédito é **parcelável em até 12x**, com juros no parcelamento.

### O campo que decide a paridade com o C6: quem paga o juro

O default é `BY_SELLER` — o portador paga `valor / parcelas` sem acréscimo e o
juro sai do repasse ao lojista —, e a escolha chega **no payload**, porque esta
API não guarda configuração comercial de cliente. Isso pressupõe que o banco
**exponha a escolha por requisição**.

| | C6 Checkout | BTG Link |
|---|---|---|
| Parcelamento | `installments` | até 12x |
| Quem paga o juro | `interest_type`: `BY_SELLER` / `BY_ISSUER` | **não confirmado** |

O C6 expõe. Do BTG só se sabe que há juro no parcelamento; **não foi confirmado
se quem paga é configurável ou fixo do banco.**

Se for fixo, o BTG não fica inviável — mas nasce uma assimetria de
comportamento que hoje não existe: o mesmo campo do payload valeria num provider
e seria ignorado no outro. Isso é decisão de produto e precisa estar registrada
**antes** de implementar, não depois. É a terceira pendência de homologação.

**Vantagem sobre o C6, e ela é operacional.** O spec do Checkout C6 **não tem
webhook** (registrado no estudo), o que obriga a consultar status por polling.
O link do BTG emite **sete eventos**:

```
payment-link.created     payment-link.activated   payment-link.paid
payment-link.updated     payment-link.expired     payment-link.cancelled
payment-link.failed
```

`paid` é o que interessa para normalizar `liquidado` sem polling. O CPF/CNPJ do
pagador vem **mascarado** no payload do webhook.

**Ressalva:** `CREDIT_CARD` **exige aprovação prévia** — a doc manda falar com
`partnerships@btgpactual.com`. Boleto e Pix no link são self-service; cartão,
não. Isso precisa ser resolvido antes de prometer a capacidade.

## Autenticação no banco

- **BTG Id**, o Authorization Server da plataforma. O portal documenta
  `client_credentials` (sistema-a-sistema), `authorization_code`,
  `authorization_code` + PKCE, refresh token, SSO e JWKS.
- **Sem mTLS** — diferente do C6, do Inter e do Sicoob. É a primeira integração
  da fila que dispensa certificado.
- Escopos por API. No link de pagamento: `openid` (obrigatório) mais
  `brn:btg:empresas:payment-link` (criar/gerenciar) ou
  `brn:btg:empresas:payment-link.readonly` (só consulta).
- Sandbox próprio com **Wiremock** e headers de controle de resposta, além de
  coleções Postman prontas.

> **A confirmar, e não é detalhe:** a referência do link de pagamento descreve o
> fluxo **Authorization Code** — que exige consentimento por redirect e não
> encaixa no modelo servidor-a-servidor do `OAuthMtlsClient`. O portal lista
> `client_credentials` como fluxo disponível, mas **não confirmei que o link de
> pagamento o aceita**. Se aceitar, o esforço é baixo; se for só Authorization
> Code, nasce um ciclo de consentimento e renovação de token que o cofre não
> tem hoje. **Esta é a primeira pergunta a responder no sandbox.**

## Esquema de credenciais (proposto — ver `GET /bancos`)

```
client_id      # da aplicação (portal BTG Empresas)
client_secret  # da aplicação
scopes         # opcional (default do provider)
```

Sem `pfx_base64`/`pfx_password`: não há mTLS. O esquema é o mais curto de todos
os providers previstos.

## Superfície prevista (BTG → gateway)

| Operação | BTG | Endpoint do gateway |
|---|---|---|
| Emitir cobrança/boleto | API Cobranças | `POST /cobranca` |
| Consultar | API Cobranças | `GET /cobranca/{id}` |
| Atualizar / cancelar | API Cobranças | `PUT` / `DELETE /cobranca/{id}` |
| Lote | Cobranças em Lote | `POST /jobs/boletos` |
| **Link de pagamento** | Link de Pagamento → `linkUrl` | rota de cartão (a definir) |
| Pix dinâmico | Pix Cobrança Dinâmico | `/pix/*` |
| Pix Automático | Pix Automático | `/pix-automatico/*` |
| Extrato / saldo | Extrato e Saldo | `GET /extrato` |
| Webhook | 7 eventos de link + eventos de cobrança | `POST /webhooks/btg[/{tenant}]` |

> **Caminhos exatos a confirmar** na referência oficial e no sandbox durante a
> implementação. Esta tabela mapeia capacidades, não URLs.

## Pix BACEN compartilhado

Se o Pix do BTG seguir o Manual da API Pix do BACEN (`/cob`, `/cobv`, `/pix`,
`/webhook`), Pix e Pix Automático saem **de graça** pelos mixins
(`BacenPixMixin`, `BacenPixRecebidosMixin`, `BacenPixAutomaticoMixin`) — basta
`PIX_BASE` e auth, como em C6 e Sicoob.

**Não confirmado.** O portal descreve "Pix Cobrança Dinâmico" com vocabulário
próprio, e a diferença entre dialeto BACEN e dialeto proprietário é o que separa
esforço baixo de provider dedicado. Verificar antes de estimar.

## Particularidades do banco

- **Boleto parcelado** é primitiva do próprio BTG (`Boletos`: único, parcelado
  ou em lote). O gateway não tem conceito de parcelamento de boleto — mapear
  exigiria decidir se vira N cobranças ou um campo novo. Fica para a
  implementação; não é bloqueio.
- **Negativação e protesto** são ações sobre cobrança já emitida, e nenhum
  provider atual as expõe. Entram como avaliação, não como requisito.
- **Conciliação:** o BTG publica um guia de conciliação. Vale lembrar a régua —
  a API **relaia** movimentação, não concilia. Se virar rota, é consulta.
- **Rate limit** documentado por API; considerar no cliente HTTP.
- **Onboarding self-service** com sandbox completo, sem depender de gerente —
  o que coloca o BTG no mesmo grupo de Inter, Sicoob e BB.

## Autenticação da API (token `bapi_`)

Igual aos demais providers: o consumidor autentica no gateway com token
`bapi_` (`POST /credenciais`), e as credenciais do banco vêm no request
(`X-Bank-Credentials`) ou do cofre. Nada específico do BTG.

## Esforço estimado

**Médio, com uma incógnita que pode derrubá-lo para baixo.**

| Peça | Esforço | Por quê |
|---|---|---|
| Auth | **Baixo** — *se* `client_credentials` valer para as APIs de cobrança e link | Sem mTLS; é o caso mais simples do `OAuthMtlsClient`. Se for só Authorization Code, sobe para **alto** (consentimento + renovação, que o cofre não tem) |
| Boleto / cobrança | Médio | Payload proprietário — o trabalho de sempre |
| Pix | **Baixo** se BACEN, **médio** se dialeto próprio | Decide sozinho boa parte da conta |
| Link de pagamento | Baixo | Criar → `linkUrl`; webhook já resolve o status |
| Extrato | Baixo | Superfície pequena, já existe no gateway |

**Duas perguntas antes de qualquer estimativa firme**, ambas respondíveis no
sandbox: (1) o link de pagamento aceita `client_credentials`? (2) o Pix é
dialeto BACEN?

## Pendências / homologação

- [ ] Confirmar fluxo OAuth aceito pelas APIs de cobrança e de link de pagamento
- [ ] Confirmar se o Pix segue o dialeto BACEN (define reuso dos mixins)
- [ ] **Confirmar se o juro do parcelamento é configurável por requisição**
      (equivalente ao `interest_type` do C6). Se for fixo do banco, decidir e
      registrar o que acontece com o default `BY_SELLER` num provider que não
      aceita a escolha por requisição
- [ ] Confirmar se o link aceita **débito**, além de crédito (o C6 aceita)
- [ ] Habilitar `CREDIT_CARD` no link (aprovação via `partnerships@btgpactual.com`)
- [ ] Levantar caminhos e payloads exatos na referência oficial
- [ ] Validar no sandbox (Wiremock) → homologação → ligar `BTG_REGISTERED_READY`
