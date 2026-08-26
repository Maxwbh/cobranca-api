# Todos os Bancos Suportados — Validação Completa

> Status de compatibilidade e particularidades de cada banco no **caminho
> offline** (engine pyCobrança). Para o caminho online — o que cada banco faz
> pela própria API — a fonte é `GET /bancos`, que responde por introspecção.
>
> 🕒 Revisado em 2026-08-19 **executando cada afirmação** contra
> `GET /api/boleto/validate` e `GET /api/boleto/data`. Onde esta página diz um
> número, ele veio da engine, não de memória.

## 🎯 Carteiras aceitas — a tabela que resolve 90% dos erros

Errar a carteira é o erro nº 1 de quem troca de banco, porque o payload é o
mesmo e só ela muda. A engine **recusa** carteira fora da lista, e diz quais
valem:

```
carteira '1' não suportada (use uma de: 10, 20)
```

| Banco | Código | Carteiras aceitas |
|-------|--------|-------------------|
| Ailos | 085 | `01`, `1` |
| Banco do Brasil | 001 | `11`, `12`, `15`, `16`, `17`, `18`, `31`, `51` |
| Banco do Nordeste | 004 | `21`, `31`, `41`, `51` |
| Banestes | 021 | `11`, `13` |
| Banrisul | 041 | `1`, `2` |
| Bradesco | 237 | `03`, `06`, `09`, `19`, `21`, `22`, `25`, `26` |
| BRB | 070 | `1`, `2` |
| Caixa | 104 | `14`, `24` |
| Citibank | 745 | `3` |
| CrediSIS | 097 | `18` |
| C6 Bank | 336 | `10`, `20` |
| HSBC | 399 | `CNR` |
| Inter | 077 | `110` |
| Itaú | 341 | `104`, `109`, `112`, `115`, `175`, `177`, `188` |
| Safra | 422 | `1`, `2` |
| Santander | 033 | `101`, `102`, `121` |
| Sicoob | 756 | `1`, `3`, `9`, `09` |
| Sicredi | 748 | `1`, `3` |
| Unicred | 136 | `21` |

> A lista sai da engine, e a mensagem de erro é a fonte viva: se um layout
> ganhar carteira nova, ela aparece no erro antes de aparecer aqui. Um teste
> varre as **55 carteiras dos 19 bancos** e confere cada boleto contra um
> verificador FEBRABAN independente, então a tabela não fica sozinha.
>
> **Inter:** só a `110`. Nas `112` e `121` quem numera é o banco e o nosso
> número só existe no arquivo retorno — não há como imprimir o boleto antes
> disso. As duas valem na **remessa**, onde o nosso número vai zerado.
>
> **Sicoob:** `9` e `09` são a mesma carteira, e a API garante que produzem o
> mesmo boleto. Até a pyCobrança 1.1.1 a grafia `09` gravava `0` no campo livre
> — carteira que o Sicoob não tem — e o título saía estruturalmente válido.
>
> **Safra** (`1`/`2`) e **Banestes** (`11`/`13`): a carteira **não** entra no
> campo livre nesses dois layouts, então as duas produzem o mesmo código de
> barras. É o layout, não defeito — no Safra a posição 25 é fixa em `2`.

## 📋 Bancos Testados e Validados

| Banco | Código | Status | PDF | Remessa | Observações |
|-------|--------|--------|-----|---------|-------------|
| **Banco do Brasil** | 001 | ✅ | ✅ | CNAB400 + CNAB240 | Convênio de **4, 6 ou 7** dígitos |
| **Sicoob** | 756 | ✅ | ✅ | CNAB240 | `variacao` **não** vai na remessa |
| **Bradesco** | 237 | ✅ | ✅ | CNAB400 | `digito_conta` esperado pelo layout |
| **Itaú** | 341 | ✅ | ✅ | CNAB400 | Conta ≤ **5** dígitos; nosso número ≤ **8** |
| **Caixa Econômica** | 104 | ✅ | ✅ | CNAB240 | Carteira **só `14` ou `24`**; convênio obrigatório |
| **Santander** | 033 | ✅ | ✅ | CNAB400 + CNAB240 | `nosso_numero` até **12** dígitos |
| **Banco C6** | 336 | ✅ | ✅ | CNAB400 | Carteira `10`/`20`; remessa exige `codigo_beneficiario` |
| **Inter** | 077 | ✅ | ✅ | CNAB400 | Só a carteira `110` no boleto; a remessa aceita `110`, `112` e `121` |

