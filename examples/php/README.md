# Exemplos PHP

Os **mesmos três scripts** de [`examples/python`](../python/), em PHP puro:
sem Composer, sem framework, sem extensão além de `json` — só
`file_get_contents` com contexto HTTP, que existe em qualquer PHP ≥ 7.4.
Nenhum SDK: o que está aqui serve de ponto de partida para o seu consumidor.

> PHP é a linguagem mais difundida entre as empresas do Mercosul que cobram
> no Brasil — por isso o espelho existe. Um guarda no CI cobra que cada script
> PHP chame **as mesmas rotas** que o seu par em Python: se um dos dois mudar
> de rota, o outro tem de acompanhar.

## 📋 Pré-requisitos

### 1. Subir a API

```bash
docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest   # http://localhost:8000
```

### 2. Verificar se está no ar

```bash
curl http://localhost:8000/api/health
# {"status":"OK","timestamp":"..."}
```

### 3. Apontar os scripts

Os três leem a variável `API`, e caem em `http://localhost:8000` sem ela:

```bash
API=https://meu-host php generate_boleto.php
```

## 🚀 Exemplos disponíveis

| Script | O que faz | Saída |
|---|---|---|
| `generate_boleto.php` | **Comece por aqui.** Uma cobrança em `POST /cobranca` + o PDF pela engine, com a conferência da linha digitável | `examples/test_output/boleto.pdf` |
| `generate_test_boletos.php` | 12 boletos de C6 e Sicoob (6 comuns e 6 com QR Pix) via `GET /api/boleto`, para conferência visual | PDFs em `examples/test_output/` |
| `generate_remessa.php` | Arquivo de remessa CNAB via `POST /api/remessa`, com upload de JSON em multipart | `.rem` de remessa |

```bash
php examples/php/generate_boleto.php
php examples/php/generate_test_boletos.php
php examples/php/generate_remessa.php
```

Os três **saem com código ≠ 0 quando alguma chamada falha** e imprimem o corpo
do erro (a API diz qual campo recusou). O de boletos vai além e confere o
**arquivo**: `200` não prova QR — os seis boletos "Pix" têm de ser maiores que
os comuns, porque o QR ocupa uns 4 KB.

## Os dois eixos: `provider` e `banco`

`provider` diz o **caminho** — `on` (API do banco) ou `off` (engine pyCobrança,
sem rede e sem convênio) — e `banco` diz a **instituição**:

```php
['provider' => 'off', 'banco' => 'itau']   // boleto pela engine, layout 341
['provider' => 'on',  'banco' => 'c6']     // registrado na API do C6
```

`provider=on` exige credencial (`POST /credenciais`) **e** o banco ligado nesta
instalação. `GET /bancos` responde as duas coisas por banco: `registrado_pronto`
e `caminho_efetivo`.

## 📚 Dados de teste e armadilhas por banco

São os mesmos do Python, e estão documentados uma vez só, no
[README dos exemplos Python](../python/README.md#-dados-de-teste-por-banco):
carteira do C6 e da Caixa, `variacao` do Sicoob, QR Pix por `chave_pix`,
limite de `instrucoes` e `template`. A referência campo a campo está em
[`docs/fields/`](../../docs/fields/).

## ⚠️ Erros frequentes

| Sintoma | Causa | O que fazer |
|---|---|---|
| `não consegui falar com http://localhost:8000` | API não está no ar | `docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest` |
| `400` com `validation_errors` | Regra do banco violada nas rotas `/api/*` | Leia a lista — ela nomeia o campo. Confira `docs/fields/` |
| `422` com `detail` | Campo que o **schema** exige faltando, ou `provider`/`banco` inválido | É o Pydantic do gateway, antes de qualquer banco |
| **`201` com `status: "erro"`** | `POST /cobranca` recusado pela regra do banco | O engano mais comum: **é 201**. Os campos recusados estão em `raw.validation_errors` |
| `allow_url_fopen` desligado | O `php.ini` do host bloqueia `file_get_contents` em URL | Ligue a diretiva, ou troque o cliente por `curl_*` — a API é a mesma |

## 📖 Próximos passos

- [Guía en español](https://maxwbh.github.io/cobranca-api/es/) — para quem cobra no Brasil a partir do Mercosul
- [Documentação da API](../../docs/api/)
- [Documentação de campos](../../docs/fields/)
- [Exemplos Python](../python/), [Oracle PL/SQL](../oracle/) e [Oracle APEX](../apex/)

## 📝 Licença

MIT License — veja [LICENSE](../../LICENSE)
