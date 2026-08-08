# Efí (364) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](./roadmap-providers.md).
> Ex-Gerencianet; hoje **Efí S.A. — Instituição de Pagamento**, código COMPE 364.
> É PSP — o dinheiro entra na conta Efí do cliente, não na conta bancária dele —
> mas entra na fila por um motivo que nenhum outro PSP tem: **a API Pix da Efí
> fala o dialeto BACEN**. Os três mixins de `bacen_pix.py` vêm de graça, e o
> que sobra de trabalho é a API de Cobranças (boleto, carnê, link) — o mesmo
> perfil de esforço do Inter, não o do Mercado Pago.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal de desenvolvedores | https://dev.efipay.com.br/ |
| API Pix (dialeto BACEN) | https://dev.efipay.com.br/docs/api-pix/ |
| Pix Automático | seção da API Pix (rec / solicrec / cobr) |
| API Cobranças (boleto, carnê, link, assinatura) | https://dev.efipay.com.br/docs/api-cobrancas/ |
| SDKs oficiais (inclusive Python) | https://github.com/efipay |

> A Efí mantém SDK Python oficial. **Não usar**: o gateway fala HTTP direto via
> `OAuthMtlsClient`, como nos outros providers — SDK de terceiro no meio é uma
> dependência a auditar e um contrato a menos sob nosso controle.

## Diferenças vs bancos (e vs os outros PSPs)

- **Pix é dialeto BACEN** (`/v2/cob`, `/v2/cobv`, `/v2/lotecobv`, `/v2/loc`,
  `/v2/pix`, webhook por chave) — a Efí foi das primeiras certificadas do país e
  é **pioneira em Pix Automático**. Herda `BacenPixMixin`,
  `BacenPixRecebidosMixin` e `BacenPixAutomaticoMixin` como C6, Sicoob e Inter.
  A tabela "Banco × PSP" do roadmap diz que PSP tem dialeto próprio — **a Efí é
  a exceção declarada**.
- **mTLS no Pix, ao contrário dos outros PSPs:** a API Pix exige certificado
  (`.p12` emitido no painel) + OAuth `client_credentials` (Basic). É o fluxo que
  o `OAuthMtlsClient` já faz para o C6. A API de Cobranças autentica **sem**
  mTLS (só `client_credentials`).
- **Dois hosts, duas famílias:** Pix em `pix.api.efipay.com.br` (homolog
  `pix-h.api.efipay.com.br`); Cobranças em host próprio (homolog separado —
  confirmar no portal; material antigo ainda cita `apis.gerencianet.com.br`).
- **Carteira PSP:** o recebido fica no saldo Efí; saque é operação do cliente no
  painel, fora do escopo da API (mesma nota do Mercado Pago).
- **O sandbox paga cobrança.** O ambiente de homologação tem endpoint para
  **simular o pagamento** de uma cob — exatamente a massa que faltou no C6
  (`P_05_*` ficou N/A porque a conta sandbox nunca recebeu Pix). Aqui,
  `pix recebidos`, devolução e webhook de liquidação são exercitáveis de ponta
  a ponta.

## Serviços da plataforma × Cobranca-API (catálogo completo)

