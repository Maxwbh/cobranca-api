# Itaú Unibanco (341) — Integração REST · **PLANEJADO**

> **Status:** roadmap (não implementado). Ver [roadmap-providers.md](roadmap-providers.md).
> É o banco com **maior base de cobrança do país** e o que mais aparece no
> caminho offline (CNAB 400/444 da engine). O que falta é o caminho **online**.
>
> **Leia a seção de onboarding antes de estimar prazo.** A dificuldade do Itaú
> não é técnica, é de acesso: as credenciais de cobrança **não** saem por
> autosserviço — dependem do gerente da conta.

## Onde baixar a documentação oficial

| Recurso | Link |
|---|---|
| Portal do desenvolvedor | https://devportal.itau.com.br/ |
| Como se conectar às APIs | https://devportal.itau.com.br/como-se-conectar-as-apis-itau |
| Autenticação mTLS (produção) | https://devportal.itau.com.br/autenticacao-documentacao |
| Autosserviço de credenciais e certificado | https://devportal.itau.com.br/certificado-dinamico-credenciais |
| API de cobrança (cash management v2) | https://devportal.itau.com.br/nossas-apis/cash-management-ext-v2 |
| Catálogo completo (exige login) | https://devportal.itau.com.br/baas/#/catalog |

> **O catálogo e os payloads exigem login no portal.** Este documento reúne o
> que é público; o que depende de conta está marcado como pendência, e não
> inventamos campo nenhum — a mesma régua da homologação: só entra o que dá
> para verificar.

## O que muda em relação aos três já integrados

| | C6 / Sicoob / Inter | **Itaú** |
|---|---|---|
| Acesso às credenciais | Portal self-service | **Gerente/OfficerCash** para cobrança (autosserviço só cobre Pix Indireto, PISP, Corban, Extrato e Câmbio) |
| Certificado | Emitido no portal | **Certificado dinâmico**: você gera o CSR e o Itaú assina, via `POST https://sts.itau.com.br/seguranca/v1/certificado/solicitacao` |
| Validade do token | 1h típico | **5 minutos** |
| Sandbox | Fala o mesmo dialeto da produção | **Sandbox não tem mTLS e não segue OAuth 2.0** — token de sandbox só vale em URL de sandbox |
| PDF do boleto | C6 e Inter devolvem | **Não devolve**: a API responde linha digitável e código de barras |

As duas últimas linhas são as que mais mexem com o nosso desenho — veja
"Particularidades".

## Serviços da plataforma × Cobranca-API (catálogo)

