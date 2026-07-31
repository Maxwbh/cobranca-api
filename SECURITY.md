# Política de Segurança

## 🔒 Versões Suportadas

Mantemos ativamente as seguintes versões:

| Versão | Suportada | Observação |
| ------ | --------- | ---------- |
| 2.1.x  | ✅ Sim    | Atual (recomendada) — serviço único, 100% Python |
| 2.0.x  | ⚠️ Só correções críticas | Migre para a 2.1.x: mesma arquitetura, sem quebra de contrato |
| 1.x    | ❌ Não    | Descontinuada: dependia do Banking Core BrCobrança (Ruby), que não existe mais |

> A linha 1.x **não recebe correções**, nem críticas: a arquitetura em que ela
> se baseava (dois runtimes + sidecar Ruby) foi removida na 2.0.0. Não há
> backport possível — migre para a 2.0.x.
>
> **A migração não quebra contrato:** paths, campos e headers `X-*` da 1.5.0
> continuam valendo. A única mudança é o formato de saída do boleto — a engine
> emite **PDF**; `jpg`/`png`/`tif` respondem **400**.

## 🐛 Reportando uma Vulnerabilidade

A segurança do Cobranca-API é levada muito a sério. Se você descobrir uma vulnerabilidade de segurança, por favor:

### ⚠️ NÃO abra uma issue pública

Vulnerabilidades de segurança devem ser reportadas de forma privada.

### ✅ Processo de Reporte

1. **Envie um e-mail para:** maxwbh@gmail.com
   - Assunto: `[SECURITY] Vulnerabilidade em Cobranca-API`

2. **Inclua as seguintes informações:**
   - Tipo de vulnerabilidade (ex: SQL injection, XSS, etc.)
   - Localização do código afetado (arquivo e linha)
   - Passos para reproduzir
   - Impacto potencial
   - Possível correção (se souber)
   - Sua informação de contato

3. **Exemplo de reporte:**
   ```
   Assunto: [SECURITY] Vulnerabilidade na Cobranca-API

   Tipo: Path Traversal
   Localização: gateway/app/core/artifacts.py:120
   Versão afetada: 2.1.0

   Descrição:
   O parâmetro 'arquivo' não é validado antes de compor o caminho
   do artefato, permitindo ler arquivos fora de ARTIFACT_DIR.

   Reprodução:
   1. POST /api/boleto
   2. nosso_numero="; rm -rf /"
   3. Comando malicioso é executado

   Impacto:
   Execução arbitrária de código no servidor

   Possível correção:
   Sanitizar o parâmetro antes de usar
   ```

### 📅 Tempo de Resposta

- **Confirmação inicial:** Dentro de 48 horas
- **Análise da vulnerabilidade:** Dentro de 7 dias
- **Correção e patch:** Varia conforme criticidade
  - Crítico: < 7 dias
  - Alto: < 14 dias
  - Médio: < 30 dias
  - Baixo: < 60 dias

### 🔐 Processo de Correção

1. Confirmaremos o recebimento do seu reporte
2. Investigaremos e validaremos a vulnerabilidade
3. Desenvolveremos uma correção
4. Lançaremos um patch de segurança
5. Publicaremos um security advisory (se crítico)
6. Creditaremos você na correção (se desejar)

## 🛡️ Práticas de Segurança

### Para Usuários da API

**Proteção de Dados Sensíveis:**
- ❌ Nunca commite arquivos `.env` com credenciais
- ❌ Nunca logue dados completos de boletos em produção
- ✅ Use variáveis de ambiente para configurações sensíveis
- ✅ Implemente rate limiting no seu proxy/gateway
- ✅ Use HTTPS em produção

**Validação de Dados:**
```python
# ✅ BOM: Validar entrada do usuário
def gerar_boleto(dados):
    if not validar_cpf(dados['sacado_documento']):
        raise ValueError("CPF inválido")
    # ...

# ❌ RUIM: Confiar cegamente em dados do usuário
def gerar_boleto(dados):
    # usar dados diretamente sem validação
```

**Deploy Seguro:**
- ✅ Use Docker com imagem base oficial e atualizada
- ✅ Execute a aplicação com usuário não-root
- ✅ Limite recursos (CPU, memória)
- ✅ Configure firewall apropriadamente
- ❌ Não exponha porta do container diretamente

### Para Desenvolvedores

**Evite Vulnerabilidades Comuns:**

1. **SQL Injection** — o cofre usa SQLite/Postgres via query parametrizada
   (`core/credential_store.py`, `core/job_store.py`). Nunca componha SQL com
   f-string.

