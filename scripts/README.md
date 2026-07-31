# Scripts de Automação

Scripts úteis para desenvolvimento e manutenção do projeto.

## 📦 bump-version.sh

Script para incrementar a versão do projeto seguindo [Semantic Versioning](https://semver.org/).

### Versionamento Semântico

```
MAJOR.MINOR.PATCH

1.0.0 -> 1.0.1  (patch - correção de bugs)
1.0.1 -> 1.1.0  (minor - nova funcionalidade)
1.1.0 -> 2.0.0  (major - mudança incompatível)
```

### Uso

```bash
# Incrementar PATCH (1.0.0 -> 1.0.1) - correções de bugs
./scripts/bump-version.sh patch

# Incrementar MINOR (1.0.1 -> 1.1.0) - nova funcionalidade
./scripts/bump-version.sh minor

# Incrementar MAJOR (1.1.0 -> 2.0.0) - breaking changes
./scripts/bump-version.sh major

# Sem argumentos = patch (padrão)
./scripts/bump-version.sh
```

### O que o script faz

1. ✅ Lê a versão atual do arquivo `VERSION`
2. ✅ Incrementa conforme o tipo (patch/minor/major)
3. ✅ Atualiza `VERSION`
4. ✅ Atualiza `app.version` em `gateway/app/main.py` — é o que `GET /api/metadata` devolve
5. ✅ Atualiza `info.version` em `docs/openapi.yaml`
6. ✅ Abre a seção da versão no `CHANGELOG.md`, logo abaixo de `[Não lançado]`
7. ✅ Mostra próximos passos

Cada substituição é conferida depois de aplicada: se um padrão não casar, o
script **falha** em vez de deixar um arquivo para trás na versão antiga.

> **O cliente pip não é tocado.** O repositório abriga dois artefatos com
> versionamentos **independentes** ([separacao-3-produtos.md](../docs/development/separacao-3-produtos.md)):
> o serviço (`VERSION` / `app.version`) e o SDK (`cobranca_api.__version__`).
> Sincronizar os dois criaria release falsa de um SDK que não mudou — por isso
> o cliente se versiona à mão, no ritmo do PyPI.

### Exemplo Completo

```bash
# 1. Fazer alterações no código
vim gateway/app/providers/sicoob.py

# 2. Executar testes
cd gateway && PYTHONPATH=. pytest

# 3. Incrementar versão (patch para bugfix)
./scripts/bump-version.sh patch

# 4. Editar CHANGELOG.md e descrever as mudanças
vim CHANGELOG.md

# 5. Commit
git add VERSION CHANGELOG.md gateway/app/main.py docs/openapi.yaml
git commit --author="Maxwell da Silva Oliveira <maxwbh@gmail.com>" -m "[RELEASE] Versão 1.0.1"

# 6. Criar tag — só depois do merge em main
git tag -a v1.0.1 -m "Versão 1.0.1"

# 7. Push com tags
git push origin main --tags
```

### Quando usar cada tipo de versão

#### PATCH (1.0.0 -> 1.0.1)
- ✅ Correção de bugs
- ✅ Pequenas melhorias
- ✅ Atualizações de documentação
- ✅ Refatorações internas
- ✅ Correções de segurança

Exemplo:
```bash
# Corrigiu bug no Sicoob
./scripts/bump-version.sh patch
```

#### MINOR (1.0.0 -> 1.1.0)
- ✅ Nova funcionalidade (compatível)
- ✅ Novo banco suportado
- ✅ Novo endpoint na API
- ✅ Melhorias significativas

Exemplo:
```bash
# Adicionou suporte para Banrisul
./scripts/bump-version.sh minor
```

#### MAJOR (1.0.0 -> 2.0.0)
- ✅ Breaking changes
- ✅ Mudança na estrutura da API
- ✅ Remoção de endpoints
- ✅ Mudança obrigatória de campos

Exemplo:
```bash
# Removeu campos deprecated
./scripts/bump-version.sh major
```

### Integração com CI/CD

Para automatizar versionamento em pipelines:

```bash
# No seu pipeline (GitHub Actions, etc.)
- name: Bump version
  run: |
    chmod +x scripts/bump-version.sh
    ./scripts/bump-version.sh patch

- name: Commit version
  run: |
    git config user.name "Maxwell da Silva Oliveira"
    git config user.email "maxwbh@gmail.com"
    git add VERSION CHANGELOG.md
    git commit -m "[AUTO] Bump version"
    git push
```

## 🔧 Manutenção

### Adicionar novo script

1. Crie o script em `scripts/`
2. Torne executável: `chmod +x scripts/seu-script.sh`
3. Documente neste README
4. Commit com mensagem descritiva

### Boas práticas para scripts

- ✅ Use `set -e` para parar em erros
- ✅ Adicione comentários explicativos
- ✅ Use cores para output (`echo -e "${GREEN}✅ Sucesso${NC}"`)
- ✅ Valide inputs e arquivos necessários
- ✅ Forneça mensagens de erro claras
- ✅ Documente uso e exemplos

---

**Versão:** 1.5.0
**Última atualização:** 2026-06-17

## `benchmark_lote.py` — tempo de resposta do lote offline

Mede a emissão em lote pelo caminho **offline** (não usa credencial: a engine
roda in-process e não fala com banco).

```bash
python scripts/benchmark_lote.py --tamanhos 10 50 100 150 200 --repeticoes 3
python scripts/benchmark_lote.py --tamanhos 300 500 --fatiar 200   # acima do limite
python scripts/benchmark_lote.py --base-url http://localhost:8000 --json saida.json
```

Compara os dois caminhos no mesmo volume:

| Caminho | Endpoint | Para quê |
|---|---|---|
| síncrono | `POST /api/boleto/multi` | um PDF com o lote inteiro |
| assíncrono | `POST /jobs/boletos` | `202` + `job_id`, artefatos, webhook |
| fatiado | `multi` em pedaços | volume **acima** do limite |

### Referência medida (HML, Sicoob, free tier)

| n | síncrono | ms/boleto |
|--:|--:|--:|
| 10 | 1,02s | 101,9 |
| 50 | 3,31s | 66,2 |
| 100 | 6,69s | 66,9 |
| 150 | 9,28s | 61,9 |
| 200 | 13,71s | 68,6 |

Custo por boleto estável em **~62–69 ms** de 50 a 200 — escala linear. Os
~102 ms em `n=10` são o overhead fixo por requisição (~0,4s) diluído em poucos
itens, não lentidão da engine.

> **Teto de 200 itens.** `LOTE_MAX_ITENS` e `JOB_MAX_ITENS` valem 200 nos
> **dois** caminhos: acima disso, ambos respondem **413**. Fatiar não piora o
> custo por boleto (66,8 vs 68,6 ms em 300), ou seja, o limite não protege
> tempo — protege **memória**, porque o PDF do lote é montado em RAM. Ao
> aumentá-lo, acompanhe consumo de memória, não latência.

> **O assíncrono não é mais rápido**: os jobs rodam em `BackgroundTasks` no
> mesmo processo, com a mesma engine. O que ele entrega é resposta em ~0,4s em
> vez de segurar a conexão, estado consultável e artefatos assinados.

### Local (Python 3.12) × HML — o que cada número mede

| n | local sync | HML sync | local job | HML job |
|--:|--:|--:|--:|--:|
| 10 | 0,11s | 1,02s | 0,20s | 2,25s |
| 50 | 0,50s | 3,31s | 0,89s | 5,15s |
| 100 | 0,97s | 6,69s | 1,60s | 6,53s |
| 150 | 1,44s | 9,28s | 2,62s | 10,94s |
| 200 | 1,97s | 13,71s | 3,38s | 15,90s |

**~9,8 ms/boleto local contra ~65 ms no HML** — a engine é ~6,6× mais rápida do
que o número de HML sugere. A diferença é infraestrutura (free tier de 512 MB +
rede), não a engine.

Localmente o **job fica ~1,7× mais lento** que o síncrono, e isso é real: ele
grava um PDF por item, o zip e o manifesto com `sha256` (medido: 1.050 arquivos
/ 13 MB para 500 boletos). No HML esse custo some no ruído da infra.

> Ao medir o job, o `--poll-intervalo` **quantiza** o resultado: com o default de
> 1s, um job de 1,2s mede 2s. Use `--poll-intervalo 0.05` em ambiente local.

### Memória e o limite de 200

Com `LOTE_MAX_ITENS=1000` local, **500 boletos num lote só levam ~5s** e o RSS do
processo vai de 78 MB para 127 MB — ou seja, ~50 MB de pico para 500 itens.
Cabe folgado nos 512 MB do free tier; o limite de 200 é conservador.

Mas há um motivo melhor para não elevá-lo sem pensar: o header
`X-Boletos-Info` cresce ~300 B por item e, acima de ~215 boletos, estoura o
limite de header do `http.client` — o cliente perde **até o PDF**. O serviço
agora trunca e sinaliza (`X-Boletos-Info-Truncado`), mas atrás de nginx (8 KB)
ou ALB (16 KB) o teto é bem menor: ajuste `HEADER_JSON_MAX_BYTES`.
