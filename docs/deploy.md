---
title: Guia de deploy
description: Imagem pronta no GHCR, o que o serviço pede do host, variáveis de ambiente, persistência e troubleshooting da Cobranca-API.
---

# Guia de deploy

> Este guia era um passo a passo do Render.com. A Cobranca-API não tem provedor
> de hospedagem próprio: é **um container**, e roda em qualquer host Docker. O
> guia passou a descrever o que o serviço **pede do host**; o Render virou um
> apêndice, ao lado de qualquer outro.

## ⚡ O que você está subindo

**Um processo.** Uvicorn servindo FastAPI, com a engine
[pyCobrança](https://github.com/Maxwbh/pyCobranca) embutida como biblioteca —
sem sidecar, sem fila, sem banco obrigatório. Requer **Python ≥ 3.12**
(exigência da engine), que já vem na imagem.

Há **um único `Dockerfile`**, sem variantes.

## 📦 Imagem pronta (o caminho curto)

Cada release publica a imagem no GHCR, em `amd64` e `arm64`. Não precisa clonar
nem buildar:

```bash
docker run -p 8000:8000 -e LOG_LEVEL=info ghcr.io/maxwbh/cobranca-api:latest
```

Em produção, **fixe a versão** — `latest` muda a cada release:

```bash
docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:3.0.0
```

Para buildar do código, `docker build -t cobranca-api .` na raiz do repositório.

## 🧩 O que o serviço pede do host

| Requisito | Valor | Por quê |
|---|---|---|
| Porta | `$PORT`, default `8000` | O container escuta a porta que a variável disser |
| Health check | `/health` | Gateway. A engine offline responde em `/api/health` |
| Memória | **512 MB** basta para os tetos default | Lote de PDF é o maior consumidor — ver [Memória](#-memória-e-os-tetos-de-lote) |
| Disco gravável | um diretório para `/app/data` | Cofre de credenciais e artefatos de job |
| Usuário | não-root (`app`), já no `Dockerfile` | — |

Qualquer host que rode um container e encaminhe uma porta serve: VPS com Docker
Compose, Kubernetes, Cloud Run, Fly.io, Render, ECS, a sua máquina.

## 🔐 Variáveis de ambiente

| Variável | Default | Para quê |
|---|---|---|
| `PORT` | `8000` | Porta que o uvicorn escuta |
| `LOG_LEVEL` | `info` | Vira o `--log-level` do uvicorn |
| `CREDENTIAL_DB_PATH` | `/app/data/credentials.db` | Cofre SQLite dos tokens `bapi_` |
| `ARTIFACT_DIR` | `/app/data/jobs` | Artefatos dos jobs em lote |
| `ARTIFACT_TTL_DIAS` | `7` | Idade máxima dos artefatos |
| `LOTE_MAX_ITENS` | `200` | Teto dos endpoints **síncronos** |
| `JOB_MAX_ITENS` | `200` | Teto dos jobs **assíncronos** |

> **`LOG_LEVEL`** aceita `critical`, `error`, `warning`, `info`, `debug` e
> `trace` — a caixa não importa, `INFO` e `info` dão no mesmo. Valor fora dessa
> lista **não derruba o serviço**: o container avisa no log e assume `info`.

As demais (credenciais de banco, webhooks, consumidores) estão no
[README do gateway](https://github.com/Maxwbh/cobranca-api/blob/main/gateway/README.md#configuração-env).

## 💾 Persistência

**`CREDENTIAL_DB_PATH` e `ARTIFACT_DIR` apontam para `/app/data` de propósito.**
O container roda como usuário `app` (não-root) e `/app` pertence ao root:
gravar direto em `/app` dá **500 no cofre de credenciais**. O `Dockerfile` cria
`/app/data` com `chown app`.

**Se o disco do host for efêmero**, `/app/data` é recriado a cada deploy: os
tokens `bapi_` e os artefatos de job **não sobrevivem**. Duas saídas:

- montar um volume persistente em `/app/data`;
- apontar `SUPABASE_DB_URL` ou `DATABASE_URL` para um Postgres — o cofre passa a
  morar lá, e só os artefatos ficam em disco.

Com disco efêmero e sem Postgres, baixe os artefatos **logo após** a conclusão
do job.

## 🧮 Memória e os tetos de lote

Os dois tetos não escalam igual, e o gargalo de cada um é diferente.

**`JOB_MAX_ITENS`** (`/jobs/boletos`, `/jobs/cnab/remessas`) é o barato de
subir: a chamada responde **202 em ~1s** e o trabalho segue em background. O
custo é memória e tempo de fundo.

**`LOTE_MAX_ITENS`** (`/api/boleto/multi` e `/api/render/carne`) segura a
conexão HTTP até o PDF ficar pronto. Medido em 512 MB compartilhados:
**200 boletos = 15,9 s** no multi (o carnê é mais rápido, 7,7 s, porque agrupa
3 por página). Dobrar põe a requisição perto de 30 s, onde proxy, balanceador
ou o próprio cliente desistem — e o servidor gasta o tempo inteiro montando um
PDF que ninguém recebe. **Acima de ~200 o caminho é o job, não um teto maior.**

Acima do teto, os dois respondem **413** em ~0,5 s, sem processar nada.

### Se estourar a memória

1. Mantenha `--workers 1` (já é o default do `CMD`)
2. Baixe `LOTE_MAX_ITENS` — lote grande de PDF é o maior consumidor
3. Prefira `/jobs/boletos` (grava em disco) a `/api/boleto/multi` (monta o PDF
   inteiro em memória)
4. Suba a memória do host

## ✅ Verificar o deploy

```bash
curl https://SEU-HOST/health        # gateway
curl https://SEU-HOST/api/health    # engine offline
# {"status":"OK","timestamp":"2026-06-17T12:00:00-03:00"}
```

As duas têm de responder na mesma URL. A documentação interativa fica em
`/docs` (gateway) e `/api/docs` (offline).

## 🌐 O hostname não é fixo — e não está cravado em lugar nenhum

Provedor de hospedagem costuma derivar o hostname do nome do serviço, e ele
muda quando o serviço é renomeado, recriado ou apontado para domínio próprio.
Por isso **a URL não está escrita em nada que quebre em silêncio**. Onde ela é
necessária, sai de configuração:

| Onde | Como definir |
|---|---|
| Regressão contra banco | `COB_BASE_URL` no shell de quem roda. **Não roda no Actions** — ver `postman/README.md`. |
| Keepalive (Actions) | Variável de repo `KEEPALIVE_URLS` (lista separada por espaço) |
| Coleção Postman | `base_url` do environment, ou `COB_BASE_URL` via `--env-var` |
| `scripts/benchmark_lote.py` | `COB_BASE_URL`, ou `--base-url`. Padrão: `http://localhost:8000` |
| Swagger UI (`docs/openapi.yaml`) | Variável de servidor `base_url`, editável na própria página |
| Oracle PL/SQL | `cobranca_api.g_base_url` + o host no ACL (`acl_setup.sql`) |
| Oracle APEX | Application Item `G_COBRANCA_API_URL` |

Nos exemplos e guias, `https://SEU-HOST` é **placeholder** — troque pelo
hostname da sua instalação. **Não há instância pública para apontar:** o
produto é self-hosted, e em desenvolvimento o endereço é `http://localhost:8000`.

## ✅ Checklist

- [ ] Imagem fixada numa versão (não `latest`) em produção
- [ ] `/health` e `/api/health` respondendo
- [ ] `/app/data` gravável — volume persistente, ou Postgres para o cofre
- [ ] Memória compatível com `LOTE_MAX_ITENS`
- [ ] `WEBHOOK_TOKEN__<BANCO>` definido, se for receber webhook de banco

---

## 📎 Apêndice — Render.com

O repositório traz um `render.yaml` (Blueprint) porque o projeto já foi
hospedado lá. **Ele não é o deploy de referência**: o `autoDeploy` está
desligado, e merge na `main` não publica nada em lugar nenhum.

Para usar mesmo assim: Dashboard → **New +** → **Web Service** → conecte o
repositório → Environment **Docker** → Health Check Path **`/health`**.

**Plano gratuito:** 512 MB de RAM, CPU compartilhada, e **sleep após 15 minutos
de inatividade** — a primeira requisição leva 30-60 s para acordar e as
seguintes podem responder `429` ou `503` durante o wake-up (ver
[troubleshooting](api/troubleshooting.md#http-429--too-many-requests-cold-start)).
Para testes isso é aceitável; para produção, não.

O disco do free tier é **efêmero** — vale tudo o que está em
[Persistência](#-persistência).

**Serviço herdado da v1 (Ruby)** pode ter, no painel, variáveis que hoje não
fazem nada — o container é uvicorn, não Puma: `PUMA_WORKERS`,
`PUMA_MAX_THREADS`, `PUMA_MIN_THREADS`, `RACK_ENV`,
`RUBY_GC_HEAP_GROWTH_FACTOR`. Pode apagar todas. `MALLOC_ARENA_MAX` **não**
entra nessa lista: é do glibc, vale para qualquer processo (Python incluído) e
ajuda a segurar o RSS. Confira também o `PORT`: serviço herdado costuma estar
em `9292`, a porta do antigo Banking Core Ruby.

---

**Desenvolvido por Maxwell da Silva Oliveira — M&S do Brasil Ltda**