2. **Path Traversal** — artefatos de job são endereçados por `job_id` +
   nome de arquivo vindos do cliente:
   ```python
   # ❌ RUIM: compor o caminho direto com a entrada
   return open(os.path.join(ARTIFACT_DIR, job_id, nome), "rb")

   # ✅ BOM: normalizar o nome, resolver e confirmar que ficou DENTRO do job
   alvo = (dir_job(job_id) / _slug(nome)).resolve()
   try:
       alvo.relative_to(dir_job(job_id).resolve())
   except ValueError:
       return None                      # fora do diretório do job
   return alvo if alvo.is_file() else None
   ```
   É exatamente o que `caminho_artefato()` e `caminho_arquivo_cnab()` fazem em
   `core/artifacts.py`. Repare nos dois cuidados: `_slug()` normaliza o nome
   **e** o `resolve()` acontece antes da comparação — sem isso, `..` escaparia.

3. **Segredo em log ou disco** — credencial de banco vinda no request
   (`credentials`, `X-Bank-Credentials`) vive **só em memória**:
   ```python
   # ❌ RUIM: registrar o corpo inteiro
   logger.info("request: %s", body)

   # ✅ BOM: nunca logar credencial nem token bapi_
   logger.info("cobranca tenant=%s provider=%s", body.tenant_id, body.provider)
   ```

4. **Vazamento de erro do upstream** — o erro do banco é traduzido
   (424/409/422), sem devolver stack trace:
   ```python
   # ❌ RUIM: repassar a exceção crua
   raise HTTPException(500, detail=str(exc))

   # ✅ BOM: status semântico + corpo do upstream controlado
   return JSONResponse(424, {"detail": "credenciais do banco rejeitadas",
                             "upstream": {"status": r.status_code}})
   ```

5. **XSS** — não aplicável (API REST sem frontend), exceto pelo Swagger
   servido em `/docs` e `/api/docs`, que é HTML estático próprio.

6. **DoS** — lote é limitado por `LOTE_MAX_ITENS` (default 200 → **413**);
   acima disso, use `/jobs/boletos` (assíncrono, grava em disco em vez de
   montar tudo em memória).

## 📋 Dependências

### Auditoria de Dependências

Verificamos regularmente dependências com:

```bash
pip-audit -r gateway/requirements.txt
pip-audit -r gateway/requirements-dev.txt
```

### Atualização de Dependências

- Dependências críticas: Atualizadas imediatamente
- Dependências de segurança: Dentro de 7 dias
- Dependências menores: Revisão mensal

### Dependências Conhecidas

**Serviço** (`gateway/requirements.txt`):
- `fastapi` / `uvicorn` — API e servidor ASGI
- [`pycobranca`](https://pypi.org/project/pycobranca/) — engine offline (boleto, CNAB 240/400, PIX, OFX) — exige Python >= 3.12
- `httpx` — cliente HTTP para as APIs dos bancos (OAuth + mTLS)
- `cryptography` — AES-256-GCM e HKDF do cofre de credenciais
- `pypdf` — concatenação de PDFs em lote

## 🔍 Auditoria de Segurança

Este projeto:
- ✅ Não armazena dados de cartão de crédito
- ✅ Não movimenta dinheiro: **emite** cobrança (boleto/Pix) e **lê** status;
  não transfere, não liquida, não estorna
- ✅ Roda como usuário não-root no container (`USER app`)
- ✅ Imagem `python:3.12-slim`, processo único, sem sidecar

**Superfície que EXIGE atenção** (não é um serviço stateless):

- ⚠️ **É stateful por necessidade.** A conciliação por polling precisa das
  credenciais sem um request na frente, então o serviço **guarda credencial de
  banco** — cofre cifrado (`core/vault.py`, `core/credential_store.py`).
- ⚠️ **Persiste em banco de dados**: cofre e estado de jobs em SQLite
  (`CREDENTIAL_DB_PATH`) ou Postgres (`DATABASE_URL`).
- ⚠️ **Grava arquivos em disco**: artefatos de job (PDF, `.rem`, zip) em
  `ARTIFACT_DIR`, com `sha256` e expiração.
- ⚠️ **Fala com APIs externas dos bancos** com certificado mTLS e OAuth.
- ⚠️ **Recebe webhooks** dos bancos e **envia** eventos assinados (HMAC-SHA256)
  para o consumidor.

O material sensível é protegido assim: o token `bapi_` é devolvido **uma única
vez** e a chave AES-256-GCM é derivada dele por HKDF — o servidor guarda o
material cifrado e **não consegue decifrar sozinho**. O AAD amarra
tenant+provider, então token de um banco em rota de outro é rejeitado (403).

## 📚 Recursos de Segurança

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [Docker Security Best Practices](https://docs.docker.com/develop/security-best-practices/)
- [CWE - Common Weakness Enumeration](https://cwe.mitre.org/)

## 🏆 Hall of Fame

Agradecemos aos seguintes pesquisadores de segurança que reportaram vulnerabilidades responsavelmente:

*(Nenhum reporte até o momento - seja o primeiro!)*

---

**Obrigado por ajudar a manter o Cobranca-API seguro!**

Para questões gerais (não relacionadas a segurança), por favor use as [issues do GitHub](https://github.com/Maxwbh/cobranca-api/issues).
