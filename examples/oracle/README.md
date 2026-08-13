# Oracle — PL/SQL e APEX

Consumir a **Cobranca-API** direto do banco de dados Oracle: emitir boletos,
gerar remessa CNAB e disparar lotes assíncronos **sem instalar nada** além do
que já existe no Oracle (`UTL_HTTP` + `APEX_JSON`, ou `APEX_WEB_SERVICE`).

> Por que isso importa: praticamente não há solução open source de boleto
> brasileiro utilizável de dentro do Oracle. Como a plataforma é REST, o banco
> chama por HTTP e recebe PDF/CNAB prontos — sem gem, sem JVM, sem wrapper.

## Arquivos

| Arquivo | O quê |
|---|---|
| [`cobranca_api_pkg.sql`](./cobranca_api_pkg.sql) | Pacote `COBRANCA_API` — boleto, CNAB, lote, **cobrança online** e **checkout de cartão** |
| [`acl_setup.sql`](./acl_setup.sql) | ACL de rede + wallet (executar como DBA) |
| [`exemplo_boleto.sql`](./exemplo_boleto.sql) | **Boleto OFFLINE** (sem credencial) — PDF em BLOB |
| [`exemplo_online_c6.sql`](./exemplo_online_c6.sql) | **Cobrança registrada no C6** — credencial → token `bapi_` → `POST /cobranca` |
| [`exemplo_online_sicoob.sql`](./exemplo_online_sicoob.sql) | **Cobrança registrada no Sicoob** — as duas vias de autenticação |
| [`exemplo_checkout.sql`](./exemplo_checkout.sql) | **Link de pagamento com cartão** (+ Pix no mesmo link) — nenhum dado de cartão passa pelo banco de dados |
| [`exemplo_remessa.sql`](./exemplo_remessa.sql) | **Remessa CNAB** com encargos (multa/juros/desconto) → `UTL_FILE` |
| [`exemplo_retorno.sql`](./exemplo_retorno.sql) | **Retorno CNAB** → `JSON_TABLE` → baixa dos títulos |
| [`exemplo_lote.sql`](./exemplo_lote.sql) | **Lote assíncrono**: cria o job e acompanha até concluir |

## Instalação (3 passos)

```sql
-- 1) como DBA: libera a rede para o host da API
@acl_setup.sql

-- 2) no schema da aplicação: cria o pacote
@cobranca_api_pkg.sql

-- 3) aponta para a sua instância (ou deixe a demo pública)
BEGIN
  cobranca_api.g_base_url := 'https://SEU-SERVICO.onrender.com';   -- troque pelo seu host
  cobranca_api.g_wallet   := 'file:/u01/app/oracle/wallet';  -- HTTPS
END;
/
```

## Uso mínimo

```sql
DECLARE
  b cobranca_api.t_boleto;
  d cobranca_api.t_dados_boleto;
  p BLOB;
BEGIN
  b.banco := 'banco_brasil'; b.agencia := '3073'; b.conta_corrente := '12345678';
  b.convenio := '1234567';   b.carteira := '18';  b.nosso_numero := '123';
  b.cedente := 'Empresa Exemplo LTDA'; b.documento_cedente := '11222333000181';
  b.sacado  := 'Joao da Silva';        b.sacado_documento := '52998224725';
  b.valor := 1500.00; b.data_vencimento := DATE '2027-12-30';

  d := cobranca_api.dados_boleto(b);      -- linha digitável, cód. barras, DV
  p := cobranca_api.gerar_boleto_pdf(b);  -- PDF em BLOB
END;
/
```

Saída real desta chamada (validada contra o HML):

```
nosso_numero_formatado : 12345670000000123
codigo_barras          : 00192204100001500000000001234567000000012318
linha_digitavel        : 00190.00009 01234.567004 ...
```

## Multipart (retorno CNAB e OFX)

`UTL_HTTP` puro não monta `multipart/form-data` com conforto. Para
`POST /api/retorno` e `POST /api/ofx/parse`, use `APEX_WEB_SERVICE` (disponível
mesmo sem aplicação APEX, desde que o schema APEX esteja instalado):

```sql
DECLARE
  l_resp CLOB;
BEGIN
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Content-Type';
  APEX_WEB_SERVICE.g_request_headers(1).value :=
    'multipart/form-data; boundary=----OraBoundary';
  l_resp := APEX_WEB_SERVICE.make_rest_request(
    p_url         => cobranca_api.g_base_url
                     || '/api/retorno?bank=banco_brasil&type=cnab400',
    p_http_method => 'POST',
    p_body_blob   => monta_multipart(l_arquivo_ret));  -- helper do seu schema
END;
/
```

