# Encargos na remessa CNAB — multa, juros/mora, desconto, IOF e abatimento

Como enviar multa, juros, desconto, IOF e abatimento em `POST /api/remessa` (e
em `POST /jobs/cnab/remessas`), e o que cada banco/layout aceita.

> **Fonte.** A engine [PyCobrança](https://github.com/Maxwbh/pyCobranca) é quem
> monta o arquivo. Este documento espelha a `docs/06-cnab.md` da engine
> (v1.0.1) e é **verificado por teste**: `gateway/tests/test_offline_pycobranca.py`
> gera o CNAB, localiza cada campo e decodifica o valor de volta. Se a engine
> mudar, os testes acusam antes da documentação envelhecer.

## O modelo: cada encargo é um trio

Todo encargo se expressa como **código/tipo → valor → data** (a data é opcional):

| Encargo | Código / tipo | Valor | Data |
|---|---|---|---|
| **Multa** | `codigo_multa` — `0` isento · `1` valor fixo · `2` percentual | `percentual_multa` | `data_multa` |
| **Juros / mora** | `tipo_mora` — `1` valor/dia · `2` taxa mensal % · `3` isento | `valor_mora` (R$) · `percentual_mora` (%) | `data_mora` |
| **Desconto** 1º/2º/3º | `cod_desconto` / `cod_segundo_desconto` / `cod_terceiro_desconto` | `valor_desconto` / `valor_segundo_desconto` / `valor_terceiro_desconto` | `data_desconto` / … |
| **IOF** | — | `valor_iof` | — |
| **Abatimento** | — | `valor_abatimento` | — |

Valores em reais ou percentual conforme o encargo; formato numérico decimal
(`2.0`, `1.50`). Todos são **opcionais** e têm default neutro — sem informá-los,
o arquivo sai com os encargos zerados.

## A unidade (% ou R$) depende do layout — e a API valida

Este é o ponto que mais gera cobrança errada, então a API **recusa** as
combinações impossíveis em vez de gerar um arquivo que o banco leria torto.

### CNAB 240 — o código vai no arquivo

O segmento do CNAB 240 grava o **código/tipo**, então o banco sabe a unidade
pelo próprio arquivo:

- **multa**: `codigo_multa='2'` + `percentual_multa` (percentual) ou
  `codigo_multa='1'` + valor (fixo);
- **mora**: `tipo_mora='2'` + `percentual_mora` (taxa mensal %) ou
  `tipo_mora='1'` + `valor_mora` (por dia).

O valor **sozinho não basta**: `percentual_mora` sem `tipo_mora='2'` é ignorado
pelo layout.

### CNAB 400 — a unidade é fixa

No 400 o código/tipo **não é gravado** — a unidade é definida pelo layout:
**multa sempre percentual**, **mora sempre valor ao dia**. Portanto:

| Enviado no 400 | Resposta |
|---|---|
| `percentual_multa` + `codigo_multa='2'` | ✅ (o código é redundante, mas aceito) |
| `valor_mora` + `tipo_mora='1'` | ✅ |
| `codigo_multa='1'` + `valor_multa` | ❌ **400** — exceto **Inter** |
| `tipo_mora='2'` + `percentual_mora` | ❌ **400** — exceto **Inter** |
| `cod_desconto='4'` + `percentual_desconto` | ❌ **400** — exceto **Inter** |
| `percentual_mora` sozinho | ❌ **400** — use `valor_mora` |

#### A exceção: Inter (077)

O layout do Inter tem os **dois** campos de cada encargo — itens 10/11 (multa),
14/15 (mora) e 30/31 (desconto) do registro tipo 1 — e escolhe pelo código. Nele
`valor_multa`, `percentual_mora` e `percentual_desconto` são gravados de verdade.

É o **único** dos 14 layouts 400 em que isso vale. Medido A/B em todos: gerar o
arquivo com dois valores diferentes do campo e comparar byte a byte. Nos outros
13 o campo entra, não é gravado e some — que é justamente o que a recusa evita.

> **Por que recusar em vez de ignorar:** `codigo_multa='1'` com valor `50`
> faria o banco cobrar **50%** onde você quis **R$ 50** — num título de
> R$ 1.500, R$ 750 de multa. Falhar alto é a única opção segura.

## Suporte por banco (espelho de `06-cnab.md` da engine)

`✅` = posição no arquivo · `—` = sem campo no layout · `📝` = via instrução (código).

### CNAB 240 — completo e uniforme

Banco do Brasil, Caixa, Santander, Sicoob, Sicredi, Unicred e Ailos: **todos os
encargos** (mora %/R$, multa, 1º/2º/3º desconto, IOF, abatimento).
Ailos emite o 2º/3º desconto e a multa só quando há multa informada.

### CNAB 400 — varia por layout

| Banco | Mora | Multa | Desc. 1º | Desc. 2º | IOF | Abat. |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Santander (033) | ✅ | ✅ | ✅ | 📅 só data | ✅ | ✅ |
| Bradesco (237) | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| Sicoob (756) | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| Banrisul (041) | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| Banco do Nordeste (004) | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| C6 (336) | ✅ | ✅ | ✅ | — | — | ✅ |
| Unicred (136) | ✅ | ✅ | ✅ | — | — | ✅ |
| CrediSIS (097) | ✅ | ✅ | ✅ (sem data) | — | — | — |
| Itaú (341) | ✅ | 📝 instrução | ✅ | — | ✅ | ✅ |
| Banco do Brasil (001) | ✅ | 📝 instrução | ✅ | — | ✅ | ✅ |
| Citibank (745) | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| BRB / Brasília (070) | ✅ | — | ✅ | — | — | ✅ |
| Safra (422) | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| Inter (077) | ✅ | ✅ | ✅ | — | — | — |

> Medida A/B em todos os 14 layouts, não copiada: gerar o arquivo com dois
> valores diferentes do campo e comparar byte a byte. `✅` significa que o
> arquivo muda — ou seja, que o campo tem posição de verdade.

- **2º e 3º desconto** existem apenas no **CNAB 240**.
- **BB e Itaú (400)**: a multa vai por **instrução** (código de ocorrência),
  não como percentual posicional — enviar `percentual_multa` não altera o
  arquivo, e isso é esperado.
- **Safra (422) e Inter (077) ganharam remessa CNAB 400** na pyCobrança 1.1.1.
  Esta página dizia que o Safra só emitia boleto; deixou de ser verdade.
- Banestes (021) e HSBC (399) só emitem boleto — não têm remessa CNAB.
- **Inter:** multa em **valor** e desconto em **percentual**, além das formas
  comuns. Sem IOF e sem abatimento no layout.

## Exemplo

```json
POST /api/remessa?bank=banco_brasil&type=cnab240
{
  "empresa_mae": "Empresa Teste LTDA",
  "documento_cedente": "11222333000181",
  "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
  "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
  "sequencial_remessa": 1,
  "pagamentos": [{
    "nosso_numero": "123456789",
    "numero_documento": "DOC-2026-001",
    "data_vencimento": "2027-12-31",
    "valor": 1500.00,

    "codigo_multa": "2", "percentual_multa": 2.00, "data_multa": "2028-01-01",
    "tipo_mora": "2", "percentual_mora": 1.00, "data_mora": "2028-01-01",
    "cod_desconto": "1", "valor_desconto": 50.00, "data_desconto": "2027-12-20",
    "valor_iof": 3.75,
    "valor_abatimento": 25.00,

    "sacado": "Joao da Silva", "sacado_documento": "52998224725",
    "sacado_endereco": "Rua Teste, 100", "sacado_bairro": "Centro",
    "sacado_cidade": "Sao Paulo", "sacado_uf": "SP", "sacado_cep": "01000000"
  }]
}
```

## Erros

| Situação | Resposta |
|---|---|
| Campo de encargo com nome inexistente | **400** listando os aceitos + dica do trio |
| Unidade impossível no CNAB 400 (`codigo_multa='1'`, `tipo_mora='2'`, `percentual_mora`) | **400** com a alternativa correta |
| Banco/layout sem posição para o encargo | aceito, mas o encargo **não entra** no arquivo (ver a matriz acima) |

## Ver também

- Engine: [`docs/06-cnab.md` da PyCobrança](https://github.com/Maxwbh/pyCobranca/blob/main/docs/06-cnab.md)
- [Exemplo Oracle de remessa](https://github.com/Maxwbh/cobranca-api/blob/main/examples/oracle/exemplo_remessa.sql)
- Spec: `POST /api/remessa` em [`docs/openapi.yaml`](../openapi.yaml)
