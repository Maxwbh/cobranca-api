# Parsing de Arquivos OFX

> **Endpoint:** `POST /api/ofx/parse` | versão do serviço em `GET /api/metadata`
> 🕒 Revisado em 2026-08-19 executando o endpoint: o JSON abaixo é resposta
> capturada, não redigida.

Guia completo do endpoint de parsing de extratos bancários OFX.

## Visão Geral

O endpoint `POST /api/ofx/parse` recebe um arquivo OFX (extrato bancário) e retorna um JSON estruturado com todas as transações, saldo, dados do banco e resumo.

### Recursos

- ✅ Suporte a OFX v1 (SGML) e v2 (XML)
- ✅ Conversão automática de encoding Latin-1 → UTF-8 (padrão em bancos brasileiros)
- ✅ Extração automática de `nosso_numero` do campo memo por banco
- ✅ Filtro opcional `somente_creditos=true`
- ✅ Resumo com totais de créditos e débitos

## Request

### Headers

```
Content-Type: multipart/form-data
```

### Parâmetros

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `file` | File | Sim | Arquivo OFX (extrato bancário) |
| `somente_creditos` | String | Não | `'true'` ou `'false'` (padrão `'false'`) |

### Exemplo com cURL

```bash
# Upload básico
curl -X POST http://localhost:8000/api/ofx/parse \
  -F "file=@extrato.ofx"

# Com filtro de créditos
curl -X POST http://localhost:8000/api/ofx/parse \
  -F "file=@extrato.ofx" \
  -F "somente_creditos=true"
```

### Exemplo com Python

```python
import requests

with open('extrato.ofx', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/ofx/parse',
        files={'file': f},
        data={'somente_creditos': 'true'}
    )

data = response.json()
print(f"Banco: {data['banco']['org']}")
print(f"Total créditos: {data['resumo']['total_creditos']}")

for tx in data['transacoes']:
    if tx['nosso_numero']:
        print(f"  → {tx['data']} R$ {tx['valor']} nn={tx['nosso_numero']}")
```

## Response

### 201 Created

```json
{
  "banco": {
    "org": "SICOOB",
    "fid": "756"
  },
  "conta": {
    "agencia": "3044",
    "numero": "12345-6",
    "tipo": "CHECKING"
  },
  "periodo": {
    "inicio": "2025-01-15",
    "fim": "2025-01-25"
  },
  "saldo": {
    "valor": 15420.5,
    "data": "2025-01-31"
  },
  "transacoes": [
    {
      "tipo": "credito",
      "valor": 1250.0,
      "data": "2025-01-15",
      "memo": "COBRANCA SICOOB 0000012345",
      "id": "202501150001",
      "nosso_numero": "0000012345"
    },
    {
      "tipo": "debito",
      "valor": 350.5,
      "data": "2025-01-16",
      "memo": "PAGAMENTO CONTA LUZ",
      "id": "202501160001",
      "nosso_numero": null
    }
  ],
  "resumo": {
    "total_creditos": 3750.0,
    "total_debitos": 530.5,
    "quantidade": 4
  }
}
```

> ⚠️ **Três nomes desta resposta mudaram de significado em relação à versão
> anterior desta página** — e um deles em silêncio:
>
> | A página dizia | O que a API devolve |
> |---|---|
> | `fitid` | **`id`** |
> | `tipo: "CREDIT"` / `"DEBIT"` | **`credito`** / **`debito`** (minúsculo) |
> | `name`, `checknum`, `refnum` | **não existem** na resposta |
> | `total_creditos` = **contagem** | `total_creditos` = **soma em reais** |
> | `soma_creditos`, `soma_debitos`, `total_transacoes` | não existem — use `total_creditos`, `total_debitos`, `quantidade` |
>
> O pior é o `total_creditos`: existe nos dois, com o mesmo nome, significando
> coisas diferentes. O exemplo Python desta própria página lia
> `resumo['soma_creditos']` e receberia `KeyError`.
>
> **`valor` é sempre positivo.** A direção está em `tipo` — não some valores
> confiando no sinal.

### 400 Bad Request

```json
{
  "erro": "Arquivo OFX inválido",
  "validation_errors": ["Arquivo OFX inválido: conteúdo não parece um OFX (faltam <OFX>/OFXHEADER)"]
}
```

### 422 Unprocessable Entity — campo `file` ausente

Não é um 400 no formato acima: é o erro de validação do FastAPI.

```json
{"detail": [{"type": "missing", "loc": ["body", "file"], "msg": "Field required", "input": null}]}
```

## Extração de nosso_numero por Banco

O campo `nosso_numero` é preenchido quando o banco é reconhecido e o memo contém uma sequência numérica que bate com o padrão do banco.

