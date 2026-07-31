# Changelog

Mudanças **do produto** — o que muda para quem consome a API, roda a imagem ou
instala o cliente.

Mudança de **processo** não entra aqui: CI, workflows, templates de issue e PR,
scripts de release, configuração de deploy e convenção de branches vivem no
histórico do git e nos próprios arquivos. O critério é uma pergunta só: *isso
muda alguma coisa para quem usa o serviço?* Se a resposta for não, fica fora.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido
- **`LOG_LEVEL` não tinha efeito nenhum.** A variável era declarada no
  `render.yaml` desde sempre, mas nada a lia: o código não configura logging e
  o `CMD` do Dockerfile não passava `--log-level` (o uvicorn lê
  `UVICORN_LOG_LEVEL`, não `LOG_LEVEL`). Quem subia o serviço com
  `LOG_LEVEL=debug` continuava com log em `info`, sem aviso. O `CMD` agora
  mapeia a variável para o `--log-level` do uvicorn, com dois cuidados: a
  caixa é normalizada (o uvicorn aborta em `INFO` e derrubaria o container no
  boot) e valor inválido cai para `info` com aviso, em vez de virar
  crash-loop. `LOG_LEVEL=info` entra como default no `ENV` da imagem.

## [2.1.0] - 2026-07-31

### Corrigido
- **Link quebrado servido pela própria API**: `_DOC_REPO` (`app/main.py`), que
  aparece na descrição da tag `bancos` do Swagger, apontava para
  `/tree/master/docs/development` — 404, já que o branch default é `main`.
- **5 links `/blob/master/` e `/tree/master/` no `docs/openapi.yaml`** —
  CHANGELOG, guias por banco, validação de campos e encargos. Todos 404, e
  todos servidos no Swagger público.

### Adicionado
- **`POST /api/render/fatura`** — renderiza a fatura pela engine
  (`render_fatura_pdf`): corpo livre no topo + boleto de pagamento abaixo, num
  só PDF. Passthrough puro (o gateway não soma nem calcula; o `valor` vem no
  payload). Expõe os níveis 1 (`itens`) e 2 (`fatura.blocos`); o nível 3
  (`fatura.desenhar`, callback Python) **não** trafega por JSON e é recusado
  com `400`.

### Alterado
- **Python mínimo 3.14 → 3.12** e **engine `pycobranca` ≥ 1.0.2**: a 1.0.2
  baixou o piso para `>=3.12`, que tem wheels prontos e **elimina a compilação
  a partir do código-fonte** (e o problema do pydantic no `3.14.0rc2`).
  Dockerfile passa a `python:3.12-slim`.

## [2.0.0] - 2026-07-28

### 🐍 Serviço único, 100% Python (engine PyCobrança)

