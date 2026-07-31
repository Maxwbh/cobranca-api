# Nosso Numero

## Campos da API

A API retorna 3 campos para cada boleto gerado:

| Campo | Descricao | Exemplo (BB) |
|-------|-----------|:-------------|
| `nosso_numero` | Valor padronizado | `"000000123"` |
| `nosso_numero_formatado` | Valor impresso no boleto | `"01234567000000123"` |
| `nosso_numero_dv` | Digito verificador | `"9"` |

**Enviar na requisicao:** apenas `nosso_numero` (valor curto, sem formatacao).

**Receber na resposta:** os 3 campos acima.

## Exemplo

```bash
# Enviar
curl "http://localhost:9292/api/boleto/data?bank=banco_brasil&data={\"nosso_numero\":\"123\",\"convenio\":\"01234567\",...}"
```

```json
{
  "nosso_numero": "000000123",
  "nosso_numero_formatado": "01234567000000123",
  "nosso_numero_dv": "9",
  "codigo_barras": "00196131200001500...",
  "linha_digitavel": "00190.00009 00123..."
}
```

## Formato por Banco

| Banco | Entrada | `nosso_numero` | `nosso_numero_formatado` | `nosso_numero_dv` |
|-------|---------|----------------|--------------------------|:-----------------:|
| Banco do Brasil (001) | `"123"` | `"000000123"` | `"01234567000000123"` | `9` |
| Sicoob (756) | `"7890"` | `"0007890"` | `"00078900"` | `0` |
| Bradesco (237) | `"12345"` | `"00000012345"` | `"09/00000012345-8"` | `8` |
| Itau (341) | `"12345678"` | `"12345678"` | `"175/12345678-4"` | `4` |
| Caixa (104) | `"000000000000001"` | `"000000000000001"` | `"14000000000000001-4"` | `4` |
| Santander (033) | `"1234567"` | `"1234567"` | `"1234567-9"` | `9` |
| Banco C6 (336) | `"12345678"` | `"0012345678"` | `"0012345678-9"` | `9` |

### Composicao do `nosso_numero_formatado`

| Banco | Formato |
|-------|---------|
| BB | `convenio(8)` + `nosso_numero(9)` |
| Sicoob | `nosso_numero(7)` + `DV(1)` |
| Bradesco | `carteira(2)` / `nosso_numero(11)` - `DV(1)` |
| Itau | `carteira(3)` / `nosso_numero(8)` - `DV(1)` |
| Caixa | `carteira(2)` + `nosso_numero(15)` - `DV(1)` |
| Santander | `nosso_numero(7)` - `DV(1)` |
| C6 | `nosso_numero(10)` - `DV(1)` |

## Tamanho Maximo

| Banco | Maximo | Observacao |
|-------|:------:|------------|
| BB | 17 | Depende do tamanho do convenio |
| Sicoob | 7 | |
| Bradesco | 11 | |
| Itau | 8 | |
| Caixa | 15 | Sempre 15 digitos |
| Santander | 7 | |
| C6 | 10 | |

## Uso em Cada Fluxo

### Gerar Boleto

Envie o valor curto. A API formata automaticamente.

**Opcao 1 — JSON com dados (sem PDF):**
```python
dados = {"nosso_numero": "123", ...}
response = requests.get(f"{API}/api/boleto/data", params={"bank": "banco_brasil", "data": json.dumps(dados)})
data = response.json()
nn     = data['nosso_numero']             # "000000123"
nn_fmt = data['nosso_numero_formatado']    # "01234567000000123"
nn_dv  = data['nosso_numero_dv']           # 9
```

**Opcao 2 — PDF + dados em headers (1 chamada):**
```python
response = requests.get(f"{API}/api/boleto", params={
    "bank": "banco_brasil", "type": "pdf", "data": json.dumps(dados)
})
pdf_bytes = response.content
nn     = response.headers['X-Nosso-Numero']            # "000000123"
nn_fmt = response.headers['X-Nosso-Numero-Formatado']  # "01234567000000123"
nn_dv  = response.headers['X-Nosso-Numero-DV']         # "9"
```

**Opcao 3 — JSON com dados + PDF em base64 (1 chamada, recomendada):**
```python
import base64
response = requests.get(f"{API}/api/boleto", params={
    "bank": "banco_brasil", "type": "pdf",
    "data": json.dumps(dados), "include_data": "true"
})
result = response.json()
nn     = result['nosso_numero']             # "000000123"
nn_fmt = result['nosso_numero_formatado']    # "01234567000000123"
nn_dv  = result['nosso_numero_dv']           # 9
pdf    = base64.b64decode(result['content_base64'])
```

### Multiplos Boletos

**Opcao 1 — PDF + metadados em headers:**
```python
response = requests.post(f"{API}/api/boleto/multi",
    data={"type": "pdf"},
    files={"data": open("boletos.json", "rb")}
)
pdf_bytes = response.content
total = int(response.headers['X-Boletos-Count'])
info = json.loads(response.headers['X-Boletos-Info'])
# info[i] = {"bank":..., "nosso_numero":..., "nosso_numero_formatado":..., ...}
```

**Opcao 2 — JSON com tudo (recomendada):**
```python
response = requests.post(f"{API}/api/boleto/multi",
    data={"type": "pdf", "include_data": "true"},
    files={"data": open("boletos.json", "rb")}
)
result = response.json()
total = result['total']
boletos = result['boletos']  # array com {bank, nosso_numero, nosso_numero_formatado, ...}
pdf = base64.b64decode(result['content_base64'])
```

### Remessa CNAB

Envie o mesmo valor curto no campo `pagamentos[].nosso_numero`.

```json
{"pagamentos": [{"nosso_numero": "123", "valor": 100.0, ...}]}
```

### Retorno CNAB

O banco retorna `nosso_numero` com zeros a esquerda. Para conciliar:

```python
match = int(retorno['nosso_numero']) == int(seu_boleto['nosso_numero'])
```

### Extrato OFX

O `nosso_numero` vem do campo MEMO via regex. O formato depende do banco:

| Banco | O que aparece no OFX | Corresponde a |
|-------|---------------------|---------------|
| BB | `"01234567000000123"` (17 dig) | `nosso_numero_formatado` |
| Sicoob | `"00078900"` (8 dig) | `nosso_numero_formatado` |
| Itau | `"12345678"` (8 dig) | `nosso_numero` |
| Bradesco | `"00000012345"` (11 dig) | `nosso_numero` |
| Caixa | `"14000000000000001"` (17 dig) | `nosso_numero_formatado` (sem DV) |
| Santander | `"1234567"` (7 dig) | `nosso_numero` |
| C6 | `"0012345678"` (10 dig) | `nosso_numero` |

### Conciliacao

Armazene `nosso_numero` e `nosso_numero_formatado` ao gerar o boleto. Para conciliar:

```python
nn = boleto_salvo['nosso_numero']           # "000000123"
nn_fmt = boleto_salvo['nosso_numero_formatado']  # "01234567000000123"

# Retorno CNAB
match_cnab = int(retorno['nosso_numero']) == int(nn)

# OFX
nn_ofx = transacao['nosso_numero']
match_ofx = nn_ofx == nn_fmt or nn_ofx == nn or int(nn_ofx) == int(nn)
```

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) — M&S do Brasil LTDA
