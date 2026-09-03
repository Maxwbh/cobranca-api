--------------------------------------------------------------------------------
-- Cobrança REGISTRADA no Sicoob (caminho ONLINE)
--
-- O Sicoob aceita DUAS vias de autenticação — mande UMA das duas:
--   (a) sandbox : client_id + access_token (token estático do portal)
--   (b) produção: client_id + client_secret + pfx_base64 + pfx_password
--                 (OAuth client_credentials sobre mTLS)
--
-- Mandar client_secret VAZIO junto com access_token faz o provider tentar
-- OAuth sem material e falhar — envie só os campos da via que você usa.
--
-- ANTES DE RODAR: `GET /bancos` diz se ESTA instalacao tem o Sicoob ligado
-- (`registrado_pronto` / `caminho_efetivo`). Com `SICOOB_REGISTERED_READY`
-- desligado, o online e rebaixado para a engine e o boleto NAO passa pelo
-- banco — responde 201 como se tivesse passado.
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_token   VARCHAR2(200);
  l_boleto  cobranca_api.t_boleto;
  l_cob     cobranca_api.t_cobranca;
  l_creds   CLOB;
BEGIN
  cobranca_api.g_base_url := 'https://SEU-SERVICO.onrender.com';   -- troque pelo seu host

  ------------------------------------------------------------------------
  -- 1) Credenciais — escolha a via
  ------------------------------------------------------------------------
  -- via (a) SANDBOX: token estático, dispensa OAuth/mTLS
  l_creds := TO_CLOB('{'
    || '"client_id":"'    || '&sicoob_client_id'    || '",'
    || '"access_token":"' || '&sicoob_access_token' || '"}');

  -- via (b) PRODUÇÃO: OAuth + mTLS — descomente e comente a via (a)
  -- l_creds := TO_CLOB('{'
  --   || '"client_id":"'     || '&sicoob_client_id'     || '",'
  --   || '"client_secret":"' || '&sicoob_client_secret' || '",'
  --   || '"pfx_base64":"'    || '&sicoob_pfx_base64'    || '",'
  --   || '"pfx_password":"'  || '&sicoob_pfx_password'  || '"}');

  l_token := cobranca_api.cadastrar_credenciais(
    p_tenant => 'empresa_hml', p_provider => 'on', p_banco => 'sicoob',
    p_credenciais_json => l_creds);

  DBMS_OUTPUT.put_line('token: ' || SUBSTR(l_token, 1, 12) || '...');

  ------------------------------------------------------------------------
  -- 2) Registra a cobranca
  ------------------------------------------------------------------------
  l_boleto.valor            := 250.00;
  l_boleto.data_vencimento  := TRUNC(SYSDATE) + 15;
  l_boleto.nosso_numero     := 'MENS-2026-03';
  l_boleto.sacado           := 'Maria Souza';
  l_boleto.sacado_documento := '52998224725';

  -- account_config do Sicoob difere do C6 — cada banco tem o seu esquema.
  -- Consulte `GET /bancos` para ver os campos exigidos por banco.
  l_cob := cobranca_api.registrar_cobranca(
    p_tenant   => 'empresa_hml',
    p_provider => 'on', p_banco => 'sicoob',
    p_boleto   => l_boleto,
    p_account_config_json => '{"cooperativa":"&cooperativa",'
                          || '"conta":"&conta",'
                          || '"numeroCliente":"&numero_cliente",'
                          || '"codigoModalidade":"&codigo_modalidade"}');

  DBMS_OUTPUT.put_line('id             : ' || l_cob.id);
  DBMS_OUTPUT.put_line('status         : ' || l_cob.status);
  DBMS_OUTPUT.put_line('linha digitavel: ' || l_cob.linha_digitavel);

EXCEPTION
  WHEN OTHERS THEN
    -- 424 com "Certificado digital e obrigatorio" = o recurso pedido exige a
    -- via (b): o access_token de sandbox nao cobre tudo (ex.: Pix Automatico).
    DBMS_OUTPUT.put_line('ERRO: ' || SQLERRM);
    RAISE;
END;
/
