# Banco Inter (077) — Integração REST · **IMPLEMENTADO**

> **Status:** provider no ar (`gateway/app/providers/inter.py`), coberto por
> `gateway/tests/test_cobranca_inter.py` e **validado no sandbox do banco** —
> `scripts/homologacao_inter.py`, evidência em
> [`evidencia-sandbox-inter.json`](../homologacao/evidencia-sandbox-inter.json).
>
> **Chamada:** `provider=on&banco=inter` (`provider=inter` segue valendo como
> apelido legado até a 3.0.0). O Inter é o único sem caminho `off`: a engine não
> tem o layout 077, e `provider=off&banco=inter` responde `422` em vez de emitir
> no banco errado.

O contrato abaixo não é suposição: foi extraído do **SDK oficial do banco**,
[`inter-co/pj-sdk-java`](https://github.com/inter-co/pj-sdk-java) (`Constants.java`,
`BillingSdk.java`, `BillingIssueRequest.java`, `Person.java`, `BillingSituation.java`).
Onde o SDK e o portal divergirem, o portal vence — mas o SDK é o que o banco
publica como uso correto.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal do Desenvolvedor | https://developers.bancointer.com.br/ |
| SDK oficial (Java) | https://github.com/inter-co/pj-sdk-java |
| Onde obter o certificado | https://developers.bancointer.com.br/v4/docs/onde-obter-o-certificado |

## Ambientes

| | Base |
|---|---|
| **Produção** | `https://cdpj.partners.bancointer.com.br` |
| **Sandbox** | `https://cdpj-sandbox.partners.uatinter.co` |

**Há sandbox** — o que muda o plano: dá para fazer o mesmo roteiro de
homologação contra a API que fizemos no C6, antes de qualquer conta de produção.
Se o comportamento for real (como o C6) e não mock de schema (como o Sicoob),
a validação vale integração ponta a ponta.

## Autenticação no banco

| Item | Valor |
|---|---|
| Fluxo | OAuth2 `client_credentials` + **mTLS** |
| Token | `POST {base}/oauth/v2/token` (`application/x-www-form-urlencoded`) |
| Certificado | gerado na criação da aplicação no Internet Banking; válido por **1 ano** (renovar = nova aplicação) |
| Header extra | **`x-conta-corrente`** quando a aplicação enxerga mais de uma conta |

→ Encaixa direto no `OAuthMtlsClient`, sem cliente novo.

> ⚠️ O `x-conta-corrente` é a mesma armadilha que o `numeroCliente` do Sicoob:
> identificador de conta que **não vai no path nem no corpo**. Lá isso fez as
> rotas de leitura chamarem o banco com o campo vazio e receberem `400` sempre,
> porque o router montava o provider sem `account_config`. Se o Inter entrar,
> a conta precisa chegar às rotas de leitura desde o primeiro commit — as
> query `numero_cliente`/`codigo_modalidade` já abriram esse caminho.

### Scopes (do SDK)

| Área | Scopes |
|---|---|
| Cobrança | `boleto-cobranca.read`, `boleto-cobranca.write` |
| Pix | `cob.read/write`, `cobv.read/write`, `lotecobv.read/write`, `pix.read/write`, `payloadlocation.read/write`, `webhook.read/write` |
| Extrato | `extrato.read` |
| Pagamentos (⛔ fora de escopo) | `pagamento-boleto.*`, `pagamento-darf.write`, `pagamento-lote.*`, `pagamento-pix.*`, `webhook-banking.*` |

## Serviços do banco × Cobranca-API

> Legenda: ✅ disponível · 🔜 planejado · ❓ dialeto pronto e **não confirmado**
> no banco · ⛔ fora de escopo do produto (cobrança).