### Outros Bancos Suportados

| Banco | Código | Status |
|-------|--------|--------|
| Sicredi | 748 | ✅ |
| Banrisul | 041 | ✅ |
| Banestes | 021 | ✅ |
| BRB | 070 | ✅ |
| Unicred | 136 | ✅ |
| Ailos | 085 | ✅ |
| CrediSIS | 097 | ✅ |
| Safra | 422 | ✅ |
| Banco do Nordeste | 004 | ✅ |
| HSBC | 399 | ✅ layout ativo — **o banco é que não existe mais** (incorporado pelo Bradesco em 2016) |
| Citibank | 745 | ✅ layout ativo — o banco opera só no **atacado** desde a venda do varejo |

> Os dois últimos **funcionam** na engine: HSBC emite com carteira `CNR` e
> Citibank com `3`. Versões anteriores desta página os marcavam
> "⚠️ descontinuado", o que se lia como "não emite" — e emite. O que acabou foi
> o banco de varejo, não o layout.
>
> A carteira **`CSB` do HSBC saiu** na pyCobrança 1.1.1: o campo livre dela
> montava 27 posições onde cabem 25, então ela **nunca** produziu um boleto
> válido — anunciá-la era promessa que sempre falhava. Corrigi-la depende do
> manual do HSBC, que o banco não publica mais.

---

## 🏦 Detalhes por Banco

### 1. Banco do Brasil (001)

```json
{
  "convenio": "1234567",      // OBRIGATÓRIO — 4, 6 ou 7 dígitos
  "carteira": "18",           // uma de: 11 12 15 16 17 18 31 51
  "nosso_numero": "123"       // tamanho varia com o convênio
}
```

**Tamanho do nosso_numero:**

- Convênio 4 dígitos → máx **7** dígitos
- Convênio 6 dígitos → máx **5** ou **17** dígitos (com `codigo_servico`)
- Convênio 7 dígitos → máx **10** dígitos

> ⚠️ **Convênio de 5 ou 8 dígitos não existe** — a engine recusa com
> `convênio deve ter 4, 6 ou 7 dígitos`. Versões anteriores desta página traziam
> "4-8 dígitos", um exemplo com `01234567` e uma regra para "convênio de 8
> dígitos". Nada disso valia.

---

### 2. Sicoob (756)

```json
{
  "convenio": "229385",       // OBRIGATÓRIO
  "carteira": "1",            // uma de: 1 3 9 09
  "variacao": "01",           // exigido pelo CONVÊNIO, não pela engine
  "modalidade": "01",
  "aceite": "N",              // exigido pelo CONVÊNIO, não pela engine
  "especie_documento": "DM"   // idem
}
```

> ⚠️ **`variacao`, `aceite` e `especie_documento` são regra do banco, e a engine
> não as valida**: `aceite: "S"` passa em `/validate`, omitir `variacao` passa.
> Garanta no seu código — a validação não vai pegar isso para você.

---

### 3. Bradesco (237)

```json
{
  "agencia": "1234",
  "conta_corrente": "567890",
  "digito_conta": "1",        // esperado pelo layout de remessa
  "carteira": "09",           // uma de: 03 06 09 19 21 22 25 26
  "nosso_numero": "12345"
}
```

> ⚠️ **Carteira `02` não existe** — versões anteriores a citavam como opção
> válida ("09, 02, 03, 06, 25"). E a engine **não** recusa o boleto sem
> `digito_conta`, apesar de ele ser necessário para a remessa sair certa.

---

### 4. Itaú (341)

```json
{
  "agencia": "0810",
  "conta_corrente": "53678",  // máximo 5 dígitos
  "carteira": "109",          // uma de: 104 109 112 115 175 177 188
  "nosso_numero": "12345678"  // máximo 8 dígitos
}
```

> ⚠️ **Carteira `174` não existe** — a página antiga a listava como "sem
> registro". E a conta tem teto: 6 dígitos devolvem
> `conta deve ter no máximo 5 dígitos`.

---

### 5. Caixa Econômica Federal (104)

```json
{
  "agencia": "1825",
  "conta_corrente": "0000528",
  "digito_conta": "6",
  "carteira": "14",           // APENAS 14 ou 24
  "convenio": "245274",       // OBRIGATÓRIO
  "nosso_numero": "000000000000001"
}
```

