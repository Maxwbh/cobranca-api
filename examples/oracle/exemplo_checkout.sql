--------------------------------------------------------------------------------
-- Link de pagamento com CARTÃO (e Pix no mesmo link) — caminho ONLINE
--
-- Nenhum dado de cartão passa por aqui nem pela API: o pagador digita o PAN na
-- página do banco, e o escopo PCI-DSS fica lá. Este script cria o link, mostra
-- a URL e acompanha o status até liquidar.
--
-- Fluxo: credenciais (uma vez) -> token bapi_ -> POST /checkout -> GET até sair
--        de `pendente`
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_ck       cobranca_api.t_checkout;
  l_venda_id VARCHAR2(40) := 'PED-2026-0042';
BEGIN
  cobranca_api.g_base_url := 'https://SEU-SERVICO.onrender.com';   -- troque pelo seu host
  cobranca_api.g_token    := '&bapi_token';   -- do cadastrar_credenciais (ver exemplo_online_c6.sql)

  ------------------------------------------------------------------------
  -- 1) Cria o link
  --
  -- p_idempotency_key derivada da VENDA, nunca de SYSTIMESTAMP: chave nova a
  -- cada chamada nao protege de nada. Com ela, rodar este bloco duas vezes
  -- devolve o MESMO link em vez de criar dois para a mesma venda — e nada
  -- impediria o pagador de pagar os dois.
  ------------------------------------------------------------------------
  l_ck := cobranca_api.criar_checkout(
    p_tenant          => 'empresa_hml',
    p_valor           => 150.00,
    p_descricao       => 'Pedido ' || l_venda_id,
    p_parcelas        => 6,
    p_com_pix         => TRUE,           -- QR Pix no MESMO link, gerado pelo banco
    p_referencia      => l_venda_id,     -- por onde o webhook reencontra a venda
    p_idempotency_key => 'venda-' || l_venda_id);

  DBMS_OUTPUT.put_line('id do checkout : ' || l_ck.id);
  DBMS_OUTPUT.put_line('URL do pagador : ' || l_ck.url);
  DBMS_OUTPUT.put_line('status         : ' || l_ck.status);   -- pendente
  DBMS_OUTPUT.put_line('expira em      : ' || l_ck.expira_em);

  ------------------------------------------------------------------------
  -- 2) Acompanha até sair de `pendente`
  --
  -- Em producao isto NAO e um loop: e o webhook (POST /config/webhook-banco
  -- com service=CHECKOUT) ou um job que varre os links abertos. O loop aqui e
  -- so para o script ser demonstravel de ponta a ponta.
  ------------------------------------------------------------------------
  FOR i IN 1 .. 10 LOOP
    DBMS_SESSION.sleep(5);
    l_ck := cobranca_api.consultar_checkout('empresa_hml', l_ck.id);
    DBMS_OUTPUT.put_line('  tentativa ' || i || ': ' || l_ck.status);
    EXIT WHEN l_ck.status != 'pendente';
  END LOOP;

  ------------------------------------------------------------------------
  -- 3) Baixa — só com o `liquidado` vindo do BANCO
  ------------------------------------------------------------------------
  IF l_ck.status = 'liquidado' THEN
    UPDATE vendas
       SET status_pgto = 'liquidado', pago_em = SYSTIMESTAMP
     WHERE id = l_venda_id
       AND status_pgto != 'liquidado';    -- idempotente: dar baixa duas vezes nao
    COMMIT;
    DBMS_OUTPUT.put_line('venda baixada');
  ELSIF l_ck.status = 'erro' THEN
    -- Cartao recusado e `erro`, nao `baixado`: o LINK se esgotou, a divida nao.
    -- Quem decide se a venda segue em aberto e voce, que conhece o contrato.
    DBMS_OUTPUT.put_line('cartao recusado — a venda continua em aberto');
  END IF;

EXCEPTION
  WHEN OTHERS THEN
    -- Erros que voce VAI encontrar, e o que cada um significa:
    --   422 -> payload. Parcelas > 1 sem juros_por, endereco do pagador
    --          incompleto, ou Idempotency-Key reusada com OUTRO corpo. O
    --          `detail` da resposta diz qual campo.
    --   424 -> o BANCO recusou a credencial. No sandbox do C6 tambem acontece
    --          FORA DA JANELA (seg-sex 7h-23h).
    --   403 -> o token bapi_ nao e deste tenant+banco.
    DBMS_OUTPUT.put_line('ERRO: ' || SQLERRM);
    RAISE;
END;
/
