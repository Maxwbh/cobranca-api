# Documentação — Cobranca-API

> Plataforma **100% Python** (engine [pyCobrança](https://github.com/Maxwbh/pyCobranca)).
> A versão corrente sai em `GET /openapi.json` (`info.version`) e em
> `GET /api/metadata` — que traz também a da engine —, e o histórico está no
> [CHANGELOG](https://github.com/Maxwbh/cobranca-api/releases). Repeti-la aqui só criaria mais um lugar para
> envelhecer.

Documentação técnica da **Cobranca-API** — plataforma REST de cobrança bancária: gateway para as APIs dos bancos, emissão de boletos, CNAB (remessa/retorno), Pix e parsing de extratos OFX.

## Início Rápido

- [README do projeto](https://github.com/Maxwbh/cobranca-api) — Overview, quick start, exemplos
- [Guia de deploy](deploy.md) — imagem no GHCR, Render, variáveis de ambiente
- [CHANGELOG.md](https://github.com/Maxwbh/cobranca-api/releases) — Histórico de versões
- [CONTRIBUTING.md](https://github.com/Maxwbh/cobranca-api/blob/main/CONTRIBUTING.md) — Como contribuir

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
| [api/online-vs-offline.md](./api/online-vs-offline.md) | **Boleto online × offline** — C6 e Sicoob lado a lado, com documentos reais dos sandboxes |
| [api/gateway-python.md#códigos-de-erro-comuns](./api/gateway-python.md) | **Erros** — o que a API responde quando o banco recusa, e o que fazer com cada faixa |
| [api/troubleshooting.md](./api/troubleshooting.md) | Solução de problemas comuns |
| [api/ofx-parsing.md](./api/ofx-parsing.md) | Guia detalhado do endpoint OFX |
| [api/pix.md](./api/pix.md) | Guia de PIX híbrido em boletos |
| [api/encargos.md](./api/encargos.md) | **Multa, juros, desconto, IOF, abatimento** no CNAB — trio código/valor/data e matriz por banco |
| [api/validacao-campos.md](./api/validacao-campos.md) | **Validação por banco** — tipos/tamanhos/formatos de agência, conta, convênio, carteira, nosso nº e especiais; contrato de erro em lista |

## Serviços disponíveis

Uma URL, **duas superfícies**. A da raiz fala com a API do banco; a de `/api/*`
gera o documento localmente, sem banco e sem credencial.

### Online — gateway REST (raiz) · [Swagger publicado](swagger/) · `/docs` no serviço

| Serviço | Rotas | O que faz | Providers |
|---|---|---|---|
| **Credenciais** | `POST/DELETE /credenciais` | Tokenização `bapi_` — a credencial do banco não trafega a cada chamada | todos |
| **Catálogo** | `GET /bancos` | Capacidades e esquema de credencial **por introspecção** | todos |
| **Cobrança** | `POST/GET/PUT/DELETE /cobranca`, `GET /cobranca/{id}/pdf` | Boleto registrado: emitir, consultar, alterar, PDF, baixar | C6, Sicoob, Inter · **alterar só no C6** |
| **Pix** | `/pix/*` | Cob imediata, cobv, lote, revisão, recebidos, devoluções | C6, Sicoob, Inter |
| **Pix Automático** | `/pix-automatico/*` | Recorrência, autorização do pagador, cobrança do ciclo | C6, Sicoob, Inter |
| **Bolepix** | `/bolepix/*` | Boleto híbrido com QR Pix embutido | C6 |
| **Checkout** | `POST/GET/DELETE /checkout` | **Link de pagamento com cartão** (crédito/débito, parcelado) + Pix no mesmo link | C6 |
| **Extrato** | `GET /extrato` | Movimentações da conta PJ | C6, Sicoob, Inter |
| **Conciliação** | `GET /conciliacao/recebiveis\|transacoes` | Recebíveis e transações da adquirência | C6 |
| **Carnê** | `POST /carne` | Carnê 3 vias A4 | — |
| **Jobs** | `/jobs/*` | Lote assíncrono: boletos e remessas CNAB, com artefatos e webhook | — |
| **Webhooks** | `/config/webhook-*`, `/webhooks/*` | Cadastro da URL no banco e recepção das notificações, com repasse assinado | C6, Inter · Pix por chave em todos |

> A coluna acima é reprodução. A **fonte** é `GET /bancos`, que introspecta as
> classes de provider — pedir ao banco o que ele não oferece responde `422`
> dizendo para onde ir, não `500`. Criar (`POST /cobranca`, `/carne`, `/pix`,
> `/checkout`) responde **`201` com `Location`**; `PUT /pix/lote/{id}` responde
> **`202`**, porque o banco enfileira o lote em vez de criá-lo.

> **Cartão não passa por aqui.** O `/checkout` opera em **modo link**: o pagador
> digita o cartão na página do banco, e `save_card` e checkout transparente não
> existem no schema — corpo com esses campos responde `422` e não chega ao banco.

### Offline — engine pyCobrança in-process (`/api/*`) · [Swagger publicado](swagger/offline.html) · `/api/docs` no serviço

Boleto, CNAB e OFX **sem chamar banco**: 18 instituições, sem credencial, sem
rede. É o caminho para quem registra por arquivo em vez de por API.

### Endpoints da superfície offline

| Endpoint | Método | Retorno |
|----------|--------|---------|
| `/api/health` | GET | `{"status": "OK"}` |
| `/api/info` | GET | Versao, bancos, formatos |
| `/api/metadata` | GET | Versão da API + da engine pyCobrança, lista de endpoints |
| `/api/bancos` | GET | 19 bancos com capacidades (boleto, CNAB, PIX, carteiras) |
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
> [pyCobrança](https://github.com/Maxwbh/pyCobranca).

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Estrutura modular, services, middleware, fluxos
- [development/roadmap-providers.md](development/roadmap-providers.md) — **Roadmap online**: próximos providers REST (bancos e PSP)
- [development/plano-jobs-lote.md](development/plano-jobs-lote.md) — Processamento em **lote/assíncrono** (contrato pyCobrança doc 12)
- [development/servicos-online-por-banco.md](development/servicos-online-por-banco.md) — **Serviços online dos 19 bancos**: quem tem API de boleto registrado e de Pix, um a um
- [development/pix-automatico.md](development/pix-automatico.md) — **Pix Automático por banco**: o que está validado, e o que a evidência prova
- [development/open-finance.md](development/open-finance.md) — **Open Finance**: o que os bancos publicam no diretório e o que a entrada custaria
- Homologação: [homologacao/](./homologacao/README.md) — roteiro v3.0 do C6 preenchido com evidência real do sandbox, mais as execuções de Sicoob e Inter e o que cada uma prova
- Integrações REST **implementadas**: [c6-rest.md](development/c6-rest.md) · [sicoob-rest.md](development/sicoob-rest.md) · [inter-rest.md](development/inter-rest.md)
- Integrações REST **planejadas**: [banco-do-brasil](development/banco-do-brasil-rest.md) · [btg](development/btg-rest.md) · [mercado-pago](development/mercado-pago-rest.md)

## Guia de Campos por Banco

- [fields/README.md](./fields/README.md) — Overview dos campos
- [fields/nosso-numero.md](./fields/nosso-numero.md) — Nosso numero: entrada, saida, conciliacao
- [fields/all-banks.md](./fields/all-banks.md) — Compatibilidade e exemplos por banco

## Exemplos por linguagem

- [examples/oracle/](https://github.com/Maxwbh/cobranca-api/tree/main/examples/oracle) — **PL/SQL**: pacote `COBRANCA_API`, ACL/wallet, boleto, CNAB, lote e checkout de cartão
- [examples/apex/](https://github.com/Maxwbh/cobranca-api/tree/main/examples/apex) — **Oracle APEX**: emissão, download de PDF, lote com progresso, checkout com cartão
- [examples/python/](https://github.com/Maxwbh/cobranca-api/tree/main/examples/python) — Python (scripts executáveis)

## Recursos Externos

- [pyCobrança](https://github.com/Maxwbh/pyCobranca) — Engine de cobrança em Python puro (boleto, CNAB, PIX)
- [ofxparse](https://github.com/jseutter/ofxparse) — Parsing de extratos OFX em Python
- [OpenAPI 3.0 Specification](https://spec.openapis.org/oas/v3.0.3)

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) - M&S do Brasil LTDA
