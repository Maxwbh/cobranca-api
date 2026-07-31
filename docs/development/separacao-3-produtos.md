# Separação de produtos — decisão de topologia

> Documento autoritativo referenciado por `docs/ARCHITECTURE.md` e
> `gateway/README.md`.

Este repositório abriga **dois artefatos com versionamentos independentes**, e
consome um terceiro que vive fora dele. Saber qual é qual desfaz a colisão de
nomes que existia até a v1.5.0.

## Os produtos

| # | Produto | Onde vive | Papel | Versão |
|---|---|---|---|---|
| 1 | **Cobranca-API** (Python/FastAPI) | `gateway/` | O **serviço**: gateway online (C6, Sicoob), cofre de credenciais multi-tenant, jobs em lote, webhooks — e a superfície offline `/api/*`, servida **in-process** | `app.version` (2.1.0) |
| 2 | **Cliente pip** (Python) | `python-client/` | SDK para consumir a **API** por HTTP a partir de qualquer app Python | `cobranca_api.__version__` |
| 3 | **PyCobrança** (engine) | [repositório próprio](https://github.com/Maxwbh/pyCobranca) | **Renderização e formato**: boleto PDF, carnê 3 vias, remessa/retorno CNAB 240/400, PIX-QR — 18 bancos, offline | dependência em `gateway/requirements.txt` |

> A engine **não vive neste repositório**: é uma dependência Python comum,
> importada pelo serviço. Quem quiser gerar boleto direto em Python usa a
> PyCobrança sem passar por esta API.

## Regras da separação

1. **"Cobranca-API" designa a plataforma; o serviço FastAPI é a porta única.**
   Não há segundo processo, segundo runtime nem sidecar.
2. **Versionamento independente**: o serviço versiona em `app.version`; a engine
   versiona no repositório dela. Nenhum release acopla os dois — a versão da
   engine em uso aparece em `GET /api/metadata`.
3. **Fluxo de dependência** (uma direção só):
   `consumidores → Cobranca-API → engine`. A engine não conhece o serviço.
4. **Caminho registrado** (API do banco): resolvido inteiro no serviço
   (OAuth + mTLS + JSON) — o banco devolve linha digitável/PDF/QR, **sem tocar
   na engine**.
   **Caminho offline** (boleto/CNAB/carnê/OFX): `core/pycob.py` chama a engine
   **no próprio processo**, sem HTTP.
5. **Empacotamento único**: um `Dockerfile`, um processo (`uvicorn`), uma URL,
   duas superfícies — REST na raiz, offline em `/api/*`.

## Roteamento de provider (contrato)

| `provider` | Caminho |
|---|---|
| `c6` / `sicoob` | API do banco — boleto registrado, Pix dinâmico, Pix Automático, conciliação |
| `pycobranca` (ou vazio/omitido) | engine offline in-process — boleto, CNAB, carnê |

Detalhes da integração C6: [c6-rest.md](./c6-rest.md).
