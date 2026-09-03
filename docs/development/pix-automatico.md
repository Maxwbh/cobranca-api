---
title: Pix Automático — estado por banco
description: O que cada banco integrado faz com o Pix Automático (BACEN), o que a evidência prova e como revalidar.
---

# Pix Automático — o que está validado, por banco

O dialeto do Pix Automático é **padronizado pelo BACEN**: `rec`, `solicrec`,
`locrec`, `cobr`, `webhookrec` e `webhookcobr` são os mesmos em todo PSP, e esta
API os implementa uma vez só, em `app/providers/bacen_pix.py`
(`BacenPixAutomaticoMixin`). Para um banco novo, Pix Automático custa o prefixo
da base e a autenticação — nada além disso.

Só que **dialeto implementado não é funcionalidade validada**. O banco pode não
herdar o mixin, não ter o produto habilitado na conta, ou responder `2xx` com
uma página de bloqueio. Esta página separa as três coisas.

## Estado por banco

| Banco | Capacidade no `GET /bancos` | Validado contra o banco | O que a evidência prova |
|---|---|---|---|
| **C6 (336)** | `pix_automatico` | ✅ **sim** — 14 casos em 2xx, Jornadas 1 a 4 | Integração ponta a ponta: `idRec` real, `locrec` com QR, `solicrec` chegando a `ENVIADA`, gestão e cancelamento |
| **Sicoob (756)** | `pix_automatico` | ⚠️ **não** — o sandbox devolveu HTML de WAF | Nada. Veja *"o 201 que não era"* abaixo |
| **Inter (077)** | `pix_automatico` | ⛔ **não perguntado** | O dialeto está pronto (mixin herdado), mas a superfície não consta no SDK oficial do banco — o caso entrou como ausente, não como falha |
| **Itaú (341)** | *ausente* | — | O provider não herda o mixin: as rotas respondem **422** dizendo quem oferece |

Evidência crua: [`docs/homologacao/evidencia-sandbox-c6.json`](../homologacao/evidencia-sandbox-c6.json)
(casos `PA_01_01` a `PA_04_04`) e
[`evidencia-sandbox-sicoob.json`](../homologacao/evidencia-sandbox-sicoob.json) (`PA_01`, `PA_02`).

## E os outros 15 bancos do catálogo?

Nenhum. Não por limitação de banco: **o caminho `off` não tem Pix**. A engine
pyCobrança emite boleto e CNAB — não fala com PSP nenhum, e não haveria com quem
criar uma recorrência. Pix Automático só existe no caminho `on`, e só existe
provider REST para quatro bancos.

Como **instituição**, quase todos oferecem — e isso não ajuda enquanto não
houver provider. Medido no Diretório de Participantes do Open Finance
(`scripts/validar_open_finance.py`), **16 das 19** publicam
`payments-pix-recurring-payments-automatic`; ficam de fora Citibank (participante
ativo, sem nenhuma família de pagamento), CrediSIS e HSBC.

Só que essa família é do **lado do pagador**: quem a publica é a detentora da
conta debitada, e quem a consome é um iniciador (ITP). Ela não é a API de
cobrança recorrente que o recebedor usa — essa é a `rec`/`cobr` do BACEN, na API
do próprio banco, e não aparece no diretório. Reforçando a diferença, a norma
tornou o lado pagador **obrigatório** desde 16/06/2025 e deixou o lado recebedor
**facultativo**: o ✅ da tabela do Open Finance é, em boa parte, obrigação
cumprida.

Ou seja, para trazer Pix Automático de um banco novo continua valendo o preço de
sempre: um provider REST com `PIX_BASE` e autenticação — o dialeto já está
escrito. A leitura completa do Open Finance está em
[open-finance.md](open-finance.md).

## O 201 que não era

Na homologação do Sicoob, `PA_01` entrou na evidência como `ok=true`,
`status_code=201`. O corpo era:

```html
<html><head><title>Request Rejected</title></head>
<body>The requested URL was rejected. Please consult with your administrator...
```

Um WAF respondeu no lugar do banco, e a resposta atravessou como sucesso. O
motivo é uma linha do `OAuthMtlsClient`: corpo `2xx` que não desserializa vira
`{"conteudo": "<texto>"}` — decisão certa para não perder a resposta de um mock,
e que sem uma segunda leitura vira *"criamos a recorrência"*.

Por isso o roteiro de validação não classifica pelo status HTTP. Um `2xx` cujo
corpo não é JSON tem veredito próprio, **`nao_provado`**, e nunca é somado a
`suportado`. A regra vive em `scripts/validar_pix_automatico.py::classificar` e
é exercitada sem rede em `gateway/tests/test_validacao_pix_automatico.py`.

## O 500 que virou 422

Banco sem o mixin não tem o método. As quinze rotas de `/pix-automatico`
chamavam `provider.criar_recorrencia(...)` direto, e o `AttributeError`
resultante saía como **500** — o serviço se acusando de defeito interno onde há
fronteira de capacidade do banco. Medido no Itaú:

```
POST /pix-automatico/recorrencias?banco=itau   ->  500 Internal Server Error
GET  /pix-automatico/recorrencias?banco=itau   ->  500 Internal Server Error
```

Agora passam pelo `exige_capacidade`, como Bolepix e checkout já faziam:

```
422 {"detail": "banco 'itau' não oferece Pix Automático; Pix Automático exige o
     dialeto BACEN de recorrência, que este banco não expõe — use `banco=` um
     destes: c6, inter, sicoob"}
```

A lista de quem oferece sai por introspecção das classes de provider — a mesma
fonte do `GET /bancos`. Catálogo e rota discordarem é o defeito caro (o
consumidor escolhe o banco pela vitrine), e há teste travando os dois juntos.

## Revalidar

```bash
export C6_SANDBOX_CLIENT_ID=... C6_SANDBOX_CLIENT_SECRET=...
export C6_SANDBOX_PFX_BASE64=... C6_SANDBOX_PFX_PASSWORD=...

PYTHONPATH=gateway python scripts/validar_pix_automatico.py c6
PYTHONPATH=gateway python scripts/validar_pix_automatico.py --json > evidencia.json
```

Sem argumento roda os quatro bancos ON. Banco sem credencial no ambiente sai
como `sem_credencial` — ausência de segredo não é falha de integração — e banco
sem a capacidade sai como `nao_oferecido` **antes** de qualquer chamada, porque
a resposta seria a mesma com o segredo em mãos.

Os vereditos, em ordem de severidade: `suportado`, `nao_provado`, `parcial`,
`recusado`, `nao_oferecido`, `sem_massa`, `sem_credencial`, `erro`. O veredito
do banco é o pior do conjunto, com uma regra a mais: falhar em `PA_01` (criar a
recorrência) não é suporte parcial — sem `rec` não existe ciclo nenhum.

## O que falta

- **Sicoob**: repetir fora do WAF, ou obter do banco a confirmação de que o
  sandbox expõe `rec`. Enquanto isso, a capacidade é declarada e não validada.
- **Inter**: confirmar no portal se o banco expõe as rotas. A homologação de
  agosto registrou o caso como ausente, com o motivo: *"não consta no SDK
  oficial do Inter (inter-co/pj-sdk-java) … prometer antes de confirmar seria
  vender o que não se sabe"*.
- **Itaú**: existe pelo Open Finance, não pela API de cobrança. Entrar por ali é
  decisão de escopo, não de implementação — veja [open-finance.md](open-finance.md).
