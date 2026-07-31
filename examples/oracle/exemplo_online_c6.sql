--------------------------------------------------------------------------------
-- Cobrança REGISTRADA no C6 Bank (caminho ONLINE)
--
-- Diferença para o offline (exemplo_boleto.sql): aqui o boleto é registrado
-- NA API DO BANCO. O banco devolve o id, a linha digitável e o status — e o
-- título passa a existir na CIP. O offline só GERA o documento localmente.
--
-- Fluxo: credenciais (uma vez) -> token bapi_ -> POST /cobranca
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_token   VARCHAR2(200);
  l_boleto  cobranca_api.t_boleto;
  l_cob     cobranca_api.t_cobranca;
BEGIN
  cobranca_api.g_base_url := 'https://SEU-SERVICO.onrender.com';   -- troque pelo seu host

  ------------------------------------------------------------------------
  -- 1) Credenciais do C6 -> token bapi_
  --
  -- O token volta UMA unica vez: guarde-o (ex.: numa tabela cifrada) se for
  -- reusar entre sessoes. O servidor NAO consegue recupera-lo — a chave de
  -- decifracao e derivada do proprio token.
  --
  -- pfx_base64: o certificado mTLS em base64. Se ele estiver numa tabela,
  -- use APEX_WEB_SERVICE.blob2clobbase64(l_pfx_blob).
  ------------------------------------------------------------------------
  l_token := cobranca_api.cadastrar_credenciais(
    p_tenant   => 'empresa_hml',
    p_provider => 'c6',
    p_credenciais_json => TO_CLOB('{'
      || '"client_id":"'     || '&c6_client_id'     || '",'
      || '"client_secret":"' || '&c6_client_secret' || '",'
      || '"pfx_base64":"'    || '&c6_pfx_base64'    || '",'
      || '"pfx_password":"'  || '&c6_pfx_password'  || '"}'));

  DBMS_OUTPUT.put_line('token: ' || SUBSTR(l_token, 1, 12) || '... (guarde-o)');

  ------------------------------------------------------------------------
  -- 2) Registra a cobranca no banco
  ------------------------------------------------------------------------
  l_boleto.valor            := 150.00;
  l_boleto.data_vencimento  := TRUNC(SYSDATE) + 30;
  l_boleto.nosso_numero     := 'PED-2026-0001';        -- vira `seu_numero`
  l_boleto.sacado           := 'João da Silva';
  l_boleto.sacado_documento := '52998224725';

  l_cob := cobranca_api.registrar_cobranca(
    p_tenant   => 'empresa_hml',
    p_provider => 'c6',
    p_boleto   => l_boleto,
    p_account_config_json => '{"agencia":"&agencia",'
                          || '"conta":"&conta",'
                          || '"convenio":"&convenio"}');

  DBMS_OUTPUT.put_line('id do banco    : ' || l_cob.id);
  DBMS_OUTPUT.put_line('status         : ' || l_cob.status);
  DBMS_OUTPUT.put_line('linha digitavel: ' || l_cob.linha_digitavel);
  DBMS_OUTPUT.put_line('codigo de barras: ' || l_cob.codigo_barras);

EXCEPTION
  WHEN OTHERS THEN
    -- Erros que voce VAI encontrar, e o que cada um significa:
    --   424 -> o BANCO recusou a credencial. Nao e falha do servico. No
    --          sandbox do C6 tambem acontece FORA DA JANELA (seg-sex 7h-23h).
    --   403 -> o token bapi_ nao e deste tenant+provider (ele amarra os dois).
    --   409 -> registro na CIP ainda em curso: re-tente em alguns segundos.
    DBMS_OUTPUT.put_line('ERRO: ' || SQLERRM);
    RAISE;
END;
/
