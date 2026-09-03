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

Os três leem a variável `API`, e caem em `http://localhost:8000` sem ela:

```bash
API=https://meu-host python generate_boleto.py
```

## 🚀 Exemplos disponíveis

| Script | O que faz | Saída |
|---|---|---|
| `generate_boleto.py` | **Comece por aqui.** Uma cobrança em `POST /cobranca` + o PDF pela engine, com a conferência da linha digitável | `examples/test_output/boleto.pdf` |
| `generate_test_boletos.py` | 12 boletos de C6 e Sicoob (6 comuns e 6 com QR Pix) via `GET /api/boleto`, para conferência visual | PDFs em `examples/test_output/` |
| `generate_remessa.py` | Arquivo de remessa CNAB via `POST /api/remessa`, com upload de JSON | `.rem` de remessa |

```bash
python examples/python/generate_boleto.py
python examples/python/generate_test_boletos.py
python examples/python/generate_remessa.py
```

Os três **saem com código ≠ 0 quando alguma chamada falha** e imprimem o corpo
do erro (a API diz qual campo recusou). O de boletos vai além e confere o
**arquivo**: `200` não prova QR, e os seis boletos "Pix" já saíram por meses
byte a byte do tamanho dos comuns, sem QR e sem aviso.

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

Armadilhas mais comuns — cada uma medida contra a engine, não lembrada:

- **Caixa (104)** — `carteira` é `'14'` ou `'24'` (a página dizia `'1'`/`'2'`,
  que a engine nunca aceitou); `convenio` tem **no máximo 6** dígitos e
  `nosso_numero` no máximo 15.
- **C6 (336)** — `carteira` é `'10'` ou `'20'`. `digito_conta` **não dá erro,
  mas também não muda nada**: no boleto e na remessa o arquivo sai idêntico com
  ou sem ele.
- **Sicoob (756)** — `convenio` e `carteira` bastam; `variacao` é opcional e
  `aceite` não é fixo em `'N'`. `/api/boleto/data` devolve `linha_digitavel`
  preenchida.
- **QR Pix no boleto** — quem desenha é `chave_pix` + `tipo_chave_pix` (a engine
  monta o EMV). `emv` e `pix_label` são da era Ruby e **respondem 400**; antes
  eram descartados em silêncio, e o boleto saía sem QR. Banco sem suporte a Pix
  recusa a chave em vez de imprimir um boleto pela metade.
- **Instruções** — `instrucoes` é uma **lista de linhas**, no máximo 7, cada
  uma com até 100 caracteres. Acima do limite a API responde **400** com a linha
  e o tamanho.
- **`template`** — `classico` ou `moderno` em `GET /api/boleto`; em
  `POST /api/boleto/multi` vale também `carne` (3 vias por A4). Valor
  desconhecido é 400 nos dois.

## ⚠️ Erros frequentes

| Sintoma | Causa | O que fazer |
|---|---|---|
| Conexão recusada | API não está no ar | `docker compose up --build` |
| `400` com `validation_errors` | Regra do banco violada nas rotas `/api/*` | Leia a lista — ela nomeia o campo. Confira `docs/fields/` |
| `422` com `detail` | Campo que o **schema** exige faltando, ou `provider`/`banco` inválido | É o Pydantic do gateway, antes de qualquer banco |
| **`201` com `status: "erro"`** | `POST /cobranca` recusado pela regra do banco | O engano mais comum: **é 201**. Os campos recusados estão em `raw.validation_errors` |
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
