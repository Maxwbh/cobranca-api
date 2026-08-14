# Exemplos Python

Scripts executáveis que chamam a **Cobrança-API por HTTP**, com `requests` ou
`urllib` da biblioteca padrão. Nenhum SDK: o que está aqui serve de ponto de
partida para escrever o seu consumidor em qualquer linguagem.

> O consumidor da API é um produto separado e não vive neste repositório — veja
> [separacao-3-produtos.md](../../docs/development/separacao-3-produtos.md).

## 📋 Pré-requisitos

### 1. Subir a API

```bash
docker compose up --build   # serviço único em http://localhost:8000
```

### 2. Verificar se está no ar

```bash
curl http://localhost:8000/api/health
# {"status":"OK","timestamp":"..."}
```

### 3. Apontar os scripts

A URL está **no topo de cada arquivo**, fixa em `http://localhost:8000`. Para
rodar contra outro ambiente, edite a constante do script
(`API_URL` / `REMESSA_URL`).

## 🚀 Exemplos disponíveis

| Script | O que faz | Saída |
|---|---|---|
| `generate_boleto.py` | **Comece por aqui.** Uma cobrança em `POST /cobranca` + o PDF pela engine, com a conferência da linha digitável | `examples/test_output/boleto.pdf` |
| `generate_test_boletos.py` | 12 boletos de C6 e Sicoob (padrão e PIX) via `GET /api/boleto`, para conferência visual | PDFs em `examples/test_output/` |
| `generate_remessa.py` | Arquivo de remessa CNAB via `POST /api/remessa`, com upload de JSON | `.rem` de remessa |

```bash
python examples/python/generate_boleto.py
python examples/python/generate_test_boletos.py
python examples/python/generate_remessa.py
```

Os três **saem com código ≠ 0 quando alguma chamada falha** e imprimem o corpo
do erro (a API diz qual campo recusou). Para apontar a outro ambiente:
`API=https://meu-host python examples/python/generate_boleto.py`.

## Os dois eixos: `provider` e `banco`

`provider` diz o **caminho** — `on` (API do banco) ou `off` (engine pyCobrança,
sem rede e sem convênio) — e `banco` diz a **instituição**:

```jsonc
{"provider": "off", "banco": "itau"}   // boleto pela engine, layout 341
{"provider": "on",  "banco": "c6"}     // registrado na API do C6
{"provider": "c6"}                     // apelido legado do anterior; sai na 3.0.0
```

`provider=on` exige credencial (`POST /credenciais`) **e** o banco ligado nesta
instalação. `GET /bancos` responde as duas coisas por banco: `registrado_pronto`
e `caminho_efetivo`. Com o banco desligado, o `on` é rebaixado para a engine —
a resposta vem `201` sem ter passado pelo banco.

## 📚 Dados de teste por banco

Os campos obrigatórios variam por banco. Os payloads prontos e validados estão
em [`postman/fixtures/sample_data.json`](../../postman/fixtures/sample_data.json)
— sete bancos, com CPF/CNPJ de DV válido, e é a mesma fonte que a coleção
Postman usa. A referência campo a campo está em
[`docs/fields/`](../../docs/fields/).

Armadilhas mais comuns:

- **Sicoob (756)** — `variacao` e `convenio` são obrigatórios; `aceite` tem de
  ser `'N'`; `linha_digitavel` pode voltar `null` em `/api/boleto/data`, mas
  aparece no PDF.
- **Caixa (104)** — `carteira` aceita só `'1'` ou `'2'`; `nosso_numero` tem 15
  dígitos.
- **C6 (336)** — `carteira` aceita só `'10'` ou `'20'`; não envie
  `digito_conta`.
- **Instruções** — `instrucoes` é uma **lista de linhas**, no máximo 7, cada
  uma com até 100 caracteres. Acima do limite a API responde 422.
- **`template`** — só `classico` ou `moderno`. Carnê **não** é template: é o
  endpoint `POST /api/render/carne`, que recebe a lista de parcelas.

## ⚠️ Erros frequentes

| Sintoma | Causa | O que fazer |
|---|---|---|
| Conexão recusada | API não está no ar | `docker compose up --build` |
| `422` com lista de campos | Campo obrigatório do banco faltando | Confira `docs/fields/` |
| `422 item_id duplicado` | Dois itens do lote com o mesmo identificador | Corrija o payload — seriam o mesmo título emitido duas vezes |
| `413` | Lote acima de `LOTE_MAX_ITENS` | Quebre o lote ou ajuste a variável de ambiente |
| Timeout no primeiro request | Free tier do Render hiberna | Repita — a primeira chamada leva ~50s |

## 📖 Próximos passos

- [Documentação da API](../../docs/api/)
- [Documentação de campos](../../docs/fields/)
- [Coleção Postman](../../postman/README.md)
- [Exemplos Oracle PL/SQL](../oracle/) e [Oracle APEX](../apex/)

## 📝 Licença

MIT License — veja [LICENSE](../../LICENSE)
