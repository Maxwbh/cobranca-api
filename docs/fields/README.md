# Guia de Campos para Boletos — engine pyCobrança

> 📚 Documentação completa dos campos aceitos por cada banco
> 🕒 Última atualização: 2026-08-19 — os exemplos desta página foram
> **executados**: os de boleto voltam `valid: true` em `GET /api/boleto/validate`,
> e os três de remessa geram arquivo CNAB em `POST /api/remessa`.

## 📋 Índice

- [Campos Comuns](#campos-comuns)
- [Banco do Brasil (001)](#banco-do-brasil-001)
- [Sicoob (756)](#sicoob-756)
- [Banco C6 (336)](#banco-c6-336)
- [Diferenças Importantes](#diferenças-importantes)
- [Nosso Numero — Guia Completo](./nosso-numero.md) — Entrada vs saida, tamanhos, conciliacao
- [Todos os Bancos](./all-banks.md) — Lista completa com todos os 18 bancos suportados

## 🎯 Legenda

- 🔒 = Campo **OBRIGATÓRIO**
- 📝 = Campo **RECOMENDADO** (opcional mas importante)
- ⏭️ = Campo **OPCIONAL** (pode omitir)
- ⚠️ = Campo com **RESTRIÇÕES** ou validações especiais
- ❌ = Campo que **NÃO** deve ser enviado

---

## Campos Comuns

Todos os bancos herdam de `BancoBase` (pyCobrança) e compartilham campos básicos.

### Obrigatórios 🔒

| Campo | Tipo | Descrição | A engine recusa sem ele? |
|-------|------|-----------|:---:|
| `valor` | Decimal | Valor do boleto | **sim** |
| `data_vencimento` | Date/String | Data de vencimento | **sim** |
| `cedente` | String | Nome do beneficiário (emissor) | **sim** |
| `carteira` | String | Carteira do convênio | **sim** |
| `convenio` | String | Convênio/código do beneficiário | **sim** (nos bancos que usam) |
| `nosso_numero` | String | Número sequencial do boleto **no banco** | não ⚠️ |
| `agencia` | String | Código da agência bancária | não ⚠️ |
| `conta_corrente` | String | Número da conta corrente | não ⚠️ |
| `sacado` | String | Nome do pagador | não ⚠️ |
| `sacado_documento` | String | CPF/CNPJ do pagador | não ⚠️ |
| `documento_cedente` | String | CPF/CNPJ do beneficiário | não ⚠️ |

> ⚠️ **A coluna da direita é a diferença entre "obrigatório" e "validado", e ela
> morde.** Os cinco primeiros a engine recusa; os demais ela **aceita ausentes e
> gera o boleto assim mesmo**. Sem `nosso_numero`, a linha digitável sai com o
> campo zerado — documento com cara de válido, que o banco não concilia:
>
> ```
> com nosso_numero=7   → 00190.00009 01234.567004 00000.007187 8 16770000150000
> sem nosso_numero     → 00190.00009 01234.567004 00000.000182 3 16770000150000
> ```
>
> Errar aqui não dá erro; dá prejuízo depois. Trate a lista inteira como
> obrigatória no **seu** código — a validação da engine não vai te salvar.

### Nomes com apelido

`documento_cedente` e `cedente_documento` são o **mesmo campo**, e o mesmo vale
para `sacado_documento` e `documento_sacado` — a engine aceita as duas grafias.
As mensagens de erro usam a forma `cedente_documento`, então não estranhe ver um
nome no erro e outro no seu payload.

> **CPF e CNPJ são validados de verdade** (dígito verificador). Documento
> inventado como `12345678000100` volta `400` com
> `cedente_documento inválido (CPF/CNPJ)` — é por isso que os exemplos abaixo
> usam documentos com DV correto.

### Recomendados 📝

| Campo | Descrição | Benefício |
|-------|-----------|-----------|
| `numero_documento` | Número da NF/pedido/contrato | Rastreabilidade e controle interno |
| `sacado_endereco` | Endereço completo do pagador | Compliance e localização |
| `data_documento` | Data de emissão | Controle temporal |
| `instrucao1` a `instrucao6` | Instruções para o caixa/pagador | Comunicação clara |
| `local_pagamento` | Local de pagamento | Informação ao pagador |
| `cedente_endereco` | Endereço do beneficiário | Contato e compliance |

### Opcionais ⏭️

| Campo | Valor Padrão | Notas |
|-------|--------------|-------|
| `moeda` | `'9'` | Código da moeda (9 = Real) |
| `especie` | `'R$'` | Símbolo da moeda |
| `aceite` | `'S'` | 'S' = aceite, 'N' = sem aceite |
| `especie_documento` | `'DM'` | DM, DS, NP, RC, etc. |
| `data_processamento` | hoje | Data de processamento |
| `quantidade` | `1` | Quantidade |
| `avalista` | - | Nome do avalista |
| `avalista_documento` | - | CPF/CNPJ do avalista |

---

## Banco do Brasil (001)

### Campos Específicos 🔒

| Campo | Tipo | Validação | Notas |
|-------|------|-----------|-------|
| `convenio` | String | **4, 6 ou 7 dígitos** | **OBRIGATÓRIO** |
| `carteira` | String | 2 dígitos | Padrão: `'18'` |

> ⚠️ **Convênio de 5 ou 8 dígitos é recusado**: `convênio deve ter 4, 6 ou 7
> dígitos`. Versões anteriores desta página diziam "4 a 8" e traziam exemplos
> com `01234567` (oito) — que a engine nunca aceitou.

### Tamanho do `nosso_numero` ⚠️

O tamanho máximo depende do convênio:

- Convênio 4 dígitos → nosso_numero máx **7 dígitos**
- Convênio 6 dígitos (sem codigo_servico) → nosso_numero máx **5 dígitos**
- Convênio 6 dígitos (com codigo_servico) → nosso_numero máx **17 dígitos**
- Convênio 7 dígitos → nosso_numero máx **10 dígitos** *(conferido: 11 dígitos
  volta `nosso número deve ter no máximo 10 dígitos para este convênio`)*

### Campos Aceitos ✅

- ✅ `numero_documento` - a validação **não impõe limite** (conferido até 120 caracteres)
- ✅ `aceite` - Aceita 'S' ou 'N'
- ✅ `especie_documento` - Aceita qualquer valor válido

### Remessa CNAB (Banco do Brasil)

> ⚠️ **A remessa não vai como corpo JSON — vai como arquivo.** `POST /api/remessa`
> recebe **multipart/form-data** com o campo `data` contendo este JSON. Mandar o
> objeto direto no corpo responde `422 Field required: data`. Os blocos abaixo
> são o **conteúdo do arquivo**:
>
> ```bash
> curl -X POST "$API/api/remessa?bank=banco_brasil&type=cnab400" \
>      -F "data=@remessa.json;type=application/json" -o remessa.rem
> ```

```json
// conteúdo de remessa.json — POST /api/remessa?bank=banco_brasil&type=cnab400
{
  "empresa_mae": "Empresa Teste LTDA",
  "documento_cedente": "11222333000181",
  "agencia": "3073",
  "conta_corrente": "12345678",
  "convenio": "1234567",
  "carteira": "18",
  "variacao_carteira": "017",
  "pagamentos": [
    {
      "nosso_numero": "123456789",
      "data_vencimento": "2026/12/31",
      "valor": 1500.00,
      "nome_sacado": "Joao da Silva",
      "documento_sacado": "11144477735",
      "endereco_sacado": "Rua Teste, 100",
      "bairro_sacado": "Centro",
      "cep_sacado": "01000000",
      "cidade_sacado": "Sao Paulo",
      "uf_sacado": "SP"
    }
  ]
}
```

### Exemplo Completo

```json
{
  "agencia": "3073",
  "conta_corrente": "12345678",
  "convenio": "1234567",
  "carteira": "18",
  "nosso_numero": "7",
  "numero_documento": "CTR-2023-0012-017/017",
  "cedente": "Empresa Exemplo LTDA",
  "documento_cedente": "11222333000181",
  "sacado": "João da Silva",
  "sacado_documento": "11144477735",
  "sacado_endereco": "Rua Exemplo, 100, Centro, Cidade, UF, CEP 12345000",
  "valor": 1500.00,
  "data_vencimento": "2025/12/31",
  "data_documento": "2025/11/26",
  "aceite": "N",
  "especie_documento": "DM",
  "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
  "instrucao1": "Não receber após o vencimento",
  "instrucao2": "Após vencimento cobrar multa de 2%",
  "cedente_endereco": "Av. Principal, 200"
}
```

---

## Sicoob (756)

### Campos Específicos 🔒

| Campo | Tipo | Validação | Valor |
|-------|------|-----------|-------|
| `convenio` | String | numérico | Código do convênio/beneficiário |
| `carteira` | String | 2 dígitos | Padrão: `'1'` |
| `variacao` | String | 2 dígitos | Exigido pelo **convênio**, não pela engine — ex: `'01'` |
| `modalidade` | String | 2 dígitos | Padrão: `'01'` |

### ⚠️ ATENÇÃO: regras do BANCO que a engine NÃO valida

| Campo | Valor esperado pelo Sicoob | A engine recusa o contrário? |
|-------|---------------|:---:|
| `aceite` | `'N'` | **não** — `'S'` passa na validação |
| `especie_documento` | `'DM'` | **não** — omitir passa na validação |
| `variacao` | `'01'` (ou a do convênio) | **não** — omitir passa na validação |

> **Estas três são regras do convênio, não da engine.** Rodar
> `GET /api/boleto/validate` com `aceite: "S"` devolve `valid: true`, e mesmo
> assim o boleto pode ser recusado no registro. Quem confia na validação para
> pegar esse erro descobre no banco — e aí já emitiu.
>
> A versão anterior desta página dizia que o Sicoob "EXIGE" e que o campo era
> "OBRIGATÓRIO", sem dizer **quem** exige. A diferença é toda: o que a engine
> exige, ela recusa; o que o banco exige, você garante no seu código.

### Campos Aceitos ✅

- ✅ `numero_documento` - Aceito e recomendado
- ✅ Todos os campos de endereço
- ✅ Instruções (instrucao1 a instrucao6)
- ✅ Campos de avalista

### ❌ Erro Comum

**NÃO** remova os campos `aceite` e `especie_documento` para Sicoob!

```python
# ❌ ERRADO - Filtrando campos
campos_removidos = ['numero_documento', 'especie_documento', 'aceite']

# ✅ CORRETO - Enviando com valores corretos
boleto_sicoob = {
    "aceite": "N",  # DEVE ser 'N' para Sicoob
    "especie_documento": "DM",  # DEVE enviar
    "numero_documento": "NF-2023-001",  # PODE e DEVE enviar
    # ... outros campos
}
```

### Exemplo Completo

```json
{
  "agencia": "4327",
  "conta_corrente": "417270",
  "convenio": "229385",
  "carteira": "1",
  "variacao": "01",
  "modalidade": "01",
  "nosso_numero": "1234567",
  "numero_documento": "NF-2025-001234",
  "aceite": "N",
  "especie_documento": "DM",
  "cedente": "Cooperativa Exemplo",
  "documento_cedente": "11222333000181",
  "sacado": "Maria dos Santos",
  "sacado_documento": "11144477735",
  "sacado_endereco": "Rua da Cooperativa, 50, Bairro, Cidade, UF, CEP 54321000",
  "valor": 2500.00,
  "data_vencimento": "2025/12/31",
  "data_documento": "2025/11/26",
  "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
  "instrucao1": "Não receber após 30 dias",
  "cedente_endereco": "Av. Cooperativa, 100"
}
```

---

### Remessa CNAB 240 (Sicoob)

> ⚠️ **O campo `variacao` é obrigatório no boleto, mas NÃO existe na classe de remessa CNAB 240 do Sicoob.** Enviar `variacao` na remessa causará `NoMethodError`.

```json
// conteúdo do arquivo — POST /api/remessa?bank=sicoob&type=cnab240 (multipart, campo `data`)
{
  "empresa_mae": "Cooperativa Teste",
  "documento_cedente": "11222333000181",
  "agencia": "4327",
  "conta_corrente": "417270",
  "convenio": "229385",
  "carteira": "1",
  "pagamentos": [
    {
      "nosso_numero": "7890",
      "data_vencimento": "2026/12/31",
      "valor": 2500.00,
      "nome_sacado": "Maria Santos",
      "documento_sacado": "11144477735",
      "endereco_sacado": "Av. Principal, 50",
      "bairro_sacado": "Centro",
      "cep_sacado": "20000000",
      "cidade_sacado": "Rio de Janeiro",
      "uf_sacado": "RJ"
    }
  ]
}
```

---

## Banco C6 (336)

### ⚠️ Carteira: só `10` ou `20`

Esta a engine **recusa**, e com mensagem clara:

```
carteira '1' não suportada (use uma de: 10, 20)
```

É a pegadinha mais comum de quem chega do Sicoob (carteira `1`) ou do Banco do
Brasil (carteira `18`): o mesmo payload, trocando só o banco, para de valer.

### Boleto (GET /api/boleto)

```json
{
  "agencia": "0001",
  "conta_corrente": "1234567",
  "carteira": "10",
  "convenio": "100",
  "nosso_numero": "12345678",
  "cedente": "Empresa C6 LTDA",
  "documento_cedente": "11222333000181",
  "sacado": "João da Silva",
  "sacado_documento": "11144477735",
  "valor": 1500.00,
  "data_vencimento": "2026/12/31"
}
```

### Remessa CNAB 400 (POST /api/remessa)

> ⚠️ **`convenio` não existe na classe de remessa do C6!** Enviar esse campo causará erro. Use `codigo_beneficiario` em vez disso.

```json
// conteúdo do arquivo — POST /api/remessa?bank=banco_c6&type=cnab400 (multipart, campo `data`)
{
  "empresa_mae": "Empresa C6 LTDA",
  "documento_cedente": "11222333000181",
  "agencia": "0001",
  "conta_corrente": "1234567",
  "digito_conta": "0",
  "carteira": "10",
  "codigo_beneficiario": "0012345678",
  "pagamentos": [
    {
      "nosso_numero": "12345678",
      "data_vencimento": "2026/12/31",
      "valor": 1500.00,
      "nome_sacado": "Joao da Silva",
      "documento_sacado": "11144477735",
      "endereco_sacado": "Rua Teste, 100",
      "bairro_sacado": "Centro",
      "cep_sacado": "01000000",
      "cidade_sacado": "Sao Paulo",
      "uf_sacado": "SP"
    }
  ]
}
```

---

## Diferenças Importantes

### `nosso_numero` vs `numero_documento`

| Campo | Propósito | Obrigatoriedade | Aparece em |
|-------|-----------|-----------------|------------|
| `nosso_numero` | Identificação **BANCÁRIA** do boleto | 🔒 **OBRIGATÓRIO** | Código de barras, linha digitável |
| `numero_documento` | Identificação **INTERNA** (NF, pedido) | 📝 **RECOMENDADO** | Apenas no PDF impresso |

**Importante:**
- `numero_documento` **NÃO** afeta o código de barras ou linha digitável
- `numero_documento` é usado apenas para rastreamento e controle interno
- `nosso_numero` **DEVE** ser sequencial e único por convênio

### O campo se chama `numero_documento`

⚠️ **`documento_numero` era o nome da gem Ruby e não existe mais.** Enviado
hoje, ele é **descartado em silêncio** — o boleto sai com o campo vazio, sem
erro nenhum:

```bash
# verificado na engine atual
enviando numero_documento -> numero_documento no boleto: 'NF-1'
enviando documento_numero -> numero_documento no boleto: ''
```

Use `numero_documento` na API e na engine: o nome é o mesmo nos dois lados, e
não há mapeamento a lembrar.

### Estratégia Recomendada 💡

**Envie o MÁXIMO de campos possíveis!**

1. ✅ Envie `numero_documento` sempre que disponível
2. ✅ Envie endereços completos (cedente e sacado)
3. ✅ Envie instruções claras
4. ✅ Envie datas (documento e processamento)
5. ❌ **NÃO** filtre campos por banco — mandar a mais não quebra; a menos, sim

> ⚠️ **O item 5 já disse "deixe a engine validar". Não deixe.** A engine valida
> o que é do formato — carteira, convênio, tamanho de nosso número, DV de
> CPF/CNPJ — e **não** valida o que é do convênio (o `aceite` do Sicoob) nem a
> ausência de campos que ela consegue contornar (`nosso_numero`, `sacado`).
> Enviar tudo continua sendo a estratégia certa; confiar na validação para
> descobrir o que faltou, não.

**Benefícios:**
- Melhor rastreabilidade
- Compliance com regulamentações
- Comunicação clara com pagador
- Facilita conciliação bancária
- Melhor experiência do usuário

---

## 📚 Documentação Adicional

- [Todos os Bancos](./all-banks.md) - Lista completa e compatibilidade por banco
- [PIX Híbrido](../api/pix.md) - Guia de boleto com QR Code PIX
- [Exemplos Python](https://github.com/Maxwbh/cobranca-api/tree/main/examples/python) - Scripts executáveis
- [Troubleshooting](../api/troubleshooting.md) - Solução de problemas
- [Engine PyCobrança](https://github.com/Maxwbh/pyCobranca) - quem gera o boleto

---

**Engine:** [pyCobrança](https://github.com/Maxwbh/pyCobranca) (Python) — versão em uso: `GET /api/metadata`
**Versão da API:** a que responde em `GET /api/metadata` (número fixo aqui
envelhece a cada release — este ficou parado na 2.1.0 por duas versões).
