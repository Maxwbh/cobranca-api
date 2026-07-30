--------------------------------------------------------------------------------
-- Processar arquivo de RETORNO CNAB e dar baixa nos títulos
--
-- Lê o .RET que o banco disponibilizou, manda para a API e percorre o JSON com
-- JSON_TABLE para atualizar a sua tabela de títulos.
--
-- Não precisa de credencial: o parse é offline.
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_arquivo   UTL_FILE.file_type;
  l_linha     VARCHAR2(32767);
  l_conteudo  CLOB;
  l_json      CLOB;
  l_baixados  PLS_INTEGER := 0;
BEGIN
  cobranca_api.g_base_url := 'https://boleto-cnab-api.onrender.com';

  ------------------------------------------------------------------------
  -- 1) Le o .RET do diretorio do banco
  --
  -- CNAB e POSICIONAL: preserve a linha como veio, sem TRIM. Cortar espacos
  -- a direita desalinha os campos e o parse devolve lixo silenciosamente.
  ------------------------------------------------------------------------
  DBMS_LOB.createtemporary(l_conteudo, TRUE);
  l_arquivo := UTL_FILE.fopen('CNAB_DIR', 'RETORNO.RET', 'r', 32767);
  BEGIN
    LOOP
      UTL_FILE.get_line(l_arquivo, l_linha, 32767);
      DBMS_LOB.writeappend(l_conteudo, LENGTH(l_linha) + 2, l_linha || CHR(13) || CHR(10));
    END LOOP;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN NULL;
  END;
  UTL_FILE.fclose(l_arquivo);

  ------------------------------------------------------------------------
  -- 2) Manda para a API
  ------------------------------------------------------------------------
  l_json := cobranca_api.processar_retorno(
    p_bank    => 'banco_brasil',
    p_tipo    => 'cnab400',        -- ou 'cnab240'
    p_arquivo => l_conteudo);

  ------------------------------------------------------------------------
  -- 3) Percorre os registros e da baixa
  --
  -- codigo_ocorrencia mais comuns:
  --   02 = entrada confirmada    06 = LIQUIDACAO (baixa)
  --   03 = entrada rejeitada     09/10 = baixa
  -- `motivo_ocorrencia` ja vem descrito em texto pela engine.
  ------------------------------------------------------------------------
  FOR r IN (
    SELECT nosso_numero, codigo_ocorrencia, motivo_ocorrencia,
           valor_titulo, valor_pago, data_ocorrencia
      FROM JSON_TABLE(l_json, '$[*]'
             COLUMNS (
               nosso_numero       VARCHAR2(30)  PATH '$.nosso_numero',
               codigo_ocorrencia  VARCHAR2(5)   PATH '$.codigo_ocorrencia',
               motivo_ocorrencia  VARCHAR2(200) PATH '$.motivo_ocorrencia',
               valor_titulo       NUMBER        PATH '$.valor_titulo',
               valor_pago         NUMBER        PATH '$.valor_pago',
               data_ocorrencia    VARCHAR2(10)  PATH '$.data_ocorrencia'))
  ) LOOP
    DBMS_OUTPUT.put_line(
      RPAD(r.nosso_numero, 20) || ' ocorr=' || r.codigo_ocorrencia ||
      ' pago=' || NVL(TO_CHAR(r.valor_pago), '-') || ' ' || r.motivo_ocorrencia);

    IF r.codigo_ocorrencia = '06' THEN     -- liquidado
      -- UPDATE titulos
      --    SET status = 'LIQUIDADO',
      --        valor_pago = r.valor_pago,
      --        data_baixa = TO_DATE(r.data_ocorrencia, 'DDMMRR')
      --  WHERE nosso_numero = LTRIM(r.nosso_numero, '0');
      --
      -- Repare no LTRIM: o CNAB traz o nosso numero com zeros a esquerda
      -- (largura fixa). Comparar sem normalizar nao casa com a sua tabela.
      l_baixados := l_baixados + 1;
    END IF;
  END LOOP;

  DBMS_OUTPUT.put_line('titulos liquidados: ' || l_baixados);
  -- COMMIT;

EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.is_open(l_arquivo) THEN UTL_FILE.fclose(l_arquivo); END IF;
    DBMS_OUTPUT.put_line('ERRO: ' || SQLERRM);
    RAISE;
END;
/
