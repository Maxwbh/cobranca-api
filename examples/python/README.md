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
| `generate_test_boletos.py` | 12 boletos de C6 e Sicoob (padrão e PIX) via `GET /api/boleto`, para conferência visual | PDFs em `examples/test_output/` |
| `generate_remessa.py` | Arquivo de remessa CNAB via `POST /api/remessa`, com upload de JSON | `.txt` de remessa |
| `generate_boleto.py` | Smoke de container: constrói a imagem, sobe, chama `POST /api/boleto/multi` e derruba | nenhuma — checa status 2xx |

```bash
python examples/python/generate_test_boletos.py
python examples/python/generate_remessa.py
```

> `generate_boleto.py` roda `docker build`/`docker run`/`docker rm` — precisa de
> Docker e da porta 8000 livre, e não deve ser apontado para um ambiente que
> você não queira derrubar.

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