| ID | Serviço no Inter | Endpoint do banco | Status | Uso na Cobranca-API |
|---|---|---|:---:|---|
| INT-S01 | Cobrança v3 — emitir | `POST /cobranca/v3/cobrancas` | ✅ | `POST /cobranca` |
| INT-S02 | Cobrança v3 — consultar | `GET /cobranca/v3/cobrancas/{codigoSolicitacao}` | ✅ | `GET /cobranca/{id}` |
| INT-S03 | Cobrança v3 — PDF | `GET /cobranca/v3/cobrancas/{codigoSolicitacao}/pdf` | ✅ | `GET /cobranca/{id}/pdf` |
| INT-S04 | Cobrança v3 — cancelar | **`POST`** `/cobranca/v3/cobrancas/{id}/cancelar` | ✅ | `DELETE /cobranca/{id}` |
| INT-S05 | Cobrança v3 — listar / sumário | `GET /cobranca/v3/cobrancas`, `/sumario` | 🔜 | Sem rota hoje; avaliar |
| INT-S06 | Cobrança v3 — webhook | `PUT/GET/DELETE /cobranca/v3/cobrancas/webhook` | ✅ | `/config/webhook-banco` + `POST /webhooks/inter[/{tenant}]` |
| INT-S07 | Pix (BACEN) | `/pix/v2` — `/cob`, `/cobv`, `/lotecobv`, `/pix`, `/loc`, `/webhook` | ✅ | **Grátis** pelo `BacenPixMixin`: só `PIX_BASE = "/pix/v2"` |
| INT-S08 | Banking v2 — extrato | `GET /banking/v2/extrato` | ✅ | `GET /extrato` |
| INT-S09 | Banking v2 — saldo | `GET /banking/v2/saldo` | 🔜 | Sem rota hoje (idem `SIC-S06`) |
| INT-S10 | Banking v2 — pagamentos, DARF, lote, Pix pagamento | `/banking/v2/pagamento*` | ⛔ | Saída de dinheiro |
| INT-S11 | Pix Automático (`rec`/`solicrec`/`cobr`) | `/pix/v2/rec`, `/solicrec`, `/cobr` | ❓ | Dialeto pronto pelo mixin; **não confirmado no banco** — ver *O que falta* |

> **Pix Automático não consta no SDK oficial.** Não há `rec`/`solicrec`/`cobr`
> em `pj-sdk-java` — pode ser ausência do SDK, não da API. Enquanto não se
> confirma, o catálogo **não anuncia** a capacidade: ver *O que falta*, item 1.
> C6 (15 casos em 4 jornadas) e Sicoob (`PA_01`) estão confirmados no sandbox.

## Mapeamento — onde está o trabalho real

O Pix vem de graça pelo mixin. O boleto é o que exige tradução.

### Payload de emissão

`seuNumero`, `valorNominal`, `dataVencimento`, `numDiasAgenda`, `pagador`,
`desconto`, `multa`, `mora`, `mensagem`, `beneficiarioFinal`, `formasRecebimento`.

`pagador` é **plano**, não aninhado como no C6:
`cpfCnpj`, `tipoPessoa`, `nome`, `endereco`, `numero`, `complemento`, `bairro`,
`cidade`, `uf`, `cep`, `email`, `ddd`, `telefone`.

Nosso `Pagador.endereco` já aceita as duas grafias e o
`_endereco_do_sacado` do offline já monta linha única — o Inter precisa de um
`_payer` próprio, mas curto.

### Status — 9 do banco para 6 nossos

| Inter | Nosso | Por quê |
|---|---|---|
| `A_RECEBER` | `registrado` | emitido, aguardando pagamento |
| `EM_PROCESSAMENTO` | `pendente` | ainda não é boleto pagável |
| `RECEBIDO` | `liquidado` | pago e liquidado pelo banco |
| `CANCELADO` | `baixado` | encerrado deliberadamente |
| `EXPIRADO` | `expirado` | direto |
| `FALHA` | `erro` | direto |
| `ATRASADO` | `registrado` | vencido **ainda é pagável**; não virou nada novo |
| `MARCADO_RECEBIDO` | `liquidado` | baixa manual do beneficiário — decidido |
| `PROTESTO` | `registrado` | segue em aberto; protesto é etapa, não desfecho |

Os dois últimos foram **decisão de produto**, e ficam registrados porque não se
deduzem do banco:

