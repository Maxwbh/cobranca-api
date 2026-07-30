--------------------------------------------------------------------------------
-- Oracle APEX — emissão em LOTE (job assíncrono) + acompanhamento na página
--
-- Padrão recomendado para fechamento mensal: a página cria o job (resposta em
-- ~1s) e um Dynamic Action com timer atualiza o progresso. Nada de travar a
-- sessão do APEX esperando centenas de PDFs.
--------------------------------------------------------------------------------

--==============================================================================
-- 1) PROCESS (On Submit) — cria o job a partir dos títulos selecionados
--==============================================================================
DECLARE
  l_boletos CLOB;
  l_resp    CLOB;
BEGIN
  APEX_JSON.initialize_clob_output;
  APEX_JSON.open_object;
  APEX_JSON.write('tenant_id', :G_TENANT_ID);
  APEX_JSON.open_array('boletos');
  FOR t IN (SELECT numero_titulo, valor, vencimento, cliente, cpf_cnpj
              FROM titulos_a_receber
             WHERE competencia = :P20_COMPETENCIA
               AND status = 'A_EMITIR')
  LOOP
    APEX_JSON.open_object;
    APEX_JSON.write('bank',              :P20_BANCO);
    APEX_JSON.write('external_id',       t.numero_titulo);
    APEX_JSON.write('agencia',           :P20_AGENCIA);
    APEX_JSON.write('conta_corrente',    :P20_CONTA);
    APEX_JSON.write('convenio',          :P20_CONVENIO);
    APEX_JSON.write('carteira',          :P20_CARTEIRA);
    APEX_JSON.write('nosso_numero',      t.numero_titulo);
    APEX_JSON.write('cedente',           :P20_CEDENTE);
    APEX_JSON.write('documento_cedente', :P20_CNPJ);
    APEX_JSON.write('sacado',            t.cliente);
    APEX_JSON.write('sacado_documento',  t.cpf_cnpj);
    APEX_JSON.write('valor',             t.valor);
    APEX_JSON.write('data_vencimento',   TO_CHAR(t.vencimento, 'YYYY-MM-DD'));
    APEX_JSON.close_object;
  END LOOP;
  APEX_JSON.close_array;
  APEX_JSON.close_object;
  l_boletos := APEX_JSON.get_clob_output;
  APEX_JSON.free_output;

  -- Idempotência: reenviar a mesma competência devolve o MESMO job
  APEX_WEB_SERVICE.g_request_headers.DELETE;
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Content-Type';
  APEX_WEB_SERVICE.g_request_headers(1).value := 'application/json';
  APEX_WEB_SERVICE.g_request_headers(2).name  := 'Idempotency-Key';
  APEX_WEB_SERVICE.g_request_headers(2).value := 'apex-' || :P20_COMPETENCIA;

  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/jobs/boletos',
              p_http_method => 'POST',
              p_body        => l_boletos);

  APEX_JSON.parse(l_resp);
  :P20_JOB_ID := APEX_JSON.get_varchar2('job_id');
END;

--==============================================================================
-- 2) AJAX Callback "ATUALIZAR_JOB" — chamado por um Dynamic Action (timer 3s)
--==============================================================================
DECLARE
  l_resp CLOB;
BEGIN
  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/jobs/boletos/' || :P20_JOB_ID,
              p_http_method => 'GET',
              p_parm_name   => APEX_UTIL.string_to_table('tenant_id'),
              p_parm_value  => APEX_UTIL.string_to_table(:G_TENANT_ID));
  -- devolve o JSON cru para o Dynamic Action tratar (status/completed/failed)
  SYS.HTP.p(l_resp);
END;

--==============================================================================
-- 3) Report dos itens do job (Region: SQL Query -> função pipeline OU
--    "Web Source Module" apontando para /jobs/boletos/{job_id}/items)
--==============================================================================
-- Alternativa 100% SQL usando JSON_TABLE sobre a resposta:
--
-- SELECT j.item_id, j.status, j.linha_digitavel, j.erro
--   FROM JSON_TABLE(
--          cobranca_api_itens(:P20_JOB_ID, :G_TENANT_ID),   -- função que faz o GET
--          '$.items[*]'
--          COLUMNS (item_id         VARCHAR2(60) PATH '$.item_id',
--                   status          VARCHAR2(20) PATH '$.status',
--                   linha_digitavel VARCHAR2(80) PATH '$.resultado.linha_digitavel',
--                   erro            VARCHAR2(400) PATH '$.resultado.errors[0]')) j;

--==============================================================================
-- 4) Botão "Baixar todos" — redireciona para o zip consolidado do job
--==============================================================================
-- URL do botão (Target -> URL):
--   &G_COBRANCA_API_URL./jobs/boletos/&P20_JOB_ID./artifacts/boletos-&P20_JOB_ID..zip?tenant_id=&G_TENANT_ID.
