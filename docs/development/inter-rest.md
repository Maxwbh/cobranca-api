# Banco Inter (077) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](./roadmap-providers.md).
> Prioridade **1ª** — melhor custo-benefício: mesma família de auth do C6
> (mTLS + OAuth), Bolepix nativo, self-service.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal do Desenvolvedor | https://developers.inter.co/ |
| API Cobrança (Boleto com Pix / Bolepix) | https://developers.inter.co/references/cobranca-bolepix |
| API Pix | https://developers.inter.co/references/pix |
| API Banking (empresas) | https://inter.co/empresas/api-banking/ |

## Serviços do banco × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).

| ID | Serviço no portal Inter | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| INT-S01 | API Cobrança v3 (Bolepix nativo) | Boleto registrado híbrido com Pix + PDF | 🔜 | `/cobranca/*`, `/bolepix` (1ª prioridade do roadmap) |
| INT-S02 | API Pix (BACEN) | Cob, cobv, recebidos, webhook | 🔜 | `/pix/*` — grátis via `BacenPixMixin` (só `PIX_BASE`) |
| INT-S03 | Pix Automático | Débito recorrente | 🔜 | `/pix-automatico/*` — via mixin |
| INT-S04 | Webhooks de cobrança | Avisos de pagamento | 🔜 | `/config/webhook-banco` + `/webhooks/inter[/{tenant}]` |
| INT-S05 | API Banking — extrato | Movimentações da conta | 🔜 | `GET /extrato` |
| INT-S06 | API Banking — pagamentos/DARF | Saída de dinheiro | ⛔ | Fora de escopo — produto é cobrança |

## Autenticação no banco

- **OAuth2 `client_credentials` + mTLS** (certificado gerado na criação da
  aplicação no Internet Banking → "Soluções para sua empresa" → "Nova Integração").
- **Scopes por API** selecionados na criação (ex.: `boleto-cobranca.read/write`,
  `pix.read/write`, `webhook.read/write`).
- Certificado válido por **1 ano** (renovação = nova aplicação).
- → Encaixa direto no `OAuthMtlsClient` (mesmo fluxo do C6).

## Esquema de credenciais (proposto — ver `GET /bancos`)

```
client_id      # da aplicação (portal Inter)
client_secret  # da aplicação
pfx_base64     # certificado mTLS (PKCS12 em base64)
pfx_password   # senha do certificado
scopes         # opcional (default do provider)
```

## Superfície prevista (Inter → gateway)

| Operação | Inter | Endpoint do gateway |
|---|---|---|
| Emitir boleto/Bolepix | `POST /cobranca/v3/cobrancas` | `POST /cobranca` / `POST /bolepix` |
| Consultar | `GET /cobranca/v3/cobrancas/{codigoSolicitacao}` | `GET /cobranca/{id}` |
| PDF | `GET /cobranca/v3/cobrancas/{codigoSolicitacao}/pdf` | `GET /cobranca/{id}/pdf` |
| Cancelar/baixar | `POST /cobranca/v3/cobrancas/{id}/cancelar` | `DELETE /cobranca/{id}` |
| **Pix (BACEN)** | `/pix/v2/cob`, `/cobv`, `/webhook`, `/pix` | herdado do `BacenPixMixin` |
| Webhook cobrança | callback configurável | `POST /webhooks/inter[/{tenant}]` |

> **URLs/paths exatos a confirmar** na doc oficial e no sandbox durante a
> implementação (o padrão acima segue a API Cobrança v3 do Inter).

## Mapeamento (o real trabalho = boleto)

`Cobranca` → payload Inter (`seuNumero`, `valorNominal`, `dataVencimento`,
`pagador{cpfCnpj, nome, tipoPessoa, endereco...}`, `formasRecebimento: [BOLETO, PIX]`
para híbrido). Pix reaproveita o dialeto BACEN (só muda `PIX_BASE`).

## Esforço estimado

**Baixo.** Auth = reutiliza `OAuthMtlsClient`; Pix/Pix Automático = grátis pelo
mixin; resta o provider de boleto (payload) + testes + e2e sandbox. Nos moldes
do que já foi feito para o C6.
