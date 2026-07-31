---
title: Cobranca-API
description: Cobrança bancária brasileira em API REST — boleto, CNAB, Pix e OFX.
---

# Cobrança bancária brasileira, em uma API REST

**Boleto · CNAB 240/400 · Pix · Pix Automático · OFX** — 18 bancos, 100% Python,
um único container. Consuma de qualquer linguagem via HTTP: Python, Java, Node,
PHP, C#, Go, Delphi, Oracle APEX ou PL/SQL.

[Swagger do Gateway](https://boleto-cnab-api.onrender.com/docs){: .btn }
[Swagger Offline](https://boleto-cnab-api.onrender.com/api/docs){: .btn }
[Código no GitHub](https://github.com/Maxwbh/cobranca-api){: .btn }

> A instância pública roda no plano gratuito do Render e hiberna após 15 minutos
> de inatividade — a **primeira** chamada pode levar até um minuto. É ambiente de
> demonstração, não de produção, e a URL **não é fixa**: o Render a deriva do nome
> do serviço. Na sua instalação, troque pelo hostname do seu.

---

## Emitir um boleto

Uma chamada devolve o PDF pronto:

```bash
curl -G https://boleto-cnab-api.onrender.com/api/boleto \
  --data-urlencode 'bank=banco_brasil' \
  --data-urlencode 'type=pdf' \
  --data-urlencode 'data={"valor":1500.00,"cedente":"Empresa LTDA","documento_cedente":"11222333000181","sacado":"Joao da Silva","sacado_documento":"52998224725","agencia":"3073","conta_corrente":"12345678","convenio":"1234567","carteira":"18","nosso_numero":"123","data_vencimento":"2027-12-31"}' \
  -o boleto.pdf
```

Trocar `type=pdf` por `/validate`, `/data` ou `/nosso_numero` devolve validação e
campos calculados sem gerar o PDF.

---

## Referência

| Guia | Para quê |
|---|---|
| [Gateway Python](api/gateway-python.md) | Credenciais, cobrança online, Pix, conciliação e webhooks |
| [Validação de campos](api/validacao-campos.md) | Regras por banco — tamanhos, carteiras, nosso número, CNPJ alfanumérico |
| [Encargos na remessa](api/encargos.md) | Multa, juros, desconto, IOF, abatimento e protesto no CNAB |
| [Pix em boletos](api/pix.md) | Bolepix — BR Code EMV e QR no boleto e na remessa |
| [Leitura de OFX](api/ofx-parsing.md) | Extrato v1/v2 e conciliação com os boletos emitidos |
| [Troubleshooting](api/troubleshooting.md) | Erros comuns e o que significam |
| [Arquitetura](ARCHITECTURE.md) | Como as peças se encaixam |

A referência completa e sempre atualizada é o **Swagger servido pela própria
API** — ele reflete o código em execução, não uma cópia que pode envelhecer.

---

## Bancos

Banco do Brasil, Bradesco, Caixa, Itaú, Santander, Sicoob, Sicredi, Banrisul,
Banestes, Banco da Amazônia, Banco do Nordeste, Banco de Brasília, C6, Inter,
Unicred, Ailos, HSBC e Safra.

A cobertura varia por recurso — boleto, CNAB 240, CNAB 400 e Pix não estão
disponíveis para todos. `GET /api/bancos` responde a matriz exata, por banco.

---

## Como rodar

```bash
git clone https://github.com/Maxwbh/cobranca-api.git
cd cobranca-api
docker build -t cobranca-api .
docker run -p 8000:8000 -e LOG_LEVEL=info cobranca-api
```

Um `Dockerfile`, um processo, sem sidecar. O
[guia de deploy](https://github.com/Maxwbh/cobranca-api/blob/main/DEPLOY.md)
cobre o Render.com e as variáveis de ambiente — inclusive os tetos de lote
(`LOTE_MAX_ITENS`, `JOB_MAX_ITENS`) e o que muda ao subir de plano.

---

Projeto sob licença MIT. A engine de cálculo e renderização é a
[pyCobrança](https://github.com/Maxwbh/pyCobranca), também open source.
