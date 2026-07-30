# Migração da Plataforma — Serviço Único Python (Gateway + Banking Core)

> ⚠️ **DOCUMENTO HISTÓRICO (concluído e superado).** Esta migração (proxy
> `/api/*` → Banking Core BrCobrança em Ruby) foi **concluída** e depois
> **superada** pela versão **2.0.0**, que descontinuou a conexão com o
> BrCobrança e passou a servir a superfície offline **nativamente** pela engine
> [pyCobrança](https://github.com/Maxwbh/pyCobranca) (100% Python).
> Mantido para rastreabilidade das decisões.

> **Status:** EM REVISÃO — v2 consolidada (funde as 3 revisões). Nenhuma etapa executada.
> **Decisões travadas:**
> 1. O **Banking Core** (Ruby BrCobrança) é componente estratégico estável ("Stable Core") e **não será reescrito**;
> 2. O **FastAPI vira a única porta de entrada** da plataforma;
> 3. Motor + gateway empacotam num **único serviço** (deploy único).
>
> **Fora de escopo:** portar o Banking Core para Python (justificativa no Apêndice C).

---

## Parte I — Visão Arquitetural (o porquê / o quê)

### 1. Objetivo

Consolidar os serviços hoje distribuídos (Ruby `:9292` + Python `:8000`) numa
única aplicação FastAPI, **preservando integralmente o Banking Core Ruby**.
O objetivo não é reescrever o mecanismo bancário, mas modernizar a
arquitetura, simplificar a implantação e preparar a plataforma para a adoção
gradual das APIs oficiais dos bancos.

### 2. Motivação

A arquitetura atual expõe dois processos, duas portas, dois deploys, dois
pontos de monitoramento e configuração duplicada. A proposta elimina essas
limitações **mantendo compatibilidade total** com os consumidores existentes.

### 3. Princípios arquiteturais

**3.1 Stable Core.** O Banking Core é maduro e validado. Fora de escopo:
reescrever regras bancárias; migrar algoritmos para Python; alterar cálculo de
Nosso Número, Dígitos Verificadores, Código de Barras, Linha Digitável ou
CNAB. O Core recebe apenas manutenção corretiva.

**3.2 Compatibilidade total.** A migração preserva: contratos REST, estrutura
dos JSON, arquivos CNAB, geração de PDF, cabeçalhos HTTP e códigos de retorno.
O consumidor não percebe nenhuma alteração funcional.

**3.3 Modernização nas camadas externas.** Evoluções acontecem no gateway e
na camada de providers — nunca dentro do Core.

**3.4 Estratégia de evolução por provider.** Para cada banco novo:
1. Existe API oficial? → implementar Provider específico (padrão C6/Sicoob).
2. Não existe? → usar o LegacyProvider (CNAB offline via Banking Core).
3. Não adicionar regra bancária nova ao Core, exceto correções.

### 4. Arquitetura proposta

```
                     Cliente
                        │
            ┌───────────▼─────────────┐
            │  FastAPI  (porta única) │  auth bapi_ · validação · OpenAPI
            │                         │  observabilidade · roteamento
            │   /api/*  → proxy ──────┼───────────────┐  (byte-a-byte)
            │   /cobranca /pix /...   │               │
            └───────────┬─────────────┘               │
                        │ registry.py                 │
            ┌───────────▼─────────────┐               ▼
            │   Camada de Providers   │   ┌───────────────────────┐
            │  (base.py — já existe)  │   │ Banking Core (Ruby)   │
            │  · LegacyProvider ──────┼──►│ 127.0.0.1:9292        │
            │  · C6Provider     ✅     │   │ interno, não exposto  │
            │  · SicoobProvider ✅     │   │ boleto·carnê·CNAB·OFX │
            │  · InterProvider  (próx)│   └───────────────────────┘
            │  · BBProvider     (próx)│
            └─────────────────────────┘
```

Dois caminhos **de propósito distintos** (decisão de design, não redundância):

| Caminho | Rota | Natureza | Garantia |
|---|---|---|---|
| **Proxy transparente** | `/api/*` | Passthrough byte-a-byte (PDF, multipart, headers `X-*`) | Contrato offline idêntico — o catch-all **não** passa pela camada de providers |
| **Canônico tipado** | `/cobranca`, `/pix`, … | Schemas Pydantic + roteamento por provider | Abstração multi-banco |

### 5. Camada de Providers — estado real (correção às revisões anteriores)

A camada **já existe e está validada** — não será criada, será **estendida**:

| Componente | Arquivo | Estado |
|---|---|---|
| Interface comum (`registrar`/`consultar`/`baixar` + mixins BACEN) | `app/providers/base.py`, `bacen_pix.py` | ✅ em uso |
| LegacyProvider (proxy → Banking Core) | `app/providers/offline_engine.py` | ✅ em uso |
| C6Provider (boleto, Pix, Bolepix, extrato, conciliação, Pix Automático) | `app/providers/c6.py` | ✅ validado sandbox |
| SicoobProvider (boleto v3, Pix, extrato, Pix Automático) | `app/providers/sicoob.py` | ✅ validado sandbox |
| Provider Manager (roteamento `provider=`) | `app/registry.py` | ✅ em uso |
| Inter / Banco do Brasil | — | 🎯 próximos ([roadmap-providers.md](./roadmap-providers.md)) |

> Itaú **não** é exemplo de próximo provider (onboarding difícil — Fase 3 do
> roadmap de providers). Os nomes de método do doc são os **reais** do código;
> não haverá renomeação de interface nesta migração.

### 6. Benefícios esperados

**Técnicos:** arquitetura simplificada; deploy unificado; monitoramento
centralizado; documentação única; escalabilidade da camada Python.
**Negócio:** preservação do conhecimento consolidado no Core; risco de
regressão zero; evolução gradual para APIs oficiais; menor custo operacional.

---

## Parte II — Plano de Execução (o como)

### 7. Inventário — superfície que o proxy deve cobrir

Fonte da verdade: `lib/boleto_api/endpoints/*.rb`.

#### 7.1 Endpoints offline (passam a ser servidos via FastAPI)

| # | Endpoint | Método | O que o proxy PRECISA preservar |
|---|---|---|---|
| 1 | `/api/health` | GET | JSON simples |
| 2 | `/api/info` | GET | JSON |
| 3 | `/api/metadata` | GET | JSON |
| 4 | `/api/bancos` | GET | JSON (catálogo offline — difere do `/bancos` do gateway) |
| 5 | `/api/boleto/validate` | GET | Query `bank` + `data` (JSON serializado na query) |
| 6 | `/api/boleto/data` | GET | Query com JSON; 400 com `validation_errors` |
| 7 | `/api/boleto/nosso_numero` | GET | Query com JSON |
| 8 | `/api/boleto` | GET | **PDF binário** + `Content-Disposition` + `X-Nosso-Numero`, `X-Nosso-Numero-Formatado`, `X-Nosso-Numero-DV`, `X-Codigo-Barras`, `X-Linha-Digitavel`; `include_data=true` → JSON + base64 |
| 9 | `/api/boleto/multi` | POST | **Multipart** (`data` = File) + binário + `X-Boletos-Info`, `X-Boletos-Count` |
| 10 | `/api/remessa` | POST | Multipart; `text/plain` CNAB + `Content-Disposition`; query `pix=true` |
| 11 | `/api/retorno` | POST | Multipart (arquivo CNAB); JSON |
| 12 | `/api/ofx/parse` | POST | Multipart (`file`); `somente_creditos` |
| 13–15 | `/api/render/boleto\|carne\|remessa` | POST | JSON→JSON (já usados internamente pelo gateway) |
| 16 | `/api/docs` | GET | Swagger UI do engine (HTML + assets) |
| 17 | `/api/openapi.json\|.yaml` | GET | Spec OpenAPI do engine |

#### 7.2 Endpoints do gateway (INALTERADOS)

`/bancos`, `/credenciais`, `/cobranca`, `/carne`, `/pix`, `/bolepix`,
`/pix-automatico`, `/conciliacao`, `/extrato`, `/config/*`, `/webhooks/*`,
`/health` — todos na raiz. **Sem colisão** com `/api/*`.

#### 7.3 Comportamentos transversais do Core que afetam o proxy

| Comportamento | Origem | Implicação |
|---|---|---|
| Gzip automático | `Rack::Deflater` no `config.ru` | httpx entrega corpo **decodificado** → remover `Content-Encoding`/`Content-Length` antes de reemitir |
| Headers hop-by-hop | RFC 7230 §6.1 | Filtrar nos 2 sentidos |
| PDF/carnê demorados | Prawn em lote | Timeout do proxy ≥ 60s |
| Erros 400 estruturados | `error!({validation_errors})` | Propagar status + corpo sem tocar |

### 8. Fases

#### FASE 1 — Proxy `/api/*` (núcleo; 100% testável neste ambiente)

| Passo | Artefato | Detalhe |
|---|---|---|
| 1.1 | `app/routers/offline.py` **(novo)** | Catch-all `/api/{path:path}` (GET/POST/PUT/PATCH/DELETE); repassa método, query multi-items, headers filtrados, corpo bruto; devolve byte-a-byte; `include_in_schema=False`; 502 JSON claro se Core indisponível; timeout 60s. **Proxy puro — não passa pela camada de providers** |
| 1.2 | `app/main.py` **(alterar)** | `include_router(offline.router)` por último; título/descrição → "serviço único: gateway online + Banking Core embutido" |
| 1.3 | `tests/test_offline_proxy.py` **(novo)** | Matriz §9 |

**Gate:** `pytest` da suíte inteira verde. **Rollback:** remover 1 include + 1 arquivo.

#### FASE 2 — Empacotamento único (Docker)

| Passo | Artefato | Detalhe |
|---|---|---|
| 2.1 | `gateway/docker/entrypoint.sh` **(novo)** | `BOLETO_ENGINE_URL=http://127.0.0.1:$ENGINE_PORT`; Puma em background; **health-gate** (até 40×1s em `/api/health`); `exec uvicorn` foreground; `tini` PID 1 |
| 2.2 | `Dockerfile` (serviço único — nome padrão desde 2026-07-21; o engine standalone é `Dockerfile.engine`) **(novo, raiz)** | Multi-stage: stage gems (ruby:3.3-slim → `bundle install`); final ruby:3.3-slim + python3/pip/tini/wget; `/engine` (Gemfile, config.ru, config/, lib/) + `/app` (gateway); `HEALTHCHECK` no `/health` FastAPI. Base **Debian-slim** (wheels manylinux de `cryptography`/`psycopg`); PEP 668 → venv `/opt/venv` se preciso |
| 2.3 | `docker-compose.yml` (serviço único como default; engine/rghost/test viram profiles) | 1 serviço, `8000:8000`, healthcheck |
| 2.4 | Smoke local (se o build rodar aqui) | §10.2 |

**Gate:** smoke §10.2 verde, ou artefatos revisados + smoke delegado ao CI/deploy
(**pendência explícita**, nunca "validado"). **Rollback:** arquivos aditivos.

#### FASE 3 — Deploy e cutover (Render)

| Passo | Detalhe |
|---|---|
| 3.1 | `render.yaml`: `dockerfilePath: ./Dockerfile.unified`; `healthCheckPath: /health`; env `PORT=8000`, `ENGINE_PORT=9292`; manter tuning jemalloc/GC do Puma interno; envs do gateway (`SUPABASE_DB_URL` etc. `sync: false`) |
| 3.2 | Cutover: deploy unificado; consumidores trocam base `:9292` → `:8000` (path idêntico). **Janela de convivência**: serviço Ruby antigo fica de pé até checklist §10.3 |
| 3.3 | Desativar a exposição pública do Banking Core **somente** após §10.3 |

**Rollback:** revert de 1 commit no `render.yaml`; serviço antigo ainda no ar.

#### FASE 4 — Documentação e reposicionamento do repositório · ✅ CONCLUÍDA (2026-07-21)

| Arquivo | Mudança |
|---|---|
| `gateway/README.md` | Seção "Serviço único" + diagrama §4 |
| `docs/README.md` | Topologia: 1 serviço, 2 superfícies (REST raiz; offline `/api`) |
| `docs/ARCHITECTURE.md` | Diagrama novo (Core sidecar interno) |
| `docs/development/separacao-3-produtos.md` | 3 produtos **lógicos** (Core, gateway, client); Core+gateway empacotam juntos; Core não é mais exposto |
| `DEPLOY.md` | Fluxo de deploy unificado |

**4.b Reposicionamento `boleto_cnab_api` → `cobranca-api`** (executado no GitHub
em 2026-07-21: desvinculação do fork akretion + rename + descrição + topics —
o GitHub redireciona as URLs antigas; referências internas atualizam aqui):

| Item | Onde |
|---|---|
| Labels OCI (`image.title/url/source`) | `Dockerfile`, `Dockerfile.rghost`, `Dockerfile` (serviço único — nome padrão desde 2026-07-21; o engine standalone é `Dockerfile.engine`) |
| Badges e links `Maxwbh/boleto_cnab_api` → `Maxwbh/cobranca-api` | `README.md`, `docs/README.md`, `DEPLOY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` |
| Crédito de origem: de linguagem de fork para "originado do projeto akretion/boleto_cnab_api (MIT)" | `README.md`, `docs/ARCHITECTURE.md` |
| Referências do cliente pip e exemplos | `python-client/`, `examples/` |
| Nome do serviço/urls | `render.yaml` |

#### FASE 5 — Modo por banco + observabilidade (evolução pós-migração)

| Item | Detalhe |
|---|---|
| 5.1 Modo por banco | Config central `provider_mode` por banco: `legacy \| api` — estende `app/registry.py` (hoje: campo `provider` por request + gate `C6_REGISTERED_READY`). Cutover de banco sem mudar o consumidor |
| 5.2 Readiness | `/health` (liveness) + `/ready` (FastAPI **e** Core respondendo) |
| 5.3 Métricas por provider | Emissões por banco, latência média, taxa de erro — logs estruturados |

> Fase 5 é evolução independente: a migração (F1–F4) se encerra sem ela (§10.4).

### 9. Matriz de testes da Fase 1 (`tests/test_offline_proxy.py`, respx)

| # | Cenário | Mock | Asserções |
|---|---|---|---|
| T1 | `GET /api/boleto` binário | 200 `application/pdf`, `%PDF...`, headers `X-*` | bytes **idênticos**; 5 headers `X-*`; `Content-Disposition` |
| T2 | Resposta gzip | 200 + `Content-Encoding: gzip` | corpo íntegro; `content-encoding` **ausente** na saída |
| T3 | `POST /api/remessa` multipart | 200 `text/plain` + `Content-Disposition` | multipart chegou ao Core; CNAB intacto |
| T4 | `POST /api/ofx/parse` | 200 JSON | passthrough |
| T5 | Query string | echo `?include_data=true&bank=itau` | query repassada (multi-items) |
| T6 | Erro de validação | 400 `{validation_errors}` | status + corpo idênticos |
| T7 | Core fora | `ConnectError` | 502 + `{"erro":"engine offline"}` |
| T8 | Método não aceito | 405 | propagado |
| T9 | `/api/docs` HTML | 200 `text/html` | content-type + corpo |
| T10 | Rotas do gateway intactas | — | `GET /health`, `GET /bancos` respondem pelo FastAPI (não caem no catch-all) |

### 10. Critérios de aceite

**10.1 Fase 1 (roda neste ambiente)**
- [ ] `pytest` 100% verde (22 arquivos atuais + T1–T10)
- [ ] `GET /openapi.json` do FastAPI sem o catch-all (schema limpo)

**10.2 Smoke Fase 2 — ✅ CONCLUÍDO em 2026-07-21 (HML real: https://boleto-cnab-api.onrender.com, commit `f9fedc0`)**
- [x] Build do `Dockerfile` (serviço único — nome padrão desde 2026-07-21; o engine standalone é `Dockerfile.engine`) conclui (no Render; Docker local indisponível — R3)
- [x] `GET /health` → FastAPI ok · `GET /api/health` → Core via proxy ok (mesma URL)
- [x] `GET /api/boleto` gera PDF válido (`%PDF`, 26.181 bytes) com os 5 headers `X-*`, sem `content-encoding` residual
- [x] Rota canônica `provider=brcobranca` → `registrado` + linha digitável + PDF 33 KB
- [x] OFX (fixture do repo) parseado via proxy; erro 400 propagado (T6 real); `/docs` e `/api/docs` no ar
- [x] RSS local: Puma 64 MB + Uvicorn 73 MB ≈ 137 MB (dentro dos 512 MB)
- Incidentes do deploy (corrigidos): `addgroup` inexistente no Debian slim (`3d92929`); colisão `PORT==ENGINE_PORT` com env do painel (`f9fedc0` — entrypoint desloca o Core)

**10.3 Cutover (produção)**
- [ ] Serviço unificado com `/health` verde por 24h
- [ ] Mesmos dados → mesmos `codigo_barras`/`linha_digitavel` no serviço novo × antigo (templates `prawn` e `carne`)
- [ ] 1 remessa CNAB240 + 1 CNAB400 nos 2 serviços → **diff vazio**
- [ ] Consumidores migrados de base URL
- [ ] Só então: desativar exposição pública do Core

**10.4 Migração concluída quando** (critérios do doc arquitetural):
contratos compatíveis · CNAB equivalente byte-a-byte · boletos idênticos ·
suíte de testes aprovada · FastAPI como única interface pública.

### 11. Riscos e planos B

| # | Risco | Prob. | Impacto | Sinal | Plano B |
|---|---|---|---|---|---|
| R1 | Proxy corromper binário (gzip/headers) | Média | Alto | T1/T2 falham | Strip de `content-encoding` previsto; gate byte-a-byte |
| R2 | Imagem única estourar 512MB (Render) | Média | Alto | RSS idle > ~420MB no smoke | **2 containers** (FastAPI público + Core em rede privada) — mesma topologia lógica; só muda `BOLETO_ENGINE_URL`; `offline.py` não muda |
| R3 | Build Docker indisponível neste ambiente | Média | Médio | build falha | Entregar F1 verde + artefatos F2 revisados; smoke vira 1º passo do CI/deploy (pendência explícita) |
| R4 | Puma interno morrer em runtime | Baixa | Médio | 502 no `/api/*` | Health-gate no boot + HEALTHCHECK derruba o container (restart); 502 claro |
| R5 | pip PEP 668 na base slim | Baixa | Baixo | pip recusa | venv `/opt/venv` |
| R6 | `/api/docs` com assets quebrados via proxy | Baixa | Baixo | T9 / smoke | Spec canônica = `/api/openapi.json`; documentar |
| R7 | Consumidores presos na base `:9292` | Média | Baixo | erros pós-descomissionamento | Janela de convivência + comunicação; path idêntico |
| R8 | Proposta futura de reescrever o Core | — | Alto | — | Princípio **Stable Core** (§3.1) + Apêndice C registrados neste doc |

### 12. O que explicitamente NÃO muda (garantias)

1. **Nenhuma linha** de `lib/` (Ruby) ou da gem BrCobrança → impossível regredir DV/código de barras/CNAB.
2. **Nenhuma rota REST** do gateway (paths, schemas, auth `bapi_`, webhooks).
3. **Contrato offline byte-a-byte** — muda só a origem (`:8000` em vez de `:9292`).
4. **Interface de providers** — sem renomeação (`registrar/consultar/baixar` + mixins).
5. `Dockerfile`/`Dockerfile.rghost`/`docker-compose.yml` atuais permanecem (unificado é aditivo até o cutover).
6. Cliente pip (`python-client/`) intocado.

### 13. Sequência de commits prevista

| Ordem | Commit (autor `maxwbh`) | Conteúdo | Gate |
|---|---|---|---|
| 1 | `feat(gateway): proxy /api/* para o Banking Core embutido` | F1 + testes | pytest verde |
| 2 | `build: imagem unificada (Banking Core + gateway)` | F2 | smoke §10.2 ou pendência |
| 3 | `deploy: serviço único no Render` + docs | F3 + F4 | revisão |

> Alternativa: 1 commit único (padrão C6). Decisão na liberação da execução.

---

## Apêndice A — Esboço do proxy (referência de revisão)

```python
# app/routers/offline.py
_DROP_REQ  = {"host", "content-length", "connection", "keep-alive",
              "transfer-encoding", "upgrade", "proxy-connection"}
_DROP_RESP = _DROP_REQ | {"content-encoding"}  # Rack::Deflater: httpx já decodificou

@router.api_route("/api/{path:path}", methods=[...], include_in_schema=False)
async def proxy_offline(path, request):
    body = await request.body()
    fwd  = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_REQ}
    async with httpx.AsyncClient(timeout=60.0) as c:
        up = await c.request(request.method, f"{_engine()}/api/{path}",
                             params=list(request.query_params.multi_items()),
                             content=body, headers=fwd)
    return Response(up.content, up.status_code,
                    {k: v for k, v in up.headers.items() if k.lower() not in _DROP_RESP},
                    media_type=up.headers.get("content-type"))
```

## Apêndice B — Variáveis de ambiente do serviço unificado

| Variável | Default | Papel |
|---|---|---|
| `PORT` | `8000` | Porta pública (Uvicorn) |
| `ENGINE_PORT` | `9292` | Porta interna do Puma (127.0.0.1) |
| `BOLETO_ENGINE_URL` | derivada no entrypoint | Consumida por `engine.py`/`offline_engine.py`/`offline.py` |
| `BOLETO_TEMPLATE` | `prawn` | Template PDF do Core |
| `RACK_ENV` | `production` | Core |
| `PUMA_*`, `RUBY_GC_*`, `MALLOC_CONF` | atuais | Tuning de memória do Puma interno |
| `SUPABASE_DB_URL`/`DATABASE_URL`, `CREDENTIAL_DB_SCHEMA`, `CREDENTIAL_DB_PATH` | atuais | Cofre de credenciais |
| `SUB__*`, `EVENT_WEBHOOK_*`, `C6_*`, `SICOOB_*` | atuais | Gateway (inalteradas) |

## Apêndice C — Por que NÃO portar o Banking Core (registro da decisão)

O Core concentra dezenas de milhares de linhas de regra bancária (nosso número
+ DV por banco, código de barras/linha digitável, CNAB 240/400 posição a
posição, PDF). Não há biblioteca Python equivalente madura (`pyboleto` cobre
poucos bancos, sem CNAB, semi-abandonado). Reescrever = alto custo + risco de
regressão silenciosa (um DV errado → boleto impagável). A consolidação por
sidecar entrega o objetivo — um serviço, uma URL, deploy único — com risco
zero sobre o cálculo bancário. Um porte real, se algum dia desejado, deveria
ser incremental (1 banco por vez, equivalência byte-a-byte contra o Ruby),
usando este serviço unificado como harness de comparação.

## Apêndice D — Histórico de revisões consolidadas nesta v2

| Revisão | O que entrou | O que foi corrigido |
|---|---|---|
| v1 (original) | Inventário, fases 1–4, testes, riscos, apêndices | — |
| Revisão md | Visão de longo prazo; Fase 5 (flags + métricas); terminologia | "Criar camada de providers" (já existe); catch-all delegando a provider (quebraria o byte-a-byte) |
| Revisão PDF | Princípios (Stable Core, Compatibilidade, Modernização); estratégia de evolução; critérios de aceite; benefícios | Exemplos de providers (C6 omitido; Sicoob como futuro; Itaú como próximo); interface com nomes divergentes do código; "Banking Service Layer" indefinida |
