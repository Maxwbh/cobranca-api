# Nosso Numero

> 🕒 Revisado em 2026-08-19 **medindo cada valor** contra a engine. Onde esta
> página mostra uma saída, ela foi capturada de `GET /api/boleto/data` — não
> escrita de memória.

## Campos da API

A API retorna 3 campos para cada boleto gerado:

| Campo | Descricao | Exemplo (BB, convênio `1234567`) |
|-------|-----------|:-------------|
| `nosso_numero` | **O valor como você enviou** — sem padding | `"123"` |
| `nosso_numero_formatado` | Valor impresso no boleto | `"12345670000000123"` |
| `nosso_numero_dv` | Digito verificador | `""` (vazio no BB) |

> ⚠️ **`nosso_numero` volta igual ao que entrou.** A versão anterior desta
> página descrevia o campo como "valor padronizado" e mostrava `"000000123"`
> para uma entrada `"123"` — a engine não faz esse preenchimento. Quem
> guardasse o valor esperando zeros à esquerda erraria a conciliação no
> primeiro boleto. O padding existe, sim, mas dentro do
> `nosso_numero_formatado`.
>
> ⚠️ **`nosso_numero_dv` vem vazio em BB e Sicoob** — não é erro, é o layout
> desses bancos: o DV já está embutido no formatado.

**Enviar na requisicao:** apenas `nosso_numero` (valor curto, sem formatacao).

**Receber na resposta:** os 3 campos acima.

## Exemplo

```bash
# Enviar (convênio do BB tem 4, 6 ou 7 dígitos — nunca 8)
curl "http://localhost:8000/api/boleto/data?bank=banco_brasil&data={\"nosso_numero\":\"123\",\"convenio\":\"1234567\",...}"
```

```json
{
  "bank": "banco_brasil",
  "nosso_numero": "123",
  "nosso_numero_formatado": "12345670000000123",
  "nosso_numero_dv": "",
  "codigo_barras": "00198167700001500000000001234567000000012318",
  "linha_digitavel": "00190.00009 01234.567004 00000.123182 8 16770000150000"
}
```

## Formato por Banco

Capturado da engine, com o `nosso_numero` da coluna "Entrada":

| Banco | Entrada | `nosso_numero` | `nosso_numero_formatado` | `nosso_numero_dv` |
|-------|---------|----------------|--------------------------|:-----------------:|
| Banco do Brasil (001) | `"123"` | `"123"` | `"12345670000000123"` | *(vazio)* |
| Sicoob (756) | `"7890"` | `"7890"` | `"00078900"` | *(vazio)* |
| Bradesco (237) | `"12345"` | `"12345"` | `"09/00000012345-8"` | `8` |
| Itau (341) | `"12345678"` | `"12345678"` | `"175/12345678-4"` | `4` |
| Caixa (104) | `"000000000000001"` | `"000000000000001"` | `"14000000000000001-4"` | `4` |
| Santander (033) | `"1234567"` | `"1234567"` | `"000001234567-9"` | `9` |
| Banco C6 (336) | `"12345678"` | `"12345678"` | `"0012345678-9"` | `9` |

### Composicao do `nosso_numero_formatado`

| Banco | Formato |
|-------|---------|
| BB | `convenio(7)` + `nosso_numero(10)` — 17 posições |
| Sicoob | `nosso_numero(7)` + `DV(1)` |
| Bradesco | `carteira(2)` / `nosso_numero(11)` - `DV(1)` |
| Itau | `carteira(3)` / `nosso_numero(8)` - `DV(1)` |
| Caixa | `carteira(2)` + `nosso_numero(15)` - `DV(1)` |
| Santander | `nosso_numero(12)` - `DV(1)` |
| C6 | `nosso_numero(10)` - `DV(1)` |

## Tamanho Maximo

Medido subindo o tamanho até a engine recusar:

| Banco | Maximo | Observacao |
|-------|:------:|------------|
| BB | **10** | com convênio de 7 dígitos — veja abaixo |
| Sicoob | 7 | |
| Bradesco | 11 | |
| Itau | 8 | e a **conta** tem no máximo 5 dígitos |
| Caixa | 15 | Sempre 15 digitos |
| Santander | **12** | |
| C6 | 10 | |

**No BB o teto depende do convênio:**

- Convênio 4 dígitos → máx **7**
- Convênio 6 dígitos → máx **5** (ou 17 com `codigo_servico`)
- Convênio 7 dígitos → máx **10**

> ⚠️ Duas correções sobre a versão anterior: o Santander aceita **12**, não 7 —
> e o BB não tem um teto único de 17. Passar do limite devolve
> `nosso número deve ter no máximo N dígitos`.

## Uso em Cada Fluxo

### Gerar Boleto

Envie o valor curto. A API formata automaticamente.

