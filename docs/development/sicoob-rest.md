# Sicoob — Integração REST (boleto v3, Pix BACEN)

> Implementada no gateway Python (`gateway`), provider `sicoob`.
> Fontes: [Portal Developers Sicoob](https://developers.sicoob.com.br/portal/),
> doc Postman oficial da Cobrança v3 e integrações de mercado. A documentação
> oficial do Sicoob é notoriamente incompleta — itens "a confirmar" fecham na
> homologação (mesmo processo feito com o C6).

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal Developers Sicoob | https://developers.sicoob.com.br/portal/ |
| Sandbox (mock oficial) | https://sandbox.sicoob.com.br/sicoob/sandbox |
| Cobrança Bancária v3 (referência/Postman oficial) | via portal (API Cobrança Bancária) |
| Pix (BACEN) | via portal (API Pix — `/pix/api/v2`) |

## Serviços do banco × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).

| ID | Serviço no portal Sicoob | O que faz | Status | Uso na Cobranca-API |
|---|---|---|:---:|---|
| SIC-S01 | Autenticação (OAuth + scopes + mTLS) | Token de acesso | ✅ | Interno (`OAuthMtlsClient` + header `client_id`) |
| SIC-S02 | Cobrança Bancária v3 | Emitir/consultar boleto registrado, segunda via | ✅ | `/cobranca/*` (baixa: rota a confirmar na homologação) |
| SIC-S03 | Pix (BACEN `/pix/api/v2`) | Cob, cobv, lote, Pix recebidos, devoluções, webhook por chave | ✅ | `/pix/*`, `/config/webhook-pix` |
| SIC-S04 | Pix Automático (rec/solicrec/cobr) | Débito recorrente via Pix | ✅ | `/pix-automatico/*` |
| SIC-S05 | Conta Corrente v4 — extrato | Movimentações (mensal) | ✅ | `GET /extrato` (multi-mês → 422) |
| SIC-S06 | Conta Corrente v4 — saldo | Saldo da conta | 🔜 | Avaliar exposição (`GET /extrato` hoje cobre movimentações) |
| SIC-S07 | Pagamentos (pagar boletos/convênios) | Saída de dinheiro | ⛔ | Fora de escopo — produto é cobrança |
| SIC-S08 | SPB (TED) / Poupança | Transferências / aplicações | ⛔ | Fora de escopo |
| SIC-S09 | Open Finance | Compartilhamento de dados | ⛔ | Fora de escopo |
| SIC-S10 | Cobrança v3 — alteração de pagador | Corrigir dados do sacado de boleto emitido | 🔜 | Sem rota; hoje o `PUT /cobranca/{id}` não é implementado pelo provider |
| SIC-S11 | Cobrança v3 — negativação | Negativar pagador de título vencido | 🔜 | É cobrança (régua de recebimento), não pagamento — cabe no escopo |
| SIC-S12 | Cobrança v3 — protesto | Protestar título vencido | 🔜 | Idem SIC-S11 |
| SIC-S13 | Cobrança v3 — movimentação | Solicitar, consultar e baixar arquivo de movimentação | 🔜 | Equivale ao retorno CNAB pela API; hoje a conciliação é por `/extrato` e OFX |

## Autenticação no banco

| Item | Valor |
|---|---|
| Fluxo | OAuth2 `client_credentials` + **scopes** + **mTLS** |
| Token | `https://auth.sicoob.com.br/auth/realms/cooperado/protocol/openid-connect/token` |
| Certificado | PFX cadastrado no portal. Produção: **A1** e-CNPJ (PJ) ou e-CPF (PF) **ICP-Brasil**, com *Uso Avançado da Chave* contendo **Autenticação de Cliente** (`1.3.6.1.5.5.7.3.2`) — sem esse atributo o mTLS não estabelece |
| Peculiaridade | header **`client_id` em toda request** |
| Sandbox | `https://sandbox.sicoob.com.br/sicoob/sandbox` — token estático do portal, **sem mTLS** (aponte com `SICOOB_BASE_URL`/`SICOOB_AUTH_URL`). É **mock de schema**: devolve dado aleatório válido, sem relação com o enviado — ver [homologação](../homologacao/README.md#sicoob--o-que-o-roteiro-dele-prova-e-o-que-não-prova) |

> **Token dura 300 s e não há refresh token** (FAQ do portal). O
> `OAuthMtlsClient` já respeita o `expires_in` devolvido pelo banco, com 30 s de
> margem — não há nada a ajustar, mas quem for medir latência precisa saber que
> uma re-autenticação cai a cada 5 min.

> **Aplicativo PJ nasce "Pendente".** Em produção, criar a credencial não basta:
> um responsável pela conta precisa autorizar no **Sicoobnet Empresarial**
> (*Transações Pendentes → Autorização para Uso de APIs*). É passo humano, fora
> da API, e costuma ser o que trava o go-live.

### Limite de requisições

O Sicoob aplica *rate limit* por segundo e devolve **`429`** ao estourar. Os
números publicados no portal:

| Endpoint | Limite |
|---|---|
| Cobrança — movimentações (solicitar, consultar, download) | **10/s** |
| Cobrança — consultar boleto | **20/s** |

A API repassa o `429` com o `Retry-After` do banco quando ele vem
(`gateway/app/main.py`), mas **não enfileira nem re-tenta**: quem chama é que
decide a política, porque só o consumidor sabe se o pedido pode esperar. O
próprio Sicoob recomenda fila e reenvio com espera.

⚠️ **O Pix de recebimento caiu de 50 para 25 req/s em 13/07/2026**, e o motivo
publicado nos diz respeito: *"padrões de consumo incompatíveis com o uso
esperado, especialmente em consultas recorrentes de status de QR Codes"* — ou
seja, polling. Quem consome esta API para saber se um Pix foi pago deve usar o
**webhook por chave** (`PUT /config/webhook-pix`), não laço de consulta. O
limite tende a apertar de novo se o padrão continuar.

Scopes usados (pedidos no token): `cobranca_boletos_incluir/consultar/baixa`,
`cob.*`, `cobv.*`, `lotecobv.*`, `pix.*`, `webhook.*`, `payloadlocation.*`.
Conta corrente (extrato mensal — implementado): `cco_extrato`, `cco_saldo`.

## Esquema de credenciais (ver `GET /bancos`)

```
client_id        # aplicação no portal (vira header em toda request)
pfx_base64       # certificado mTLS (produção — e-CNPJ ICP-Brasil)
pfx_password     # senha do certificado
access_token     # SÓ sandbox (token estático do portal, sem mTLS)
```

## Superfície (Sicoob → gateway)

| Operação | Sicoob | Endpoint do gateway |
|---|---|---|
| Emitir boleto | `POST /cobranca-bancaria/v3/boletos` (**v3** — v2 descontinuada em 2025) | `POST /cobranca` |
| Consultar boleto | `GET /v3/boletos?numeroCliente&codigoModalidade&nossoNumero` | `GET /cobranca/{id}` |
| Segunda via (PDF) | consulta com `gerarPdf=true` | `GET /cobranca/{id}/pdf` |
| Baixar | comando de baixa (a confirmar rota exata) | `DELETE /cobranca/{id}` |
| **Pix (BACEN)** | `/pix/api/v2` — **mesmo dialeto do C6** | `/pix`, `/pix/{txid}`, `PATCH`, listas, `/pix/lote/*` |
| Extrato conta-corrente | `GET /conta-corrente/v4/extrato/{mes}/{ano}` (mensal) | `GET /extrato` |
| Webhook Pix | BACEN (`/webhook`, push com array `pix`) | `POST /webhooks/sicoob[/{tenant}]` |

**Boleto híbrido:** com chave Pix vinculada à conta, a emissão v3 já devolve
`pixCopiaECola` (QR no boleto) — normalizado em `CobrancaOut.pix_copia_cola`.

## Pix Automático, recebidos e webhook por chave (BACEN, compartilhado)

Implementados no dialeto BACEN compartilhado (`bacen_pix.py`) — valem para C6 e
Sicoob: **Pix Automático** (`/pix-automatico/*`: rec, solicrec, locrec, cobr,
retentativa, webhookrec/cobr — o agendamento de cada cobrança fica no produto
consumidor), **Pix recebidos** (`/pix/recebidos`, devoluções) e **webhook por
chave** (`/config/webhook-pix`).

O dialeto é implementado UMA vez (`BacenPixMixin`) e cada provider define só
o prefixo: C6 `/v2/pix`, Sicoob `/pix/api/v2` — idêntico em qualquer banco futuro.

## Particularidades do banco — conciliação

- **Pix:** webhook BACEN (tempo real) → push assinado ao consumidor.
- **Boleto:** o Sicoob não tem webhook de boleto — conciliação por **polling**
  (`GET /cobranca/{id}`). O agendamento do polling fica no **produto
  consumidor** — o gateway é interface de consumo (stateless), por decisão
  de arquitetura.

## Autenticação da API (token `bapi_`)

Cada banco tem seu **próprio esquema** de credenciais, mas o mecanismo da API é
o mesmo: `POST /credenciais` recebe os parâmetros deste banco, armazena cifrado
(zero-knowledge) e devolve o token `bapi_`; as demais chamadas validam pelo
`Authorization: Bearer bapi_...`. Esquema vigente por banco: `GET /bancos`.

## account_config (por tenant)

`{numeroCliente, codigoModalidade (1), numeroContaCorrente, chave_pix, ...}`
Credenciais: mesmos 3 modos do C6 (Bearer `bapi_` / request / cofre `VAULT__`).

## Validado no SANDBOX oficial (mock do portal)

Com o token estático do portal (`SICOOB_SANDBOX_TOKEN`/`_CLIENT_ID`), o e2e
(`tests/test_sandbox_sicoob.py`) validou:

- **Consulta de boleto** (`GET /v3/boletos`): 200 com o contrato completo
  (`resultado{linhaDigitavel, codigoBarras, ...}`) — confirma o mapeamento.
- **Segunda via**: rota dedicada `GET /v3/boletos/segunda-via` (descoberta no
  sandbox; o provider usa essa rota).
- **Pix**: `POST /cob` 200 — o Sicoob devolve **`brcode`** (não
  `pixCopiaECola`); normalizado no `_pix_out` compartilhado.
- **Pix recebidos** (`GET /pix`): 200 `{parametros, pix[]}` — mesmo dialeto
  BACEN do C6 ✔.
- **Pix Automático** (`POST /rec`): 200 no sandbox — PA validado nos DOIS
  bancos.
- **Limitação do mock**: o `POST /v3/boletos` (emissão) devolve um **400
  enlatado** (`{"mensagens":[{"mensagem":"string"...}]}`) para qualquer
  payload — comportamento do simulador, não do contrato; a emissão real fecha
  na homologação com a cooperativa.

## A confirmar na homologação (produção)

1. Emissão real (`POST /v3/boletos`) — mock do sandbox não valida payload.
2. Rota/verbo exatos da **baixa** v3.
3. Campos mínimos aceitos pela cooperativa (varia por config da conta).
4. Webhook de movimentação de boleto (se a v3 expuser, substitui o polling).
