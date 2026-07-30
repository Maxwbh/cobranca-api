# syntax=docker/dockerfile:1

# ============================================================
# Cobranca-API — serviço único 100% Python
# FastAPI (gateway multi-banco) + pyCobranca (engine offline, in-process).
# A conexão com o Banking Core BrCobrança (Ruby) foi DESCONTINUADA.
# ============================================================
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Cobranca-API"
LABEL org.opencontainers.image.description="Cobrança multi-banco (C6/Sicoob) + engine pyCobranca — 100% Python"
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

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
 && mkdir -p /app/data/jobs && chown -R app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