Alternativa sem multipart: `POST /api/render/remessa` aceita **JSON puro** e é o
que o pacote usa em `gerar_remessa`.

## Lote (fechamento mensal)

Para centenas de títulos, **não** emita um a um: crie um **job**.

```sql
l_job := cobranca_api.criar_job_lote(
           p_tenant          => 'empresa1',
           p_boletos_json    => l_array_json,          -- ver exemplo_lote.sql
           p_idempotency_key => 'fechamento-202607');  -- reexecutar não duplica
```

A API responde **202** em ~1s e processa em background; depois:

- `GET /jobs/boletos/{job_id}` → `completed` / `partially_completed` / `failed`
- `GET /jobs/boletos/{job_id}/items?status=failed` → só o que falhou
- `GET /jobs/boletos/{job_id}/artifacts` → manifesto com `sha256` + **zip** com todos os PDFs

Um item inválido **não** cancela o lote.

## Cartão (link de pagamento)

```sql
l_ck := cobranca_api.criar_checkout(
          p_tenant          => 'empresa1',
          p_valor           => 150.00,
          p_parcelas        => 6,
          p_com_pix         => TRUE,              -- QR Pix no MESMO link
          p_referencia      => 'PED-2026-0042',
          p_idempotency_key => 'venda-PED-2026-0042');
-- l_ck.url é para onde o pagador vai
```

Quatro coisas que decidem se isto funciona em produção:

- **`p_idempotency_key` derivada da venda**, nunca de `SYSTIMESTAMP`. Chave nova
  a cada chamada não protege de nada; a graça é o reenvio devolver o **mesmo**
  link em vez de criar um segundo para a mesma venda.
- **A política de parcelamento é sua, não da API.** `p_parcelas` é o teto
  oferecido ao pagador e vai ao banco como veio — **não existe valor mínimo de
  parcela nesta API**. Com "até 3x, mínimo R$ 100", quem calcula é você:
  `GREATEST(1, LEAST(3, FLOOR(l_valor / 100)))`. Mandar `3` fixo numa venda de
  R$ 90 oferece 3 × R$ 30 ao pagador, e o banco não barra isso por você.
- **A baixa vem do `liquidado` que o banco devolve**, não do retorno do
  navegador. O pagador pode fechar a aba antes de voltar, e pode voltar sem ter
  pago.
- **`erro` é cartão recusado, não título baixado.** O link se esgotou; a dívida
  não. Quem decide se a venda segue em aberto é você.

Para dar baixa com a tela fechada, use o webhook em vez do polling — o
[`../apex/apex_checkout.sql`](../apex/apex_checkout.sql) traz o handler ORDS,
com a validação de assinatura que não pode faltar.

## Erros e diagnóstico

| HTTP | Significado | O que fazer |
|---|---|---|
| `400` | Dados do boleto inválidos | Ler `validation_errors` (campo a campo) |
| `401` | Token `bapi_` ausente/revogado | Recadastrar em `POST /credenciais` |
| `403` | Token não corresponde ao tenant/banco | Usar o token do banco certo |
| `409` | CIP processando o registro | Re-tentar em alguns segundos |
| `413` | Lote acima do limite (200) | Dividir em mais jobs |
| `424` | Banco rejeitou a credencial (ex.: sandbox C6 fora da janela) | Ver `upstream` no corpo |

`ORA-24247` (ACL) ou `ORA-29024` (certificado) → revise o [`acl_setup.sql`](./acl_setup.sql).

**`201` com `status: erro` numa chamada online** é o caso que mais engana: o
banco está desligado nesta instalação (`<BANCO>_REGISTERED_READY`), o caminho
`on` foi rebaixado para a engine e o `account_config` que a API do banco pede
não basta para ela. Confira antes em `GET /bancos` — `registrado_pronto` e
`caminho_efetivo` respondem por banco.

## `p_provider`: caminho e banco

A API separa os dois eixos: `provider` é o **caminho** (`on` = API do banco,
`off` = engine pyCobrança) e `banco` é a **instituição**. Este pacote passa o
nome do banco em `p_provider` (`'c6'`, `'sicoob'`) — apelido que a API aceita
como `on` + `banco` e mantém até a **3.0.0**. Nada aqui precisa mudar agora.
