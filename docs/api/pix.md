# PIX Híbrido no Boleto

> **Versão:** 2.0.0 (engine pyCobrança)

## Campos PIX do boleto

O boleto aceita 3 campos adicionais para PIX:

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `chave_pix` | String | Chave PIX (CPF, CNPJ, email, telefone ou aleatoria) |
| `tipo_chave_pix` | String | Tipo da chave: `cpf`, `cnpj`, `email`, `telefone`, `aleatoria` |
| `txid` | String | Codigo de identificacao da transacao PIX |

Esses campos sao opcionais e complementam o `emv`. Quando enviados, aparecem no `dados_pix` do response.

## Duas formas de usar PIX

| Recurso | Endpoint | O que faz |
|---------|----------|-----------|
| **Boleto com QR Code PIX** | `GET /api/boleto` com campo `emv` nos dados | PDF com QR Code PIX embutido |
| **Remessa CNAB com PIX** | `POST /api/remessa?pix=true` | Arquivo CNAB com segmento PIX |

## 1. Boleto com QR Code PIX

Adicione o campo `emv` nos dados do boleto:

```python
response = requests.get(f"{API}/api/boleto", params={
    "bank": "sicoob", "type": "pdf",
    "data": json.dumps({
        ...dados_do_boleto,
        "emv": "00020126580014br.gov.bcb.pix0136...",
        "pix_label": "Escaneie para pagar via PIX"
    })
})
```

### Bancos com suporte

| Banco | Código | PIX no boleto | PIX na remessa CNAB 400 | PIX na remessa CNAB 240 |
|-------|:------:|:-------------:|:-----------------------:|:-----------------------:|
| Banco do Brasil | 001 | ✅ | — | ✅ |
| Santander | 033 | ✅ | ✅ | — |
| Caixa | 104 | ✅ | — | ✅ |
| Bradesco | 237 | ✅ | ✅ | — |
| Banco C6 | 336 | ✅ | ✅ | — |
| Itaú | 341 | ✅ | ✅ | — |
| Sicredi | 748 | ✅ | — | — |
| Sicoob | 756 | ✅ | — | ✅ |

## 2. Remessa CNAB com PIX

Adicione `pix=true` ao endpoint de remessa:

```bash
POST /api/remessa?bank=bradesco&type=cnab400&pix=true
```

Isso usa as classes PIX da gem (ex: `BradescoPix`, `SicoobPix`) que adicionam segmento PIX no arquivo CNAB:
- CNAB 400: registro tipo 8
- CNAB 240: Segmento Y-03

O banco então gera o boleto híbrido automaticamente ao processar a remessa.

## Campo `emv`

Payload EMV do PIX (string alfanumérica). Pode ser gerado por:
- API do banco (endpoint de cobrança PIX com vencimento)
- Lib geradora de EMV
- Portal PIX do Banco Central

## Troubleshooting

### QR Code não aparece no PDF

1. Confirme que o banco suporta PIX (tabela acima)
2. Verifique que `emv` é string válida
3. Use `template=prawn` para renderização nativa do QR Code

### Remessa PIX retorna erro

Verifique se o banco suporta PIX no formato solicitado. Exemplo: Sicoob suporta PIX apenas em CNAB 240, não em CNAB 400.

---

**Mantido por:** Maxwell da Silva Oliveira ([@maxwbh](https://github.com/maxwbh)) — M&S do Brasil LTDA
