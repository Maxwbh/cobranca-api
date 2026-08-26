# Postman — Cenário de Teste HML (Cobranca-API)

Coleção de regressão do serviço único: REST online na raiz e superfície offline
em `/api/*`. Este documento é a **fonte única** — o plano que originou estes
artefatos foi absorvido aqui quando virou código; o que sobrava dele era
processo já materializado, e foi lá que um `provider=brcobranca` sobreviveu anos
depois de o valor deixar de existir.

Coleção **schema v2.1**, com IDs de rastreabilidade (`BC-xxx` funcional,
`NEG-xxx` negativo, `SMK-xx` smoke) na [matriz](#matriz-de-rastreabilidade) e
nos [critérios T1–T10](#critérios-de-aceite-t1t10). As descrições das pastas
citam os **IDs de catálogo de serviços** (`C6-Sxx`, `SIC-Sxx`) — catálogo
completo por banco (inclusive não implementados) em
`docs/development/<banco>-rest.md`, seção "Serviços do banco × Cobranca-API".

## Arquivos

| Arquivo | O quê |
|---|---|
| `cobranca-api.postman_collection.json` | Coleção (14 pastas: SMK + 00–11 + NEG) — todos os endpoints da versão atual |
| `hml.postman_environment.json` | Environment HML. O `base_url` vem preenchido com a instância de demonstração, mas a URL do Render **não é fixa** — troque no environment ou sobreponha com `--env-var base_url=...` |
| `local.postman_environment.json` | Environment local (`http://localhost:8000`) |
| `check_coverage.py` | Guarda de cobertura (§8): endpoint do OpenAPI sem request ⇒ `exit 1` |

## Importar e preencher

1. Postman → **Import** → os 3 JSONs.
2. Selecione o environment (HML ou Local) e preencha: `agencia`, `conta`,
   `convenio`, `chave_pix` + segredos (tipo `secret`): `c6_client_id`,
   `c6_client_secret`, `c6_pfx_base64`, `c6_pfx_password`, `sicoob_client_id`,
   `sicoob_access_token`.
3. **Uploads (pasta 10/NEG-005):** os arquivos vêm de `postman/fixtures/`.
   No Postman UI: Settings → **Working Directory** = raiz do repositório.
   No newman: executar a partir da raiz do repositório.

> Environments versionados têm os segredos **vazios** de propósito. Nunca
> commitar preenchido; no CI, injete com `--env-var`.

## Credenciais: regra e sinalização

| Banco | Regra |
|---|---|
| **C6** | exige a credencial **completa**: `client_id`, `client_secret`, `pfx_base64`, `pfx_password` |
| **Sicoob** | `client_id` + **uma das duas** vias: `access_token` (sandbox) **ou** `client_secret`+`pfx_base64`+`pfx_password` (OAuth+mTLS) |

O **pré-flight** (primeiro request) aplica a regra e reporta:

- **GRAVE (falha)** — C6 sem credencial, ou Sicoob sem **nenhuma** das duas vias.
  Não é ausência banal: é má configuração.
- **AVISO** — dados de conta (`chave_pix`, `agencia`, `conta`, `convenio`) ausentes.

### 424 é falha — exceto quando a credencial não existe

`424` = o **banco** rejeitou a credencial. A suíte **não tolera** 424 como
sucesso:

- credencial **ausente** → **AVISO**, nomeando exatamente qual falta;
- credencial **presente** e ainda assim rejeitada → **FALHA** (é o erro de
  credencial que se quer enxergar).

No encerramento sai um resumo **por credencial**, listando quais requests cada
uma bloqueou.

## ⏰ Janela do sandbox C6

O sandbox do C6 tem **trava de horário**: fora da janela, a autenticação
responde 403 e o gateway devolve **424** (`upstream.status: 403`). Por isso os
requests online do C6 aceitam `424` como resultado tolerado — a suíte não
acusa falha falsa fora do expediente. **Para validar a integração online de
verdade, rode dentro da janela.** O caminho offline (`04`, `10`, `08b · Jobs`)
não é afetado.

## Executar com segredos (recomendado)

`postman/run-regressao.sh` injeta os segredos por `--env-var`, lendo de
variáveis do **shell** — nada de segredo em arquivo versionado nem no
`.postman_environment.json`.

```bash
export COB_CHAVE_PIX='sua-chave-pix'
export COB_AGENCIA='3073' COB_CONTA='12345678' COB_CONVENIO='1234567'
export COB_C6_CLIENT_ID='...'      COB_C6_CLIENT_SECRET='...'
export COB_C6_PFX_BASE64="$(base64 -w0 certificado.pfx)"
export COB_C6_PFX_PASSWORD='...'
export COB_SICOOB_CLIENT_ID='...'  COB_SICOOB_ACCESS_TOKEN='...'
# Pix Automático do Sicoob exige OAuth+mTLS (o access_token de sandbox não cobre):
export COB_SICOOB_CLIENT_SECRET='...'
export COB_SICOOB_PFX_BASE64="$(base64 -w0 sicoob.pfx)"
export COB_SICOOB_PFX_PASSWORD='...'

./postman/run-regressao.sh            # regressão completa
./postman/run-regressao.sh --smoke    # só o smoke (< 5 min)
```

Preferindo um arquivo (mantenha-o **fora do git**):

```bash
set -a; source .secrets.env; set +a
./postman/run-regressao.sh
```

O script avisa quais variáveis ficaram vazias **e quais falhas isso causa**, e
alerta quando a execução está fora da janela do sandbox C6. Rodar sem nenhum
segredo funciona — apenas com as falhas esperadas.

Outros ambientes: `COB_ENV_FILE=postman/local.postman_environment.json`.

## Executar direto com newman

```bash
# SMOKE (pre-deploy, < 5 min — 9 requests)
newman run postman/cobranca-api.postman_collection.json \
  -e postman/hml.postman_environment.json \
  --folder "SMK · Smoke (pre-deploy, < 5 min)"

# REGRESSÃO completa (diária + antes do cutover) com evidências (§9 do plano)
newman run postman/cobranca-api.postman_collection.json \
  -e postman/hml.postman_environment.json \
  -r cli,htmlextra,junit,json \
  --reporter-htmlextra-export postman/reports/regressao.html \
  --reporter-junit-export postman/reports/regressao.xml \
  --reporter-json-export postman/reports/regressao.json

# Guarda de cobertura (CI): endpoint novo sem BC-xxx => falha
python postman/check_coverage.py
```

Reporters: `npm i -g newman newman-reporter-htmlextra`. `postman/reports/` fica
fora do git (evidência anexada ao ciclo de HML, com versão da coleção
(`collection_version`), versão da API (BC-001/BC-047) e commit do deploy).

## Ordem e automatismos

- Ordem de regressão: `00 → 01 → 02 → … → 11 → NEG` (o encadeamento segue essa sequência).
- **Automático** (nenhuma massa de dados a manter): datas recalculadas por
  execução; `txid`/`external_reference_id` gerados; tokens `bapi_` capturados
  pela pasta 02; `cobranca_id`/`txid`/`id_rec`/`id_solic`/`loc_id` encadeados
  das respostas.
- **Troca de banco em 1 clique**: requests "Utilitário · usar C6/Sicoob como
  ativo" (trocam `bapi_token` + `provider`).
- `409` (CIP) e `422` (regras documentadas, ex. extrato Sicoob multi-mês)
  contam como sucesso onde o cenário espera.
- `BC-048/049/050` (Pix recebidos por `e2eid`) precisam de um Pix real no
  sandbox — preencha `{{e2eid}}`; sem ele, respondem 404 (aceito pelo teste).
- **Request com id encadeado ausente é PULADO, não aborta o run.** O id vem da
  resposta anterior; quando ela falha (janela do sandbox, credencial ausente), a
  URL colapsaria em 405 — falha enganosa. O nome do pulado sai no `pulados` do
  environment e o encerramento (`ZZ`) reclama se algum for do smoke.

## Os dois eixos: `provider` (caminho) e `banco` (instituição)

`provider` diz **por onde** — `on` = API do banco, `off` = engine pyCobrança — e
`banco` diz **qual instituição**. O nome do banco no `provider` (`provider=c6`)
segue valendo como apelido; é o que a maior parte da coleção usa, de propósito:
é a forma que está em produção e no roteiro já enviado ao banco.

| Request | O que fixa |
|---|---|
| `BC-004` | o catálogo responde `caminhos`, e cada banco REST diz `registrado_pronto`, `fallback_offline` e `caminho_efetivo` |
| `BC-090` | mesma emissão do `BC-018`, na forma nova (`provider=off` + `banco`) — se as duas divergirem, a migração quebra quem já integrou |
| `NEG-008` | `on` em banco sem API REST → `422` com a lista de quem tem |
| `NEG-009` | `off` no Inter → `422` (a engine não tem o layout 077; cair em outro banco registraria no lugar errado) |
| `NEG-010` | caminho sem `banco` → `422`: a API não escolhe banco sozinha |

## Webhook de entrada: `webhook_token`

`POST /webhooks/{banco}` é **fail-closed** desde a 2.2.0 — sem `?token=`
conferindo com `WEBHOOK_TOKEN__<BANCO>` no servidor, responde `401` antes de
olhar o corpo. `BC-066/067` afirmam os dois lados:

- `webhook_token` **vazio** → exige `401` (é o fail-closed que se quer provar);
- `webhook_token` **preenchido** (`COB_WEBHOOK_TOKEN`, igual ao do servidor) →
  exige `200`/`422`, exercitando a entrega de verdade.

## Matriz de rastreabilidade

Cobertura = esta matriz completa. Endpoint novo ⇒ nova linha com ID ⇒ novo request — e o
`check_coverage.py` reprova o build se faltar. A coluna **Roadmap** liga aos critérios T1–T10, logo abaixo.

### Cenários funcionais (BC)

| ID | Funcionalidade | Endpoint | Origem | Roadmap |
|---|---|---|---|---|
| BC-001 | Health gateway | `GET /health` | Gateway | T10 |
| BC-002 | Health da engine offline | `GET /api/health` | engine offline | Fase 1 |
| BC-003 | Info do engine | `GET /api/info` | engine offline | — |
| BC-004 | Catálogo com capacidades/esquemas | `GET /bancos` | Gateway | T10 |
| BC-005 | Catálogo offline (19 bancos CNAB) | `GET /api/bancos` | engine offline | — |
| BC-006 | Cadastrar credenciais C6 → `bapi_` | `POST /credenciais` | Gateway | — |
| BC-007 | Cadastrar credenciais Sicoob → `bapi_` | `POST /credenciais` | Gateway | — |
| BC-008 | Revogar token | `DELETE /credenciais` | Gateway | — |
| BC-009 | Emitir boleto registrado | `POST /cobranca` | Gateway | — |
| BC-010 | Consultar boleto | `GET /cobranca/{id}` | Gateway | — |
| BC-011 | PDF do boleto registrado | `GET /cobranca/{id}/pdf` | Gateway | — |
| BC-012 | Alterar boleto (due_date) | `PUT /cobranca/{id}` | Gateway | — |
| BC-013 | Baixar/cancelar (tolera 409 CIP) | `DELETE /cobranca/{id}` | Gateway | — |
| BC-014 | Validar dados do boleto | `GET /api/boleto/validate` | engine offline | T5 |
| BC-015 | Dados do boleto (3 campos nosso_numero) | `GET /api/boleto/data` | engine offline | T5 |
| BC-016 | Nosso número | `GET /api/boleto/nosso_numero` | engine offline | — |
| BC-017 | **PDF binário + headers `X-*`** (magic `%PDF`) | `GET /api/boleto` | engine offline | **T1, T2** |
| BC-018 | Cobrança offline pela rota canônica | `POST /cobranca` (`provider=off` + `banco`) | Gateway→Core | — |
| BC-019 | Swagger do engine offline | `GET /api/docs` | engine offline | T9 |
| BC-020 | Carnê 3-vias (2 parcelas) | `POST /carne` | Gateway→Core | — |
| BC-021 | Pix cob imediata (normaliza `pixCopiaECola`\|`brcode`) | `POST /pix` | Gateway | — |
| BC-022 | Pix cobv (com vencimento/devedor) | `POST /pix` | Gateway | — |
| BC-023 | Consultar Pix por txid | `GET /pix/{txid}` | Gateway | — |
| BC-024 | Listar cobranças Pix (janela) | `GET /pix` | Gateway | — |
| BC-025 | Pix recebidos (conciliação) | `GET /pix/recebidos` | Gateway | — |
| BC-026 | Emitir Bolepix (201) | `POST /bolepix` | Gateway | — |
| BC-027 | Consultar Bolepix | `GET /bolepix/{ref}` | Gateway | — |
| BC-028 | PDF Bolepix | `GET /bolepix/{ref}/pdf` | Gateway | — |
| BC-029 | Cancelar Bolepix (tolera 409) | `DELETE /bolepix/{ref}` | Gateway | — |
| BC-030 | Criar recorrência (rec) | `POST /pix-automatico/recorrencias` | Gateway | — |
| BC-031 | Consultar recorrência | `GET /pix-automatico/recorrencias/{idRec}` | Gateway | — |
| BC-032 | Solicitação de autorização (solicrec) | `POST /pix-automatico/solicitacoes` | Gateway | — |
| BC-033 | Cobrança do ciclo (cobr, ≥2 dias) | `PUT /pix-automatico/cobrancas/{txid}` | Gateway | — |
| BC-034 | Config webhooks rec/cobr | `PUT /pix-automatico/config/webhooks` | Gateway | — |
| BC-035 | Extrato por período | `GET /extrato` | Gateway | — |
| BC-036 | Conciliação — recebíveis | `GET /conciliacao/recebiveis` | Gateway | — |
| BC-037 | Conciliação — transações | `GET /conciliacao/transacoes` | Gateway | — |
| BC-038 | Remessa CNAB240/400 (fixture do repo) | `POST /api/remessa` | engine offline | **T3** |
| BC-039 | Retorno CNAB (fixture do repo) | `POST /api/retorno` | engine offline | — |
| BC-040 | Parsing OFX (fixture do repo) | `POST /api/ofx/parse` | engine offline | **T4** |
| BC-041 | Cadastrar webhook boleto | `POST /config/webhook-banco` | Gateway | — |
| BC-042 | Consultar webhook boleto | `GET /config/webhook-banco` | Gateway | — |
| BC-043 | Remover webhook boleto | `DELETE /config/webhook-banco` | Gateway | — |
| BC-044 | Configurar webhook Pix por chave | `PUT /config/webhook-pix` | Gateway | — |
| BC-045 | Consultar webhook Pix | `GET /config/webhook-pix` | Gateway | — |
| BC-046 | Remover webhook Pix | `DELETE /config/webhook-pix` | Gateway | — |

> Rotas de menor uso do dialeto BACEN (devoluções, lotes cobv, locations,
> retentativa, PATCH de revisão) entram na matriz na geração da coleção,
> seguindo a numeração — a regra do §8 impede que fiquem de fora.

| ID | Funcionalidade | Endpoint | Cobre |
|---|---|---|---|
| BC-088 | Revisar cobranças dentro do lote de cobv | `PATCH /pix/lote/{id}` | `P_03_02` do roteiro C6 — encadeia no `lote_id`/`txid_lote1` do BC-052 |

> **BC-088 fechou uma ausência de homologação, não só uma linha de matriz.**
> `revisar_lote_cobv` existia no mixin BACEN e o router não expunha, então
> `P_03_02` saía do roteiro do C6 como caso ausente. A cobrança individual já
> tinha o seu `PATCH /pix/{txid}`; a assimetria era o defeito.
>
> O teste aceita `502` entre os status esperados: o sandbox do C6 devolve `502`
> em `/lotecobv` no `PUT` e no `GET`, e isso está registrado em
> [docs/homologacao/](../docs/homologacao/README.md) como defeito do banco. Marcar o
> request como falho por causa disso apontaria para o lugar errado.

### Cenários negativos (NEG)

| ID | Cenário | Esperado |
|---|---|---|
| NEG-001 | Bearer inválido/revogado em rota REST | 401 |
| NEG-002 | `provider` inexistente | 422 (enum) |
| NEG-003 | Boleto offline com dados inválidos | 400 + `validation_errors` | 
| NEG-004 | JSON malformado no body | 422 (FastAPI) |
| NEG-005 | OFX inválido no upload | 400 |
| NEG-006 | Extrato Sicoob multi-mês | 422 |
| NEG-007 | Pix no caminho offline (`provider=off`) | 422 |

> NEG-003 cobre o **T6**: propagação do erro de validação.

### Critérios de aceite T1–T10

Vinham do roadmap de migração para o serviço único, que foi **concluído e
removido**. Ficam aqui porque a coluna *Roadmap* da matriz acima os cita por
nome — e porque descrevem comportamento da superfície offline que continua
valendo, mesmo sem o proxy que os originou.

| # | Critério | Onde é verificado hoje |
|---|---|---|
| T1 | `GET /api/boleto` devolve binário: `%PDF`, 5 headers `X-*`, `Content-Disposition` | BC-017 · `test_pdf_binario_com_headers_x` |
| T2 | ~~Resposta gzip íntegra, sem `content-encoding` na saída~~ | **Sem objeto.** Era problema do proxy HTTP; a engine é in-process desde a 2.0.0 |
| T3 | `POST /api/remessa` multipart → CNAB intacto | BC-038 · `test_remessa_cnab240` |
| T4 | `POST /api/ofx/parse` → JSON | BC-040 |
| T5 | Query string repassada (multi-items) | BC-014, BC-015 |
| T6 | Erro de validação: `400` com `validation_errors` | NEG-003 · `test_boleto_invalido_400_com_validation_errors` |
| T7 | Engine indisponível → `502` | pytest (não induzível em e2e) |
| T8 | Método não aceito → `405` | pytest |
| T9 | `/api/docs` responde HTML | BC-019 |
| T10 | Rotas do gateway não caem no catch-all do offline | BC-001, BC-004 |

> **T2 é o único que morreu de vez**, e vale entender por quê: ele existia para
> garantir que o proxy não corrompesse corpo comprimido a caminho do Core Ruby.
> Sem proxy e sem Core, não há caminho onde a corrupção aconteça. Critério que
> perdeu o objeto não vira teste órfão — sai.

### O que NÃO é coberto aqui (é pytest)

| Roadmap | Motivo | Onde é coberto |
|---|---|---|
| T7 (engine indisponível → 502) | não induzível em e2e sem derrubar o Core | `tests/test_offline_proxy.py` |
| T8 (método não aceito → 405) | valor marginal em e2e | idem |

### Cartão no C6

> `POST/GET/DELETE /checkout` existem, e a pasta **`12 · Checkout (cartão — C6)`**
> está na Collection com BC-081, BC-082, BC-083, BC-084 e BC-085 — o §8 volta a
> 100% de cobertura. Os cenários seguem nesta seção, e não nas tabelas §4.1/§4.2,
> porque o que os afirma é **pytest**, não Postman: o essencial do cartão são as
> recusas (`save_card`, transparente, capacidade por provider) e o mapeamento dos
> dez status do spec — nada disso é observável num request contra o sandbox.
>
> Cobertura em `gateway/tests/test_c6_checkout.py` (30 testes).

| ID | Funcionalidade | Endpoint | Cobre |
|---|---|---|---|
| BC-081 | Criar link de pagamento (201 + `url`, `expira_em`) | `POST /checkout` | caminho feliz |
| BC-082 | Criar link com Pix no mesmo objeto | `POST /checkout` | um link, dois meios |
| BC-083 | Consultar link — status normalizado | `GET /checkout/{id}` | leitura |
| BC-084 | Cancelar link (`CANCELLED` → `baixado`) | `DELETE /checkout/{id}` | encerramento deliberado |
| BC-085 | Criar parcelado (`parcelas`, `juros_por`) | `POST /checkout` | `juros_por` no payload, default `loja` |
| BC-086 | Webhook do banco com `service: CHECKOUT` | `POST /config/webhook-banco` | a metade que já existe |
| BC-087 | Receber evento de checkout e repassar ao Consumidor | `POST /webhooks/c6/{tenant}` | cadeia HMAC completa |

**BC-087 é o menos óbvio e o mais importante.** O evento não vai do banco para o
Consumidor: é *banco → Cobranca-API → Consumidor*, com `resolve_callback`
achando o dono do tenant e `forward_event` assinando em HMAC-SHA256. As três
peças já existem — muda só o `service` no cadastro —, mas nenhuma foi exercitada
com `CHECKOUT`.

| ID | Cenário | Esperado | Por que existe |
|---|---|---|---|
| NEG-008 | Rota de cartão em `provider=sicoob` | **422** dizendo para onde ir | o critério de entrada executando, via `exige_capacidade` |
| NEG-009 | Corpo com `save_card` | **422** (campo inexistente no schema) | modo link: cartão não passa por aqui |
| NEG-010 | Pedir checkout transparente / chave pública | **422** ou rota ausente | idem |
| NEG-011 | `parcelas > 1` sem `juros_por` | **422** daqui, não `400` do banco | recusa antes de chamar o banco |

**NEG-009 e NEG-010 não são formalidade.** A decisão 3 só é real se o campo não
existir no schema — o próprio estudo diz que documentar não segura isso. Sem
esses dois, a decisão de não guardar dado de cartão pode ser revogada por um
chamador, sem ninguém revisar, e o custo de descobrir tarde não é um bug: é
escopo PCI-DSS.

#### O que fica fora do Postman, e por quê

| Situação | Motivo | Onde é coberto |
|---|---|---|
| Chegar a `PAID` | ninguém paga link de cartão por script — o PAN é digitado na página do C6, e é isso que a decisão 3 quer | roteiro manual de homologação, uma vez |
| `EXPIRED` → `expirado` | expiração default de 7 dias; não induzível em e2e | mock (`tests/test_c6_cartao.py`) |
| `DECLINED`/`ERROR` → `erro` | exige cartão de teste recusado no sandbox | mock; sandbox se o C6 fornecer cartão de recusa |
| Conciliação de cartão | não existe: a baixa é fixada em `PAID` e deixa a API de Recebíveis fora do escopo | — |

A divergência entre baixa e extrato por até 30 dias no crédito é **comportamento
esperado**, não falha de integração — não há cenário que a verifique porque não
há o que verificar deste lado.


## Critérios de aceite (quantitativos)

| Métrica | Meta |
|---|---|
| Requests executados (regressão completa) | **100%** |
| Erros de script JavaScript | **0** |
| Assertions aprovadas | **100%** |
| Endpoints do `openapi.json` cobertos pela matriz acima | **100%** (via `check_coverage.py`) |
| Duração do Smoke | **< 5 min** |
| 409 (CIP) e 422 (regras documentadas) | contam como **sucesso** quando esperados pelo cenário |
