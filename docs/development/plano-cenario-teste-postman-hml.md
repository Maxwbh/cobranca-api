# Plano — Cenário de Teste HML via Postman (v2)

> **Status:** IMPLEMENTADO. A coleção e os environments existem em
> [`postman/`](https://github.com/Maxwbh/cobranca-api/tree/main/postman) (schema v2.1, IDs de rastreabilidade); a
> execução com segredos é o [`postman/run-regressao.sh`](https://github.com/Maxwbh/cobranca-api/blob/main/postman/run-regressao.sh),
> agendada semanalmente pelo workflow `Regressão HML (janela C6)`.
> **Contexto:** valida o **serviço único** (FastAPI + engine pyCobrança embutida)
> da v2.0.0. Este documento é o plano que originou esses artefatos.

---

## 1. Objetivo e princípios

Uma **única Collection** importável cobrindo as duas superfícies do serviço
único: REST online (raiz) e offline nativa (`/api/*`).

| Princípio | Como se materializa |
|---|---|
| **Rastreabilidade** (eixo do plano) | Todo cenário tem ID (`BC-xxx`/`NEG-xxx`) ligado a endpoint e a critério do roadmap (§4) |
| **Cobertura verificável** | A Collection deve conter **todos os endpoints suportados na versão atual** — verificação automática contra o `GET /openapi.json` (§8); o total de requests é consequência, nunca meta |
| **Fiel ao código** | Payloads derivados dos schemas reais; dados nunca inventados (§6) |
| **Zero manutenção de massa** | Datas/ids dinâmicos por script; fixtures vêm do repositório |
| **Segredo nunca versionado** | Environments no repo com campos `secret` vazios; preenchimento local ou via `--env-var` |
| **Veredito automático + evidência** | Assertions em todo request; execução gera relatórios versionáveis (§9) |

## 2. Modos de execução — Smoke × Regressão

**Uma Collection só** (evita dessincronização de manutenção); a separação é por
pasta + execução seletiva nativa (`--folder` no newman / seleção no Runner):

| Modo | Conteúdo | Quando roda | Alvo |
|---|---|---|---|
| **SMK · Smoke** | Pasta própria no topo, **máx. 9 requests**: health gateway, health Core (proxy), info, `/bancos`, cadastrar credencial, emitir boleto, consultar boleto, PDF offline, Pix cob | **Antes de qualquer deploy** | **< 5 min** |
| **Regressão** | Todas as demais pastas (BC-xxx + NEG-xxx) | Diária no ciclo de HML + antes do cutover | completa |

```bash
newman run postman/cobranca-api.postman_collection.json -e postman/hml.postman_environment.json \
  --folder "SMK · Smoke"          # pre-deploy
newman run postman/cobranca-api.postman_collection.json -e postman/hml.postman_environment.json
                                   # regressão completa
```

## 3. Formato e arquitetura de variáveis

**Formato:** Collection **schema v2.1** + Environments separados (HML, Local).

### 3.1 Três camadas

| Camada | Onde | Carrega |
|---|---|---|
| **Environment** | `hml/local.postman_environment.json` | `base_url`; conta (`agencia`, `conta`, `convenio`, `chave_pix`); **segredos** tipo `secret`: `c6_client_id/secret`, `c6_pfx_base64/password`, `sicoob_client_id`, `sicoob_access_token` |
| **Coleção** | variáveis da collection | Defaults não-sensíveis (`tenant_id`, `provider`, `bank_offline`, pagador, `collection_version`) |
| **Runtime** | scripts | Dinâmicos e encadeados (§3.2–3.3) |

### 3.2 Dinâmica (pre-request de coleção)

Datas recalculadas por execução (`vencimento`=+30d, janelas=−30d); `txid` Pix
(`[a-zA-Z0-9]{26,35}`), `external_reference_id` Bolepix (`^[A-Z0-9]{26}$`) e
`seu_numero` únicos por sessão.

### 3.3 Encadeamento (tests → environment)

`POST /credenciais` → `bapi_token_c6|sicoob` → `bapi_token` ativo (Bearer da
coleção); utilitários trocam token+`provider` juntos (**troca de banco em 1
clique**); `cobranca_id`, `txid`, `id_rec`, `external_reference_id` capturados
das respostas alimentam os requests seguintes.

### 3.4 Organização dos scripts (zero duplicação de JS)

Utilitários definidos **uma única vez** nos scripts de nível de coleção e
expostos como funções (`assertPdf()`, `assertCamposNossoNumero()`,
`saveToken()`, `novoTxid()`); os requests apenas invocam. Abordagem portável
(Postman free + newman) — sem dependência do Package Library (plano pago).

### 3.5 Autenticação

Coleção: `Bearer {{bapi_token}}`. Pastas offline/saúde/catálogo/credenciais:
`noauth`. Alternativas documentadas: header `X-Bank-Credentials` (JSON base64)
ou campo `credentials` no body (precedência já implementada no gateway).

## 4. Matriz de Rastreabilidade (seção principal)

Cobertura = esta matriz completa. Endpoint novo ⇒ nova linha com ID ⇒ novo
request (verificado pelo §8). Coluna **Roadmap** liga aos critérios T1–T10 (§4.2b).

### 4.1 Cenários funcionais (BC)

| ID | Funcionalidade | Endpoint | Origem | Roadmap |
|---|---|---|---|---|
| BC-001 | Health gateway | `GET /health` | Gateway | T10 |
| BC-002 | Health da engine offline | `GET /api/health` | engine offline | Fase 1 |
| BC-003 | Info do engine | `GET /api/info` | engine offline | — |
| BC-004 | Catálogo com capacidades/esquemas | `GET /bancos` | Gateway | T10 |
| BC-005 | Catálogo offline (18 bancos CNAB) | `GET /api/bancos` | engine offline | — |
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
| BC-018 | Cobrança offline pela rota canônica | `POST /cobranca` (`provider=brcobranca`) | Gateway→Core | — |
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
> [docs/homologacao/](../homologacao/README.md) como defeito do banco. Marcar o
> request como falho por causa disso apontaria para o lugar errado.

### 4.2 Cenários negativos (NEG) — enxutos, só comportamento já implementado

| ID | Cenário | Esperado |
|---|---|---|
| NEG-001 | Bearer inválido/revogado em rota REST | 401 |
| NEG-002 | `provider` inexistente | 422 (enum) |
| NEG-003 | Boleto offline com dados inválidos | 400 + `validation_errors` | 
| NEG-004 | JSON malformado no body | 422 (FastAPI) |
| NEG-005 | OFX inválido no upload | 400 |
| NEG-006 | Extrato Sicoob multi-mês | 422 |
| NEG-007 | Pix em provider offline (`brcobranca`) | 422 |

> NEG-003 cobre o **T6** (§4.2b): propagação do erro de validação.

### 4.2b Critérios de aceite T1–T10 (herdados da migração)

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

### 4.3 Critérios NÃO cobertos pelo Postman (cobertos por pytest)

| Roadmap | Motivo | Onde é coberto |
|---|---|---|
| T7 (engine indisponível → 502) | não induzível em e2e sem derrubar o Core | `tests/test_offline_proxy.py` |
| T8 (método não aceito → 405) | valor marginal em e2e | idem |

### 4.4 Cartão no C6 — implementado

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

## 5. Estrutura de pastas da Collection

`SMK · Smoke` (≤9 req) → `00 Saúde` → `01 Catálogo` → `02 Credenciais` →
`03 Cobrança REST` → `04 Offline /api/*` → `05 Carnê` → `06 Pix` →
`07 Bolepix` → `08 Pix Automático` → `09 Extrato & Conciliação` →
`10 CNAB & OFX` → `11 Webhooks` → `NEG · Negativos`.

Nome de request = `<ID> · <Funcionalidade>` (ex.: `BC-017 · PDF binário + headers X-*`).

## 6. Fontes de dados (não existem payloads inventados)

Cadeia de origem, em ordem de precedência:

1. **Schemas OpenAPI/Pydantic do serviço** (`app/schemas.py`, `GET /openapi.json`)
   → estrutura de todos os bodies.
2. **Fixtures do repositório** (`spec/fixtures/`) → arquivos de upload:
   `sample_data.json` (boleto/remessa), `extrato_itau.ofx`, `extrato_sicoob.ofx`.
   **Regra: nunca gerar CNAB/OFX manualmente** — a regressão compara comportamento real.
   *Ação derivada:* extrair o conteúdo de retorno `.RET` hoje inline nos specs
   Ruby para `spec/fixtures/` (fonte única RSpec + Postman).
3. **Variáveis de environment** → conta/credenciais do sandbox.
4. **Geração dinâmica em runtime** → somente datas e identificadores (§3.2).

## 7. Critérios de aceite (quantitativos)

| Métrica | Meta |
|---|---|
| Requests executados (regressão completa) | **100%** |
| Erros de script JavaScript | **0** |
| Assertions aprovadas | **100%** |
| Endpoints do `openapi.json` cobertos pela matriz §4 | **100%** (via §8) |
| Duração do Smoke | **< 5 min** |
| 409 (CIP) e 422 (regras documentadas) | contam como **sucesso** quando esperados pelo cenário |

## 8. Cobertura verificável (guarda anti-esquecimento)

Script de verificação no CI (`postman/check_coverage.py`): compara os paths de
`GET /openapi.json` (+ inventário `/api/*` do roadmap §7) com os requests da
Collection. **Endpoint sem BC-xxx correspondente ⇒ build falha.** A "tabela de
cobertura por endpoint" é o output gerado desse script (snapshot anexado à
evidência), não uma tabela mantida à mão.

## 9. Evidências e versionamento de execução

Cada execução de regressão gera e arquiva:

- **Relatórios**: `newman` com reporters **htmlextra** (leitura humana),
  **junit** (CI) e **json** (histórico) — incluem tempo, falhas e warnings.
- **Vínculo com o código testado**, registrado no relatório via variáveis e
  chamadas já disponíveis: `collection_version` (variável da coleção),
  versão da API (`GET /health` do gateway + `GET /api/metadata` do Core),
  commit git do deploy e data/hora.

Evidências ficam fora do git (`postman/reports/` no `.gitignore`), anexadas à
documentação do ciclo de HML como os PDFs de evidência do roteiro C6.

## 10. Integração com o ciclo de HML e CI

- Artefatos em `postman/` no branch `hml/migracao-servico-unico` (entram no
  squash final): collection, 2 environments, `check_coverage.py`, `README.md`.
- Smoke = gate de pre-deploy; regressão = diária + obrigatória antes do cutover
  (§10.3 do roadmap).
- A pasta 04 + BC-017 são o **teste de aceite executável** da Fase 1
  (complementa o pytest, que roda com engine mockado; aqui é end-to-end real).

## 11. Decisões em aberto

| # | Decisão | Opções |
|---|---|---|
| 1 | 3º environment de produção (só `SMK` read-only: BC-001..005)? | sim / não |
| 2 | Momento de gerar a coleção | (a) junto com a implementação do proxy (valida na hora) · (b) só após pytest T1–T10 verde |

*(Resolvidas nas revisões: escopo completo com Smoke separado por pasta;
fixtures = as do repositório; IDs + matriz de rastreabilidade como seção
principal; negativos enxutos limitados a comportamento implementado.)*

---

## Apêndice — Histórico de revisões do plano

| Versão | Mudanças |
|---|---|
| v1 | Estrutura inicial: 3 camadas de variáveis, 12 pastas, encadeamento, aceite qualitativo |
| **v2** | Revisão 1 (13 pontos): Smoke×Regressão (1 collection + `--folder`), IDs BC/NEG, **matriz de rastreabilidade como seção principal**, cobertura verificada contra OpenAPI (build falha), sem números-meta, evidências htmlextra/junit/json, capítulo de fontes de dados, fixtures CNAB/OFX do repo (ação: extrair `.RET` dos specs), utils JS sem duplicação, negativos, aceite quantitativo, versionamento de execução. Revisão 2 (refinos): Smoke ≤ 9 req / < 5 min; negativos enxutos (7) |
