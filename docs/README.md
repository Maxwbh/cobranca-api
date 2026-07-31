# Documentação — Cobranca-API

> **Versão:** 2.1.0 — plataforma **100% Python** (engine [pyCobrança](https://github.com/Maxwbh/pyCobranca))

Documentação técnica da **Cobranca-API** — plataforma REST de cobrança bancária: gateway para as APIs dos bancos, emissão de boletos, CNAB (remessa/retorno), Pix e parsing de extratos OFX.

## Início Rápido

- [README do projeto](../README.md) — Overview, quick start, exemplos
- [DEPLOY.md](../DEPLOY.md) — Guia de deploy no Render.com
- [CHANGELOG.md](../CHANGELOG.md) — Histórico de versões
- [CONTRIBUTING.md](../CONTRIBUTING.md) — Como contribuir

## Referência da API

### Documentação Interativa (servida pela própria API)

- **`GET /api/docs`** — Swagger UI navegável (recomendado para exploração)
- **`GET /api/openapi.json`** — Spec OpenAPI 3.0 em JSON (Postman/Insomnia/SDK)
- **`GET /api/openapi.yaml`** — Spec OpenAPI 3.0 em YAML

### Documentação Estática

| Recurso | Descrição |
|---------|-----------|
| [openapi.yaml](./openapi.yaml) | Especificação OpenAPI 3.0 da superfície offline (`/api/*`) |
| [api/gateway-python.md](./api/gateway-python.md) | **Referência do gateway Python** — credenciais/token, cobrança, Pix, conciliação, webhooks |
| [api/troubleshooting.md](./api/troubleshooting.md) | Solução de problemas comuns |
| [api/ofx-parsing.md](./api/ofx-parsing.md) | Guia detalhado do endpoint OFX |
| [api/pix.md](./api/pix.md) | Guia de PIX híbrido em boletos |
| [api/encargos.md](./api/encargos.md) | **Multa, juros, desconto, IOF, abatimento** no CNAB — trio código/valor/data e matriz por banco |
| [api/validacao-campos.md](./api/validacao-campos.md) | **Validação por banco** — tipos/tamanhos/formatos de agência, conta, convênio, carteira, nosso nº e especiais; contrato de erro em lista |

### Endpoints

| Endpoint | Método | Retorno |
|----------|--------|---------|
| `/api/health` | GET | `{"status": "OK"}` |
| `/api/info` | GET | Versao, bancos, formatos |
| `/api/metadata` | GET | Versao API + gem, lista de endpoints |
| `/api/bancos` | GET | 18 bancos com capacidades (boleto, CNAB, PIX, carteiras) |
| `/api/boleto/validate` | GET | `{"valid": true}` ou erros |
| `/api/boleto/data` | GET | JSON com `nosso_numero`, `nosso_numero_formatado`, `nosso_numero_dv`, `codigo_barras`, `linha_digitavel` |
| `/api/boleto/nosso_numero` | GET | Apenas campos do nosso_numero |
| `/api/boleto` | GET | PDF + headers `X-Nosso-Numero*`. Com `include_data=true`: JSON + base64 |
| `/api/boleto/multi` | POST | PDF multi + headers `X-Boletos-Info`. Com `include_data=true`: JSON + base64 |
| `/api/remessa` | POST | Arquivo CNAB 240/400 |
| `/api/retorno` | POST | JSON com pagamentos parseados |
| `/api/ofx/parse` | POST | JSON com transacoes do extrato OFX |
| `/api/render/boleto` | POST | Corpo JSON → dados + PDF base64 (engine p/ o gateway) |
| `/api/render/carne` | POST | Corpo JSON → carnê 3-vias A4 em PDF base64 |
| `/api/render/fatura` | POST | Corpo JSON → fatura (itens/blocos) + boleto em PDF base64 |
| `/api/render/remessa` | POST | Corpo JSON → conteúdo CNAB |

### Campos de nosso_numero retornados

Todos os endpoints de boleto retornam **3 campos** (nunca `nosso_numero_boleto`):

| Campo | Descricao | Exemplo (BB) |
|-------|-----------|:-------------|
| `nosso_numero` | Valor padronizado | `"000000123"` |
| `nosso_numero_formatado` | Impresso no boleto | `"01234567000000123"` |
| `nosso_numero_dv` | Digito verificador | `"9"` |

## Arquitetura

> **Topologia (serviço único, 100% Python):** uma URL, duas superfícies — REST do
> gateway na raiz (`/cobranca`, `/pix`, …; Swagger em `/docs`) e offline em `/api/*`
> (Swagger em `/api/docs`), servida **nativamente** pela engine
> [pyCobrança](https://github.com/Maxwbh/pyCobranca). Detalhes:
> [roadmap-migracao-servico-unico.md](./development/roadmap-migracao-servico-unico.md).

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Estrutura modular, services, middleware, fluxos
- [development/brcobranca-fork.md](./development/brcobranca-fork.md) — BrCobrança (Ruby): engine offline **descontinuada** na 2.0.0
- [development/roadmap-providers.md](./development/roadmap-providers.md) — **Roadmap** de providers (bancos e PSP)
- [development/plano-jobs-lote.md](./development/plano-jobs-lote.md) — Processamento em **lote/assíncrono** (contrato pyCobrança doc 12)
- Integrações REST: [c6-rest.md](./development/c6-rest.md) · [sicoob-rest.md](./development/sicoob-rest.md) · planejados: [inter](./development/inter-rest.md) · [banco-do-brasil](./development/banco-do-brasil-rest.md) · [mercado-pago](./development/mercado-pago-rest.md)

## Guia de Campos por Banco

- [fields/README.md](./fields/README.md) — Overview dos campos
- [fields/nosso-numero.md](./fields/nosso-numero.md) — Nosso numero: entrada, saida, conciliacao
- [fields/all-banks.md](./fields/all-banks.md) — Compatibilidade e exemplos por banco

## Cliente Python

- [python-client/README.md](../python-client/README.md) — Cliente Python oficial

## Exemplos por linguagem

- [examples/oracle/](../examples/oracle/) — **PL/SQL**: pacote `COBRANCA_API`, ACL/wallet, boleto, CNAB e lote
- [examples/apex/](../examples/apex/) — **Oracle APEX**: emissão, download de PDF, lote com progresso
- [examples/python/](../examples/python/) — Python (scripts executáveis)
- [examples/python/](../examples/python/) — Exemplos executáveis

## Recursos Externos

- [pyCobrança](https://github.com/Maxwbh/pyCobranca) — Engine de cobrança em Python puro (boleto, CNAB, PIX)
- [ofxparse](https://github.com/jseutter/ofxparse) — Parsing de extratos OFX em Python
- [OpenAPI 3.0 Specification](https://spec.openapis.org/oas/v3.0.3)

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) - M&S do Brasil LTDA
