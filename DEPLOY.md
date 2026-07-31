# Guia de Deploy - Render Free Tier

> Como fazer deploy do **serviço único** (FastAPI + engine offline (pyCobrança) embutido) no
> Render.com usando o plano gratuito.

## ⚡ Serviço único (arquitetura atual)

O deploy usa **`Dockerfile`**: **um único processo** (Uvicorn) na porta pública
(`$PORT`, injetada pelo Render), com a engine [pyCobrança](https://github.com/Maxwbh/pyCobranca)
embutida como biblioteca. **Requer Python ≥ 3.12** (exigência da engine).
Health check: **`/health`**. Validação: `/health` e `/api/health` respondendo na
mesma URL.

Campos no painel (serviço criado manualmente):
- **Dockerfile Path:** `./Dockerfile` (o padrão — pode deixar vazio)
- **Health Check Path:** `/health`

Há **um único Dockerfile**: o serviço é um processo só (FastAPI + engine
pyCobrança embutida). Não existem variantes.

O restante deste guia segue valendo (o `render.yaml` do repo já traz essa
configuração para deploys via Blueprint).

## 🚀 Deploy Rápido (1-Click)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

**OU** siga o passo a passo abaixo:

---

## 📋 Pré-requisitos

1. Conta no [Render.com](https://render.com) (gratuita)
2. Repositório no GitHub com este código
3. 5 minutos do seu tempo ⏱️

---

## 🔧 Passo a Passo

### 1. Preparar Repositório

Certifique-se de que seu repositório tem:
- ✅ `Dockerfile` (serviço único — já incluído)
- ✅ `render.yaml` (já incluído)
- ✅ `gateway/requirements.txt` (já incluído)

```bash
# Verificar arquivos
ls Dockerfile render.yaml gateway/requirements.txt

# Se estiver tudo ok, fazer push
git add .
git commit -m "Deploy para Render"
git push origin main
```

### 2. Criar Serviço no Render

1. Acesse [dashboard.render.com](https://dashboard.render.com)
2. Clique em **"New +"** → **"Web Service"**
3. Conecte seu repositório GitHub
4. Configure:

```yaml
Name: boleto-cnab-api
Environment: Docker
Region: Oregon (ou Frankfurt/Singapore)
Plan: Free
```

5. Clique em **"Create Web Service"**

### 3. Aguardar Deploy

O Render irá:
1. ✅ Clonar o repositório
2. ✅ Ler o `render.yaml`
3. ✅ Fazer build do `Dockerfile`
4. ✅ Executar a aplicação
5. ✅ Fornecer URL pública

**Tempo estimado:** 3-5 minutos

---

## ✅ Verificar Deploy

Após o deploy, você terá uma URL derivada do nome do serviço:

```
https://<nome-do-servico>.onrender.com
```

**Testar:**

```bash
# Health check
curl https://SEU-SERVICO.onrender.com/api/health

# Deve retornar:
{"status":"OK","timestamp":"2026-06-17T12:00:00-03:00"}
```

---

## 🔧 Configurações do Free Tier

### Recursos Incluídos (Grátis)

| Recurso | Limite |
|---------|--------|
| RAM | 512 MB |
| CPU | Compartilhado |
| Build Time | 500 minutos/mês |
| Bandwidth | 100 GB/mês |
| Deploy | Ilimitados |

### ⚠️ Importante: Sleep Mode

**O plano gratuito entra em "sleep" após 15 minutos de inatividade.**

**Comportamento:**
- ✅ Primeira requisição: ~30-60s (wake-up)
- ✅ Próximas requisições: Normal (~200-500ms)
- ✅ Após 15min sem uso: Sleep novamente

**Soluções:**

1. **Aceitar o comportamento** (recomendado para testes)
2. **Usar ping service** (ex: UptimeRobot, cron-job.org)
3. **Upgrade para plano pago** ($7/mês - sem sleep)

---

## 🔄 Deploy Automático

O `render.yaml` já está configurado com `autoDeploy: true`.

**Isso significa:**
- ✅ Push para `main` → Deploy automático
- ✅ Pull Request merged → Deploy automático
- ✅ Não precisa fazer nada manual

**Desabilitar auto-deploy:**

```yaml
# render.yaml
autoDeploy: false
```

---

## 🌍 Regiões Disponíveis

Escolha a região mais próxima dos seus usuários:

| Região | Localização | Latência Brasil |
|--------|-------------|-----------------|
| `oregon` | EUA (Oeste) | ~200ms |
| `ohio` | EUA (Leste) | ~150ms |
| `frankfurt` | Alemanha | ~250ms |
| `singapore` | Singapura | ~350ms |

**Alterar região:** Edite `render.yaml` e faça commit.

---

## 📊 Monitoramento

### Logs em Tempo Real

```bash
# Via Dashboard
Dashboard → Seu Service → Logs (tab)

# Via CLI (opcional)
render logs -f
```

### Métricas

O Render fornece automaticamente:
- ✅ CPU usage
- ✅ Memory usage
- ✅ Request count
- ✅ Response times

**Acesso:** Dashboard → Seu Service → Metrics

---

## 🔐 Variáveis de Ambiente

### Já Configuradas no `render.yaml`:

```yaml
- PORT=8000
- LOG_LEVEL=info
- CREDENTIAL_DB_PATH=/app/data/credentials.db   # cofre SQLite (dir gravável)
- ARTIFACT_DIR=/app/data/jobs                   # artefatos dos jobs em lote
- ARTIFACT_TTL_DIAS=7
- LOTE_MAX_ITENS=200                            # teto dos endpoints síncronos
- JOB_MAX_ITENS=200                             # teto dos jobs assíncronos
```

> **Os dois tetos de lote não escalam igual.** Trocar de plano é editar a
> variável no painel — sem deploy —, mas o gargalo de cada uma é diferente.
>
> **`JOB_MAX_ITENS`** (`/jobs/boletos`, `/jobs/cnab/remessas`) é o barato de
> subir: a chamada responde **202 em ~1s** e o trabalho segue em background. O
> custo é memória e tempo de fundo.
>
> **`LOTE_MAX_ITENS`** (`/api/boleto/multi` e `/api/render/carne`) segura a
> conexão HTTP até o PDF ficar pronto. Medido no free tier: **200 boletos =
> 15,9s** no multi (o carnê é mais rápido, 7,7s, porque agrupa 3 por página).
> Dobrar põe a requisição perto de 30s, onde proxy, balanceador ou o próprio
> cliente desistem — e o servidor gasta o tempo inteiro montando um PDF que
> ninguém recebe. **Acima de ~200 o caminho é o job, não um teto maior.**
>
> Acima do teto os dois respondem **413** em ~0,5s, sem processar nada.

> **`CREDENTIAL_DB_PATH` e `ARTIFACT_DIR` apontam para `/app/data` de
> propósito.** O container roda como usuário `app` (não-root) e `/app` pertence
> ao root: gravar direto em `/app` dá **500 no cofre de credenciais**. O
> `Dockerfile` cria `/app/data` com `chown app`.
>
> **Disco efêmero no free tier:** `/app/data` é recriado a cada deploy. Os
> tokens `bapi_` e os artefatos de job **não sobrevivem** a um redeploy — baixe
> os artefatos logo após a conclusão do job. Para persistir o cofre, aponte
> `SUPABASE_DB_URL`/`DATABASE_URL` para um Postgres.

> **`LOG_LEVEL`** vira o `--log-level` do uvicorn. Valores aceitos:
> `critical`, `error`, `warning`, `info` (default), `debug`, `trace` — a caixa
> não importa, `INFO` e `info` dão no mesmo. Valor fora dessa lista **não
> derruba o serviço**: o container avisa no log e assume `info`.

### Sobras de configuração da v1 (Ruby)

Serviço que existe desde antes da 2.0.0 pode ter, no painel, variáveis do
runtime Ruby que **não fazem mais nada** — o container hoje é uvicorn, não
Puma:

| Variável | Era de |
|---|---|
| `PUMA_WORKERS`, `PUMA_MAX_THREADS`, `PUMA_MIN_THREADS` | Puma, o servidor web do Ruby |
| `RACK_ENV` | Rack |
| `RUBY_GC_HEAP_GROWTH_FACTOR` | GC do Ruby |

Pode apagar todas. `MALLOC_ARENA_MAX` **não** entra nessa lista: é do glibc,
vale para qualquer processo (inclusive Python) e ajuda a segurar o RSS nos
512 MB do free tier.

Confira também o `PORT`: um serviço herdado da v1 costuma estar em `9292`,
a porta do antigo Banking Core Ruby. Qualquer porta funciona — o Render roteia
para a que o processo escuta — mas `8000` é o que este blueprint declara.

### Adicionar Novas:

**Via Dashboard:**
1. Service → Environment
2. Add Environment Variable
3. Key: `MINHA_VAR`
4. Value: `meu_valor`
5. Save Changes (faz redeploy)

**Via render.yaml:**

```yaml
envVars:
  - key: MINHA_VAR
    value: meu_valor
```

---

## 🐛 Troubleshooting

### Deploy Falhou

```bash
# Ver logs completos
Dashboard → Deploy Logs

# Causas comuns:
1. Dockerfile com erro
2. Dependências faltando
3. Gem incompatível
```

### Serviço Lento

```bash
# Verificar se está em sleep
curl https://SEU-SERVICO.onrender.com/api/health

# Primeira requisição ~30-60s = Normal (wake-up)
# Se sempre lento, verificar:
- Logs de erro
- Memory usage (dashboard)
```

### Out of Memory (OOM)

```bash
# Free tier: 512MB RAM
# Se estourar, otimize:

1. Reduzir a concorrência do uvicorn (`--workers 1`, que já é o default do CMD)
2. Baixar LOTE_MAX_ITENS (default 200) — vale para /api/boleto/multi E para
   /api/render/carne; lote grande de PDF é o maior consumidor
3. Preferir /jobs/boletos (assíncrono, grava em disco) a /api/boleto/multi
   (monta o PDF inteiro em memória)
4. Considerar upgrade para Starter ($7/mês, 2GB RAM)
```

---

## 💰 Upgrade para Plano Pago

### Starter Plan ($7/mês)

**Benefícios:**
- ✅ **2GB RAM** (4x mais)
- ✅ **Sem sleep mode** (sempre ativo)
- ✅ Mais CPU
- ✅ Deploy mais rápido

**Quando fazer upgrade:**
- Produção real
- Requisitos de SLA
- Tráfego constante
- Performance crítica

**Como fazer:**
```
Dashboard → Service → Settings → Plan → Starter
```

---

## 📚 Documentação Oficial

- [Render Docs](https://render.com/docs)
- [Docker Deploys](https://render.com/docs/docker)
- [render.yaml Reference](https://render.com/docs/yaml-spec)

---

## 🌐 A URL do Render não é fixa

O Render deriva o hostname do **nome do serviço**: `<nome>.onrender.com`. Ela
muda quando você renomeia o serviço, quando o recria (blueprint novo, conta
nova) e quando aponta um domínio próprio. Não há garantia de estabilidade — o
`render.yaml` deste repositório declara `name: cobranca-api`, e a instância de
demonstração citada no README responde por outro nome, criado antes de o projeto
ser renomeado.

Por isso **a URL não está cravada em lugar nenhum que quebre em silêncio**. Onde
ela é necessária, sai de configuração:

| Onde | Como definir |
|---|---|
| Regressão HML (Actions) | Variável de repo `HML_BASE_URL`, ou `base_url` no dispatch. Sem ela, o job falha explicando. |
| Keepalive (Actions) | Variável de repo `KEEPALIVE_URLS` (lista separada por espaço) |
| Coleção Postman | `base_url` do environment, ou `COB_BASE_URL` via `--env-var` |
| `scripts/benchmark_lote.py` | `COB_BASE_URL`, ou `--base-url`. Padrão: `http://localhost:8000` |
| Swagger UI (`docs/openapi.yaml`) | Variável de servidor `base_url`, editável na própria página |
| Oracle PL/SQL | `cobranca_api.g_base_url` + o host no ACL (`acl_setup.sql`) |
| Oracle APEX | Application Item `G_COBRANCA_API_URL` |

Nos exemplos e guias, `https://SEU-SERVICO.onrender.com` é **placeholder** —
troque pelo hostname que o Render mostrar no topo do seu serviço.

---

## 🔗 URLs Úteis

Após deploy, você terá:

```bash
# URL pública
https://SEU-SERVICO.onrender.com

# Endpoints
https://SEU-SERVICO.onrender.com/api/health
https://SEU-SERVICO.onrender.com/api/boleto
https://SEU-SERVICO.onrender.com/api/boleto/data

# Dashboard
https://dashboard.render.com/web/[seu-service-id]
```

---

## ✅ Checklist de Deploy

Antes de fazer deploy, verifique:

- [ ] `Dockerfile` presente e testado localmente
- [ ] `render.yaml` com configurações corretas
- [ ] `gateway/requirements.txt` atualizado
- [ ] Código commitado e pushed para `main`
- [ ] Testes passando (`pytest gateway/tests`)
- [ ] Health check funcionando (`/health` — gateway; `/api/health` — engine offline)

**Pronto!** Agora é só criar o service no Render! 🚀

---

**Desenvolvido por Maxwell da Silva Oliveira - M&S do Brasil Ltda**