> Legenda: ✅ disponível na Cobranca-API · 🔜 planejado (roadmap) · ⛔ sem previsão / fora de escopo do produto (cobrança).
>
> O ⛔ segue a [régua de escopo](./roadmap-providers.md#princípio-de-escopo-o-que-não-entra-em-provider-nenhum).

| ID | Serviço no portal Efí | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| EF-S01 | OAuth (`client_credentials`, Basic) + certificado `.p12` | Token de acesso; mTLS na família Pix | 🔜 | Interno (`OAuthMtlsClient` — mesmo fluxo do C6) |
| EF-S02 | Pix — cob / cobv | QR dinâmico imediato e com vencimento | 🔜 | `/pix/*` via `BacenPixMixin` (de graça) |
| EF-S03 | Pix — lote de cobv | Criar/revisar/consultar lote | 🔜 | `/pix/lote/*` (mixin) |
| EF-S04 | Pix — recebidos e devolução | `GET /v2/pix`, devolução | 🔜 | `BacenPixRecebidosMixin`; **testável no sandbox** (simulador de pagamento) |
| EF-S05 | Pix — webhook por chave | `PUT /v2/webhook/{chave}`; entrega com mTLS do lado receptor **ou** modo `skip-mtls` + HMAC na URL | 🔜 | `configurar_webhook_pix` + `POST /webhooks/efi[/{tenant}]` — o HMAC na URL casa com o nosso `?token=` fail-closed |
| EF-S06 | Pix Automático (rec / solicrec / cobr) | Recorrência BACEN — a Efí é pioneira | 🔜 | `/pix-automatico/*` via `BacenPixAutomaticoMixin`; primeiro provider onde dá para **homologar de verdade** (no C6 faltou massa; no Inter, contratação) |
| EF-S07 | Cobranças — boleto (billet) | Boleto emitido pelo PSP, com juros/multa/desconto | 🔜 | `POST /cobranca` — dialeto próprio, é o trabalho real |
| EF-S08 | Cobranças — boleto + QR Pix no mesmo documento | O híbrido da casa | 🔜 | Capacidade `bolepix` (como C6 e Inter) — confirmar nome/forma no portal |
| EF-S09 | Cobranças — **carnê** | Parcelas registradas de uma vez, herança Gerencianet | 🔜 avaliar | `POST /carne` hoje é **offline-only**; a Efí seria o primeiro carnê registrado **online**. Decisão de contrato antes de codar (ver "Particularidades") |
| EF-S10 | Cobranças — link de pagamento | Página hospedada; boleto + cartão | 🔜 possibilidade | Capacidade `checkout_cartao` — modo link, PAN no domínio da Efí; passa no critério do roadmap |
| EF-S11 | Cobranças — assinaturas (planos) | Recorrência de cartão/boleto do PSP | 🔜 avaliar | Mapear em rota própria ou deixar fora na v1 (mesma pendência do MP-S05) |
| EF-S12 | Notificações de cobrança (token) | A Efí `POST`a um token; o detalhe vem em `GET /notification/{token}` | 🔜 | `POST /webhooks/efi[/{tenant}]` — o modelo "token → consulta" **é** a nossa reconsulta fail-closed, feita protocolo |
| EF-S13 | Split de pagamento | Repartir o recebido com terceiros | ⛔ | Régua de escopo: participar do fluxo do dinheiro |
| EF-S14 | API de Pagamentos (pagar boleto), saldo/extrato da conta, Open Finance | Saída de dinheiro e dado de conta | ⛔ | Fora de escopo — o produto é cobrança (entrada) |

## Autenticação no banco

1. `POST /oauth/token` com `Authorization: Basic base64(client_id:client_secret)`
   e `grant_type=client_credentials`.
2. Família **Pix**: a conexão exige o certificado `.p12` emitido no painel Efí
   (mTLS). Família **Cobranças**: sem certificado.
3. Escopos por endpoint (cob.write, pix.read, webhook.write, …) — o portal lista
   por rota; pedir o conjunto todo no token, como no C6.

É o `OAuthMtlsClient` sem nada novo: OAuth Basic + mTLS é o fluxo C6; OAuth
Basic sem mTLS é o fluxo Cobranças. Cache de token por tenant como hoje.

## Esquema de credenciais (proposto — fonte viva: `GET /bancos`)

```
client_id        # obrigatório (aplicação criada no painel Efí)
client_secret    # obrigatório
pfx_base64       # certificado .p12 do painel — obrigatório para a família Pix
pfx_password     # senha do .p12, quando houver
cert_pem/key_pem # alternativa em PEM (POST /credenciais já aceita)
chave_pix        # chave Pix da conta Efí (destino das cobs)
```

Uma credencial, duas famílias: o provider decide por rota se a chamada vai com
ou sem o certificado.

## Superfície prevista (Efí → gateway)

| Operação | Efí | Endpoint do gateway |
|---|---|---|
| Cobrança Pix (cob/cobv) | `PUT/POST /v2/cob`, `/v2/cobv` | `POST /pix` (mixin BACEN) |
| Lote de cobv | `PUT/PATCH/GET /v2/lotecobv/{id}` | `POST/PATCH/GET /pix/lote/*` |
| Pix recebidos / devolução | `GET /v2/pix`, `PUT .../devolucao/{id}` | `GET /pix/recebidos`, devolução |
| Pix Automático | `/v2/rec`, `/v2/solicrec`, `/v2/cobr` | `/pix-automatico/*` |
| Webhook Pix por chave | `PUT /v2/webhook/{chave}` | `POST /config/webhook-banco` |
| Boleto | API Cobranças (billet) | `POST /cobranca` |
| Boleto híbrido (QR no documento) | API Cobranças | `POST /bolepix` |
| Carnê registrado | API Cobranças (carnet) | avaliar — `POST /carne` online |
| Link de pagamento | API Cobranças (link) | `POST /checkout` (modo link) |
| Notificação de cobrança | token → `GET /notification/{token}` | `POST /webhooks/efi[/{tenant}]` |

## Particularidades conhecidas (a validar no sandbox)

- **Carnê online é decisão de contrato, não só de código.** `POST /carne` hoje
  significa "engine offline monta o PDF de 3 vias". Carnê Efí é outra coisa:
  N cobranças registradas no PSP com vencimentos encadeados. Opções: (a) o
  mesmo `POST /carne` com `provider=efi` registra online — coerente com "trocar
  de mundo é trocar um campo"; (b) fica fora da v1. Decidir **antes** de
  implementar, com o payload real do portal na mesa.
- **Status a normalizar (família Cobranças):** `new/waiting → pendente`,
  `paid → liquidado`, `unpaid/canceled → baixado`, `refunded → devolvido`
  (nomes exatos a confirmar no portal). A família Pix já sai normalizada pelo
  mixin.
- **Webhook de Pix exige HTTPS com particularidades** (mTLS do lado receptor ou
  `skip-mtls` com HMAC). Documentar no guia de deploy o que o consumidor precisa
  expor — mesmo assunto já resolvido para o C6, prosa a reaproveitar.
- Hosts e nomes de campo da API de Cobranças **a confirmar no portal** — este
  documento foi escrito sem versionar spec de terceiro, como os demais.

## Homologação (o argumento de venda interno)

Sandbox self-service (sem convênio, sem gerente) e **com simulador de
pagamento**: dá para criar a cob, "pagá-la", receber o webhook e devolver — o
ciclo completo que nenhum banco da Fase 0 permitiu exercitar inteiro.
`scripts/homologacao_efi.py` no molde dos outros três runners (mesmos
argumentos, mesma evidência JSON), e a evidência entra em
`docs/homologacao/evidencia-sandbox-efi.json` com a nota de que **é sandbox de
comportamento real** (categoria do Inter, não do Sicoob).

## Esforço estimado

**Baixo-médio** — o menor da fila de PSPs, e comparável ao Inter:

| Bloco | Custo | Por quê |
|---|---|---|
| Pix completo (cob, cobv, lote, recebidos, webhook, Pix Automático) | **Muito baixo** | `PIX_BASE` + auth; mixins prontos |
| Auth | Muito baixo | `OAuthMtlsClient` já faz OAuth Basic + mTLS (C6) |
| Boleto / bolepix (API Cobranças) | Médio | dialeto próprio — é o trabalho real |
| Webhook de cobrança (token → consulta) | Baixo | o modelo do PSP coincide com o nosso fail-closed + reconsulta |
| Carnê online | Médio | decisão de contrato antes do código |
| Link de pagamento | Baixo | rota `/checkout` já existe; mapear payload |

Fases sugeridas: **F1** Pix inteiro via mixins + homologação com simulador
(entrega valor sozinha e destrava o Pix Automático de verdade) → **F2** boleto
+ bolepix + notificações → **F3** link de pagamento; carnê e assinaturas
entram se houver demanda de cliente.

## Pendências

- ☐ Confirmar no portal: host/homolog da API de Cobranças, payloads de boleto,
  carnê e link, nomes de status, forma do boleto híbrido.
- ☐ Decidir o contrato do carnê online (EF-S09) — a alternativa (a) é a
  preferida se o payload permitir.
- ☐ Criar conta Efí + aplicação + `.p12` de homologação quando a implementação
  entrar na fila.
