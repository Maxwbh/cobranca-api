# Mercado Pago (PSP) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](./roadmap-providers.md).
> Prioridade **1ª da categoria PSP**. **Não é banco:** o dinheiro cai na conta/
> carteira Mercado Pago (depois saca), não na conta bancária do cliente.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal Developers | https://www.mercadopago.com.br/developers/pt |
| Pagamento Pix (Orders/Payments API) | https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/payment-integration/pix |
| Pagamento Boleto | https://www.mercadopago.com.br/developers/pt/docs/checkout-api-orders/payment-integration/boleto |
| OAuth / Access Token | https://www.mercadopago.com.br/developers/pt/reference/oauth/_oauth_token/post |
| Assinaturas (Preapproval) | https://www.mercadopago.com.br/developers/pt/reference/subscriptions/_preapproval/post |

## Diferenças vs bancos (importante)

- **Dialeto próprio** (Orders / `/v1/payments`) — **não** reaproveita o
  `BacenPixMixin` do BACEN. Precisa de um provider dedicado.
- **Auth simples:** `Access Token` (Bearer) — **sem mTLS, sem OAuth por request**.
  OAuth (PKCE) só para modelo **marketplace** (agir por conta de terceiros).
- Suporta **Pix, boleto, cartão e carteira** numa API só, e **assinaturas
  (preapproval)** como recorrência nativa (alternativa ao Pix Automático).

## Serviços da plataforma × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).

| ID | Serviço Mercado Pago | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| MP-S01 | Payments/Orders — Pix | QR + copia-e-cola | 🔜 | `POST /pix` (dialeto próprio, provider dedicado) |
| MP-S02 | Payments/Orders — Boleto | Boleto não-registrado via PSP | 🔜 | `POST /cobranca` |
| MP-S03 | Payments/Orders — Cartão | Crédito/débito | 🔜 | Avaliar — seria capacidade NOVA da plataforma (hoje não há cartão) |
| MP-S04 | Refunds | Estorno/devolução | 🔜 | `PUT /pix/recebidos/.../devolucao` (mapear) |
| MP-S05 | Assinaturas (Preapproval) | Recorrência nativa do PSP | 🔜 | Mapear em `/pix-automatico` ou rota própria |
| MP-S06 | Webhooks (IPN) | Notificações de pagamento | 🔜 | `/webhooks/mercadopago[/{tenant}]` |
| MP-S07 | Checkout Pro (página hospedada) | `POST /checkout/preferences` → `init_point` (URL do checkout) | 🔜 | Possibilidade — página hospedada, PAN fora daqui, atende à restrição de **modo link**. Coerente com o critério de entrada: cartão existe onde a instituição **oferece** — o Mercado Pago oferece, o Sicoob não |
| MP-S08 | Marketplace (OAuth) | Agir em nome de terceiros | ⛔ | Fora de escopo |

## Esquema de credenciais (proposto — ver `GET /bancos`)

```
access_token   # Access Token de produção/teste (Bearer) — único obrigatório
public_key     # opcional (checkout no front)
```
> Encaixa direto na tokenização `bapi_` (é só um Bearer — mais simples que os bancos).

## Superfície prevista (Mercado Pago → gateway)

| Operação | Mercado Pago | Endpoint do gateway |
|---|---|---|
| Cobrança Pix | `POST /v1/payments` (`payment_method_id: pix`) → QR + copia-e-cola | `POST /pix` |
| Consultar pagamento | `GET /v1/payments/{id}` | `GET /pix/{id}` / `GET /cobranca/{id}` |
| Boleto | `POST /v1/payments` (`payment_method_id: bolbradesco`) | `POST /cobranca` |
| Estorno/devolução | `POST /v1/payments/{id}/refunds` | `PUT /pix/recebidos/.../devolucao` |
| Assinatura (recorrência) | `POST /preapproval` | (mapear em `/pix-automatico` ou rota própria) |
| Webhook (IPN) | notificação de pagamento | `POST /webhooks/mercadopago[/{tenant}]` |

## Status a normalizar

`pending → pendente`, `approved → liquidado`, `cancelled/refunded → baixado`,
`rejected → erro` (mapa próprio, diferente do BACEN).

## Esforço estimado

**Médio.** Auth trivial (só Bearer). Mas é **API proprietária** — provider
dedicado mapeando Pix/boleto/assinatura no dialeto Orders/Payments (não herda o
mixin BACEN). Sandbox e credenciais de teste são self-service (sem convênio).
