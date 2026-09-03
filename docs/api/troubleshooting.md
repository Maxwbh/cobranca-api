# Troubleshooting — Cobranca-API

> Versão do serviço: `GET /api/metadata`.
> 🕒 Revisado em 2026-08-19 **provocando cada erro** desta página contra a API e
> colando a resposta real. Onde a página antiga previa um corpo de erro que o
> serviço não devolve mais, o corpo foi substituído pelo verdadeiro — errar o
> formato do erro é pior do que não documentá-lo, porque o cliente escreve
> tratamento para uma chave que nunca chega.

Este guia ajuda a resolver problemas comuns ao usar a API.

## Índice

- [Logging](#logging)
- [Deploy no Render.com](#deploy-no-rendercom)
- [Erros Comuns — Boletos](#erros-comuns--boletos)
- [Erros Comuns — Remessa CNAB](#erros-comuns--remessa-cnab)
- [Erros Comuns — Retorno CNAB](#erros-comuns--retorno-cnab)
- [Erros Comuns — OFX](#erros-comuns--ofx)
- [Checklist de Debug](#checklist-de-debug)

## Logging

O log é o **access log do uvicorn**, no formato padrão dele:

```
INFO:     127.0.0.1:52344 - "POST /api/ofx/parse HTTP/1.1" 201 Created
INFO:     127.0.0.1:52346 - "GET /api/boleto HTTP/1.1" 400 Bad Request
```

O nível sai de `LOG_LEVEL` (`critical`, `error`, `warning`, `info`, `debug`,
`trace`; a caixa não importa). Valor inválido **não derruba o serviço**: o
container avisa e assume `info`.

> ⚠️ A versão anterior desta página descrevia log estruturado em JSON, com um
> middleware `RequestLogger` e um `ErrorHandler` emitindo linhas
> `[ERROR] [400] ValidationError: ...`. Nada disso existe no serviço Python —
> era o formato do Banking Core Ruby. Quem montasse alerta em cima de
> `event: "request_end"` não veria evento nenhum.

## Deploy no Render.com

### Logs não aparecem no dashboard do Render

**Causa:** em container, o Python bufferiza `stdout`/`stderr` em blocos. Os
logs só aparecem quando o buffer enche — o que em baixo volume pode demorar
muito ou nunca acontecer.

**Solução (já aplicada):** o `Dockerfile` define `PYTHONUNBUFFERED=1`, que
desliga o buffer do interpretador. O uvicorn escreve direto no stdout do
container.

**Verificação local:**
```bash
docker run --rm cobranca-api python -c "import sys; print(sys.stdout.line_buffering)"
docker logs -f <container>   # deve sair linha a linha
```

**Se ainda assim não aparecer:**
1. Confirme `PYTHONUNBUFFERED=1` (`docker inspect` → `Config.Env`)
2. Force rebuild no Render (Manual Deploy → Clear build cache & deploy)
3. No dashboard, clique em "Logs" e role para cima (Render mostra as últimas
   1000 linhas)

### HTTP 429 — Too Many Requests (cold start)

**Causa:** Isto **não é rate limiting da API** — a API não possui rate limiting. O 429 vem do próprio **Render.com free tier**:

1. **Cold start (sleep mode):** Após 15 minutos de inatividade, o Render suspende o serviço. A primeira request pode demorar 30-60s para acordar.
2. **Durante o wake up, requests subsequentes podem receber 429 ou 503** enquanto o serviço se inicializa.
3. Se o cliente envia múltiplas requests em paralelo ou em sequência rápida, as primeiras acordam o serviço e as seguintes podem receber 429 enquanto o wake está em progresso.

**Exemplo no log do cliente:**
```
ERROR ... Erro Cobranca-API: 429 - Too Many Requests
ERROR ... Erro Cobranca-API: 429 - Too Many Requests  (480ms depois)
```

**Soluções:**

| Opção | Custo | Descrição |
|-------|-------|-----------|
| **1. Retry com backoff no cliente** | Grátis | Implementar retry exponencial (1s, 2s, 4s, 8s) até 4 tentativas |
| **2. Ping service (manter acordado)** | Grátis | Usar [cron-job.org](https://cron-job.org) ou [UptimeRobot](https://uptimerobot.com) para pingar `/api/health` a cada **10 minutos** (14 min fica no limite do sleep de 15 min). Há também o workflow `.github/workflows/keepalive.yml` |
| **3. Upgrade para Starter ($7/mês)** | Pago | Elimina sleep mode e aumenta RAM para 2GB |

**Exemplo de retry em Python (no cliente):**

```python
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(
    total=4,
    backoff_factor=1,           # 1s, 2s, 4s, 8s
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=['GET', 'POST']
)
session.mount('https://', HTTPAdapter(max_retries=retry))

# Primeira chamada acorda o servidor
response = session.get('https://SEU-SERVICO.onrender.com/api/health', timeout=60)
```

**Exemplo de ping service (cron-job.org):**
- URL: `https://SEU-SERVICO.onrender.com/api/health`
- Intervalo: a cada 10 minutos
- Método: GET
- Timeout: 30s

## Erros Comuns — Boletos

### 1. Parâmetros do `/api/boleto`

| Parâmetro | Obrigatório? | Valores |
|-----------|:---:|---|
| `bank` | **sim** | `banco_brasil`, `sicoob`, … (18 slugs; veja `GET /api/bancos`) |
| `data` | **sim** | JSON com os dados do boleto |
| `type` | não | só **`pdf`** — e é o default, então dá para omitir |

> ⚠️ **`jpg`, `png` e `tif` foram descontinuados.** A página antiga os listava
> como formatos válidos; hoje qualquer um deles responde:
>
> ```json
> {"error": "Formato 'jpg' descontinuado — a engine pyCobranca gera PDF"}
> ```
>
> E `type` **não é obrigatório**: sem ele a rota devolve PDF do mesmo jeito.

**Chamada completa:**
```python
response = requests.get(
    f"{API_URL}/api/boleto",
    params={
        "bank": "sicoob",
        "type": "pdf",
        "data": json.dumps(boleto_data)
    }
)
```

### 2. JSON inválido no parâmetro `data`

**Response (400)** — o erro do JSON vem **dentro** de `validation_errors`, não
numa chave `details`:
```json
{
  "error": "Dados do boleto inválidos",
  "validation_errors": [
    "JSON inválido no parâmetro data: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"
  ],
  "hint": "Verifique se todos os campos obrigatórios estão preenchidos"
}
```

**Solução:** Use aspas duplas no JSON. Em Python, use `json.dumps()`.

### 3. Campos obrigatórios ausentes

**Response (400)** — `validation_errors` é uma **lista de frases**, não um
dicionário por campo:
```json
{
  "error": "Dados do boleto inválidos",
  "validation_errors": ["valor deve ser positivo", "data_vencimento é obrigatória"],
  "hint": "Verifique se todos os campos obrigatórios estão preenchidos"
}
```

> ⚠️ A página antiga mostrava `{"nosso_numero": ["não pode ficar em branco"]}` —
> formato de dicionário que a API nunca devolveu. Código que fizesse
> `erros["nosso_numero"]` quebra com `TypeError`.

**Solução:** Use `/api/boleto/validate` antes de gerar o PDF. Veja [fields/all-banks.md](../fields/all-banks.md) para campos obrigatórios por banco.

### 4. `numero_documento` — e o `documento_numero` que some em silêncio

- **`nosso_numero`** — faz parte do código de barras
- **`numero_documento`** — o nome do campo, na API **e** na engine
- **`documento_numero`** — nome antigo, da gem Ruby: **não é convertido**

> ⚠️ **Não há conversão automática.** A página antiga afirmava que a API
> traduzia `numero_documento` → `documento_numero`; hoje é o contrário, e nem
> há tradução: `documento_numero` é **descartado sem erro** e o boleto sai com
> o campo vazio.
>
> ```
> enviando numero_documento  -> numero_documento no boleto: 'NF-1'
> enviando documento_numero  -> numero_documento no boleto: ''
> ```

```python
# ✅ Correto
boleto_data = {
    "numero_documento": "NF-12345",
    "nosso_numero": "1234567",
}
```

### 5. Linha digitável "vazia" — quase sempre é outra coisa

Sem `nosso_numero`, a engine **não** deixa a linha vazia nem dá erro: ela gera
o boleto com o campo zerado.

```
com nosso_numero=123  -> 00190.00009 01234.567004 00000.123182 8 16770000150000
sem nosso_numero      -> 00190.00009 01234.567004 00000.000182 3 16770000150000
```

O documento sai com cara de válido e o banco não concilia. Se a linha "parece
errada", compare o trecho do nosso número antes de procurar defeito na
renderização.

**Debug:**
```python
# Validar antes de gerar
validate = requests.get(
    f"{API_URL}/api/boleto/validate",
    params={"bank": "sicoob", "data": json.dumps(boleto_data)}
)
print(validate.json())
```

### 6. `aceite` / `especie_documento` em branco

**Comportamento:** campos com valor padrão (`aceite`, `especie_documento`,
`especie`, `moeda`, `local_pagamento`) enviados **em branco** (`""`) caem
automaticamente no default da engine pyCobrança (`aceite='S'`, `especie_documento='DM'`,
`especie='R$'`, `moeda='9'`). Não é mais necessário omitir o campo — vazio e
ausente têm o mesmo efeito. Para usar outro valor, basta enviá-lo preenchido.

## Erros Comuns — Remessa CNAB

### 1. Formato CNAB incorreto

**Response (400)** — a mensagem lista **todas** as combinações banco/formato
suportadas, o que já responde a próxima pergunta:
```json
{
  "error": "Erro ao gerar remessa",
  "validation_errors": [
    "Remessa 240 não suportada para 'banco_brasil'. Suportadas: ailos/cnab240, banco_brasil/cnab240, banco_brasil/cnab240+pix, banco_brasil/cnab400, …"
  ]
}
```

**Solução:** Use `cnab240` ou `cnab400` (não apenas `240` ou `400`) no parâmetro `type`.

> A remessa vai como **multipart** (campo `data`), não como corpo JSON — corpo
> JSON responde `422 Field required: data`.

### 2. Pagamentos devem ser objetos

**Causa:** Envio de array vazio ou com formato incorreto.

**Solução:** Cada pagamento no array deve conter:
```json
{
  "nosso_numero": "123456789",
  "data_vencimento": "2026/12/31",
  "valor": 1500.00,
  "nome_sacado": "João da Silva",
  "documento_sacado": "11144477735"
}
```

> **`sacado`/`sacado_documento` também funcionam** — a engine aceita as duas
> grafias no pagamento, e o nome sai igual no arquivo (conferido gerando os dois
> e comparando o CNAB). O par `nome_sacado`/`documento_sacado` é o preferido por
> ser o que a documentação de remessa usa.

### 3. Campos obrigatórios no cabeçalho da remessa

Alguns bancos exigem campos específicos:

| Banco | Campo obrigatório |
|-------|-------------------|
| Sicoob (CNAB 240) | `convenio`, `modalidade` (o `variacao` é do boleto e é ignorado na remessa) |
| Banco do Brasil | `convenio` (4-7 dígitos) |
| Itaú | `carteira` |

Consulte [fields/all-banks.md](../fields/all-banks.md).

### 4. Remessa PIX — banco não suportado

**Response (400):**
```json
{"error": "Parâmetro inválido", "details": "Remessa PIX não disponível para banco 'banrisul' com formato 'cnab400'."}
```

**Solução:** Verifique a tabela de suporte PIX em [api/pix.md](./pix.md). Nem todo banco suporta PIX em todos os formatos CNAB.

### 5. Sicoob Layout 810

Para usar o layout alternativo onde o cliente calcula o DV, envie no payload da remessa Sicoob CNAB240:

```json
{"versao_layout_arquivo_opcao": "810", ...}
```

O valor padrão é `"081"`. O campo passa direto para a engine, sem configuração adicional na API.

### 6. Campos não suportados pela classe de remessa são ignorados

**Comportamento:** um campo que existe no **boleto** mas **não** na classe de
remessa do banco é **ignorado** (não gera erro). Exemplo: `variacao` é usado no
boleto Sicoob, mas não existe na remessa **CNAB 240** do Sicoob — enviar `variacao`
no payload CNAB 240 não quebra a geração. O mesmo vale para campos extras dentro
de cada `pagamento` (ex.: `cedente` vazado do nível de remessa): são descartados
em vez de causar `500`. Campos **obrigatórios** ausentes continuam retornando erro
de validação normalmente.

## Erros Comuns — Retorno CNAB

### 1. Banco ou tipo não encontrado

**Response (400):**
```json
{"error": "Banco ou tipo não encontrado", "details": "Classe de retorno não encontrada para banco 'xyz' e tipo 'cnab400'"}
```

**Solução:** Verifique se o banco suporta o tipo CNAB em [fields/all-banks.md](../fields/all-banks.md).

### 2. Arquivo vazio ou corrompido

**Debug:** Verifique tamanho do arquivo e primeiras linhas:
```bash
wc -l retorno.ret
head -3 retorno.ret
```

Arquivos CNAB 400 têm linhas de 400 caracteres; CNAB 240 tem 240 caracteres.

## Erros Comuns — OFX

### 1. Arquivo OFX inválido

**Response (400)** — note a chave `erro` (sem "r" no fim), diferente do `error`
das rotas de boleto:
```json
{
  "erro": "Arquivo OFX inválido",
  "validation_errors": ["Arquivo OFX inválido: conteúdo não parece um OFX (faltam <OFX>/OFXHEADER)"]
}
```

**Causa:** Arquivo não é um OFX válido ou está corrompido.

**Solução:**
- Confirme que é um arquivo `.ofx` (não `.ret` que é CNAB de retorno)
- Abra em um editor e verifique se começa com `OFXHEADER:` (v1) ou `<?xml` (v2)
- Tente abrir em um visualizador OFX (Money, GnuCash, etc)

### 2. Campo `file` ausente ou com nome errado

**Response (422)** — é o erro de validação do próprio FastAPI, com a chave
`detail`, e **não** um 400 no formato das outras rotas:
```json
{"detail": [{"type": "missing", "loc": ["body", "file"], "msg": "Field required", "input": null}]}
```

**Causa:** Campo `file` não enviado ou nome errado — mandar `data=@extrato.ofx`
(o nome usado na remessa) cai exatamente aqui.

**Solução:**
```bash
# ✅ Correto
curl -X POST http://localhost:8000/api/ofx/parse -F "file=@extrato.ofx"

# ❌ Errado (campo errado)
curl -X POST http://localhost:8000/api/ofx/parse -F "data=@extrato.ofx"
```

### 3. `nosso_numero` sempre null

**Causa:** Banco não reconhecido ou memo sem sequência numérica adequada.

**Debug:**
```python
response = requests.post(
    f"{API_URL}/api/ofx/parse",
    files={'file': open('extrato.ofx', 'rb')}
)
data = response.json()

# Confirme que o banco foi reconhecido
print(f"Banco: {data['banco']}")  # {'org': 'SICOOB', 'fid': '756'}

# Veja os memos
for tx in data['transacoes']:
    print(f"memo: '{tx['memo']}' → {tx['nosso_numero']}")
```

Veja [ofx-parsing.md](./ofx-parsing.md) para os padrões regex de cada banco.

### 4. Caracteres com encoding errado (`�`, `?`)

**Causa:** Arquivo original tem encoding diferente de Latin-1 ou UTF-8.

O service tenta automaticamente:
1. UTF-8 (se válido)
2. Latin-1 → UTF-8 (padrão de bancos brasileiros)
3. ASCII-8BIT com replace (fallback)

Se ainda assim houver problemas, reporte um issue com arquivo de exemplo.

## Checklist de Debug

### Boleto não gera

1. [ ] `bank` e `data` estão sendo enviados? (`type` é opcional e só aceita `pdf`)
2. [ ] JSON é válido (use `json.dumps()`)?
3. [ ] Usou `/api/boleto/validate` primeiro?
4. [ ] Campo `nosso_numero` está presente?
5. [ ] `data_vencimento` está no formato `YYYY/MM/DD`?
6. [ ] Consultou os campos obrigatórios em [fields/all-banks.md](../fields/all-banks.md)?

### Remessa não gera

1. [ ] `type` é `cnab240` ou `cnab400` (não apenas números)?
2. [ ] Array `pagamentos` tem pelo menos 1 item?
3. [ ] Cada pagamento tem `nosso_numero`, `data_vencimento`, `valor`, `nome_sacado`, `documento_sacado`?
4. [ ] Enviou como **multipart** no campo `data` (não como corpo JSON)?
5. [ ] Banco suporta o tipo CNAB? **Bradesco, Itaú e C6 só têm CNAB400** — confira em `GET /api/bancos`, campo `cnab`

### OFX não parseia

1. [ ] Arquivo é `.ofx` válido (v1 SGML ou v2 XML)?
2. [ ] Enviou via `multipart/form-data` com campo `file`?
3. [ ] Verificou que o banco foi reconhecido (`banco.org` no response)?
4. [ ] Confirmou encoding do arquivo?

## Suporte

- **Documentação:** [documentação do projeto](../)
- **Campos por banco:** [docs/fields/all-banks.md](../fields/all-banks.md)
- **OpenAPI Spec:** [docs/openapi.yaml](../openapi.yaml)
- **Issues:** https://github.com/Maxwbh/cobranca-api/issues

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) - M&S do Brasil LTDA
