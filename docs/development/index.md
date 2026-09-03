---
title: Notas de engenharia
description: Roadmap de providers, guias de integração por banco e planos internos da Cobranca-API.
---

# Notas de engenharia

Estas páginas são o **como pensamos a integração** — roadmap, estudo por
instituição e planos de implementação. Não são guia de uso: quem chega para
integrar começa pela [documentação da API](../).

## Roadmap e escopo

| Página | O que traz |
|---|---|
| [Roadmap de providers](roadmap-providers.md) | Fila de bancos e PSPs, princípio de esforço e a régua de escopo (o que nunca entra) |
| [Separação em 3 produtos](separacao-3-produtos.md) | Como API, engine e integrações se dividem |
| [Plano de jobs em lote](plano-jobs-lote.md) | Desenho do processamento assíncrono |
| [Serviços online por banco](servicos-online-por-banco.md) | O que cada um dos 19 bancos do catálogo offline oferece de API online, um a um |
| [Pix Automático por banco](pix-automatico.md) | O que está validado em cada banco, e o que a evidência prova |
| [Open Finance](open-finance.md) | O que os bancos publicam no diretório, o que a entrada custaria e por que segue fora de escopo |
| [Cenário de teste (Postman/HML)](https://github.com/Maxwbh/cobranca-api/blob/main/postman/README.md) | Coleção de regressão, matriz de rastreabilidade e critérios de aceite |

## Integrados

| Banco | Página |
|---|---|
| C6 Bank (336) | [c6-rest.md](c6-rest.md) |
| Sicoob (756) | [sicoob-rest.md](sicoob-rest.md) |
| Banco Inter (077) | [inter-rest.md](inter-rest.md) |

## Planejados

| Instituição | Página |
|---|---|
| Banco do Brasil (001) | [banco-do-brasil-rest.md](banco-do-brasil-rest.md) |
| BTG Pactual (208) | [btg-rest.md](btg-rest.md) |
| Mercado Pago (PSP) | [mercado-pago-rest.md](mercado-pago-rest.md) |
| Efí (364) | [efi-rest.md](efi-rest.md) |
| Itaú Unibanco (341) | [itau-rest.md](itau-rest.md) |

Cada página segue o mesmo template: catálogo completo de serviços da
instituição, autenticação, esquema de credenciais, superfície mapeada para as
rotas desta API e o que ficou fora de escopo — com o motivo.
