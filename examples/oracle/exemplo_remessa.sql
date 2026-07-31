--------------------------------------------------------------------------------
-- Gerar arquivo de REMESSA CNAB direto do Oracle
--
-- Monta o payload a partir da sua tabela de títulos, chama a API e grava o
-- arquivo num diretório do banco (DIRECTORY) pronto para enviar ao banco.
--
-- Não precisa de credencial: a remessa é gerada offline pela engine.
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON SIZE UNLIMITED

-- Pré-requisito (uma vez, como DBA):
--   CREATE OR REPLACE DIRECTORY CNAB_DIR AS '/u01/app/oracle/cnab';
--   GRANT READ, WRITE ON DIRECTORY CNAB_DIR TO seu_usuario;

DECLARE
  l_payload   CLOB;
  l_cnab      CLOB;
  l_arquivo   UTL_FILE.file_type;
  l_off       NUMBER := 1;
  l_amt       NUMBER := 8000;
  l_chunk     VARCHAR2(32767);
  l_nome      VARCHAR2(100) := 'CB' || TO_CHAR(SYSDATE, 'DDMM') || '01.REM';
BEGIN
  cobranca_api.g_base_url := 'https://boleto-cnab-api.onrender.com';

  ------------------------------------------------------------------------
  -- 1) Cabecalho da remessa + os titulos
  --
  -- `sequencial_remessa` DEVE ser incrementado a cada arquivo enviado: o banco
  -- rejeita sequencial repetido. Guarde-o numa sequence ou tabela de controle.
  ------------------------------------------------------------------------
  l_payload := TO_CLOB('{'
    || '"empresa_mae":"Empresa Teste LTDA",'
    || '"documento_cedente":"11222333000181",'
    || '"agencia":"3073",'
    || '"conta_corrente":"12345678",'
    || '"digito_conta":"0",'
    || '"convenio":"1234567",'
    || '"carteira":"18",'
    || '"variacao_carteira":"017",'
    || '"sequencial_remessa":' || TO_CHAR(1) || ','
    || '"pagamentos":[');

  -- Na vida real isto vem de um cursor sobre a sua tabela:
  --   FOR t IN (SELECT ... FROM titulos WHERE status = 'A_ENVIAR') LOOP
  l_payload := l_payload || TO_CLOB('{'
    || '"nosso_numero":"123456789",'
    -- numero_documento tem largura MAXIMA de 10 no CNAB 400. Valor maior
    -- estoura o registro e a API responde 400 com "registro com N posicoes".
    || '"numero_documento":"DOC2026001",'
    || '"data_vencimento":"2027-12-31",'
    || '"valor":1500.00,'
    || '"sacado":"Joao da Silva",'
    || '"sacado_documento":"52998224725",'
    || '"sacado_endereco":"Rua Teste, 100",'
    || '"sacado_bairro":"Centro",'
    || '"sacado_cidade":"Sao Paulo",'
    || '"sacado_uf":"SP",'
    || '"sacado_cep":"01000000",'
    -- ENCARGOS (opcionais) — cada um e um TRIO codigo/tipo -> valor -> data.
    -- ATENCAO a semantica POR LAYOUT:
    --   CNAB 400: mora e VALOR/dia  -> valor_mora
    --   CNAB 240: mora pode ser %   -> tipo_mora='2' + percentual_mora
    -- Mandar percentual_mora num 400 NAO tem efeito (o layout nao tem a
    -- posicao). Nome generico (multa/juros/desconto) e RECUSADO com 400 e uma
    -- dica — de proposito: um apelido esconderia o encargo sumindo.
    || '"codigo_multa":"2",'
    || '"percentual_multa":2.00,'
    || '"valor_mora":1.00,'
    || '"cod_desconto":"1",'
    || '"valor_desconto":50.00,'
    || '"data_desconto":"2027-12-20"}');
  --   END LOOP;  -- separando com vírgula

  l_payload := l_payload || TO_CLOB(']}');

  ------------------------------------------------------------------------
  -- 2) Gera o CNAB
  ------------------------------------------------------------------------
  l_cnab := cobranca_api.gerar_remessa(
    p_bank    => 'banco_brasil',
    p_tipo    => 'cnab240',        -- ou 'cnab400'
    p_payload => l_payload);

  DBMS_OUTPUT.put_line('CNAB gerado: ' || DBMS_LOB.getlength(l_cnab) || ' bytes');
  DBMS_OUTPUT.put_line('1a linha   : ' || DBMS_LOB.substr(l_cnab, 80, 1));

  ------------------------------------------------------------------------
  -- 3) Grava em disco, linha a linha
  --
  -- O CNAB e um arquivo POSICIONAL: nao use funcoes que cortem espacos a
  -- direita, senao o banco recusa o arquivo por tamanho de registro.
  ------------------------------------------------------------------------
  l_arquivo := UTL_FILE.fopen('CNAB_DIR', l_nome, 'w', 32767);
  WHILE l_off <= DBMS_LOB.getlength(l_cnab) LOOP
    l_chunk := DBMS_LOB.substr(l_cnab, l_amt, l_off);
    UTL_FILE.put(l_arquivo, l_chunk);       -- put, nao put_line: o CLOB ja traz \n
    l_off := l_off + l_amt;
  END LOOP;
  UTL_FILE.fclose(l_arquivo);

  DBMS_OUTPUT.put_line('arquivo: CNAB_DIR/' || l_nome);

EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.is_open(l_arquivo) THEN UTL_FILE.fclose(l_arquivo); END IF;
    DBMS_OUTPUT.put_line('ERRO: ' || SQLERRM);
    RAISE;
END;
/
