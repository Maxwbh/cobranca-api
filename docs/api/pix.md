# PIX Híbrido no Boleto

> Versão do serviço: `GET /api/metadata`.
> 🕒 Revisado em 2026-08-19 contra a engine — desta vez conferindo o **PDF**, e
> não o status. Foi assim que apareceu o defeito da seção seguinte: a revisão
> anterior mediu `200` e concluiu que o QR estava lá.

## Campos PIX do boleto

| Campo | Desenha o QR? | Observação |
|-------|:---:|---|
| `chave_pix` | ✅ | **é ele que liga o Bolepix** — mapeado para `pix_chave` |
| `txid` | ✅ | identificador da transação; mapeado para `pix_txid`. Sem ele vai `***` |
| `tipo_chave_pix` | ⛔ | descartado — a engine deduz o tipo do valor da chave |
| `emv` | 🚫 **400** | payload pronto: a engine monta o dela e não tem por onde receber o seu |
| `pix_label` | 🚫 **400** | a legenda do QR é do modelo, não do payload |

> ⚠️ **`emv` e `pix_label` respondiam `200` e sumiam.** Esta página ensinava que
> `emv` "vira o QR Code no PDF". Não vira: nenhum código da engine lê o campo —
> ele existia só no schema, herdado da era Ruby, onde o payload chegava pronto.
> O boleto saía **sem QR**, com `200` e sem nada na resposta indicando a falta,
> e o pagador recebia um boleto que não dá para pagar por Pix. Os seis boletos
> "pix" de `examples/python/generate_test_boletos.py` eram exatamente isso —
> byte a byte do mesmo tamanho dos comuns.
>
> Agora os dois campos respondem **400** apontando para `chave_pix`. Se a sua
> integração os enviava, troque: o QR que você achava que estava saindo não
> estava.

> ⚠️ **Não há `dados_pix` na resposta.** Nem `/api/boleto/data` nem
> `include_data=true` devolvem essa chave — as duas respondem os mesmos seis
> campos de sempre (`bank`, `nosso_numero`, `nosso_numero_formatado`,
> `nosso_numero_dv`, `codigo_barras`, `linha_digitavel`).

## Duas formas de usar PIX

| Recurso | Endpoint | O que faz |
|---------|----------|-----------|
| **Boleto com QR Code PIX** | `GET /api/boleto` com `chave_pix` nos dados | PDF com QR Code PIX embutido |
| **Remessa CNAB com PIX** | `POST /api/remessa?pix=true` | Arquivo CNAB com segmento PIX |

## 1. Boleto com QR Code PIX

Informe a **chave** — a engine monta o payload EMV e desenha o QR:

```python
response = requests.get(f"{API}/api/boleto", params={
    "bank": "sicoob", "type": "pdf",
    "data": json.dumps({
        **dados_do_boleto,
        "chave_pix": "11222333000181",
        "txid": "PED-2026-0042",
    })
})
```

**O QR depende de o banco suportar PIX**, e a engine recusa quando não suporta:
`banco 041 (Banrisul) não suporta PIX`, em `400`. São **sete** — Banco do
Brasil, Bradesco, Caixa, Itaú, Santander, Sicoob e C6, conferidos um a um
comparando o PDF com e sem a chave. Pedir o QR fora dessa lista é erro, e não
um boleto impresso pela metade.

> A revisão anterior desta página afirmava o contrário — que o QR "não depende
> de o banco suportar PIX", com o Banrisul de exemplo. A medição por trás disso
> foi um `200` obtido mandando `emv`, que era descartado: o PDF nunca teve QR.
> Conferir o status não bastava; conferir o arquivo, sim.

A tabela mais abaixo é sobre **remessa**, que é outra coisa.

## 2. Remessa CNAB com PIX

```bash
POST /api/remessa?bank=bradesco&type=cnab400&pix=true
```

Isso aciona a variante PIX do layout na engine, que acrescenta o segmento:

- CNAB 400: registro tipo 8
- CNAB 240: Segmento Y-03

O banco então gera o boleto híbrido ao processar a remessa.