> ⚠️ **A carteira da Caixa é `14` ou `24`.** A página antiga dizia "`'1'` ou
> `'2'` (não aceita `'SR'`, `'RG'`)" — e o exemplo inteiro, com carteira `1`,
> era recusado pela engine. Nenhum dos quatro valores citados funciona.

---

### 6. Santander (033)

```json
{
  "agencia": "1234",
  "conta_corrente": "9876543",
  "digito_conta": "2",
  "carteira": "102",          // uma de: 101 102 121
  "nosso_numero": "1234567"   // até 12 dígitos
}
```

> ⚠️ Duas correções: o limite é **12** dígitos, não 7 — e o exemplo antigo
> trazia `"nosso_numero": "12345678901234567890"` (vinte) com o comentário
> "// Até 7 dígitos", número que a engine recusa
> (`nosso número deve ter no máximo 12 dígitos`). A carteira `201`, também
> citada, não existe.

---

### 7. Banco C6 (336) — desde v1.3.0

#### 7.1 Boleto (GET /api/boleto)

```json
{
  "agencia": "0001",
  "conta_corrente": "1234567",
  "convenio": "100",
  "carteira": "10",           // APENAS 10 ou 20
  "nosso_numero": "12345678"
}
```

**Particularidades:**
- ✅ Código de barras, linha digitável e nosso número formatado
- ✅ PIX híbrido — pelo campo `chave_pix` (`emv`/`pix_label` respondem 400)
- ✅ Templates: `moderno` (default) e `classico` — `prawn` e `carne` **não existem**
- ❌ CNAB 240 **não** suportado
- ⚠️ `digito_conta` é filtrado pela API (a engine não aceita no boleto do C6)

**Exemplo completo — valida:**
```python
dados_c6 = {
    "cedente": "Empresa C6 LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Pedro Almeida",
    "sacado_documento": "11144477735",
    "sacado_endereco": "Av. Faria Lima, 1500, Itaim Bibi, São Paulo, SP, CEP 04538133",
    "agencia": "0001",
    "conta_corrente": "1234567",
    "carteira": "10",
    "convenio": "100",
    "nosso_numero": "12345678",
    "numero_documento": "INV-2026-001",
    "valor": 2750.00,
    "data_vencimento": "2026/12/31",
    "aceite": "N"
}

requests.get(f"{API_URL}/api/boleto", params={
    "bank": "banco_c6", "type": "pdf", "data": json.dumps(dados_c6)
})
```

#### 7.2 Remessa CNAB 400 (POST /api/remessa)

> **Atenção:** o payload de remessa usa campos **diferentes** dos de boleto, e a
> remessa vai como **multipart** (campo `data`), não como corpo JSON.

```json
{
  "empresa_mae": "Empresa C6 LTDA",
  "documento_cedente": "11222333000181",
  "agencia": "0001",
  "conta_corrente": "1234567",
  "digito_conta": "0",
  "carteira": "10",
  "codigo_beneficiario": "0012345678",
  "pagamentos": [...]
}
```

- ✅ `codigo_beneficiario` — código do cedente fornecido pelo C6 (até 10 dígitos)
- ❌ `convenio` — **não** existe na classe de remessa do C6
- ❌ CNAB 240 — não suportado para C6

**Campos do pagamento (remessa):**
```json
{
  "nosso_numero": "12345678",
  "data_vencimento": "2026/12/31",
  "valor": 1500.00,
  "nome_sacado": "Joao da Silva",       // `sacado` também é aceito
  "documento_sacado": "11144477735",    // `sacado_documento` também é aceito
  "endereco_sacado": "Rua Teste, 100",
  "bairro_sacado": "Centro",
  "cep_sacado": "01000000",
  "cidade_sacado": "Sao Paulo",
  "uf_sacado": "SP"
}
```

---

## 🔧 O que `GET /api/boleto/data` devolve

A resposta tem **seis** campos, e só isso:

| Campo | Sempre presente? | Observação |
|-------|:---:|---|
| `bank` | ✅ | slug do banco |
| `codigo_barras` | ✅ | 44 posições |
| `linha_digitavel` | ✅ | formatada, com espaços |
| `nosso_numero` | ✅ | como foi enviado |
| `nosso_numero_formatado` | ✅ | como sai impresso no boleto |
| `nosso_numero_dv` | ⚠️ | **vazio** em BB e Sicoob; preenchido em Bradesco, Caixa, Santander e C6 |

