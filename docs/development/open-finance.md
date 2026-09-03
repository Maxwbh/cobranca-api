---
title: Open Finance — o que os bancos expõem e o que custaria consumir
description: Levantamento do Open Finance Brasil para a Cobranca-API: o que o diretório de participantes diz dos quatro bancos integrados, o que a entrada exigiria e por que o escopo segue fora.
---

# Open Finance — levantamento

Nos estudos por instituição, Open Finance aparecia sempre da mesma forma: uma
linha marcada ⛔ *fora de escopo* ([Sicoob SIC-S09](sicoob-rest.md),
[BTG BTG-S20](btg-rest.md), [Efí EF-S14](efi-rest.md)). A régua é a mesma de
sempre — o produto é **cobrança**, entrada de dinheiro; iniciação de pagamento é
saída. A conclusão continua valendo, mas ela vinha sem os números por trás.
Esta página é o levantamento que faltava.

## O que os bancos integrados expõem — medido, não presumido

Open Finance não se descobre no portal do banco. Quem publica o que cada
instituição expõe é o **Diretório de Participantes**, e ele é aberto: um JSON
sem autenticação em `https://data.directory.openbankingbrasil.org.br/participants`,
com organização, papéis, authorisation servers, famílias de API, versão,
certificação e endpoint mTLS. Execução de **18/08/2026**, 107 organizações no
diretório:

| Banco | Organização | Status | Papéis ativos | Auth. servers | Famílias publicadas |
|---|---|---|---|---|---|
| C6 (336) | BCO C6 S.A. | Active | CONTA, DADOS | 1 | 22 |
| Sicoob (756) | Confederação Nacional das Cooperativas do Sicoob | Active | CONTA, DADOS, PAGTO | 1 | 51 |
| Inter (077) | BANCO INTER | Active | CONTA, DADOS, PAGTO | 4 | 48 |
| Itaú (341) | ITAU UNIBANCO S.A. | Active | CONTA, DADOS, PAGTO | 12 | 55 |

### O lado importa, e é onde a leitura fácil erra

Nas APIs de pagamento do Open Finance quem **publica** é a detentora da conta do
**pagador**; quem **consome** é o iniciador (ITP), que debita essa conta. Então
`payments-pix-recurring-payments-automatic` publicada por um banco quer dizer
*"sou o banco do pagador e aceito débito de Pix Automático iniciado por um
ITP"* — e **não** *"ofereço ao meu cliente PJ a API de cobrança recorrente"*.

Essa segunda, a que uma API de cobrança precisa, é a `rec`/`cobr` do BACEN, na
API do próprio banco, e **não aparece no diretório**. Some-se a norma: desde
16/06/2025 o lado pagador é **obrigatório** para quem oferece conta transacional
a pagadores, e o lado recebedor é **facultativo**. Um ✅ na tabela abaixo é, em
boa parte, obrigação cumprida — não diferencial de produto, e não a porta que
esta API usaria.

E as famílias que interessariam a uma API de cobrança — **os quatro publicam
todas, nas mesmas versões**:

| Família | Versão | O que é |
|---|---|---|
| `payments-pix` | 5.0.0 | iniciação de pagamento Pix |
| `payments-consents` | 5.0.0 | consentimento de pagamento |
| `payments-pix-recurring-payments` | 2.2.0 | pagamento recorrente Pix |
| **`payments-pix-recurring-payments-automatic`** | **2.2.0** | **Pix Automático** |
| `payments-recurring-consents-automatic` | 2.2.0 | consentimento do Pix Automático |
| `enrollments` | 2.2.0 | vínculo de dispositivo (jornada sem redirecionamento) |
| `accounts` | 2.5.x | dados de conta |

Todas com certificação `Self-Certified` no diretório.

### As 19 instituições do catálogo

O roteiro cobre o catálogo inteiro, não só os quatro do caminho ON. Coluna
"Pix Aut." = publica `payments-pix-recurring-payments-automatic` (lado
pagador):

| Instituição | Pix Aut. | Instituição | Pix Aut. |
|---|:--:|---|:--:|
| Ailos | ✅ | Caixa | ✅ |
| Banco do Brasil | ✅ | Citibank | ⛔ |
| BRB | ✅ | CrediSIS | — |
| Banco do Nordeste | ✅ | HSBC | — |
| Banestes | ✅ | Itaú | ✅ |
| Banrisul | ✅ | Safra | ✅ |
| Bradesco | ✅ | Santander | ✅ |
| C6 | ✅ | Sicoob | ✅ |
| Inter | ✅ | Sicredi | ✅ |
| | | Unicred | ✅ |

