# syntax=docker/dockerfile:1

# ============================================================
# Cobranca-API — serviço único 100% Python
# FastAPI (gateway multi-banco) + pyCobranca (engine offline, in-process).
# A conexão com o Banking Core BrCobrança (Ruby) foi DESCONTINUADA.
# ============================================================
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Cobranca-API"
# A descrição ficou em "(C6/Sicoob)" por dois bancos online e uma major: o
# Inter e o Itaú entraram e nada aqui cobrava o texto. Está presa ao serviço em
# `gateway/tests/test_numeros_da_doc.py`, que a compara com o catálogo que o
# `GET /bancos` publica — é a mesma regra dos outros números da vitrine.
LABEL org.opencontainers.image.description="Cobrança bancária brasileira numa API REST: 4 bancos online (C6, Sicoob, Inter, Itaú) e 19 offline por CNAB — boleto, Pix, Pix Automático e OFX, 100% Python"
LABEL org.opencontainers.image.authors="Maxwell Oliveira <maxwbh@gmail.com>"
LABEL org.opencontainers.image.url="https://github.com/Maxwbh/cobranca-api"
LABEL org.opencontainers.image.source="https://github.com/Maxwbh/cobranca-api"
LABEL org.opencontainers.image.vendor="M&S do Brasil LTDA"
LABEL org.opencontainers.image.licenses="MIT"

# `git` saiu junto com a instalacao por git+https: a engine agora vem do PyPI.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tini wget \
    && rm -rf /var/lib/apt/lists/*

ENV PORT=8000 \
    LOG_LEVEL=info \
    CREDENTIAL_DB_PATH=/app/data/credentials.db \
    ARTIFACT_DIR=/app/data/jobs \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY gateway/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY gateway/app ./app
# Spec OpenAPI da superfície offline (servida em /api/openapi.json|yaml)
COPY docs/openapi.yaml /docs/openapi.yaml
# Dicionário PT->ES do Swagger: `/openapi.json?lang=es` e `Accept-Language: es`
# o leem em runtime (core/i18n_openapi). Sem ele a imagem respondia a spec em
# português com `Content-Language: es` — e nenhum teste via, porque todos rodam
# do checkout. O `.dockerignore` já o deixa passar; aqui ele chega ao destino.
COPY docs/i18n /docs/i18n
# Renderizador do Swagger (~1,6 MB), servido em /swagger-ui. Sem ele a página
# busca CSS e JS na unpkg.com, e num deploy self-hosted sem essa saída o
# Swagger não renderiza — só o cabeçalho aparece. Ausente, a página cai na CDN.
COPY docs/swagger/vendor /swagger-ui

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
 && mkdir -p /app/data/jobs && chown -R app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]

# LOG_LEVEL vira --log-level do uvicorn. Duas defesas, porque essa variavel
# costuma vir de painel (Render, Docker Compose) e nao de arquivo revisado:
#   - caixa alta e normalizada: o uvicorn so aceita os valores em minusculas e
#     aborta em "INFO", derrubando o container no boot;
#   - valor invalido cai para "info" com aviso, em vez de virar crash-loop --
#     um typo em variavel de ambiente nao deveria tirar a API do ar.
# `exec` mantem o uvicorn como PID do processo, para o tini repassar os sinais.
CMD ["sh", "-c", "\
NIVEL=$(printf '%s' \"${LOG_LEVEL:-info}\" | tr '[:upper:]' '[:lower:]'); \
case \"$NIVEL\" in \
  critical|error|warning|info|debug|trace) ;; \
  *) echo \"[entrypoint] LOG_LEVEL='${LOG_LEVEL}' invalido (use: critical, error, warning, info, debug, trace) - assumindo 'info'\" >&2; NIVEL=info ;; \
esac; \
exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT}\" --log-level \"$NIVEL\"\
"]