**Opcao 1 — JSON com dados (sem PDF):**
```python
dados = {"nosso_numero": "123", ...}
response = requests.get(f"{API}/api/boleto/data", params={"bank": "banco_brasil", "data": json.dumps(dados)})
data = response.json()
nn     = data['nosso_numero']              # "123"
nn_fmt = data['nosso_numero_formatado']    # "12345670000000123"
nn_dv  = data['nosso_numero_dv']           # "" no BB
```

**Opcao 2 — PDF + dados em headers (1 chamada):**
```python
response = requests.get(f"{API}/api/boleto", params={
    "bank": "banco_brasil", "type": "pdf", "data": json.dumps(dados)
})
pdf_bytes = response.content
nn     = response.headers['X-Nosso-Numero']            # "123"
nn_fmt = response.headers['X-Nosso-Numero-Formatado']  # "12345670000000123"
nn_dv  = response.headers['X-Nosso-Numero-DV']         # "" no BB
```

São **cinco** headers, não três — o PDF vem acompanhado também de
`X-Codigo-Barras` e `X-Linha-Digitavel`, o que costuma dispensar a segunda
chamada ao `/data`.

**Opcao 3 — JSON com dados + PDF em base64 (1 chamada, recomendada):**
```python
import base64
response = requests.get(f"{API}/api/boleto", params={
    "bank": "banco_brasil", "type": "pdf",
    "data": json.dumps(dados), "include_data": "true"
})
result = response.json()
nn     = result['nosso_numero']             # "123"
nn_fmt = result['nosso_numero_formatado']   # "12345670000000123"
pdf    = base64.b64decode(result['content_base64'])
```

### Multiplos Boletos

> ⚠️ **`type` e `include_data` são parâmetros de QUERY, não campos do
> formulário.** Mandados em `data={...}` eles são ignorados em silêncio — e o
> `include_data` ignorado significa receber **PDF** onde se esperava JSON, sem
> erro nenhum para denunciar. Use `params=`.

**Opcao 1 — PDF + metadados em headers:**
```python
response = requests.post(f"{API}/api/boleto/multi",
    params={"type": "pdf"},
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
    params={"type": "pdf", "include_data": "true"},
    files={"data": open("boletos.json", "rb")}
)
result = response.json()
total = result['total']            # + completed, failed, erros, status
boletos = result['boletos']        # {bank, indice, item_id, status, nosso_numero, ...}
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

O `nosso_numero` vem do campo MEMO via regex, e a rota recebe o arquivo no
campo **`file`**:

```python
r = requests.post(f"{API}/api/ofx/parse", files={"file": open("extrato.ofx", "rb")})
for t in r.json()["transacoes"]:
    print(t["memo"], "->", t["nosso_numero"])
```

```
COBRANCA SICOOB 0000012345 -> "0000012345"
PAGAMENTO CONTA LUZ        -> None
```

> ⚠️ **`nosso_numero` é `null` quando o MEMO não traz número** — tarifa, TED,
> cashback. Comparar sem checar antes quebra com `TypeError`, e num extrato real
> a maioria das linhas não é boleto.

O formato do que aparece no MEMO depende do banco:

| Banco | O que aparece no OFX | Corresponde a |
|-------|---------------------|---------------|
| BB | `"12345670000000123"` (17 dig) | `nosso_numero_formatado` |
| Sicoob | `"00078900"` (8 dig) | `nosso_numero_formatado` |
| Itau | `"12345678"` (8 dig) | `nosso_numero` |
| Bradesco | `"00000012345"` (11 dig) | `nosso_numero` |
| Caixa | `"14000000000000001"` (17 dig) | `nosso_numero_formatado` (sem DV) |
| Santander | `"1234567"` (7 dig) | `nosso_numero` |
| C6 | `"0012345678"` (10 dig) | `nosso_numero` |

> Esta tabela vem de extratos observados, não da engine: o MEMO é texto livre
> que cada banco preenche como quer. Trate-a como ponto de partida e confirme
> com o extrato do seu convênio.

### Conciliacao

Armazene `nosso_numero` e `nosso_numero_formatado` ao gerar o boleto. Para
conciliar:

```python
nn = boleto_salvo['nosso_numero']                 # "123"
nn_fmt = boleto_salvo['nosso_numero_formatado']   # "12345670000000123"

# Retorno CNAB
match_cnab = int(retorno['nosso_numero']) == int(nn)

# OFX — o campo pode ser None
nn_ofx = transacao['nosso_numero']
match_ofx = bool(nn_ofx) and (
    nn_ofx == nn_fmt or nn_ofx == nn or nn_ofx.lstrip("0") == nn.lstrip("0")
)
```

> Guardar os **dois** campos é o que faz a conciliação funcionar nos dois
> caminhos: o CNAB devolve o valor curto com zeros, e boa parte dos extratos
> traz o formatado.

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) — M&S do Brasil LTDA