**BREAKING:** a conexão com o **Banking Core BrCobrança (Ruby) foi
DESCONTINUADA**. A superfície offline (`/api/*`) passa a ser servida
**nativamente** pela engine [PyCobrança](https://github.com/Maxwbh/pyCobranca)
dentro do próprio processo FastAPI — um container, um processo, sem sidecar.

A v2 **não carrega o vocabulário da v1**: o que existia só por compatibilidade
foi removido (ver "Removido").

### Adicionado
- `app/core/pycob.py` — adaptador da engine (boleto, multi/carnê, remessa
  CNAB 240/400, retorno, leitura de OFX).
- `/api/*` nativo: health, info, metadata, bancos, boleto (validate/data/
  nosso_numero/PDF/multi), remessa, retorno, OFX, render/* e Swagger próprio.
- **Jobs em lote assíncrono** (`/jobs/boletos`, `/jobs/cnab/remessas`): 202 +
  `job_id`, isolamento por item, idempotência, artefatos com `sha256`, webhook
  de conclusão (HMAC) e métricas.
- **Encargos na remessa CNAB** validados e documentados: multa, juros/mora,
  desconto (1º/2º/3º), IOF, abatimento e protesto — modelo de trio
  código/tipo → valor → data, com a unidade recusada quando o layout não a
  expressa (guia `docs/api/encargos.md`, schema `Pagamento` no Swagger).
- `provider: "pycobranca"` — valor canônico do caminho offline/CNAB.
- **Validação de campos por banco** (engine PyCobrança ≥ 1.0.1): tipos,
  tamanhos, formatos, carteiras válidas, nosso número e campos especiais;
  os erros vêm em **lista** (`validation_errors`), um por campo. Inclui
  **CNPJ alfanumérico** (formato 2026). Guia: `docs/api/validacao-campos.md`.

### Alterado
- Imagem Docker `python:3.14-slim` (exigência da engine), processo único,
  usuário não-root; `git` sai da imagem (a engine vem do PyPI, não de git).
- Dependência da engine: `pycobranca>=1.0.1,<2` (PyPI) — build reprodutível.
- OFX passa a ser lido pela engine (regra de nosso número **por banco**).

### Removido
- Engine Ruby (`lib/`, `spec/`, `config/`, `config.ru`, `Gemfile*`), variantes
  de Dockerfile e o entrypoint de sidecar.
- Geração de **imagens** (JPG/PNG/TIF) — a engine emite **PDF** (`jpg/png/tif`
  respondem 400).
- `provider: "brcobranca"` — **removido**; enviar o valor antigo responde 422
  listando os válidos.
- Campo `nosso_numero_extraido` no OFX — ficou só `nosso_numero`.
- Dependência `ofxparse` (OFX agora é da engine).
- Pacote pip `boleto-cnab-client` → **`cobranca-api-client`** (import
  `boleto_cnab_client` → `cobranca_api`).

## [1.5.0] - 2026-06-17

### Adicionado

- 🧩 **Endpoints de renderização** `POST /api/render/boleto`, `/api/render/carne`
  e `/api/render/remessa`: corpo JSON e resposta normalizada (boleto → dados +
  PDF base64; carnê 3-vias A4 em PDF; remessa → conteúdo CNAB). São a superfície
  consumida pelo gateway **Boleto-API (Python)** via proxy — o `boleto_cnab_api`
  passa a atuar como **engine de renderização** (BrCobrança). Documentados no
  `openapi.yaml` (tag `Render`) e no Swagger (`/api/docs`).

### Modificado

- 📦 **brcobranca atualizado**: `12.10.2` → `12.10.3` (revision `2613452` →
  `e555745`). Corrige o template **PrawnCarne** (faltava o `autoload` de
  `PrawnCarne`/`PrawnTema` e o método `PrawnTema.texto_logo_banco`), restaurando
  o carnê 3-vias A4 sem GhostScript (`template=carne`).

### Corrigido

- 🛡️ **Robustez de campos (boleto e remessa)**:
  - Campos com default (`aceite`, `especie_documento`, `especie`, `moeda`,
    `local_pagamento`) enviados **em branco** agora caem no default do brcobrança
    (antes falhavam com "não pode estar em branco").
  - A remessa **ignora campos não suportados** pela classe do banco (ex.:
    `variacao` no CNAB 240 do Sicoob) e campos extras dentro de cada `pagamento`
    (ex.: `cedente`), em vez de gerar `500` (`NoMethodError`). Códigos de formato
    do pagamento em branco também caem no default.
  - **`bairro_sacado` ausente** não quebra mais a remessa. O brcobrança usa
    `bairro_sacado.format_size` no detalhe (ex.: BB CNAB 400) sem validar
    presença; sem o campo, dava `undefined method 'format_size' for nil` → `500`.
    Agora o campo é normalizado para `''` quando ausente.
  - **Swagger/OpenAPI em produção**: o `docs/openapi.yaml` era excluído da imagem
    pelo `.dockerignore`, então `/api/openapi.json` e `/api/docs` davam `500`.
    Agora o arquivo é incluído na imagem (`!docs/openapi.yaml`) e o endpoint tem
    fallback para uma spec mínima válida (nunca `500`).

## [1.4.1] - 2026-06-14

### Modificado

- 📦 **brcobranca atualizado**: `12.10.1` → `12.10.2` (revision `cca5f1a` → `2613452`).
  O módulo `Brcobranca::Bancos` passa a permitir **registro/remoção de bancos em
  runtime** (`Bancos.registrar`, `Bancos.classe_boleto/classe_remessa/classe_pix`),
  com bancos customizados aparecendo em `todos`/`find`/`as_json` sem afetar os 18
  bancos nativos. Inclui correção menor de metadados na gemspec. Sem mudanças no
  contrato público desta API (o `/api/bancos` continua funcionando como antes).

## [1.4.0] - 2026-06-12

### Adicionado

- 🧾 **Template de carnê** no `/api/boleto` e `/api/boleto/multi` via
  `template=carne`: gera carnê em PDF (1 via por página; no `/multi`, 3 vias por
  folha A4) usando `Brcobranca::Boleto::Template::PrawnCarne` (sem GhostScript).
- 🎨 **Tema visual** nos templates Prawn (`prawn` e `carne`) — novos campos
  **opcionais** aceitos em `data`, passados direto ao boleto (attr_accessor na
  Base do brcobranca v12.10):
  - `logo_empresa` — logo da empresa (path PNG/JPG)
  - `cor_marca` — cor da marca em hex `RRGGBB` (contraste automático)
  - `marca_dagua` — texto da marca d'água diagonal antifraude
  - `rodape_contato` — rodapé com contato da empresa
  - `fonte_ttf` — fonte TTF (UTF-8 completo)
  - `parcela_atual` / `total_parcelas` — selo "PARCELA n/N"
- 🧱 Constantes `TEMPLATES`, `PDF_ONLY_TEMPLATES` e `THEME_FIELDS` +
  helpers `template_supported?` / `pdf_only_template?` em `Config::Constants`.
- 🧪 Specs de integração `spec/integration/carne_boleto_spec.rb` (carnê single,
  carnê em lote e tema no template prawn).
- 📖 OpenAPI: parâmetro `template` documentado (`rghost`/`prawn`/`carne`) e
  campos de tema adicionados ao schema `BoletoData`.

### Modificado

- 📦 **brcobranca atualizado**: `12.9.0` → `12.10.1` (revision `fa43157` → `cca5f1a`),
  que traz PrawnCarne, PrawnTema, marca d'água, fontes TTF e fixes de PIX/QR.
- 🐳 **Docker focado em Prawn**: a imagem principal (`Dockerfile`) passa a ser a
  variante **sem GhostScript** (PDF-only, mais leve e com menor uso de memória —
  ideal para o Render Free Tier). A antiga imagem com GhostScript foi movida para
  **`Dockerfile.rghost`** (use-a para gerar JPG/PNG/TIF). O `render.yaml` e o
  `docker-compose` (serviço padrão) usam a imagem Prawn; a variante rghost fica no
  profile `rghost`.
- ⚙️ **Template padrão por ambiente**: o default de `template` em `/api/boleto` e
  `/api/boleto/multi` agora vem de `BOLETO_TEMPLATE` (helper `Constants.default_template`).
  Na imagem principal o padrão é `prawn`; na `Dockerfile.rghost`, `rghost`.

### Corrigido (herdado do brcobranca)

- 🐛 **PIX/QR Code**: correção de sobreposição QR × código de barras no Bolepix
  (Prawn e RGhost) e nível de correção de erro do QR ajustado para M (padrão BACEN).
- 🐛 **Normalização de remessa**: além do Sicoob CNAB400 (`carteira`/`convenio`),
  agora também Banco do Brasil CNAB 240/400 recebe padding automático de campos.

## [1.3.2] - 2026-06-12

### Modificado

- 📦 **brcobranca atualizado**: `12.8.1` → `12.9.0` (revision `5e85c31` → `fa43157`).

### Corrigido

- 🐛 **Remessa Sicoob (CNAB400) — `carteira`/`convenio`**: a versão 12.9.0 do
  brcobranca adiciona *setters* que normalizam os campos automaticamente
  (`carteira` → `rjust(2, '0')`, `convenio` → `rjust(9, '0')`). Isso resolve os
  erros de validação `"Carteira deve ter 2 dígitos."` e `"Convenio deve ter 9
  dígitos."` que ocorriam ao gerar a remessa Sicoob com dados que geravam o
  boleto sem problemas (a classe de boleto era mais leniente que a de remessa).
  Agora `carteira: "1"` é aceito e tratado como `"01"`.

## [1.3.1] - 2026-06-12

### Otimizações de Docker / Render Free Tier (512MB RAM)

#### Memória
- ✅ **jemalloc** ativado via `LD_PRELOAD` no `Dockerfile` e `Dockerfile.prawn`.
  Substitui o allocator padrão do musl (Alpine), que tem alta fragmentação sob
  múltiplas threads — ganho real de RAM no free tier.
- ❌ Removido `MALLOC_ARENA_MAX`: é um tunable **exclusivo do glibc** e não tinha
  efeito algum em Alpine/musl (era um no-op).
- ✅ `MALLOC_CONF` (jemalloc) e `RUBY_GC_MALLOC_LIMIT` / `RUBY_GC_OLDMALLOC_LIMIT`
  ajustados para devolver memória ociosa ao SO de forma mais agressiva.

#### Imagem mais enxuta
- ✅ `bundle clean --force` + `deployment mode` no build stage.
- ✅ `.dockerignore` exclui `python-client/`, `*.md`, `scripts/` e `Dockerfile.prawn`
  → contexto de build reduzido para ~330KB.

#### Robustez de deploy
- ✅ `tini` como PID 1 (`ENTRYPOINT`) → propaga `SIGTERM` ao Puma, garantindo
  shutdown gracioso durante deploys.
- ✅ `PUMA_WORKER_TIMEOUT=60` → evita kill do worker durante o cold start
  (wake-up do sleep no free tier).
- ✅ `config/puma.rb`: `min_threads=1` (elimina latência na 1ª requisição) e
  `preload_app!` apenas em cluster mode (workers ≥ 1).
- ✅ `HEALTHCHECK` usa `${PORT}` em vez de porta fixa.

#### render.yaml
- ✅ Valores de env como strings (padrão exigido pelo Render).
- ✅ `PORT` não é mais fixado — o Render injeta a porta e o Puma faz bind via
  `ENV['PORT']`.
- 📖 `DEPLOY.md` atualizado com as novas variáveis de ambiente e dicas de OOM.

## [1.3.0] - 2026-04-10

### Adicionado

#### Banco C6 (336) — NOVO
- ✅ `banco_c6` adicionado em `SUPPORTED_BANKS` e `CNAB400_BANKS`
- ✅ Suporte completo a geração de boletos C6 (código 336)
- ✅ Remessa e retorno CNAB 400 para Banco C6
- ✅ PIX híbrido suportado (campo `emv`)
- ✅ Fixture `banco_c6_valido` em `spec/fixtures/sample_data.json`
- ✅ Testes no `all_banks_spec.rb` incluindo PDF generation

#### PIX Híbrido documentado
- 📄 `docs/api/pix.md` — Guia completo de PIX híbrido
- 📄 Bancos com PIX: Banco do Brasil, Bradesco, Itaú, Sicoob, Caixa, Banco C6, Santander, Sicredi
- 📄 Campos `emv` e `pix_label` adicionados no schema OpenAPI `BoletoData`
- 📄 Objeto `pix` no schema `BoletoResponse`

#### Documentação brcobranca-fork.md reescrita
- 📄 Tabela completa de 18 bancos com colunas Boleto, CNAB 400, CNAB 240, PIX
- 📄 Histórico de versões do fork (v12.0 → v12.6.1)
- 📄 Métodos modernos da gem: `to_hash`, `dados_calculados`, `dados_entrada`, `dados_pix`, `valido?`, `to_hash_seguro`
- 📄 Factory methods: `Brcobranca::Remessa.criar`, `Brcobranca::Retorno.parse`
- 📄 Seção detalhada por banco com particularidades

### Modificado
- 📦 **brcobranca atualizado**: 12.6.0 → 12.6.1 (traz suporte nativo a Banco C6)
- 📖 OpenAPI v1.2.0 → v1.3.0, schema `BankCode` inclui `banco_c6`
- 📖 README.md, ARCHITECTURE.md, python-client/README.md atualizados para v1.3.0
- 📖 `docs/fields/all-banks.md` inclui seção detalhada do Banco C6

### Versão da Gem

Este release atualiza brcobranca de 12.6.0 → 12.6.1, trazendo:
- Banco C6 (336) com CNAB 400 completo
- PIX expandido (6 bancos: Bradesco, Itaú, Banco C6, Sicoob, Caixa, Banco Brasil)
- Sicoob: suporte a Carteira 9 e Layout 810
- PrawnBolepix (alternativa ao Ghostscript para PIX)

---

## [1.2.0] - 2026-04-09

### Adicionado

#### Endpoint OFX (Extrato Bancário)
- `POST /api/ofx/parse` - Parsing de arquivos OFX com retorno JSON estruturado
- Suporte a OFX v1 (SGML) e v2 (XML)
- Conversão automática de encoding Latin-1 para UTF-8
- Filtro `somente_creditos=true` para retornar apenas créditos
- Extração automática de `nosso_numero` do campo memo por banco

#### Módulo NossoNumeroExtractor
- Extração por regex para Sicoob (756), Itaú (341), BB (001), Bradesco (237), Caixa (104)
- Fallback genérico para bancos não mapeados

#### Testes
- 20 testes unitários para NossoNumeroExtractor
- 14 testes unitários para OFXParserService
- 7 testes de integração para endpoint OFX
- Fixtures OFX para Sicoob e Itaú
- **Total: 158 testes Ruby + 44 testes Python (202 passando)**

#### Documentação
- `docs/README.md` - Índice central da documentação
- `docs/api/ofx-parsing.md` - Guia detalhado do endpoint OFX
- `docs/openapi.yaml` atualizado com schemas `OfxResponse`, `OfxTransacao`, `OfxError`
- Troubleshooting reescrito com seções por endpoint incluindo OFX

### Modificado
- Gemfile: adicionada gem `ofx` para parsing de extratos bancários
- Gemfile: adicionadas gems `rspec` e `rack-test` no grupo de teste
- ErrorHandler: trata `Grape::Exceptions::ValidationErrors` e `Brcobranca::NaoImplementado` como HTTP 400
- BoletoService.create: filtra campos não suportados por banco (evita NoMethodError em Bradesco por `digito_conta`)
- BoletoService.data: normaliza contrato público (`documento_numero` → `numero_documento` alias)
- BoletoService.nosso_numero: mantém compatibilidade com `nosso_numero` como chave formatada
- BoletoService.generate_multi: valida array vazio
- RemessaService: factory method usa `**kwargs` corretamente (Ruby 3.0+)
- RemessaService: converte hashes em objetos `Brcobranca::Remessa::Pagamento`
- FieldMapper: novo mapeamento `PAGAMENTO_FIELD_MAPPINGS` (sacado → nome_sacado, etc)
- Endpoints POST retornam explicitamente status 200 para binários (boleto, remessa, retorno, multi)
- Dockerfile: `BUNDLE_WITHOUT=development:test` no runtime stage
- Dockerfile: label de versão atualizado para 1.2.0
- docker-compose: serviço test instala dev deps antes de rodar rspec
- CI workflow: tag Docker em lowercase, dependências pytest instaladas via pip install -e

### Corrigido
- Remessa: `tipo:` → `formato:` (chave correta para `Brcobranca::Remessa.criar`)
- Remessa: passagem posicional → keyword arguments em Ruby 3.0+
- Remessa: formato correto `cnab400`/`cnab240` (não apenas `400`/`240`)
- Client Python: `RetryError` convertido para `BoletoAPIError`
- Fixtures: `caixa_valido` carteira `"SR"` → `"1"`, `santander_valido` ajustado para convenio válido
- `spec_helper.rb`: forçar encoding UTF-8 para arquivos com acentos
- `all_banks_spec.rb`: correção de scoping (`let` dentro de `context.each`)

### Removido
- `docs/DEPLOY.md` (duplicado do `DEPLOY.md` na raiz)
- `docs/TODO_INTEGRACAO.md` (roadmap concluído, histórico disponível em commits)
- `docs/swagger.html` (deve ser gerado sob demanda do `openapi.yaml`)

---

## [1.1.0] - 2026-01-06

### Adicionado

#### Arquitetura Modular (Fase 1)
- ✅ Refatoração completa: de 444 linhas em 1 arquivo para 12 arquivos modulares
- ✅ `lib/boleto_api/config/constants.rb` - Constantes centralizadas
- ✅ `lib/boleto_api/services/` - Camada de serviços (BoletoService, RemessaService, RetornoService)
- ✅ `lib/boleto_api/endpoints/` - Endpoints separados por domínio
- ✅ `lib/boleto_api/middleware/` - Error handler e request logger

#### Cliente Python (Fase 3)
- ✅ `pyproject.toml` - Configuração moderna PEP 517/518
- ✅ `types.py` - TypedDict para tipagem estática (BoletoDataDict, BoletoResponseDict, etc.)
- ✅ Suite de testes pytest completa (test_client.py, test_models.py, test_exceptions.py, test_types.py)
- ✅ Compatibilidade com Python 3.8+ via typing_extensions

#### Infraestrutura (Fase 4)
- ✅ Testes de integração: `spec/integration/` (remessa, retorno, multi_boleto)
- ✅ Documentação OpenAPI 3.0: `docs/openapi.yaml`
- ✅ Interface Swagger UI: `docs/swagger.html`
- ✅ Docker multi-stage build otimizado (~150MB)

#### Integração brcobranca v12.5+ (Fase 5)
- ✅ BoletoService usa `boleto.to_hash` e `dados_calculados`
- ✅ RemessaService usa `Brcobranca::Remessa.criar` factory method
- ✅ RetornoService usa `Brcobranca::Retorno.parse` com detecção automática
- ✅ Fallback mantido para versões anteriores da gem

### Modificado
- 📦 Gemfile atualizado para usar fork @maxwbh do brcobranca
- 📝 TODO_INTEGRACAO.md - Todas as 5 fases concluídas
- 🔧 Services refatorados para usar novos métodos da gem

### Repositórios
- brcobranca: https://github.com/Maxwbh/brcobranca (v12.5.0)
- boleto_cnab_api: https://github.com/Maxwbh/cobranca-api (v1.1.0)

---

## [1.0.0] - 2025-11-27

### Adicionado
- 🎉 Versão inicial estável
- ✅ Suporte completo para 6+ bancos brasileiros
- ✅ API REST com Grape framework
- ✅ Endpoints para validação, geração de dados e PDF
- ✅ Mapeamento automático `numero_documento` ↔ `documento_numero`
- ✅ Logs estruturados com timestamps e tempo de processamento
- ✅ Tratamento seguro de métodos que podem não existir em todos os bancos
- ✅ Testes automatizados com RSpec para múltiplos bancos
- ✅ Docker e Docker Compose para desenvolvimento
- ✅ Configuração otimizada para Render Free Tier
- ✅ Documentação completa de campos por banco
- ✅ Guia de deploy detalhado
- ✅ Health check endpoint

### Bancos Suportados
- Banco do Brasil (001)
- Sicoob (756)
- Bradesco (237)
- Itaú (341)
- Caixa Econômica Federal (104)
- Santander (033)
- Sicredi (748)
- Banrisul (041)
- Banestes (021)
- BRB (070)

### Endpoints
- `GET /api/health` - Health check
- `GET /api/boleto/validate` - Validar dados do boleto
- `GET /api/boleto/data` - Obter dados completos sem gerar PDF
- `GET /api/boleto/nosso_numero` - Gerar nosso número
- `GET /api/boleto` - Gerar boleto (PDF/JPG/PNG/TIF)
- `POST /api/boleto/multi` - Gerar múltiplos boletos
- `POST /api/remessa` - Gerar arquivo de remessa CNAB
- `POST /api/retorno` - Processar arquivo de retorno CNAB

### Segurança
- ✅ Validação de tipos de parâmetros
- ✅ Tratamento robusto de erros
- ✅ Logs sem informações sensíveis
- ✅ Execução como usuário não-root no Docker

### Performance
- ✅ Otimizações para 512MB RAM (Render Free Tier)
- ✅ Puma com 1 worker e até 5 threads
- ✅ MALLOC_ARENA_MAX=2 para reduzir uso de memória
- ✅ Build Docker otimizado

### Documentação
- ✅ README completo e profissional
- ✅ Guia de campos por banco
- ✅ Exemplos práticos Python/Ruby
- ✅ Troubleshooting detalhado
- ✅ Deploy guide para Render
- ✅ Documentação de API inline

### Testes
- ✅ Suite completa com RSpec
- ✅ Testes de integração para todos os bancos
- ✅ Fixtures com dados válidos
- ✅ Cobertura de casos de erro
- ✅ Testes de mapeamento de campos

---

## [Unreleased]

### Em Desenvolvimento
- 🔄 Publicação do cliente Python no PyPI
- 🔄 GitHub Actions para CI/CD
- 🔄 Badges de status e qualidade
- 🔄 Suporte a PIX (QR Code)

---

## Tipos de Mudanças

- `Adicionado` - Novas funcionalidades
- `Modificado` - Mudanças em funcionalidades existentes
- `Obsoleto` - Funcionalidades que serão removidas
- `Removido` - Funcionalidades removidas
- `Corrigido` - Correção de bugs
- `Segurança` - Correções de vulnerabilidades

---

**Formato:** [MAJOR.MINOR.PATCH]
- **MAJOR** - Mudanças incompatíveis na API
- **MINOR** - Novas funcionalidades compatíveis
- **PATCH** - Correções de bugs compatíveis