| Banco | Identificador (ORG/FID) | Regex | Exemplo memo |
|-------|-------------------------|-------|--------------|
| **Sicoob** | `SICOOB` / `756` | `\d{7,12}` | `COBRANCA SICOOB 0000012345` → `0000012345` |
| **Itaú** | `ITAU` / `341` | `\d{8}` | `RECEBIMENTO BOLETO 12345678` → `12345678` |
| **Banco do Brasil** | `BRASIL` / `001` | `\d{10,17}` | `BB COBRANCA 1234567890` → `1234567890` |
| **Bradesco** | `BRADESCO` / `237` | `\d{11}` | `BRADESCO COB 12345678901` → `12345678901` |
| **Caixa** | `CAIXA` / `104` | `\d{14,17}` | `CAIXA 12345678901234` → `12345678901234` |
| **Outros** | (qualquer) | `\d{7,17}` | Captura a primeira sequência de 7-17 dígitos |

Se o memo não contém dígitos suficientes, `nosso_numero` é `null`. **Conferido
contra a engine**: os seis padrões acima são exatamente os que ela aplica.

O banco é reconhecido casando o padrão contra **ORG ou FID**, sem diferenciar
maiúsculas — o Itaú também casa com `ITA`. E `null` é o caso comum, não a
exceção: no extrato de teste, metade dos lançamentos (tarifa, TED) não traz
número nenhum.

## Crédito × débito

`tipo` vale `credito` ou `debito`, e **`valor` é sempre positivo** — a direção
está no `tipo`, nunca no sinal.

```json
{"tipo": "credito", "valor": 1250.0, "memo": "COBRANCA SICOOB 0000012345"}
{"tipo": "debito",  "valor": 350.5,  "memo": "PAGAMENTO CONTA LUZ"}
```

O `resumo` soma cada lado em reais:

```json
{"total_creditos": 3750.0, "total_debitos": 530.5, "quantidade": 4}
```

> ⚠️ **Até a 2.2.0 isto vinha errado.** A engine normaliza o valor para positivo
> e guarda a direção no TRNTYPE; o serviço deduzia do sinal, que nunca é
> negativo depois da normalização. Resultado: **toda** transação saía como
> `credito` e `total_debitos` era eternamente `0` — um pagamento de R$ 350,50
> entrava na soma do que a conta recebeu. Se você concilia por este endpoint e
> guardou totais, vale reprocessar.

`somente_creditos=true` (campo do **formulário**, não query string) descarta os
débitos antes de somar.

## Encoding

Bancos brasileiros tipicamente enviam OFX em **Latin-1 (ISO-8859-1)**. O service:

1. Tenta ler como UTF-8 primeiro
2. Se inválido, converte de Latin-1 para UTF-8
3. Em último caso, decodifica byte a byte substituindo o que não mapear

Isso garante que caracteres especiais (`ç`, `ã`, `é`, etc) são preservados corretamente no JSON de resposta.

## Formatos Suportados

### OFX v1 (SGML)

Formato padrão de bancos brasileiros. Começa com headers do tipo:

```
OFXHEADER:100
DATA:OFXSGML
VERSION:102
```

### OFX v2 (XML)

Formato moderno baseado em XML. Começa com declaração XML:

```xml
<?xml version="1.0"?>
<?OFX OFXHEADER="200" VERSION="200"?>
```

Ambos são suportados pela engine pyCobrança, que lê o arquivo sem dependência externa.

## Troubleshooting

### Erro: "Arquivo OFX inválido ou não reconhecido"

- Verifique se o arquivo é um OFX válido (v1 SGML ou v2 XML)
- Tente abrir em um visualizador de OFX para confirmar a estrutura
- Arquivos .ret (retorno CNAB) NÃO são OFX — use `/api/retorno`

### Erro: "file is missing"

- O campo deve se chamar exatamente `file` (case-sensitive)
- Use `multipart/form-data`, não `application/json`

### `nosso_numero` sempre null

- Confirme que o banco é reconhecido (campo `banco.org`/`banco.fid` no response)
- Verifique se o memo contém a sequência numérica esperada
- Para bancos não suportados diretamente, o fallback genérico (7-17 dígitos) é aplicado

### Caracteres com encoding errado (�, ?)

- Geralmente significa que o arquivo original tem encoding diferente de Latin-1/UTF-8
- Abra o arquivo em um editor e confirme o encoding
- Reporte o issue com um arquivo de exemplo

## Response Schema (OpenAPI)

Veja [openapi.yaml](../openapi.yaml) — schemas `OfxResponse`, `OfxTransacao` e `OfxError`.

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) - M&S do Brasil LTDA
