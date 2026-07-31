# Roadmap de Providers — Bancos e PSPs

> Próximos passos de integração do **gateway** (`gateway`). Estado
> atual: **C6** e **Sicoob** REST validados em sandbox; **18 bancos** via CNAB
> offline (engine pyCobrança). Cada linha aqui é **planejada**, não implementada.

## Princípio de esforço (o que torna barato)

- **Pix é padronizado pelo BACEN** (`/cob`, `/cobv`, `/cobr`, `/loc`, `/webhook`,
  `/pix`) → já implementado uma vez em `app/providers/bacen_pix.py`. Para um banco
  novo, Pix + Pix Automático = **só `PIX_BASE` + auth**.
- **Auth** já coberta pelo `OAuthMtlsClient` (OAuth `client_credentials` + mTLS +
  token estático + headers custom) e pela **tokenização** (`bapi_`).
- **O trabalho real é o boleto registrado** (payload proprietário por banco) —
  1 provider novo + testes. `GET /bancos` lista o novo provider automaticamente
  (capacidades por introspecção).

## Fases

### ✅ Fase 0 — Concluída
| Provider | Tipo | Estado |
|---|---|---|
| C6 Bank (336) | Banco REST | boleto, Pix, Bolepix, extrato, conciliação, Pix Automático — validado sandbox |
| Sicoob (756) | Banco REST | boleto v3, Pix, extrato, Pix Automático — validado sandbox |
| 18 bancos CNAB | Offline | via engine pyCobrança |

### 🎯 Fase 1 — Bancos self-service (próximos)
| Prioridade | Provider | Cód | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª ⭐ | **Banco Inter** | 077 | Melhor self-service; mTLS+OAuth (= família C6); Bolepix nativo | **Baixo** | [inter-rest.md](./inter-rest.md) |
| 2ª | **Banco do Brasil** | 001 | Maior alcance; API Cobrança + Arrecadação Pix; híbrido | Médio | [banco-do-brasil-rest.md](./banco-do-brasil-rest.md) |
| 3ª | **Sicredi** | 748 | Cooperativo; reaproveita quase tudo do Sicoob | **Muito baixo** | (planejado) |

### 🔌 Fase 2 — PSP / Agregador
| Prioridade | Provider | Tipo | Por quê | Esforço | Doc |
|---|---|---|---|---|---|
| 1ª ⭐ | **Mercado Pago** | PSP | Maior plataforma de pagamento; API mais fácil (só access token); Pix+boleto+cartão+assinatura | Médio | [mercado-pago-rest.md](./mercado-pago-rest.md) |
| 2ª | Efí (Gerencianet) / Asaas | PSP | Dev-friendly; cobrem quem não tem convênio | Médio | (planejado) |

### 🕓 Fase 3 — Avaliar (onboarding pesado / API limitada)
| Provider | Cód | Observação |
|---|---|---|
| Bradesco | 237 | Maior base de contas, mas onboarding pesado |
| Santander | 033 | Big 5; API disponível |
| Itaú | 341 | Mais rentável, mas onboarding notoriamente difícil (precisa gerente) |
| Nubank / Caixa | 260 / 104 | Base gigante, mas API PJ de boleto registrado limitada/incerta |

## Diferença Banco × PSP (decisão de produto)

| | Banco (C6, Sicoob, Inter, BB…) | PSP (Mercado Pago, Efí, Asaas) |
|---|---|---|
| Recebimento | Na **conta bancária do próprio cliente** | Na **conta/carteira do PSP** (depois saca) |
| Dialeto Pix | **BACEN** → reaproveita `bacen_pix.py` ✅ | **Próprio** (não reaproveita) |
| Auth | OAuth + mTLS (certificado) | Access token (Bearer), sem mTLS |
| Convênio | Exige convênio/conta PJ | Cadastro self-service |
| Público | Cobrança tradicional (aluguel/mensalidade) | E-commerce, sem convênio, cartão |

**Estratégia sugerida:** bancos como trilha principal (Inter → BB → Sicredi) +
Mercado Pago como o provider "PSP" de referência (menor atrito, cartão + carteira).

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
| 7 | `## Pix BACEN compartilhado` (só `PIX_BASE`; mixins fazem o resto) | ✔ | — (PSP tem dialeto próprio) |
| 8 | `## account_config (por tenant)` | ✔ | ✔ |
| 9 | `## Particularidades do banco` (CIP, carteiras, conciliação, status a normalizar…) | ✔ | ✔ |
| 10 | `## Autenticação da API (token bapi_)` (mecanismo único) | ✔ | ✔ |
| 11 | `## Validação` (sandbox/e2e) **ou** `## Esforço estimado` (planejado) | ✔ | ✔ |
| 12 | `## Pendências / homologação` | ✔ | ✔ |
