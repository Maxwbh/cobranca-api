# Validação de campos e contrato de erro

A **Cobranca-API** valida os dados na geração (boleto e remessa CNAB) e devolve
os problemas como uma **lista** — uma entrada por campo violado. A validação em
si é da engine [PyCobrança](https://github.com/Maxwbh/pyCobranca) (doc
`14-validacao-campos`); a API apenas **repassa** os erros sem colapsá-los.

> Requer **PyCobrança ≥ 1.0.1**: foi nela que `BoletoInvalido` ganhou o atributo
> `.erros` (lista). Em 1.0.0 a validação existia, mas vinha como um texto único.

## Contrato de erro

| Situação | HTTP | Corpo |
|---|---|---|
| Dados de boleto/pagamento inválidos | **400** | `{ "validation_errors": [ "…", "…" ] }` |
| Banco não suportado | **400** | `{ "validation_errors": ["Banco não suportado: …"] }` |
| Arquivo OFX inválido (`/api/ofx/parse`) | **400** | `{ "erro": "Arquivo OFX inválido", "validation_errors": [...] }` |
| Arquivo de retorno CNAB inválido (`/api/retorno`) | **400** | `{ "error": "…", "details": [...] }` |

`validation_errors` é **sempre uma lista** — mapeie cada item ao campo do seu
formulário. Um OFX válido **sem transações** não é erro (extrato vazio, 201).

```json
// GET /api/boleto/validate  (Itaú, 3 violações simultâneas)
{
  "valid": false,
  "validation_errors": [
    "carteira '999' não suportada (use uma de: 104, 109, 112, 115, 175, 177, 188)",
    "agência deve ter no máximo 4 dígitos",
    "conta deve ter no máximo 5 dígitos"
  ]
}
```

## Regras por banco (boleto)

Campos de agência/conta/convênio/nosso número são **numéricos** (a máscara é
descartada; um valor sem nenhum dígito falha no mínimo). A **carteira** é um
conjunto fechado por banco. Tamanhos abaixo são em **dígitos** (mín.–máx.).

| Banco (cód) | Agência | Conta | Convênio | Carteiras válidas | Nosso nº | Especiais / obrigatórios |
|---|---|---|---|---|---|---|
| **Itaú** (341) | 1–4 | 1–5 | — | 104, 109, 112, 115, 175, 177, 188 | 1–8 (+DAC) | — |
| **Banco do Brasil** (001) | 0–4¹ | 0–8¹ | 4 / 6 / 7 | 11, 12, 15, 16, 17, 18, 31, 51 | conv7→10 · conv6→5 · conv4→7 | nosso nº e layout dependem do convênio |
| **Bradesco** (237) | 1–4 | 1–7 | — | 03, 06, 09, 19, 21, 22, 25, 26 | 1–11 (+DV; pode ser `P`) | — |
| **Caixa** (104) | 4² | —³ | 1–6 (cód. benef.) | 14, 24 | 1–15 | 2 DVs (benef. + campo livre) |
| **Santander** (033) | —³ | fallback⁴ | 1–7 (cód. cedente) | 101, 102, 121 | 1–12 (+DV) | cedente = convênio **ou** conta |
| **Sicoob** (756) | 1–4 | —³ | 0–7 (ou nº contrato) | 1, 3, 9, 09 | 1–7 (+DV) | `numero_contrato` na carteira 9 |
| **Sicredi** (748) | 1–4 | 1–5 (convênio) | 1–5 | 1, 3 | 1–5 (+ano+byte+DV) | `byte_idt` **obrig.**; `posto`; `data_documento` **obrig.** |
| **Banrisul** (041) | 1–4 | —³ | 1–7 | 1, 2 | 1–8 (+duplo dígito) | `digito_convenio` (impressão) |
| **Ailos** (085) | —³ | 1–7 (+DV) | 1–6 | 01, 1 | 1–9 | — |
| **Unicred** (136) | 1–4 | 1–9 (+`digito_conta`) | — | 21 | 1–10 (+DV) | `digito_conta` **obrig.** |
| **Citibank** (745) | 1–4 | —³ | 1–10 | 3 | 1–11 (+DV) | `portfolio` |
| **CrediSIS** (097) | 1–4 | —³ | 1–6 | 18 | 1–6 | `cedente_documento` **obrig.** |
| **BRB / Brasília** (070) | **1–3** | 1–7 | — | 1, 2 | 1–6 (+duplo dígito) | `incremento` **obrig.** |
| **Banco do Nordeste** (004) | 1–4 | 1–7 (+`digito_conta`) | — | 21, 31, 41, 51 | 1–7 (+DV) | `digito_conta` |
| **Banestes** (021) | (impressão) | 1–10 (+`digito_conta`) | — | 11, 13 | 1–8 (+DV duplo) | `digito_conta` |
| **C6 Bank** (336) | 4 | —³ | 1–12 | 10, 20 | 1–10 (+DV; pode ser `P`) | indicador conforme carteira |
| **HSBC** (399) | 4 | 1–7 | — | **CNR, CSB** (alfanum.) | 1–13 | CNR: `data_vencimento` **obrig.** |
| **Safra** (422) | 1–4 (+`digito_agencia`) | 1–8 (+`digito_conta`) | — | 1, 2 | 1–8 (+DV) | `digito_agencia`, `digito_conta` **obrig.** |

¹BB só usa agência/conta nos convênios 4 e 6. ²Caixa: agência só na impressão.
³Não entra no campo livre (o beneficiário vem do convênio). ⁴Santander usa
`convenio` ou, na falta, `conta`.

### Campos comuns

| Campo | Tipo | Regra |
|---|---|---|
| `valor` | número | > 0 |
| `data_vencimento` | data (`YYYY-MM-DD`) | obrigatória |
| `cedente` | texto | obrigatório |
| `documento_cedente` / `sacado_documento` | texto | se informado, **CPF, CNPJ numérico ou CNPJ alfanumérico** válido |
| `carteira` | texto | deve pertencer ao conjunto do banco |

> **CNPJ alfanumérico (formato 2026):** **suportado.** A engine valida o DV
> pelo algoritmo oficial (valor do caractere = `ord(c) − 48`) e preserva as
> letras na geração do código de barras e do CNAB. DV inválido — alfanumérico
> ou numérico — é recusado. Requer a engine com suporte alfanumérico.

## Regras da remessa CNAB (`pagamento`)

Além dos campos do sacado, a validação cobre a **coerência dos encargos**
(modelo de trio código/tipo → valor → data). Detalhe em
[encargos.md](./encargos.md) e nas posições por banco na doc `06-cnab` da engine.

| Regra | Erro |
|---|---|
| `nosso_numero`, `documento_sacado`, `nome_sacado`, `endereco_sacado`, `cep_sacado`, `data_vencimento` ausentes | `campo obrigatório ausente: <campo>` |
| `valor` ≤ 0 | `valor deve ser positivo` |
| `tipo_mora="1"` sem `valor_mora` | `tipo_mora="1" (valor ao dia) exige valor_mora > 0` |
| `tipo_mora="2"` sem `percentual_mora` | `tipo_mora="2" (taxa mensal) exige percentual_mora > 0` |
| `codigo_multa` ≠ 0 sem `percentual_multa` | `codigo_multa != 0 exige percentual_multa > 0` |
| desconto indicado sem valor/data | `Nº desconto indicado (cód. != 0) exige valor > 0` / `exige data` |
| `uf_sacado` ≠ 2 letras | `uf_sacado deve ter 2 letras` |
| `cep_sacado` > 8 dígitos | `cep_sacado deve ter no máximo 8 dígitos` |