**16 das 19** publicam. O Citibank consta no diretório como participante ativo e
**não** publica nenhuma família de pagamento — a operação de varejo dele no
Brasil foi vendida ao Itaú em 2017, e o que restou é banco de atacado.
**CrediSIS** não foi localizado sob a central do sistema e **HSBC** não opera
mais no Brasil (incorporado pelo Bradesco em 2016) — a engine mantém os dois
porque o layout CNAB deles ainda é pedido para boleto, o que não implica Pix
nenhum.

Ausência no diretório é resultado fraco, e está dito como tal: o endpoint
devolveu 107 organizações, e sistemas cooperativos entram pela central, não pela
singular. Presença sem a família — o caso do Citibank — é resultado forte.

Para reproduzir a tabela:

```bash
python scripts/validar_open_finance.py
python scripts/validar_open_finance.py --json > evidencia-open-finance.json
```

Nenhuma credencial é usada e nada é enviado a banco nenhum: o roteiro só lê o
diretório público.

## O que o levantamento NÃO prova

Que o banco publique a família não significa que esta API poderia consumi-la. A
distância entre as duas frases é o ponto inteiro deste documento.

As APIs de Open Finance **não** se consomem com `client_id` + `client_secret` +
certificado tirados do portal do banco — que é o modelo desta API, o de um
**cliente do banco**, um par de credenciais por instituição. Consumir Open
Finance é entrar no ecossistema como participante:

- **papel habilitado no diretório** — `DADOS` para receber dados compartilhados,
  ou iniciador de transação de pagamento (ITP) para iniciar pagamento;
- **autorização do Banco Central** para o papel de ITP, com capital mínimo de
  R$ 1.000.000,00 (Resolução BCB nº 80/2021), estrutura de compliance e PLD-FT;
- **certificados da ICP do Open Finance** — BRCAC para transporte, BRSEAL para
  assinatura de payload — e não o certificado que o banco emite para o cliente
  dele;
- **FAPI-BR (FAPI 1.0 Advanced com os adendos brasileiros)**: `private_key_jwt`,
  PAR, e desde 2026 a jornada sem redirecionamento (JSR) obrigatória para
  iniciadores;
- **DCR/DCM** — registro dinâmico de cliente em cada detentora, em vez de
  credencial cadastrada à mão;
- **certificação de conformidade** funcional e de segurança publicada no
  diretório antes de ir a produção.

Nada disso é opcional nem contornável por integração: sem o registro no
diretório, o `client_id` sequer existe do lado do banco.

## Veredito de escopo

**Segue fora**, e agora com o custo medido em vez de estimado. Três leituras:

1. **Iniciação de pagamento (ITP)** — continua fora pela régua de sempre: quem
   inicia move dinheiro para fora da conta, e esta API é de cobrança. Some-se o
   capital mínimo e a autorização do BCB: é outra empresa, não outra rota.
2. **Compartilhamento de dados (`accounts`, `resources`)** — serviria à
   conciliação, mas exige o papel `DADOS` e a mesma pilha FAPI-BR/DCR. Para o
   que a conciliação precisa hoje, extrato e recebíveis já vêm pela API do
   próprio banco, com a credencial que o cliente já tem.
3. **Pix Automático pelo Open Finance** — parece a porta para os bancos que não
   têm a API de cobrança recorrente, e **não é**: o que os 16 publicam é o lado
   do pagador, consumido por um ITP que debita a conta dele. Usar isso é ser
   iniciador, ou seja, o item 1 outra vez. O que uma API de cobrança precisa é a
   `rec`/`cobr` do BACEN na API do banco do recebedor — e essa não passa pelo
   diretório nem pela pilha FAPI-BR.

**Se um dia entrar**, o desenho previsível é por **parceiro regulado**: as
instituições autorizadas podem contratar terceiros não autorizados para o
compartilhamento, e existe mercado de Open Finance como serviço. O provider
seria do parceiro, não dos bancos — e aí o modelo de credencial desta API volta
a servir, porque o parceiro é quem emite `client_id`/`client_secret`. Isso não
está planejado: está registrado para não ser redescoberto.

## Fontes

- Diretório de Participantes (produção): `https://data.directory.openbankingbrasil.org.br/participants`
- [Guia de Certificação de Conformidade — Open Finance Brasil](https://openfinancebrasil.atlassian.net/wiki/spaces/OF/pages/155910145)
- Resolução BCB nº 80/2021 (autorização e capital mínimo de instituição de pagamento)
