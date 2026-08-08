# Postman — Cenário de Teste HML (Cobranca-API)

Artefatos do [plano v2](../docs/development/plano-cenario-teste-postman-hml.md).
As descrições das pastas citam os **IDs de catálogo de serviços** (`C6-Sxx`,
`SIC-Sxx`) — catálogo completo por banco (inclusive não implementados) em
`docs/development/<banco>-rest.md`, seção "Serviços do banco × Cobranca-API".
Coleção **schema v2.1**, com IDs de rastreabilidade (`BC-xxx` funcional,
`NEG-xxx` negativo, `SMK-xx` smoke) ligados à matriz §4 do plano e aos testes
T1–T10, na [§4.2b do plano de cenário](../docs/development/plano-cenario-teste-postman-hml.md).

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
