--------------------------------------------------------------------------------
-- Exemplo 2 — emissão em LOTE a partir de uma tabela (job assíncrono)
-- Cenário típico de ERP: fechamento mensal com centenas de títulos.
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON

DECLARE
  l_boletos  CLOB;
  l_job_id   VARCHAR2(60);
  l_estado   CLOB;
  l_status   VARCHAR2(40);
BEGIN
  -- 1) Monta o array de boletos a partir da sua tabela de títulos
  APEX_JSON.initialize_clob_output;
  APEX_JSON.open_array;
  FOR t IN (SELECT numero_titulo, valor, vencimento, cliente, cpf_cnpj
              FROM titulos_a_receber
             WHERE status = 'A_EMITIR'
               AND ROWNUM <= 200)                       -- teto do job
  LOOP
    APEX_JSON.open_object;
    APEX_JSON.write('bank',              'banco_brasil');
    APEX_JSON.write('external_id',       t.numero_titulo);   -- idempotência por item
    APEX_JSON.write('agencia',           '3073');
    APEX_JSON.write('conta_corrente',    '12345678');
    APEX_JSON.write('convenio',          '1234567');
    APEX_JSON.write('carteira',          '18');
    APEX_JSON.write('nosso_numero',      t.numero_titulo);
    APEX_JSON.write('cedente',           'Empresa Exemplo LTDA');
    APEX_JSON.write('documento_cedente', '11222333000181');
    APEX_JSON.write('sacado',            t.cliente);
    APEX_JSON.write('sacado_documento',  t.cpf_cnpj);
    APEX_JSON.write('valor',             t.valor);
    APEX_JSON.write('data_vencimento',   TO_CHAR(t.vencimento, 'YYYY-MM-DD'));
    APEX_JSON.close_object;
  END LOOP;
  APEX_JSON.close_array;
  l_boletos := APEX_JSON.get_clob_output;
  APEX_JSON.free_output;

  -- 2) Cria o job (202 + job_id). Idempotência: rodar de novo NÃO duplica.
  l_job_id := cobranca_api.criar_job_lote(
                p_tenant          => 'empresa1',
                p_boletos_json    => l_boletos,
                p_idempotency_key => 'fechamento-' || TO_CHAR(SYSDATE, 'YYYYMM'));
  DBMS_OUTPUT.put_line('Job criado: ' || l_job_id);

  -- 3) Acompanha (em produção, faça isso num job do Scheduler)
  l_estado := cobranca_api.consultar_job('empresa1', l_job_id);
  APEX_JSON.parse(l_estado);
  l_status := APEX_JSON.get_varchar2('status');
  DBMS_OUTPUT.put_line('Status: ' || l_status
    || ' | ok: '    || APEX_JSON.get_number('completed')
    || ' | falhas: '|| APEX_JSON.get_number('failed'));

  -- 4) Os PDFs ficam disponíveis em /jobs/boletos/<job_id>/artifacts
  --    (zip consolidado com manifesto e sha256 — sem base64 no JSON)
END;
/