### Onde a remessa com PIX existe

Extraído do catálogo de remessas da engine — **`pix=true` só funciona nas
combinações abaixo**:

| Banco | Código | Remessas | PIX na remessa |
|-------|:------:|----------|:--------------:|
| Banco do Brasil | 001 | cnab240, cnab400 | **cnab240** |
| Bradesco | 237 | cnab400 | **cnab400** |
| Caixa | 104 | cnab240 | **cnab240** |
| Itaú | 341 | cnab400 | **cnab400** |
| Santander | 033 | cnab240, cnab400 | **cnab400** |
| Banco C6 | 336 | cnab400 | **cnab400** |
| Sicoob | 756 | cnab240, cnab400 | **cnab240** |
| Ailos | 085 | cnab240 | — |
| Banestes / HSBC / Safra | 021 / 399 / 422 | *(sem remessa)* | — |
| BRB | 070 | cnab400 | — |
| Banco do Nordeste | 004 | cnab400 | — |
| Banrisul | 041 | cnab400 | — |
| Citibank | 745 | cnab400 | — |
| CrediSIS | 097 | cnab400 | — |
| Sicredi | 748 | cnab240 | — |
| Unicred | 136 | cnab240, cnab400 | — |

> A versão anterior listava só oito bancos, o que fazia os outros dez parecerem
> "sem PIX no boleto" — quando o que eles não têm é **remessa com PIX**. Três
> deles (Banestes, HSBC e Safra) não têm remessa nenhuma na engine, o que também
> não estava dito.

Pedindo uma combinação que não existe, o erro **lista todas as válidas**:

```json
{
  "error": "Erro ao gerar remessa",
  "validation_errors": [
    "Remessa cnab400+pix não suportada para 'sicoob'. Suportadas: ailos/cnab240, banco_brasil/cnab240, …"
  ]
}
```

## Campo `emv`

Payload EMV do PIX (string alfanumérica). Pode ser gerado por:
- API do banco (endpoint de cobrança PIX com vencimento)
- Lib geradora de EMV
- Portal PIX do Banco Central

No caminho **online** você não precisa gerar nada: `POST /pix` devolve o
`pixCopiaECola` do próprio banco, que é o `emv` pronto para pôr no boleto.

## Troubleshooting

### QR Code não aparece no PDF

1. Verifique que `emv` é string válida e **não vazia** — campo vazio é
   descartado na montagem, sem erro
2. Confirme que o PDF é o que você está olhando (o `include_data=true` devolve
   o PDF em base64, não o binário)
3. **Não** existe `template=prawn`: os modelos válidos são **`classico`** e
   **`moderno`** (default). Pedir outro devolve
   `template 'prawn' inválido (use: classico, moderno)` — a instrução antiga
   de "usar `template=prawn` para renderização nativa do QR" apontava para um
   modelo da era Ruby, e quem a seguisse trocaria um QR ausente por um 400.

### Remessa PIX retorna erro

Verifique a tabela acima: a combinação banco × formato tem de existir. Exemplo:
Sicoob tem PIX em **CNAB 240**, não em CNAB 400.

### Sicredi e Unicred respondem erro ao gerar o boleto

Não é o PIX. Os dois layouts exigem campos que a validação não cobre:

- **Sicredi** pede `data_documento` (de onde sai o ano do nosso número) e
  `byte_idt` (1 = agência, 2-9 = beneficiário). Sem eles o boleto responde
  **400** nomeando o campo que falta — até a 2.2.0 isso escapava como `500`.
- **Unicred** ainda pode falhar na montagem do código de barras
  (`campo livre deve ter 25 dígitos`) quando convênio e conta não têm o tamanho
  que o layout espera. Esse caso **continua saindo como 500**: a exceção vem da
  engine como `ValueError` genérico, e capturá-la às cegas mascararia defeito
  nosso. Está registrado como lacuna da engine, não como comportamento.

> Nos dois casos o `GET /api/boleto/validate` responde `valid: true` antes de o
> boleto falhar. Validação verde não garante boleto gerado nesses dois layouts.

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) — M&S do Brasil LTDA
