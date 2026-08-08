---
title: Cobranca-API
description: Cobrança bancária brasileira em API REST — boleto, CNAB, Pix, cartão e OFX.
---

# Cobrança bancária brasileira, em uma API REST

**Boleto · CNAB 240/400 · Pix · Cartão · Pix Automático · OFX** — 19 bancos
tratados (**3 online**: C6, Sicoob e Inter · **18 offline** pela engine),
100% Python, um único container. Consuma de qualquer linguagem via HTTP: Python, Java, Node,
PHP, C#, Go, Delphi, Oracle APEX ou PL/SQL.

**Dois mundos, um contrato.** *Online*: boleto registrado, Pix, Pix Automático e
link de pagamento com cartão nas APIs dos bancos (OAuth2 + mTLS). *Offline*:
boleto em PDF, CNAB e carnê pela engine embutida — sem rede, sem convênio, sem
sidecar. É o mesmo `POST /cobranca`: trocar de mundo é trocar um campo.

[Swagger do Gateway](https://cobranca-api-sq67.onrender.com/docs){: .btn }
[Swagger Offline](https://cobranca-api-sq67.onrender.com/api/docs){: .btn }
[Código no GitHub](https://github.com/Maxwbh/cobranca-api){: .btn }

> A instância pública roda no plano gratuito do Render e hiberna após 15 minutos
> de inatividade — a **primeira** chamada pode levar até um minuto. É ambiente de
> demonstração, não de produção, e a URL **não é fixa**: o Render a deriva do nome
> do serviço. Na sua instalação, troque pelo hostname do seu.

---

## Emitir um boleto

Uma chamada devolve o PDF pronto:

```bash
curl -G https://cobranca-api-sq67.onrender.com/api/boleto \
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

**Online (API do banco):** C6 (336), Sicoob (756) e Banco Inter (077).

**Offline (engine embutida):** os grandes emissores de boleto por arquivo —
Banco do Brasil, Bradesco, Caixa, Itaú, Santander, Sicoob, Sicredi, Banrisul,
C6 e as cooperativas, entre outros.

As duas listas **não se sobrepõem por acaso**, e o Inter mostra por quê: ele
fala online e **não** tem layout offline, então `provider=inter` sem credencial
responde `424` em vez de cair na engine — cair emitiria um boleto registrado no
banco errado.

A cobertura varia por recurso — boleto, CNAB 240, CNAB 400 e Pix não estão
disponíveis para todos. Em vez de repetir a lista aqui, consulte a fonte:
`GET /api/bancos` responde a matriz offline e `GET /bancos` a online, ambas por
introspecção do código.

---

## Como rodar

Imagem pronta, publicada a cada release no GitHub Container Registry — sem
clonar e sem buildar:

```bash
docker run -p 8000:8000 -e LOG_LEVEL=info ghcr.io/maxwbh/cobranca-api:latest
```

Em produção, fixe a versão (`ghcr.io/maxwbh/cobranca-api:2.1.0`) em vez de
`latest`. Para mexer no código, o caminho é o clone:

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

## Quem faz

Desenvolvido por **[Maxwell da Silva Oliveira](https://www.linkedin.com/in/maxwbh)**
([GitHub](https://github.com/Maxwbh) · [maxwbh@gmail.com](mailto:maxwbh@gmail.com)),
da **[M&S do Brasil LTDA](https://msbrasil.inf.br)** — consultoria e
desenvolvimento em integração bancária, Oracle APEX e Python.

Precisa de ajuda para integrar a Cobranca-API ao seu ERP, Oracle APEX ou
sistema legado? [Fale com a gente](https://msbrasil.inf.br).
