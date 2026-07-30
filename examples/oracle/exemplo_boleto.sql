--------------------------------------------------------------------------------
-- Exemplo 1 — emitir boleto do PL/SQL e gravar o PDF em tabela
--------------------------------------------------------------------------------
SET SERVEROUTPUT ON

-- Tabela de exemplo para guardar os boletos emitidos
CREATE TABLE boletos_emitidos (
  id                     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nosso_numero           VARCHAR2(30),
  nosso_numero_formatado VARCHAR2(50),
  linha_digitavel        VARCHAR2(80),
  codigo_barras          VARCHAR2(60),
  pdf                    BLOB,
  emitido_em             TIMESTAMP DEFAULT SYSTIMESTAMP
);
/

DECLARE
  l_boleto  cobranca_api.t_boleto;
  l_dados   cobranca_api.t_dados_boleto;
  l_pdf     BLOB;
BEGIN
  -- 1) Monta o boleto
  l_boleto.banco             := 'banco_brasil';
  l_boleto.agencia           := '3073';
  l_boleto.conta_corrente    := '12345678';
  l_boleto.convenio          := '1234567';       -- BB: 4, 6 ou 7 dígitos
  l_boleto.carteira          := '18';
  l_boleto.nosso_numero      := '123';
  l_boleto.cedente           := 'Empresa Exemplo LTDA';
  l_boleto.documento_cedente := '11222333000181';
  l_boleto.sacado            := 'Joao da Silva';
  l_boleto.sacado_documento  := '52998224725';
  l_boleto.valor             := 1500.00;
  l_boleto.data_vencimento   := TO_DATE('2027-12-30', 'YYYY-MM-DD');

  -- 2) Dados calculados (linha digitável, código de barras, nosso número + DV)
  l_dados := cobranca_api.dados_boleto(l_boleto);
  DBMS_OUTPUT.put_line('Nosso numero : ' || l_dados.nosso_numero_formatado);
  DBMS_OUTPUT.put_line('Linha digit. : ' || l_dados.linha_digitavel);
  DBMS_OUTPUT.put_line('Cod. barras  : ' || l_dados.codigo_barras);

  -- 3) PDF
  l_pdf := cobranca_api.gerar_boleto_pdf(l_boleto);
  DBMS_OUTPUT.put_line('PDF          : ' || DBMS_LOB.getlength(l_pdf) || ' bytes');

  INSERT INTO boletos_emitidos (nosso_numero, nosso_numero_formatado,
                                linha_digitavel, codigo_barras, pdf)
  VALUES (l_dados.nosso_numero, l_dados.nosso_numero_formatado,
          l_dados.linha_digitavel, l_dados.codigo_barras, l_pdf);
  COMMIT;
END;
/
