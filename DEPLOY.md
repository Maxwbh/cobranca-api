# Guia de Deploy

O guia completo — imagem pronta no GHCR, Render.com passo a passo, variáveis de
ambiente e troubleshooting — vive no site do projeto, onde é servido como
página, não como arquivo:

**➡ [maxwbh.github.io/cobranca-api/deploy](https://maxwbh.github.io/cobranca-api/deploy)**

Fonte: [`docs/deploy.md`](./docs/deploy.md). Este arquivo é só o ponteiro — o
conteúdo tem **um** lugar, para não haver duas versões divergindo.

Resumo de um minuto:

```bash
docker run -p 8000:8000 -e LOG_LEVEL=info ghcr.io/maxwbh/cobranca-api:latest
```