- **`MARCADO_RECEBIDO` → `liquidado`.** Alguém marcou como recebido no internet
  banking; o dinheiro pode não ter entrado pela compensação. Vale `liquidado`
  porque a pergunta do consumidor é *"posso liberar?"* e o banco está dizendo
  que sim. Quem concilia por extrato tem o valor cru em `raw`.
- **`PROTESTO` → `registrado`**, e **não** um sétimo status. O título segue em
  aberto; protesto é etapa da cobrança, não desfecho. Um status exclusivo do
  Inter obrigaria todo consumidor a tratar um caso que só ele tem.

Ambos têm teste em `test_os_nove_status_do_inter_cabem_nos_seis_nossos`.

## Esquema de credenciais (`GET /bancos`)

```
client_id       # da aplicação (portal Inter)
client_secret   # da aplicação
cert_pem        # o .crt como o banco entrega (PEM cru ou base64)
key_pem         # o .key correspondente
pfx_base64      # alternativa: o mesmo material em PKCS12/base64
pfx_password    # senha, quando houver
conta_corrente  # header x-conta-corrente, quando a aplicação vê mais de uma conta
scopes          # opcional (default do provider)
```

> **O Inter entrega PEM separado (`.crt` + `.key`), não PKCS12.** O
> `OAuthMtlsClient` passou a aceitar os dois formatos — sem isso, integrar
> exigiria rodar `openssl pkcs12 -export` antes da primeira chamada. Os campos
> aceitam PEM cru (quem cola o conteúdo do arquivo) ou base64 (quem automatiza).
>
> Verificado contra o sandbox em 04/08/2026: com o certificado do banco o
> **handshake mTLS estabelece** e o `POST /oauth/v2/token` responde `401 "The
> given client credentials were not valid"` para credencial inválida — ou seja,
> o TLS mútuo passou e só o OAuth recusou.

> ⚠️ O certificado de sandbox emitido pelo Inter vale **30 dias**, não um ano.
> O de produção vale 1 ano. Nos dois casos não há renovação in-place.

## Esforço

**Baixo**, e agora dá para dizer de onde vem cada parte:

| Peça | Custo | Por quê |
|---|---|---|
| Auth | ~zero | `OAuthMtlsClient` já faz OAuth+mTLS; só a URL do token e o header da conta |
| Pix, cobv, lote, recebidos, webhook Pix | ~zero | `BacenPixMixin` + `PIX_BASE = "/pix/v2"` |
| Boleto (emitir/consultar/PDF/cancelar) | o trabalho | payload próprio + mapa de 9 status |
| Extrato | pequeno | `/banking/v2/extrato` |
| Webhook de cobrança | pequeno | `normalizar_webhook` próprio |
| Roteiro de homologação | reaproveita | mesmo molde de `homologacao_c6.py` |

O maior risco não é técnico: é o **certificado de 1 ano sem renovação
in-place** — vence e a integração para. Vale alarme no roadmap de operação,
não só uma linha aqui.

## Validação no sandbox — 04/08/2026

**13 casos em 2xx, zero falhas, 3 ausentes declarados.** Ciclo completo do
boleto (emitir → consultar → PDF → cancelar), Pix (cob, consulta, lista,
recebidos), os dois webhooks e o extrato.

**O sandbox do Inter tem comportamento real**, não mock de schema. A sonda de
eco do roteiro confirmou: o `seuNumero` (`A4F69B14A5`), o valor (`150.0`) e o
vencimento (`2026-09-03`) voltaram **iguais** aos enviados, e o boleto veio com
linha digitável e código de barras próprios. Isso põe o Inter na mesma
categoria do C6 — a validação vale **integração ponta a ponta**, não só
contrato como no Sicoob.

O ciclo completo do boleto fechou: emitir (`201`, `A_RECEBER` → `registrado`),
consultar, PDF e cancelar (`baixado`). Webhook de cobrança e extrato também.

Ausentes: pagamentos e saldo por escopo; Pix Automático por não constar no SDK.

A chave Pix da conta de teste não é publicada no portal, mas **se descobre pela
própria API**: `GET /pix/v2/cobv` lista as cobranças com vencimento do período,
e cada uma traz o campo `chave`. Vale para qualquer conta — inclusive produção,
quando alguém não sabe qual chave está vinculada.

