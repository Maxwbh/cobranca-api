# Banco do Brasil (001) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](./roadmap-providers.md).
> Prioridade **1ª da Fase 1** — maior alcance de mercado.
> Quando entrar, a chamada é `provider=on&banco=banco_brasil`.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal Developers BB | https://developers.bb.com.br/ |
| API Cobrança (BB como Serviço) | https://www.bb.com.br/site/developers/bb-como-servico/api-cobranca/ |
| API Arrecadação integrada ao Pix | https://www.bb.com.br/site/developers/api-arrecadacao-integrada-ao-pix/ |
| API Pix | https://developers.bb.com.br/ (catálogo → Pix) |

## Serviços do banco × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).

| ID | Serviço no portal BB | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| BB-S01 | API Cobrança (boleto híbrido c/ Pix) | Emitir/consultar/alterar/baixar boleto registrado | 🔜 | `/cobranca/*` |
| BB-S02 | API Pix (BACEN) | Cob, cobv, recebidos, webhook | 🔜 | `/pix/*` — via `BacenPixMixin` |
| BB-S03 | Pix Automático | Débito recorrente | 🔜 | `/pix-automatico/*` — via mixin |
| BB-S04 | Arrecadação integrada ao Pix | Guias/convênios de arrecadação com QR | 🔜 | Avaliar mapeamento (pode entrar em `/cobranca` ou rota própria) |
| BB-S05 | Extratos | Movimentações da conta | 🔜 | `GET /extrato` |
| BB-S06 | Pagamentos em lote | Saída de dinheiro | ⛔ | Fora de escopo — produto é cobrança |

## Pré-requisitos

- **Convênio de cobrança ativo** no BB (obrigatório para emitir boleto).
- Aplicação criada no Portal Developers → `client_id` + `client_secret`.

## Autenticação no banco

- **OAuth2 `client_credentials`** (token em `oauth.bb.com.br`).
- **Header `gw-dev-app-key`** (developer application key) em **toda request** —
  peculiaridade do gateway do BB (padrão de header extra, como o `client_id` do
  Sicoob → suportado por `default_headers` do `OAuthMtlsClient`).
- mTLS conforme o produto/ambiente.

## Esquema de credenciais (proposto — ver `GET /bancos`)

```
client_id            # aplicação (portal BB)
client_secret        # aplicação
developer_app_key    # gw-dev-app-key (header em toda request)
pfx_base64/pfx_password   # se o produto exigir mTLS
```

## Superfície prevista (BB → gateway)

| Operação | BB | Endpoint do gateway |
|---|---|---|
| Emitir boleto (híbrido c/ Pix) | `POST /cobrancas/v2/boletos` | `POST /cobranca` |
| Consultar | `GET /cobrancas/v2/boletos/{id}` | `GET /cobranca/{id}` |
| Baixar | `POST /cobrancas/v2/boletos/{id}/baixar` | `DELETE /cobranca/{id}` |
| Alterar | `PATCH /cobrancas/v2/boletos/{id}` | `PUT /cobranca/{id}` |
| **Pix (BACEN)** | `/pix/v2/cob`, `/cobv`, `/webhook` | herdado do `BacenPixMixin` |

> **Paths/versões exatos a confirmar** na doc oficial e no sandbox (o BB usa
> `numeroConvenio`, `numeroCarteira`, `numeroVariacaoCarteira` no payload).

## account_config previsto

`{numeroConvenio, numeroCarteira, numeroVariacaoCarteira, chave_pix, ...}`

## Esforço estimado

**Médio.** Auth reutiliza `OAuthMtlsClient` (+ header `gw-dev-app-key`); Pix pelo
mixin; boleto exige mapear o payload de convênio/carteira do BB + testes + e2e.
Bloqueio externo: obter **convênio ativo** para homologar emissão real.
