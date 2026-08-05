# Separação de produtos — decisão de topologia

> Documento autoritativo referenciado por `docs/ARCHITECTURE.md` e
> `gateway/README.md`.

São **três produtos separados, cada um com sua versão**, e este repositório
abriga **um** deles. Saber qual é qual desfaz a colisão de nomes que existia até
a v1.5.0.

## Os produtos

| # | Produto | Onde vive | Papel | Versão |
|---|---|---|---|---|
| 1 | **PyCobrança** (engine) | [repositório próprio](https://github.com/Maxwbh/pyCobranca) | **Renderização e formato**: boleto PDF, carnê 3 vias, remessa/retorno CNAB 240/400, PIX-QR — 18 bancos, offline | própria; a versão em uso aparece em `GET /api/metadata` |
| 2 | **Cobranca-API** (Python/FastAPI) | **este repositório**, em `gateway/` | O **serviço**: gateway online (C6, Sicoob), cofre de credenciais multi-tenant, jobs em lote, webhooks — e a superfície offline `/api/*`, servida **in-process** | `app.version` (ver `VERSION`) |
| 3 | **Consumidor da API** | fora deste repositório | Quem chama o serviço por HTTP: SDK, app, job, PL/SQL — qualquer linguagem | própria |

> Nem a engine nem o consumidor vivem aqui. A engine é uma dependência Python
> comum, declarada em `gateway/requirements.txt`; o consumidor está do outro
> lado da seta, atrás do contrato HTTP. Este repositório versiona **só o
> serviço** — a tag `vX.Y.Z` daqui não fala pelos outros dois.

O que fica aqui do lado do consumidor é **documentação de contrato**, não
produto: a spec OpenAPI (`docs/openapi.yaml`), a coleção Postman e os scripts de
`examples/` — todos exercitam a API por HTTP, sem SDK próprio.

## Regras da separação

1. **"Cobranca-API" designa a plataforma; o serviço FastAPI é a porta única.**
   Não há segundo processo, segundo runtime nem sidecar.
2. **Versionamento independente**: o serviço versiona em `app.version`; a engine
   versiona no repositório dela; o consumidor versiona no dele. Nenhum release
   acopla os três — a versão da engine em uso aparece em `GET /api/metadata`.
3. **Fluxo de dependência** (uma direção só):
   `consumidores → Cobranca-API → engine`. A engine não conhece o serviço, e o
   serviço não conhece o consumidor — por isso nenhum dos dois mora aqui.
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
