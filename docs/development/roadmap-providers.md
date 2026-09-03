# Roadmap de Providers ONLINE — Bancos e PSPs

> Próximos passos de integração do **gateway** (`gateway`) — o caminho **online**
> (`provider=on`), que fala com a API do banco. Estado atual: **quatro**
> instituições com provider REST — **C6** e **Inter** validados ponta a ponta em
> sandbox, **Sicoob** validado em contrato (o sandbox dele é mock) e **Itaú**
> implementado como esqueleto e **desligado por flag**. Mais **19 bancos** pelo
> caminho offline (`provider=off`, engine pyCobrança) — 19 instituições
> distintas no total, porque C6, Sicoob e Itaú contam nos dois caminhos.
> Salvo o que está marcado ✅, cada linha aqui é **planejada**, não implementada.
>
> Só o caminho online. O catálogo **offline** é da engine
> [pyCobrança](https://github.com/Maxwbh/pyCobranca) e a fila dele vive lá — esta
> API apenas expõe o que a engine suporta, em `GET /api/bancos`.

> **Quem dos 18 poderia ser `on`?** Não é mais especulação: o levantamento
> instituição por instituição, com o catálogo completo de cada uma, está em
> [servicos-online-por-banco.md](servicos-online-por-banco.md). **14 dos 18** têm
> API REST de boleto registrado, a Caixa tem em SOAP, e três não têm caminho
> online nenhum — cada um por um motivo diferente. É de lá que sai a Fase 1
> revisada abaixo.

## Princípio de esforço (o que torna barato)

- **Pix é padronizado pelo BACEN** (`/cob`, `/cobv`, `/cobr`, `/loc`, `/webhook`,
  `/pix`) → já implementado uma vez em `app/providers/bacen_pix.py`. Para um banco
  novo, Pix + Pix Automático = **só `PIX_BASE` + auth**. Barato de escrever não é
  o mesmo que validado: o que cada banco de fato responde no Pix Automático está
  em [pix-automatico.md](pix-automatico.md).
- **Auth** já coberta pelo `OAuthMtlsClient` (OAuth `client_credentials` + mTLS +
  token estático + headers custom) e pela **tokenização** (`bapi_`).
- **O trabalho real é o boleto registrado** (payload proprietário por banco) —
  1 provider novo + testes. `GET /bancos` lista o novo provider automaticamente
  (capacidades por introspecção).

## Princípio de escopo (o que não entra, em provider nenhum)

A API é **intermediária**: traduz a requisição, fala com a instituição e
normaliza o status de volta. **Não calcula, não confere e não guarda regra de
negócio de cliente.** Isto é régua de seleção, não só de implementação — o que
cai aqui sai antes da discussão de esforço:

- **Split e comissão** (ex.: Marketplace/OAuth do Mercado Pago, MP-S08) —
  ficar com fatia de pagamento alheio faz o serviço participar do fluxo do
  dinheiro, e ele deixa de ser tradutor.
- **Saída de dinheiro** (pagamentos, DDA, TED) — o produto é cobrança, entrada.
- **Configuração comercial do cliente** (juro de parcelamento, baixa de parcela)
  — chega no payload, resolvida por quem chama.
- **Captura presencial** (maquininha) — não há superfície para esta API
  consumir; não vira nem linha de catálogo.
- **Open Finance** — cai por duas réguas ao mesmo tempo. Iniciação de pagamento
  (ITP) é saída de dinheiro, e consumir qualquer família do ecossistema exige
  ser participante habilitado no diretório, com autorização do BCB, certificados
  BRCAC/BRSEAL, FAPI-BR e DCR — o modelo de credencial desta API é o de
  **cliente do banco** e não alcança nada disso. O custo medido, e o erro de
  leitura que quase o transformou num atalho, estão em
  [open-finance.md](open-finance.md).

Duas coisas que **cabem** no escopo e ainda não existem, e por isso valem mais
que qualquer provider novo da fila: **negativação** e **protesto**. Aparecem no
Sicoob (`SIC-S11`/`SIC-S12`), no Itaú (instrução) e na Caixa. São régua de
recebimento, não pagamento — é a maior superfície de cobrança que existe nos
bancos integrados e não existe aqui.

## Fases

### ✅ Fase 0 — Implementado
| Provider | Tipo | Estado |
|---|---|---|
| C6 Bank (336) | Banco REST | boleto, Pix, Bolepix, extrato, conciliação, checkout, Pix Automático — **validado sandbox**, ponta a ponta |
| Sicoob (756) | Banco REST | boleto v3, Pix, extrato, Pix Automático — sandbox é **mock de schema**: valida contrato, não comportamento |
| Banco Inter (077) | Banco REST | boleto híbrido (QR Pix no mesmo documento), Pix, extrato, webhook — **validado sandbox**, 13 casos em 2xx, zero falhas |
| **Itaú (341)** | Banco REST | **esqueleto**: emissão, instrução e consulta escritas com paths e payload **a confirmar** (o catálogo exige login). **Desligado** por `ITAU_REGISTERED_READY` — sem a flag, `banco=itau` emite pela engine, que tem o layout 341. Não devolve PDF, e **não tem Pix Automático**: as rotas respondem `422` |
| 19 bancos CNAB | Offline | via engine pyCobrança |

### 🎯 Fase 1 — Bancos self-service (próximos)

Revisada a partir do [levantamento dos 18](servicos-online-por-banco.md): o que
define esta fase é **portal público com sandbox e credencial sem intermediário
comercial**. Três candidatos entraram agora, que não estavam aqui antes.

| Prioridade | Provider | Cód | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª | **Banco do Brasil** | 001 | Maior alcance; API Cobrança + Arrecadação Pix; híbrido | Médio | [banco-do-brasil-rest.md](./banco-do-brasil-rest.md) |
| 2ª | **Sicredi** | 748 | Cooperativo, base grande; Cobrança v3 **com webhook próprio** e extrato | Médio¹ | (planejado) |
| 3ª | **Banrisul** | 041 | Portal público (2025) com catálogo enxuto — só 5 APIs, das quais **duas são nossas**: Cobrança de Títulos e Pix. Superfície pequena, sem ruído | Médio | (planejado) |
| 4ª | **BTG Pactual** | 208 | Único outro banco com **link de cartão hospedado por API**; self-service, **sem mTLS** | Médio² | [btg-rest.md](./btg-rest.md) |
| 5ª | **Unicred** | 136 | Cooperativo; **boleto + Pix numa integração só**, registro em até 5 min, sandbox e homologação formais | Médio | (planejado) |
| 6ª | **Banestes** | 021 | Portal público, Pix completo (cobrança, arrecadação e **automático**) | Médio³ | (planejado) |

> ¹ **Correção de rota.** A versão anterior deste documento dava esforço "muito
> baixo" para o Sicredi, com a justificativa de que ele "reaproveita quase tudo
> do Sicoob". **Não reaproveita.** Sicoob e Sicredi são sistemas cooperativos
> concorrentes, com plataformas distintas: endpoints, versão, autenticação e
> payload de boleto são diferentes. O que se reaproveita é o Pix BACEN — o
> mesmo que se reaproveita de qualquer banco. A conta certa é a de sempre: o
> boleto é o trabalho.
>
> ² Duas incógnitas decidem a conta, ambas respondíveis no sandbox: o link de
> pagamento aceita `client_credentials` (ou só Authorization Code, que o cofre
> não comporta hoje)? E o Pix é dialeto BACEN (mixins de graça) ou próprio?
>
> ³ Com uma pegadinha de descoberta: o portal do Banestes lista **só Pix**. A
> cobrança de boleto é documentada em outro host (`dev.apps.banestes.b.br`).
> Quem levantar só pelo portal conclui, errado, que o banco não tem boleto.

Ficam fora da Fase 1, apesar de terem API, os bancos cuja **credencial não sai
por autosserviço** — BRB, Ailos, Safra e CrediSIS. A API existe (há ERP
integrado com todas), mas a documentação sai por gerente: não dá para começar
pelo portal, e sim pelo cliente que já tem o convênio.

### 🔌 Fase 2 — PSP / Agregador
| Prioridade | Provider | Tipo | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª ⭐ | **Mercado Pago** | PSP | Maior plataforma de pagamento; API mais fácil (só access token); Pix+boleto+cartão+assinatura | Médio | [mercado-pago-rest.md](./mercado-pago-rest.md) |
| 2ª | **Efí** (ex-Gerencianet) | PSP · 364 | **Único PSP com Pix em dialeto BACEN** — os três mixins de graça, Pix Automático pioneiro, e o sandbox **simula pagamento** (a massa que faltou no C6). Perfil de esforço do Inter, não de PSP | **Baixo-médio** | [efi-rest.md](./efi-rest.md) |
| 3ª | Asaas | PSP | Dev-friendly; cobre quem não tem convênio | Médio | (planejado) |

### 🕓 Fase 3 — Avaliar (onboarding pesado ou transporte fora do padrão)
| Provider | Cód | Observação |
|---|---|---|
| Bradesco | 237 | Maior base de contas. Portal com **mais de 120 APIs** (boleto, Pix, extrato, conciliação, notificações) e sandbox aberta inclusive a quem não é cliente — o gargalo não é a documentação, é o **certificado A1 ICP-Brasil** e o onboarding |
| Santander | 033 | Big 5, portal público. Boleto com **registro instantâneo** e webhook próprio; certificado `.pem` carregado no portal. Homologação longa e por tipo de operação (cobrança, pagamento, extrato separadamente) |
| Caixa | 104 | **Não é falta de API — é outro transporte.** A cobrança é **WebService XML/SOAP** (SIGCB), então não reaproveita o `OAuthMtlsClient`: é envelope, cliente e testes próprios. O Pix, esse, é REST BACEN como todos, e a `X-API-KEY` sai por chamado |
| Nubank | 260 | Base gigante, mas API PJ de boleto registrado limitada/incerta. Não está entre os 18 do catálogo offline |
| Banco do Nordeste | 004 | **Só Pix.** O boleto é CNAB 400, sem API — é a única lacuna real do catálogo. Entra quando houver cliente, e entra pelo Pix |

## Diferença Banco × PSP (decisão de produto)

| | Banco (C6, Sicoob, Inter, BB…) | PSP (Mercado Pago, Efí, Asaas) |
|---|---|---|
| Recebimento | Na **conta bancária do próprio cliente** | Na **conta/carteira do PSP** (depois saca) |
| Dialeto Pix | **BACEN** → reaproveita `bacen_pix.py` ✅ | **Próprio** (não reaproveita) — **exceção: a Efí é BACEN** e herda os mixins como um banco |
| Auth | OAuth + mTLS (certificado) | Access token (Bearer), sem mTLS — **exceção: a Efí exige mTLS na família Pix** |
| Convênio | Exige convênio/conta PJ | Cadastro self-service |
| Público | Cobrança tradicional (aluguel/mensalidade) | E-commerce, sem convênio, cartão |

**Estratégia sugerida:** bancos como trilha principal (BB → Sicredi → Banrisul
→ BTG; Inter e Itaú já estão na Fase 0) + dois PSPs com papéis distintos:
**Mercado Pago** pelo alcance (a maior base de quem não tem convênio) e **Efí**
pelo custo (dialeto BACEN = mixins prontos, e o único sandbox onde o ciclo de
pagamento fecha).

Um atalho que o levantamento tornou visível: **cooperativa é sistema, não banco
único**. Sicredi, Unicred e Ailos têm central e singulares — a API é da central
e o convênio é com a singular, então **um provider atende todas as cooperativas
daquela central**. Por cliente potencialmente atendido, esse grupo é o mais
barato da fila, e é o motivo de o Sicredi seguir alto mesmo depois da correção
de esforço.

## Cartão — link de pagamento (capacidade, não provider)

Cartão atravessa as fases acima em vez de ocupar uma linha nelas: não é um
provider novo, é uma capacidade que cada instituição tem ou não tem.

**Critério de entrada:** a instituição **oferece link hospedado**. Quem oferece,
tem; quem não oferece responde `422` do `exige_capacidade` dizendo para onde ir,
como já acontece com o Bolepix. Não é lista fechada de bancos — é teste aplicado
a cada um, e a assimetria entre providers é o resultado esperado, não exceção a
justificar.

**Restrição dura: modo link, e só ele.** O PAN é digitado no domínio da
instituição, e o escopo PCI-DSS fica com ela. Checkout transparente e
`save_card` estão fora em definitivo — integração que exija cartão no nosso
domínio troca o assunto de integração para certificação.

| Instituição | Oferece link hospedado? | Estado | Onde |
|---|---|---|---|
| **C6 Bank** | Sim — API Checkout, mesmo host e auth do boleto | ✅ **implementado** (`/checkout`) | [c6-rest.md](./c6-rest.md) · C6-S09 |
| **BTG Pactual** | Sim — link → `linkUrl`, área não logada; **7 webhooks** | 🔜 possibilidade | [btg-rest.md](./btg-rest.md) · BTG-S05 |
| **Mercado Pago** | Sim — Checkout Pro (`POST /checkout/preferences` → `init_point`) | 🔜 possibilidade | [mercado-pago-rest.md](./mercado-pago-rest.md) · MP-S07 |
| **Efí** | Sim — link de pagamento na API Cobranças (boleto + cartão) | 🔜 possibilidade | [efi-rest.md](./efi-rest.md) · EF-S10 |
| **Sicoob** | Não — cartão é da Sipag, sem API pública | ⛔ `422` por capacidade | [sicoob-rest.md](./sicoob-rest.md) |
| **Banco Inter** | Não levantado — o portal PJ não expõe checkout de cartão nas APIs que integramos | ⛔ `422` por capacidade | [inter-rest.md](./inter-rest.md) |
| **Itaú** | Não levantado — o catálogo exige login, e o que é público não expõe link hospedado | ⛔ `422` por capacidade | [itau-rest.md](./itau-rest.md) |

O C6 é o mais barato por larga margem: mesmo host, mesma OAuth+mTLS, mesmo
cofre — rota nova sobre o `OAuthMtlsClient` que já existe, não integração nova.
Asaas, PagBank e Cielo também oferecem link hospedado e passam no mesmo
critério; entram quando existir cliente que nenhum banco integrado atenda.

## Como cada provider entra (checklist)

1. ☐ `schemas.Banco` — novo valor do enum. **É o `Banco`, não o `Provider`**:
   desde a separação dos dois eixos, `provider` diz o CAMINHO (`on`/`off`) e é
   um enum fechado. Acrescentar banco ali era o modelo antigo, e hoje só
   produziria mais um apelido legado.
2. ☐ `app/providers/<banco>.py` — classe do provider (mapeia boleto; herda
   `BacenPixMixin`/`BacenPixRecebidosMixin`/`BacenPixAutomaticoMixin` se BACEN).
3. ☐ `app/registry.py` — registrar em **`_REST_POR_BANCO`** (caminho ON) e, se a
   engine tiver o layout, em **`_SLUG_ENGINE`** (caminho OFF). `_PROVIDERS` e
   `_OFFLINE_BANK` são derivados de compatibilidade: não se edita à mão.
4. ☐ `app/routers/bancos.py` — esquema de credenciais + entrada no catálogo. As
   **capacidades saem por introspecção**, não se declaram: método sobrescrito é
   capacidade real.
5. ☐ Testes mock (`tests/test_<banco>.py`) + e2e sandbox gated (`test_sandbox_<banco>.py`).
6. ☐ Doc `docs/development/<banco>-rest.md` + link no `docs/README.md` e no
   [índice de engenharia](index.md).
7. ☐ Cobertura na coleção Postman (`python postman/check_coverage.py` = 100%) e
   Swagger publicado em dia (`scripts/gerar-swagger-estatico.py --conferir`) —
   os dois são guardas de CI e reprovam o PR.
8. ☐ Validar no sandbox oficial → homologação → ligar `<BANCO>_REGISTERED_READY`.
   **Antes da flag, `provider=on` cai na engine em silêncio** — é a proteção que
   C6, Sicoob e Itaú tiveram, e é o que o `GET /bancos` reporta em
   `registrado_pronto`.

Referência das APIs oficiais: cada doc de provider linka o portal do banco/PSP
(as specs **não** são versionadas neste repo — ver o padrão na seção "Onde
baixar a documentação oficial" em [`c6-rest.md`](./c6-rest.md)).

## Template de documentação por provider (estrutura única)

Todo provider tem **1 documento** em `docs/development/<provider>-rest.md`, com
estas seções **nesta ordem** (docs planejados usam as seções 1–6 + "Esforço
estimado"; ao implementar, completam o restante):

| # | Seção | Banco | PSP |
|---|---|:---:|:---:|
| 1 | Título `# <Nome> (<código>) — Integração REST [· PLANEJADO]` + quote de status | ✔ | ✔ |
| 2 | `## Onde baixar a documentação oficial` (só links do portal) | ✔ | ✔ |
| 3 | `## Serviços do banco × Cobranca-API` — **catálogo completo** do portal, cada serviço com status ✅ disponível / 🔜 planejado / ⛔ sem previsão-fora de escopo. Mostra a evolução possível mesmo do que não foi implementado | ✔ | ✔ |
| 3b | `## Diferenças vs bancos` (dialeto próprio, carteira/wallet, sem mTLS) | — | ✔ |
| 4 | `## Autenticação no banco` (fluxo OAuth/mTLS/scopes/headers) | ✔ | ✔ |
| 5 | `## Esquema de credenciais` (campos do `POST /credenciais`; fonte viva: `GET /bancos`) | ✔ | ✔ |
| 6 | `## Superfície (<provider> → gateway)` (tabela operação × endpoint) | ✔ | ✔ |
| 7 | `## Pix BACEN compartilhado` (só `PIX_BASE`; mixins fazem o resto) | ✔ | — (PSP tem dialeto próprio; a Efí é a exceção e usa esta seção como banco) |
| 8 | `## account_config (por tenant)` | ✔ | ✔ |
| 9 | `## Particularidades do banco` (CIP, carteiras, conciliação, status a normalizar…) | ✔ | ✔ |
| 10 | `## Autenticação da API (token bapi_)` (mecanismo único) | ✔ | ✔ |
| 11 | `## Validação` (sandbox/e2e) **ou** `## Esforço estimado` (planejado) | ✔ | ✔ |
| 12 | `## Pendências / homologação` | ✔ | ✔ |
