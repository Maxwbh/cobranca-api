# Contribuindo para a Cobranca-API

Obrigado por considerar contribuir com a Cobranca-API! Este documento fornece diretrizes para contribuir com o projeto.

## 📋 Índice

- [Código de Conduta](#código-de-conduta)
- [Como Contribuir](#como-contribuir)
- [Configuração do Ambiente](#configuração-do-ambiente)
- [Processo de Desenvolvimento](#processo-de-desenvolvimento)
- [Padrões de Código](#padrões-de-código)
- [Commits e Versionamento](#commits-e-versionamento)
- [Testes](#testes)
- [Documentação](#documentação)
- [Pull Requests](#pull-requests)

## 🤝 Código de Conduta

Este projeto adere ao [Código de Conduta](./CODE_OF_CONDUCT.md). Ao participar, espera-se que você mantenha este código:

- Use linguagem acolhedora e inclusiva
- Seja respeitoso com diferentes pontos de vista
- Aceite críticas construtivas com elegância
- Foque no que é melhor para a comunidade
- Mostre empatia com outros membros da comunidade

Comportamento inaceitável pode ser reportado em maxwbh@gmail.com. Vulnerabilidades
de segurança seguem o processo privado de [SECURITY.md](./SECURITY.md) — nunca uma issue pública.

## 🎯 Como Contribuir

Existem várias maneiras de contribuir:

### 1. Reportar Bugs

Encontrou um bug? Por favor:

1. Verifique se já não existe uma [issue aberta](https://github.com/Maxwbh/cobranca-api/issues)
2. Se não existir, [crie uma nova issue](https://github.com/Maxwbh/cobranca-api/issues/new)
3. Inclua:
   - Descrição clara do problema
   - Passos para reproduzir
   - Comportamento esperado vs observado
   - Versão da API (`VERSION`)
   - Logs de erro (se aplicável)
   - Banco afetado (BB, Sicoob, etc.)

**Exemplo de boa issue:**
```
Título: 500 ao gerar boleto Bradesco com carteira 09

Descrição:
Ao gerar boleto do Bradesco na carteira 09, a API responde 500
em vez de um erro de validação.

Passos para reproduzir:
1. POST /api/boleto
2. banco=bradesco, carteira=09
3. Dados: {...}

Erro:
AttributeError: 'BradescoProvider' object has no attribute 'xyz'

Versão da API: 2.1.0   (GET /api/metadata)
Engine pyCobrança: 1.0.2
Python: 3.12
Docker: Sim
```

### 2. Sugerir Melhorias

Tem uma ideia? Ótimo! Por favor:

1. Verifique se não existe uma sugestão similar
2. Crie uma issue com o label "enhancement"
3. Descreva:
   - O que você quer ver implementado
   - Por que isso seria útil
   - Exemplos de uso (se possível)

### 3. Adicionar Suporte para Novo Banco

Quer adicionar suporte para um novo banco? Siga:

O suporte a banco existe em **duas camadas** — escolha a certa:

**a) Banco OFFLINE (boleto/CNAB, sem API do banco)** — mora na engine
[pyCobrança](https://github.com/Maxwbh/pyCobranca), não neste repositório.
Contribua lá; aqui o banco aparece sozinho em `GET /api/bancos`.

**b) Banco ONLINE (API REST: cobrança registrada, Pix)** — aqui:

1. Crie `gateway/app/providers/<banco>.py` implementando `BankProvider`
   (`gateway/app/providers/base.py`). Só implemente o que o banco de fato
   oferece: `GET /bancos` reporta capacidade por **introspecção**.
2. Registre em `_PROVIDERS` (`gateway/app/registry.py`) e no enum `Provider`
   (`gateway/app/schemas.py`).
3. Se o banco usa OAuth+mTLS, reaproveite `gateway/app/clients/oauth_mtls.py`.
4. Adicione testes em `gateway/tests/test_<banco>.py` (use `respx` para
   simular o upstream — nenhum teste chama banco de verdade).
5. Documente em `docs/development/<banco>-rest.md`, seguindo a estrutura dos
   guias já existentes (inclusive o catálogo de serviços do banco).
6. Acrescente requests na coleção Postman com IDs `BC-xxx`
   (`postman/check_coverage.py` quebra o build se um endpoint ficar sem teste).

> Rota que chama método opcional **precisa checar antes** com
> `exige_capacidade()` (`gateway/app/routers/_capacidades.py`) — chamada direta
> num provider que não implementa vira `AttributeError` e 500.

### 4. Melhorar Documentação

Documentação clara é essencial! Você pode:

- Corrigir erros de ortografia/gramática
- Adicionar exemplos
- Clarificar instruções confusas
- Traduzir documentação
- Adicionar diagramas/imagens

### 5. Contribuir com Código

Quer resolver um bug ou implementar um recurso?

1. Veja a seção [Processo de Desenvolvimento](#processo-de-desenvolvimento)
2. Faça fork do repositório
3. Crie uma branch para sua feature
4. Desenvolva seguindo os [Padrões de Código](#padrões-de-código)
5. Adicione testes
6. Atualize documentação
7. Submeta um Pull Request

## 🛠️ Configuração do Ambiente

### Pré-requisitos

- **Python 3.12+** — obrigatório: a engine `pycobranca` (≥ 1.0.2) exige `>=3.12`
- Docker & Docker Compose (opcional, mas recomendado)
- Git

> Em Python < 3.12 o `pip install` falha com
> `Package 'pycobranca' requires a different Python`. Não é bug de ambiente:
> é a versão mínima da engine ([pycobranca no PyPI](https://pypi.org/project/pycobranca/)).
> O 3.12 (release estável, wheels prontos) evita a compilação a partir do
> código-fonte que ocorria em alguns interpretadores mais novos.

### Setup Local

```bash
# 1. Fork e clone o repositório
git clone https://github.com/SEU-USUARIO/cobranca-api.git
cd cobranca-api

# 2. Dependências do serviço (gateway + engine)
pip install -r gateway/requirements.txt -r gateway/requirements-dev.txt

# 3. Rodar testes
pytest gateway/tests

# 4. Subir a API localmente (as DUAS superfícies na mesma porta)
uvicorn app.main:app --app-dir gateway --reload --port 8000
#   gateway  -> http://localhost:8000/docs
#   offline  -> http://localhost:8000/api/docs
```

### Com Docker

```bash
# Build da imagem
docker-compose build

# Iniciar serviços
docker-compose up

# Rodar testes no container
docker-compose run cobranca_api pytest gateway/tests
```

## 🔄 Processo de Desenvolvimento

### 1. Criar Branch

```bash
# Atualizar main
git checkout main
git pull origin main

# Criar branch descritiva
git checkout -b feature/adicionar-banco-banrisul
# ou
git checkout -b fix/corrigir-sicoob-linha-digitavel
# ou
git checkout -b docs/melhorar-readme
```

**Convenção de nomes:**
- `feature/` - Nova funcionalidade
- `fix/` - Correção de bug
- `docs/` - Mudanças em documentação
- `test/` - Adicionar/melhorar testes
- `refactor/` - Refatoração de código
- `hml/` - Homologação: além do CI de PR, o workflow `Build` também dispara no
  push dessas branches (`hml/**`), então dá para validar antes de abrir o PR

### 2. Desenvolver

Faça suas mudanças seguindo os padrões do projeto.

### 3. Testar

```bash
# Rodar todos os testes
pytest gateway/tests

# Rodar teste específico
pytest gateway/tests/test_cobranca_offline.py

# Com verbose
pytest gateway/tests -v

# Validar as specs OpenAPI (o CI faz o mesmo)
python -c "import yaml; from openapi_spec_validator import validate; \
  validate(yaml.safe_load(open('docs/openapi.yaml')))"

# Guarda de cobertura: endpoint sem request Postman quebra o build
python postman/check_coverage.py
```

### 4. Documentar

- Atualize `docs/` se mudou API
- Atualize `README.md` se mudou setup
- Adicione exemplos em `examples/`
- Comente código complexo

### 5. Commit

Siga as [convenções de commit](#commits-e-versionamento).

## 📝 Padrões de Código

### Camadas (onde cada coisa mora)

```
routers/     HTTP: valida entrada, traduz erro, monta resposta
registry.py  escolhe o provider e resolve credenciais
providers/   um dialeto por banco
core/        cofre, jobs, artefatos, eventos, engine
```

Router não fala com banco; provider não fala com HTTP do cliente. Detalhes em
[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md).

### Python

```python
# ✅ BOM: Type hints e docstrings
def gerar_boleto(banco: str, dados: Dict[str, Any]) -> bytes:
    """
    Gera PDF do boleto.

    Args:
        banco: Código do banco (ex: 'banco_brasil')
        dados: Dicionário com dados do boleto

    Returns:
        bytes: Conteúdo do PDF

    Raises:
        BoletoValidationError: Se dados inválidos
    """
    # implementação

# ❌ RUIM: Sem type hints ou documentação
def gerar(b, d):
    # implementação
```

**Diretrizes:**
- Use type hints
- Adicione docstrings em funções públicas
- Siga PEP 8
- Use nomes descritivos
- Prefira list/dict comprehensions

### Markdown

- Use títulos hierárquicos (`#`, `##`, `###`)
- Adicione exemplos de código com syntax highlighting
- Use listas para enumerar itens
- Adicione links para documentação relacionada
- Use tabelas para comparações

## 📌 Commits e Versionamento

### Mensagens de Commit

Use o padrão **Conventional Commits** com prefixos:

```
[TIPO] Descrição curta (50 chars)

Descrição detalhada (se necessário)
- Item 1
- Item 2
```

**Tipos:**
- `[FEAT]` - Nova funcionalidade
- `[FIX]` - Correção de bug
- `[DOC]` - Mudanças em documentação
- `[TEST]` - Adicionar/modificar testes
- `[REFACTOR]` - Refatoração de código
- `[PERF]` - Melhorias de performance
- `[STYLE]` - Formatação, ponto e vírgula, etc.
- `[CHORE]` - Manutenção, deps, config
- `[RELEASE]` - Nova versão

**Exemplos:**

```bash
# ✅ BOM
git commit -m "[FEAT] Adicionar suporte para Banco Banrisul

- Implementar BanrisulProvider (gateway/app/providers/banrisul.py)
- Registrar no registry e no enum Provider
- Adicionar testes com respx
- Documentar em docs/development/banrisul-rest.md"

# ✅ BOM
git commit -m "[FIX] Corrigir linha_digitavel do Sicoob

Usar respond_to? para evitar NoMethodError quando
método não está disponível no banco."

# ❌ RUIM
git commit -m "fix bug"

# ❌ RUIM
git commit -m "mudanças"
```

### Versionamento Semântico

Use o script `bump-version.sh`:

```bash
# PATCH: Correções de bugs (1.0.0 -> 1.0.1)
./scripts/bump-version.sh patch

# MINOR: Nova funcionalidade compatível (1.0.1 -> 1.1.0)
./scripts/bump-version.sh minor

# MAJOR: Breaking changes (1.1.0 -> 2.0.0)
./scripts/bump-version.sh major
```

**Quando usar cada tipo:**

- **PATCH**: Bugfixes, correções de documentação, refatorações internas
- **MINOR**: Novo banco, novo endpoint, nova funcionalidade compatível
- **MAJOR**: Mudança na API, remoção de endpoint, mudança de campos obrigatórios

### Atribuição de Commits

**Assine com a sua própria identidade.** Configure uma vez no clone e esqueça:

```bash
git config user.name "Seu Nome"
git config user.email "seu@email.com"
git commit -m "[FEAT] Nova funcionalidade"
```

**Não use `--author` para assinar como outra pessoa.** O `git blame` é como se
descobre quem perguntar sobre um trecho meses depois; commit assinado por quem
não escreveu manda a pergunta para a pessoa errada. A BSD-3-Clause também
pressupõe autoria real — ela preserva os avisos de copyright de quem escreveu.

**Nem como assistente de IA.** Nada de `Co-Authored-By` com nome de ferramenta,
rodapé de "generated by" ou link de sessão — no autor, no committer, no corpo do
commit, no título/corpo do PR ou em comentário. O
[`guarda-ia.yml`](.github/workflows/guarda-ia.yml) recusa, e a checagem de
comentário roda fora do check suite do PR: ela avisa, mas não bloqueia sozinha.

## 🧪 Testes

### Estrutura de Testes

```
gateway/tests/               # 32 arquivos (pytest)
├── conftest.py              # fixtures: client, cobranca_payload, pfx_b64
├── test_cobranca_offline.py # caminho offline (engine in-process)
├── test_cobranca_sicoob.py  # provider REST (upstream simulado por respx)
├── test_offline_pycobranca.py
├── test_jobs_lote.py        # lote assíncrono de boletos
├── test_jobs_cnab.py        # lote de remessas CNAB
├── test_webhook_banco.py    # capacidades opcionais -> 422, nunca 500
├── test_sandbox_c6.py       # e2e contra o sandbox real — pulado sem credencial
└── ...
postman/                     # coleção de contrato contra o HML
```

> Contagens de teste e de request **não** ficam escritas aqui de propósito:
> envelhecem a cada PR e ninguém relê. Para o número do dia,
> `cd gateway && PYTHONPATH=. pytest -q` e
> `python postman/check_coverage.py`.

Nenhum teste chama banco de verdade: o upstream é simulado com `respx`.

### Escrevendo Testes

```python
# gateway/tests/test_banco_novo.py
import pytest


@pytest.fixture
def banco_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__banconovo__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__banconovo__client_secret", "sec")


def test_registra_cobranca(client, cobranca_payload, banco_env, respx_mock):
    respx_mock.post("https://api.banconovo.com.br/v1/boletos").respond(
        201, json={"id": "123", "status": "REGISTRADO"})
    r = client.post("/cobranca", json={
        "tenant_id": "empresa1", "provider": "banconovo",
        "account_config": {"agencia": "1234", "conta": "56789"},
        "cobranca": cobranca_payload,
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "registrado"

  describe 'GET /api/boleto/validate' do
    it 'valida dados corretos' do
      get '/api/boleto/validate', {
        bank: 'banco_novo',
        data: dados_validos.to_json
      }

      expect(last_response.status).to eq(200)
      body = JSON.parse(last_response.body)
      expect(body['valid']).to be true
    end

    it 'retorna erro para dados inválidos' do
      get '/api/boleto/validate', {
        bank: 'banco_novo',
        data: {}.to_json
      }

      expect(last_response.status).to eq(400)
    end
  end
end
```

### Rodando Testes

```bash
# Todos os testes
pytest gateway/tests

# Teste específico
pytest gateway/tests/test_cobranca_offline.py::test_cobranca_offline_registra_com_pycobranca

# Verbose
pytest gateway/tests -v

# Contrato contra um ambiente de verdade (HML)
./postman/run-regressao.sh --smoke
```

### Cobertura de Testes

Idealmente, novos códigos devem ter:
- ✅ Cobertura mínima de 80%
- ✅ Testes de casos felizes (happy path)
- ✅ Testes de casos de erro
- ✅ Testes de edge cases

## 📖 Documentação

### Onde Documentar

| O que                | Onde                           |
|----------------------|--------------------------------|
| API endpoints        | `docs/api/`                    |
| Campos por banco     | `docs/fields/`                 |
| Exemplos de uso      | `examples/python/`             |
| Guia de deploy       | `DEPLOY.md`                    |
| Scripts              | `scripts/README.md`            |
| README principal     | `README.md`                    |
| Changelog            | `CHANGELOG.md`                 |
| Detalhes técnicos    | `docs/development/`            |

## 🔀 Pull Requests

### Antes de Submeter

Checklist:
- [ ] Código segue os padrões do projeto
- [ ] Testes foram adicionados/atualizados
- [ ] Todos os testes passam (`pytest gateway/tests`)
- [ ] Documentação foi atualizada
- [ ] CHANGELOG.md foi atualizado (se aplicável)
- [ ] Commits seguem convenção
- [ ] Branch está atualizado com `main`

### Criando Pull Request

1. **Título descritivo:**
   ```
   [FEAT] Adicionar suporte para Banco Banrisul
   ```

2. **Descrição completa:**
   ```markdown
   ## Resumo
   Adiciona suporte completo para geração de boletos do Banco Banrisul (código 041).

   ## Mudanças
   - Implementação da classe Boleto::Banrisul
   - Testes de validação e geração
   - Documentação de campos obrigatórios
   - Exemplo Python

   ## Como testar
   1. Iniciar API
   2. Executar `python examples/python/exemplo_banrisul.py`
   3. Verificar PDF gerado

   ## Checklist
   - [x] Testes passam
   - [x] Documentação atualizada
   - [x] CHANGELOG atualizado
   - [x] Exemplo adicionado

   ## Screenshots
   [Se aplicável]

   ## Issues relacionadas
   Resolve #123
   ```

3. **Atribua labels apropriados:**
   - `enhancement` - Nova funcionalidade
   - `bug` - Correção de bug
   - `documentation` - Mudanças em docs
   - `good first issue` - Bom para iniciantes

### Revisão de Código

Ao revisar PRs:
- ✅ Seja construtivo e respeitoso
- ✅ Sugira melhorias específicas
- ✅ Teste o código localmente
- ✅ Verifique documentação
- ❌ Não seja excessivamente crítico
- ❌ Não aprove sem testar

### Merge

Mantedores irão:
1. Revisar código
2. Testar mudanças
3. Verificar documentação
4. Fazer merge usando "Squash and merge"
5. Atualizar versão (se aplicável)
6. Criar release (se nova versão)

## 🎓 Recursos Úteis

### Documentação Técnica

- [PEP 8 - Python Style Guide](https://pep8.org/)
- [FastAPI](https://fastapi.tiangolo.com/) · [pydantic v2](https://docs.pydantic.dev/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)

### Ferramentas

- [Black](https://black.readthedocs.io/) - Python formatter
- [Pytest](https://pytest.org/) - Python testing
- [respx](https://lundberg.github.io/respx/) - simula o upstream HTTP nos testes
- [newman](https://github.com/postmanlabs/newman) - roda a coleção Postman no CI

### Repositórios Relacionados

- [PyCobrança](https://github.com/Maxwbh/pyCobranca) — a engine offline desta plataforma

## 💬 Precisa de Ajuda?

- 📖 Leia a [documentação](./docs/)
- 💬 Abra uma [discussão](https://github.com/Maxwbh/cobranca-api/discussions)
- 🐛 Reporte um [bug](https://github.com/Maxwbh/cobranca-api/issues)
- 📧 Entre em contato: maxwbh@gmail.com

## 🙏 Agradecimentos

Obrigado por dedicar seu tempo para contribuir! Cada contribuição, grande ou pequena, é valiosa e apreciada.

---

**Desenvolvido por Maxwell da Silva Oliveira - M&S do Brasil Ltda**