### Duas armadilhas que só o banco real revelou

**A barra final.** `POST /cobranca/v3/cobrancas/` responde `307`, e o cliente
não segue redirect — a emissão virava `502`. O C6 **exige** a barra
(`/v1/bank_slips/`) e o Inter **recusa**. Copiar o padrão do provider vizinho
foi o que quebrou; hoje há teste fixando o caminho sem barra.

**`formasRecebimento` e o QR que sumia.** O default era `BOLETO`, e o
`BOLETO` puro **suprime o Pix**: o banco devolve `pix: null`. Justamente a
funcionalidade que fez o Inter ser priorizado no roadmap sairia desligada, em
silêncio. O valor certo é **`BOLETO_PIX`**, que é hoje o default do provider —
`"PIX"` sozinho o banco recusa, e omitir o campo também dá híbrido. Quem quer
boleto sem Pix pede `formas_recebimento: "BOLETO"` explicitamente.

## O que falta

1. **Confirmar o Pix Automático no portal.** O provider herda o mixin BACEN, o
   dialeto está pronto — mas `rec`/`solicrec` não constam no SDK oficial e não
   foram exercitados no sandbox (`PA_01`).

   **O que já se sabe:** o portal lista o produto —
   [developers.inter.co/references/pix-automatico](https://developers.inter.co/references/pix-automatico),
   *"Pix Automático — Receba pagamentos recorrentes de forma automática e
   instantânea"*. Ou seja, o Inter **oferece** Pix Automático; a ausência no
   `pj-sdk-java` era do SDK, não do banco.

   **O que ainda falta**, e é o que a flag espera: os **paths**, o **path base**
   (`/pix/v2` como o resto do BACEN, ou outro) e os **scopes** OAuth. A página de
   referência monta o conteúdo por JavaScript, então nem o fetch nem o `curl`
   chegam à tabela de endpoints — vem só a casca do catálogo. Confirmar exige
   abrir a página no navegador ou uma chamada com credencial real.

   Ligar a capacidade só com o nome do produto seria trocar uma promessa sem
   lastro por outra: o mixin fala BACEN puro, e um path base diferente faz toda
   chamada bater em 404 — que é exatamente a falha que a flag existe para não
   entregar ao integrador.

   Até a confirmação, a capacidade **não é anunciada**: `GET /bancos` deixou de
   listar `pix_automatico` para o Inter e passou a trazer

   ```json
   "capacidades_nao_confirmadas": {"pix_automatico": "INTER_PIX_AUTOMATICO_READY"}
   ```

   e a rota responde `422` dizendo *não foi confirmado* — que é diferente de
   *não oferece*, a frase reservada a quem sabidamente não tem (Itaú). Quem
   tiver credencial real confirma, liga `INTER_PIX_AUTOMATICO_READY=true` e usa,
   sem esperar por versão nossa. Confirmado: some da lista e volta às
   capacidades — o teste que prende isso lê a própria evidência de homologação.

2. **`INT-S05` — listar/sumário de cobranças.** Sem rota hoje; avaliar.

   > **Ciclo `on`→`off` — resolvido.** O Inter é o único banco que existe nos
   > dois caminhos com o mesmo layout, então dá para registrar no `on` e
   > desenhar o PDF no `off` com o QR que liquida (`pix_copia_cola`). O risco
   > era o número: o `registrar` daqui manda `seuNumero` e **nunca**
   > `nossoNumero` — quem numera é o banco. Renderizar offline com o próprio
   > número imprimia outro título, com `200`.
   >
   > `data.codigo_barras` e `data.linha_digitavel` agora são **conferidos**: se
   > o cálculo local discordar do que o banco registrou, `400`. Use o
   > `nossoNumero` que a consulta (`INT-S02`) devolve em `raw.boleto`.

3. **`INT-S09` — saldo.** Lacuna de superfície, não do Inter: o gateway não
   expõe saldo para banco nenhum (idem `SIC-S06`).

4. **Alarme de vencimento do certificado.** Vale 1 ano, sem renovação in-place:
   vence e a integração para. É risco de operação, e vale para C6 e Sicoob
   também.
