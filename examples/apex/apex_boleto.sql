--------------------------------------------------------------------------------
-- Oracle APEX — emitir boleto e exibir/baixar o PDF na página
--
-- Usa APEX_WEB_SERVICE (já vem com o APEX): não precisa de UTL_HTTP nem
-- montar request na mão. A wallet do APEX (ADB já tem) cobre o HTTPS.
--------------------------------------------------------------------------------

--==============================================================================
-- 1) PROCESS (On Submit) — emite o boleto e guarda na coleção da sessão
--==============================================================================
DECLARE
  l_url    VARCHAR2(4000);
  l_data   VARCHAR2(4000);
  l_pdf    BLOB;
  l_dados  CLOB;
BEGIN
  -- APEX_ESCAPE.json nos campos de TEXTO LIVRE: um nome com aspas
  -- (EMPRESA "X" LTDA) quebraria o JSON inteiro e a API responderia 400 com
  -- uma causa nada obvia.
  l_data :=
    '{"agencia":"'          || :P10_AGENCIA          || '"' ||
    ',"conta_corrente":"'   || :P10_CONTA            || '"' ||
    ',"convenio":"'         || :P10_CONVENIO         || '"' ||
    ',"carteira":"'         || :P10_CARTEIRA         || '"' ||
    ',"nosso_numero":"'     || :P10_NOSSO_NUMERO     || '"' ||
    ',"cedente":"'          || APEX_ESCAPE.json(:P10_CEDENTE) || '"' ||
    ',"documento_cedente":"'|| :P10_CNPJ_CEDENTE     || '"' ||
    ',"sacado":"'           || APEX_ESCAPE.json(:P10_SACADO)  || '"' ||
    ',"sacado_documento":"' || :P10_CPF_SACADO       || '"' ||
    ',"valor":'             || TO_CHAR(:P10_VALOR, 'FM9999999990.00',
                                       'NLS_NUMERIC_CHARACTERS=''.,''') ||
    ',"data_vencimento":"'  || TO_CHAR(TO_DATE(:P10_VENCIMENTO, 'DD/MM/YYYY'),
                                       'YYYY-MM-DD') || '"}';

  -- 1.1) Dados calculados (linha digitável, código de barras, nosso número)
  l_dados := APEX_WEB_SERVICE.make_rest_request(
    p_url         => :G_COBRANCA_API_URL || '/api/boleto/data',
    p_http_method => 'GET',
    p_parm_name   => APEX_UTIL.string_to_table('bank:data'),
    p_parm_value  => APEX_UTIL.string_to_table(:P10_BANCO || ':' || l_data));

  APEX_JSON.parse(l_dados);
  :P10_LINHA_DIGITAVEL := APEX_JSON.get_varchar2('linha_digitavel');
  :P10_CODIGO_BARRAS   := APEX_JSON.get_varchar2('codigo_barras');
  :P10_NOSSO_NUM_FMT   := APEX_JSON.get_varchar2('nosso_numero_formatado');

  -- 1.2) PDF (binário)
  l_pdf := APEX_WEB_SERVICE.make_rest_request_b(
    p_url         => :G_COBRANCA_API_URL || '/api/boleto',
    p_http_method => 'GET',
    p_parm_name   => APEX_UTIL.string_to_table('bank:type:data'),
    p_parm_value  => APEX_UTIL.string_to_table(:P10_BANCO || ':pdf:' || l_data));

  IF APEX_WEB_SERVICE.g_status_code != 200 THEN
    APEX_ERROR.add_error(
      p_message          => 'Falha ao gerar boleto (HTTP '
                            || APEX_WEB_SERVICE.g_status_code || ')',
      p_display_location => APEX_ERROR.c_inline_in_notification);
    RETURN;
  END IF;

  -- 1.3) Guarda o PDF para download na mesma página
  INSERT INTO boletos_emitidos (nosso_numero_formatado, linha_digitavel,
                                codigo_barras, pdf)
  VALUES (:P10_NOSSO_NUM_FMT, :P10_LINHA_DIGITAVEL, :P10_CODIGO_BARRAS, l_pdf)
  RETURNING id INTO :P10_BOLETO_ID;
END;

--==============================================================================
-- 2) DOWNLOAD do PDF — Process do tipo "PL/SQL Code" com
--    "Reload on Submit = Only for Success" ou via Application Process (On Demand)
--==============================================================================
DECLARE
  l_pdf  BLOB;
BEGIN
  SELECT pdf INTO l_pdf FROM boletos_emitidos WHERE id = :P10_BOLETO_ID;

  SYS.HTP.init;
  SYS.OWA_UTIL.mime_header('application/pdf', FALSE);
  SYS.HTP.p('Content-Length: ' || DBMS_LOB.getlength(l_pdf));
  SYS.HTP.p('Content-Disposition: inline; filename="boleto.pdf"');
  SYS.OWA_UTIL.http_header_close;
  SYS.WPG_DOCLOAD.download_file(l_pdf);
  APEX_APPLICATION.stop_apex_engine;
EXCEPTION
  WHEN APEX_APPLICATION.e_stop_apex_engine THEN NULL;   -- fluxo normal
END;

--==============================================================================
-- 3) Exibir o PDF embutido na página (Region "PL/SQL Dynamic Content")
--    Aponta para o Application Process de download criado no passo 2.
--==============================================================================
BEGIN
  SYS.HTP.p('<iframe src="' ||
    APEX_PAGE.get_url(p_application => :APP_ID,
                      p_page        => :APP_PAGE_ID,
                      p_request     => 'APPLICATION_PROCESS=BAIXAR_BOLETO',
                      p_items       => 'P10_BOLETO_ID',
                      p_values      => :P10_BOLETO_ID) ||
    '" width="100%" height="700" style="border:0"></iframe>');
END;