> Conferido nos sete bancos das seções acima. Versões anteriores desta página
> traziam duas tabelas de "métodos" em vocabulário da gem Ruby — `valid?`,
> `to_pdf`, `respond_to?`, `rescue nil` —, que descreviam o interior de uma
> biblioteca que não é mais usada e nunca foram o contrato da API.

---

## 🧪 Testes

```bash
cd gateway && PYTHONPATH=. pytest              # suíte completa
cd gateway && PYTHONPATH=. pytest -k offline   # só o caminho offline
python postman/check_coverage.py               # cobertura da coleção
```

> As instruções antigas mandavam `bundle exec rspec spec/all_banks_spec.rb`. Não
> existe `bundle`, `rspec` nem `spec/` neste repositório desde a 2.0.0 — o
> serviço é Python e os testes são pytest.

---

## ⚠️ Notas Importantes

### 1. `numero_documento` — o nome é um só

Não há mapeamento: o campo se chama `numero_documento` na API e na engine.

O nome antigo `documento_numero` vinha da gem Ruby (BRCobrança), que não é mais
usada. Enviá-lo hoje **não dá erro** — o campo simplesmente não chega, e o
boleto sai com ele vazio.

### 2. Campos de Boleto ≠ Campos de Remessa

| Contexto | Campo do sacado | Campo do documento |
|----------|-----------------|--------------------|
| **Boleto** (`GET /api/boleto`) | `sacado` | `sacado_documento` |
| **Remessa** (`POST /api/remessa`) | `nome_sacado` | `documento_sacado` |

> Na **remessa** as duas grafias funcionam: `sacado`/`sacado_documento` geram o
> mesmo arquivo que `nome_sacado`/`documento_sacado` (conferido comparando o
> CNAB dos dois). `nome_sacado` é o nome preferido por ser o do layout.

### 3. Campos Específicos por Banco — Remessa

| Banco | Formato | Campos obrigatórios extras | Campos que NÃO vão na remessa |
|-------|---------|---------------------------|-------------------------------|
| Banco do Brasil | CNAB400 + CNAB240 | `convenio`, `carteira`, `variacao_carteira` | — |
| Sicoob | CNAB240 | `convenio`, `carteira` | `variacao` |
| Bradesco | CNAB400 | `carteira`, `digito_conta` | — |
| Caixa | CNAB240 | `convenio`, `digito_conta` | — |
| Santander | CNAB400 + CNAB240 | `digito_conta` | — |
| **Banco C6** | **CNAB400** | `carteira`, `codigo_beneficiario` | `convenio` |

### 4. CPF e CNPJ são validados

Dígito verificador conferido: documento inventado volta `400` com
`cedente_documento inválido (CPF/CNPJ)`. Os exemplos desta página usam
documentos com DV correto justamente para poderem ser copiados e rodados.

### 5. O mito da linha digitável do Sicoob

Versões anteriores desta página afirmavam, em quatro lugares, que o Sicoob podia
devolver `linha_digitavel: null` em `/api/boleto/data`, e sugeriam contornos.
**Não devolve.** Conferido:

```
sicoob -> 75691.43279 01022.938516 23456.790015 8 16770000150000
```

Todos os sete bancos testados devolvem linha digitável preenchida. A ressalva
saiu — e com ela a coluna ⚠️ que ela justificava no resumo.

---

## 📊 Resumo de Compatibilidade

| Recurso | BB | Sicoob | Bradesco | Itaú | Caixa | Santander | C6 |
|---------|----|----|----------|------|-------|-----------|----|
| Validação | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PDF | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `linha_digitavel` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `codigo_barras` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `nosso_numero_dv` | — | — | ✅ | ✅ | ✅ | ✅ | ✅ |

**Legenda:** ✅ = disponível · — = vem vazio (não é erro)

---

## 🔗 Referências

- [Guia de Campos](./README.md) — obrigatórios, opcionais e o que a engine valida
- [Nosso Número](./nosso-numero.md) — entrada, saída e conciliação
- [Exemplos Python](https://github.com/Maxwbh/cobranca-api/tree/main/examples/python)
- [Engine pyCobrança](https://github.com/Maxwbh/pyCobranca) — quem gera o boleto

---

**Última atualização:** 2026-08-19
**Método:** cada carteira, limite e campo desta página foi executado contra a
engine; onde a página antiga discordava da engine, a engine ganhou.
