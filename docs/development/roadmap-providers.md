# Roadmap de Providers ONLINE — Bancos e PSPs

> Próximos passos de integração do **gateway** (`gateway`) — o caminho **online**,
> que fala com a API do banco. Estado atual: **C6** e **Inter** validados ponta
> a ponta em sandbox, **Sicoob** validado em contrato (o sandbox dele é mock);
> **18 bancos** via CNAB offline (engine pyCobrança) — 19 instituições
> distintas no total.
> Salvo o que está marcado ✅, cada linha aqui é **planejada**, não implementada.
>
> Só o caminho online. O catálogo **offline** é da engine
> [pyCobrança](https://github.com/Maxwbh/pyCobranca) e a fila dele vive lá — esta
> API apenas expõe o que a engine suporta, em `GET /api/bancos`.

## Princípio de esforço (o que torna barato)

- **Pix é padronizado pelo BACEN** (`/cob`, `/cobv`, `/cobr`, `/loc`, `/webhook`,
  `/pix`) → já implementado uma vez em `app/providers/bacen_pix.py`. Para um banco
  novo, Pix + Pix Automático = **só `PIX_BASE` + auth**.
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

## Fases

### ✅ Fase 0 — Concluída
| Provider | Tipo | Estado |
|---|---|---|
| C6 Bank (336) | Banco REST | boleto, Pix, Bolepix, extrato, conciliação, Pix Automático — validado sandbox |
| Sicoob (756) | Banco REST | boleto v3, Pix, extrato, Pix Automático — sandbox é **mock de schema**: valida contrato, não comportamento |
| Banco Inter (077) | Banco REST | boleto híbrido (QR Pix no mesmo documento), Pix, extrato, webhook — **validado sandbox**, 13 casos em 2xx, zero falhas |
| 18 bancos CNAB | Offline | via engine pyCobrança |

### 🎯 Fase 1 — Bancos self-service (próximos)
| Prioridade | Provider | Cód | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª | **Banco do Brasil** | 001 | Maior alcance; API Cobrança + Arrecadação Pix; híbrido | Médio | [banco-do-brasil-rest.md](./banco-do-brasil-rest.md) |
| 2ª | **Sicredi** | 748 | Cooperativo; reaproveita quase tudo do Sicoob | **Muito baixo** | (planejado) |
| 3ª | **BTG Pactual** | 208 | Único outro banco com **link de cartão hospedado por API**; self-service, **sem mTLS** | Médio¹ | [btg-rest.md](./btg-rest.md) |

> ¹ Duas incógnitas decidem a conta, ambas respondíveis no sandbox: o link de
> pagamento aceita `client_credentials` (ou só Authorization Code, que o cofre
> não comporta hoje)? E o Pix é dialeto BACEN (mixins de graça) ou próprio?

### 🔌 Fase 2 — PSP / Agregador
| Prioridade | Provider | Tipo | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª ⭐ | **Mercado Pago** | PSP | Maior plataforma de pagamento; API mais fácil (só access token); Pix+boleto+cartão+assinatura | Médio | [mercado-pago-rest.md](./mercado-pago-rest.md) |
| 2ª | **Efí** (ex-Gerencianet) | PSP · 364 | **Único PSP com Pix em dialeto BACEN** — os três mixins de graça, Pix Automático pioneiro, e o sandbox **simula pagamento** (a massa que faltou no C6). Perfil de esforço do Inter, não de PSP | **Baixo-médio** | [efi-rest.md](./efi-rest.md) |
| 3ª | Asaas | PSP | Dev-friendly; cobre quem não tem convênio | Médio | (planejado) |

### 🕓 Fase 3 — Avaliar (onboarding pesado / API limitada)
| Provider | Cód | Observação |
|---|---|---|
| Bradesco | 237 | Maior base de contas, mas onboarding pesado |
| Santander | 033 | Big 5; API disponível |
| Itaú | 341 | Maior base de cobrança do país e **a API não devolve PDF** — a engine já renderiza o 341, então o registro online reaproveita o offline. O gargalo é comercial: credencial de cobrança **não** sai por autosserviço. [itau-rest.md](itau-rest.md) |
| Nubank / Caixa | 260 / 104 | Base gigante, mas API PJ de boleto registrado limitada/incerta |

## Diferença Banco × PSP (decisão de produto)

| | Banco (C6, Sicoob, Inter, BB…) | PSP (Mercado Pago, Efí, Asaas) |
|---|---|---|
| Recebimento | Na **conta bancária do próprio cliente** | Na **conta/carteira do PSP** (depois saca) |
| Dialeto Pix | **BACEN** → reaproveita `bacen_pix.py` ✅ | **Próprio** (não reaproveita) — **exceção: a Efí é BACEN** e herda os mixins como um banco |
| Auth | OAuth + mTLS (certificado) | Access token (Bearer), sem mTLS — **exceção: a Efí exige mTLS na família Pix** |
| Convênio | Exige convênio/conta PJ | Cadastro self-service |
| Público | Cobrança tradicional (aluguel/mensalidade) | E-commerce, sem convênio, cartão |

**Estratégia sugerida:** bancos como trilha principal (BB → Sicredi → BTG; o
Inter já é Fase 0) + dois PSPs com papéis distintos: **Mercado Pago** pelo
alcance (a maior base de quem não tem convênio) e **Efí** pelo custo (dialeto
BACEN = mixins prontos, e o único sandbox onde o ciclo de pagamento fecha).

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

O C6 é o mais barato por larga margem: mesmo host, mesma OAuth+mTLS, mesmo
cofre — rota nova sobre o `OAuthMtlsClient` que já existe, não integração nova.
Asaas, PagBank e Cielo também oferecem link hospedado e passam no mesmo
critério; entram quando existir cliente que nenhum banco integrado atenda.

## Como cada provider entra (checklist)

1. ☐ `app/providers/<banco>.py` — classe `Provider` (mapeia boleto; herda
   `BacenPixMixin`/`BacenPixRecebidosMixin`/`BacenPixAutomaticoMixin` se BACEN).
2. ☐ `app/registry.py` — registrar em `_PROVIDERS` e (se offline) `_OFFLINE_BANK`.
3. ☐ `app/routers/bancos.py` — adicionar esquema de credenciais + entrada no catálogo.
4. ☐ `schemas.Provider` — novo valor do enum.
5. ☐ Testes mock (`tests/test_<banco>.py`) + e2e sandbox gated (`test_sandbox_<banco>.py`).
6. ☐ Doc `docs/development/<banco>-rest.md` + link no `docs/README.md`.
7. ☐ Validar no sandbox oficial → homologação → ligar `<BANCO>_REGISTERED_READY`.

Referência das APIs oficiais: cada doc de provider linka o portal do banco/PSP
(as specs **não** são versionadas neste repo — ver o padrão em
a seção "Onde baixar a documentação oficial" em [`c6-rest.md`](./c6-rest.md)).

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