> Legenda: ✅ disponível · 🔜 planejado · ⛔ sem previsão / fora de escopo.
> O ⛔ segue a [régua de escopo](roadmap-providers.md#princípio-de-escopo-o-que-não-entra-em-provider-nenhum).

| ID | Serviço | O que faz | Status | Uso previsto |
|---|---|---|:---:|---|
| IT-S01 | STS — OAuth `client_credentials` + mTLS | Token de acesso (5 min) | 🔜 | Interno (`OAuthMtlsClient`) |
| IT-S02 | STS — certificado dinâmico | Assina o CSR e devolve o `.crt` | 🔜 | Operação de onboarding, fora do runtime |
| IT-S03 | **cash management v2 — emissão** | Registra o boleto (escopo `cash_management/emissaocobranca.write`) | 🔜 | `POST /cobranca` |
| IT-S04 | **cash management v2 — instrução** | Alterar, baixar, protestar (escopo `cash_management/instrucaocobranca.write`) | 🔜 | `PUT`/`DELETE /cobranca/{id}` — o Itaú seria o **segundo** banco com alteração, hoje só o C6 |
| IT-S05 | **cash management v2 — consulta** | `GET /boletos` (escopo `cash-boletos-consulta_titulo`) | 🔜 | `GET /cobranca/{id}` |
| IT-S06 | **Bolecode** | Boleto híbrido com QR Pix — API separada da de boleto puro | 🔜 | `POST /bolepix` (capacidade que hoje só o C6 tem) |
| IT-S07 | Pix Recebimentos (API Pix v2) | cob/cobv, webhook por chave | 🔜 | `/pix/*` — **confirmar aderência ao BACEN** (ver pendências) |
| IT-S08 | Extrato | Movimentação da conta | 🔜 | `GET /extrato` — e é dos poucos com **autosserviço de credencial** |
| IT-S09 | Conciliação / retorno | Arquivo e API | 🔜 avaliar | Só se for consulta; a API **não concilia** |
| IT-S10 | Pix Pagamentos, PISP, DDA | Saída de dinheiro / iniciação | ⛔ | Fora de escopo — o produto é cobrança (entrada) |
| IT-S11 | Câmbio (FX as a Service), Corban Digital | Outros produtos do portal | ⛔ | Fora de escopo |

## Autenticação no banco

1. **Credenciais** (`client_id`, `client_secret` e um **token temporário**,
   válido por **5 minutos**) chegam por e-mail depois da solicitação —
   para cobrança, via gerente/OfficerCash.
2. **Certificado dinâmico**: gera-se o CSR com OpenSSL (chave privada fica com
   você) e posta-se em `POST https://sts.itau.com.br/seguranca/v1/certificado/solicitacao`
   com o token temporário no `Authorization`. A resposta traz o `.crt` assinado
   e o `client_secret` definitivo. **Validade de 365 dias**, renovável nos 30
   dias anteriores ao vencimento.
3. **Token de acesso**: `POST https://sts.itau.com.br/api/oauth/token` com
   `grant_type=client_credentials` (há também o fluxo JWT em
   `https://sts.itau.com.br/as/token.oauth2`, com
   `grant_type=urn:ietf:params:oauth:grant-type:client_credentials`).
   `Content-Type: application/x-www-form-urlencoded`, mTLS na conexão.
   Headers `x-itau-correlationID` e `x-itau-flowID` aparecem nos exemplos como
   opcionais — úteis para rastreio no suporte.

**Encaixa no `OAuthMtlsClient` sem código novo de auth**: é o mesmo fluxo do C6
(OAuth `client_credentials` + mTLS). O cache de token já respeita o `expires_in`
com margem de 30s (`oauth_mtls.py`), então o TTL de 5 minutos funciona — mas
veja a nota de custo em "Particularidades".

## Esquema de credenciais (proposto — fonte viva: `GET /bancos`)

```
client_id        # obrigatório
client_secret    # obrigatório (o definitivo, devolvido junto com o certificado)
cert_pem         # .crt assinado pelo Itaú (PEM ou base64)
key_pem          # a chave privada gerada no CSR
pfx_base64       # alternativa: o mesmo material em PKCS12
pfx_password     # senha do PKCS12, quando houver
agencia          # account_config
conta            # account_config (com dígito)
carteira         # account_config — 109 é a citada como padrão nas integrações
```

O par `cert_pem` + `key_pem` é o mesmo caminho já aberto para o **Inter**: o
Itaú também entrega `.crt` + `.key`, não PKCS12.

## Superfície prevista (Itaú → gateway)

| Operação | Itaú | Endpoint do gateway |
|---|---|---|
| Token | `POST /api/oauth/token` (STS) | interno |
| Emitir boleto | cash management v2 — emissão | `POST /cobranca` |
| Consultar | `GET /boletos` | `GET /cobranca/{id}` |
| Alterar / instruir | cash management v2 — instrução | `PUT /cobranca/{id}` |
| Baixar | instrução de baixa | `DELETE /cobranca/{id}` |
| Boleto com QR Pix | Bolecode | `POST /bolepix` |
| Pix cob/cobv | API Pix v2 | `/pix/*` (a confirmar: mixin BACEN ou provider próprio) |
| Extrato | API Extrato | `GET /extrato` |

## Particularidades (e o que elas custam)

- **A API não devolve o PDF.** Ela responde linha digitável e código de barras.
  Para os outros bancos isso seria um problema; aqui é o **melhor encaixe que
  este projeto podia ter**: o Itaú registra, e a engine pyCobrança — que já
  emite o layout 341 offline — renderiza o PDF com os dados devolvidos. É o
  argumento mais forte a favor do Itaú na fila: o registro online reaproveita
  o desenho offline que já existe e está testado.
- **Token de 5 minutos.** Em lote isso significa renovar no meio do job. O
  cache atual (por `client_id` + `base_url`, com margem de 30s) cobre, mas o
  provider não pode segurar token entre chamadas longas — e vale medir quantas
  renovações um lote de 200 provoca antes de prometer throughput.
- **Sandbox diferente da produção.** Sem mTLS e fora do OAuth 2.0: o roteiro de
  homologação vai exercitar um dialeto de autenticação que **não é** o de
  produção. Isso rebaixa o valor da evidência — na categoria do Sicoob (prova
  contrato, não comportamento), não na do C6/Inter. Deve estar dito no
  documento de homologação desde o primeiro dia.
- **Certificado com validade de 365 dias e renovação por CSR.** Diferente dos
  outros três, a renovação é um procedimento nosso, não um download do portal —
  candidato a alerta no `docs/homologacao/` (o certificado do Inter já rendeu a
  nota de expiração).
- **Carteira 109** aparece como padrão nas integrações de mercado; as demais
  precisam ser confirmadas com o convênio do cliente.

## PDF: quem renderiza é a engine (e a conferência que isso exige)

**Decisão:** o Itaú registra; quem precisa do PDF pede à engine. O 341 já está
entre os 18 layouts, então não há nada a construir — mas há uma regra a
respeitar, e ela é o que separa "funciona" de "boleto que ninguém consegue
pagar".

O código de barras é **determinístico**: função pura de banco, vencimento,
valor, agência/conta/carteira e nosso número. Verificado na engine:

```
mesmo payload            -> 34199167700000150001091234567843073123451000
nosso_numero 12345679    -> 34194167700000150001091234567923073123451000
```

Um dígito diferente muda o código inteiro (inclusive o DV geral, na 5ª
posição). Ou seja: **o PDF offline é o mesmo boleto registrado se — e só se —
for renderizado com exatamente o que o banco registrou.**

Fluxo, em duas chamadas:

```bash
# 1. registra no Itaú e recebe id, linha digitável e código de barras
curl -X POST {base}/cobranca -H 'Authorization: Bearer bapi_...' \
     -H 'content-type: application/json' -d '{"provider":"itau", ...}'

# 2. renderiza o PDF com OS MESMOS dados do convênio e o nosso número registrado
curl -X POST {base}/api/render/boleto -H 'content-type: application/json' \
     -d '{"bank":"itau","data":{...,"nosso_numero":"<o que o banco registrou>"}}'
```

**Conferência obrigatória antes de entregar ao pagador:** compare a
`linha_digitavel` que a engine calculou com a que o Itaú devolveu. Iguais, é o
boleto registrado. Diferentes, algum campo divergiu (nosso número normalizado
pelo banco, carteira trocada pelo convênio) e o PDF **não** pode ser entregue —
o pagamento não conciliaria.

Dois testes em `test_cobranca_itau.py` guardam essa propriedade: o
determinismo e a detecção da divergência. Se uma versão futura da engine
quebrar qualquer um dos dois, o fluxo de PDF do Itaú para de ser seguro e o
build avisa.

> Quando o catálogo abrir e o payload da consulta for conhecido, dá para
> internalizar isso: `pdf()` passa a existir no provider, consulta o banco,
> renderiza pela engine e **só devolve se a conferência bater** — uma chamada
> em vez de duas, com a mesma garantia. Hoje seria adivinhação, porque o
> mapeamento de volta (resposta do banco → campos da engine) não é público.


## Onboarding — o gargalo real

O autosserviço de credenciais do portal cobre **Pix Indireto, PISP, Corban
Digital, Extrato e Câmbio**. **Cobrança não está na lista**: as credenciais de
`cash_management` e Bolecode saem por solicitação ao gerente da conta ou ao
OfficerCash, e chegam por e-mail. É por isso que o roadmap classifica o Itaú
como "onboarding notoriamente difícil" — a barreira é comercial, não técnica.

Consequência prática para o planejamento: **começar pelo Extrato** (IT-S08) é
uma forma de validar auth, certificado dinâmico e mTLS **sem depender do
gerente**, e só depois pedir cobrança. Não entrega cobrança, mas derruba o risco
técnico antes da espera comercial.

## Esforço estimado

**Médio** — comparável ao C6, com um risco de calendário que os outros não têm:

| Bloco | Custo | Por quê |
|---|---|---|
| Auth (OAuth + mTLS) | Muito baixo | `OAuthMtlsClient` já faz; muda a URL |
| Certificado dinâmico | Baixo (operação) | CSR + POST no STS; roda uma vez por ano, fora do runtime |
| Boleto (emissão/consulta/instrução) | **Médio** | Payload proprietário — é o trabalho real |
| PDF | **Nenhum** | A engine já renderiza o 341 |
| Bolecode | Médio | API separada, mapeia em `/bolepix` |
| Pix | Baixo **se** for BACEN puro | Mixins prontos; há relato de divergências em credenciais, métodos e headers — confirmar |
| Extrato | Baixo | Rota já existe |
| **Onboarding** | **Alto (calendário)** | Depende do gerente; não é código |

## Pendências

- ☐ Conta no portal para abrir o catálogo: URLs base de produção e sandbox,
  paths exatos e payload de emissão/instrução (hoje só o `GET /boletos` é
  público).
- ☐ Confirmar se a API Pix do Itaú é BACEN puro (mixins de graça) ou dialeto
  próprio — é o que decide o esforço do bloco Pix.
- ☐ Confirmar carteiras aceitas por convênio e a faixa de nosso número.
- ☐ Decidir se o piloto começa pelo **Extrato** (sem gerente) ou espera as
  credenciais de cobrança.
- ☐ Medir o custo do token de 5 min num lote de 200 antes de publicar número
  de throughput.

## Esqueleto no código (o que já está escrito)

`gateway/app/providers/itau.py`, com testes em `gateway/tests/test_cobranca_itau.py`.
A regra que guiou o que entrou: **só é real o que a documentação pública
confirma** — o resto está isolado, marcado e sai por variável de ambiente.

| Peça | Estado |
|---|---|
| Auth (OAuth + mTLS, `sts.itau.com.br`) | **Real** — `OAuthMtlsClient`, sem código novo |
| Credenciais `.crt` + `.key` (e PKCS12 como alternativa) | **Real** — mesmo caminho do Inter |
| `registrar` / `consultar` / `alterar` / `baixar` | Estrutura pronta; **path e payload provisórios** (`ITAU_BASE_URL`, `ITAU_PATH_BOLETOS`) |
| Leitura da resposta | Tolerante a apelidos (`id_boleto`/`id`, `linha_digitavel`/`codigo_linha_digitavel`…) — quando o catálogo abrir, acrescenta-se ou remove-se um apelido |
| `pdf()` | **Não implementado de propósito** — o banco não devolve PDF; quem renderiza é a engine, e sobrescrever mentiria no `GET /bancos` |
| Mixins BACEN (Pix) | **Não herdados ainda** — há relato de divergências no Pix do Itaú; herdar declararia capacidade sem lastro |
| `normalizar_webhook` | Ausente — formato não confirmado |
| Gate | `ITAU_REGISTERED_READY`; **desligado**, `provider=itau` emite pela engine (o 341 está entre os 18) |

Os 20 testes afirmam **o nosso lado** — gate e fallback, dados do convênio
vindos do `account_config`, documento e CEP só com dígitos, dedução de
CPF/CNPJ, header de correlação só quando informado, leitura tolerante,
ausência de PDF, mapa de status e o que o catálogo declara. Nenhum deles afirma
nome de campo do Itaú como se fosse confirmado.

Uma regra de segurança vale destacar, porque é decisão de produto: **status
desconhecido vira `registrado`, nunca `liquidado`**. Errar para "ainda em
aberto" é o erro barato; o contrário libera mercadoria de graça.

Quando o catálogo abrir, o trabalho é: confirmar `ITAU_BASE_URL` e o path,
ajustar `_payload_emissao` (uma função) e a tabela de `_map_status`.
