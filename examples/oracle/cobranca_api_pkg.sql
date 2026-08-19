--------------------------------------------------------------------------------
-- COBRANCA_API — pacote PL/SQL para consumir a Cobranca-API
--
-- Emite boleto (PDF), gera remessa CNAB, processa retorno e cria jobs em lote
-- direto do Oracle Database, sem instalar nada além do que já existe no banco
-- (UTL_HTTP + APEX_JSON, ou APEX_WEB_SERVICE quando houver APEX instalado).
--
-- Pré-requisitos (uma vez, como DBA):
--   1) ACL de rede para o host da API (ver acl_setup.sql)
--   2) Wallet com o certificado do host, se a API for HTTPS (ver acl_setup.sql)
--
-- A URL do Render vem do NOME do servico e muda se ele for renomeado,
-- recriado ou apontado para dominio proprio. Defina g_base_url no seu schema.
--
-- SOBRE `p_provider`: a API tem DOIS eixos — `provider` diz o CAMINHO (`on` =
-- API do banco, `off` = engine pyCobranca) e `banco` diz a INSTITUICAO. Este
-- pacote passa o NOME DO BANCO no `provider` ('c6', 'sicoob'), que a API aceita
-- como apelido de `on` + `banco` e mantem por compatibilidade ate a 3.0.0.
-- Enquanto isso, nada aqui precisa mudar.
--------------------------------------------------------------------------------
CREATE OR REPLACE PACKAGE cobranca_api AS

  -- URL base da API (troque para a sua instância)
  g_base_url  VARCHAR2(500) := 'https://SEU-SERVICO.onrender.com';
  -- Wallet (obrigatório para HTTPS no UTL_HTTP; vazio se usar APEX_WEB_SERVICE)
  g_wallet    VARCHAR2(500) := 'file:/u01/app/oracle/wallet';
  g_wallet_pw VARCHAR2(100) := NULL;

  -- Token bapi_ da cobrança online (opcional; só para rotas de banco)
  g_token     VARCHAR2(200);

  TYPE t_boleto IS RECORD (
    banco               VARCHAR2(30)   := 'banco_brasil',
    agencia             VARCHAR2(10),
    conta_corrente      VARCHAR2(20),
    convenio            VARCHAR2(20),
    carteira            VARCHAR2(10),
    nosso_numero        VARCHAR2(30),
    cedente             VARCHAR2(200),
    documento_cedente   VARCHAR2(20),
    sacado              VARCHAR2(200),
    sacado_documento    VARCHAR2(20),
    valor               NUMBER,
    data_vencimento     DATE
  );

  TYPE t_dados_boleto IS RECORD (
    nosso_numero            VARCHAR2(30),
    nosso_numero_formatado  VARCHAR2(50),
    nosso_numero_dv         VARCHAR2(5),
    codigo_barras           VARCHAR2(60),
    linha_digitavel         VARCHAR2(80)
  );

  -- Dados calculados (sem gerar PDF) — GET /api/boleto/data
  FUNCTION dados_boleto(p_boleto IN t_boleto) RETURN t_dados_boleto;

  -- PDF do boleto em BLOB — GET /api/boleto
  FUNCTION gerar_boleto_pdf(p_boleto IN t_boleto) RETURN BLOB;

  -- Resultado da cobranca REGISTRADA (online, API do banco)
  TYPE t_cobranca IS RECORD (
    id               VARCHAR2(100),
    status           VARCHAR2(30),
    linha_digitavel  VARCHAR2(80),
    codigo_barras    VARCHAR2(60),
    pix_copia_cola   VARCHAR2(1000)
  );

  -- OS DOIS EIXOS
  --
  -- `p_provider` e o CAMINHO ('on' = API do banco | 'off' = engine) e `p_banco`
  -- a INSTITUICAO ('c6', 'sicoob', 'itau', 'banco_brasil', ...).
  --
  -- O nome do banco em `p_provider` ('c6', 'sicoob', 'inter', 'itau') segue
  -- aceito como apelido de on+banco, e sai na 3.0.0. Mas o apelido so existe
  -- para esses QUATRO: `p_provider => 'banco_brasil'` e 422, e `'off'` sem
  -- `p_banco` tambem — a API responde pedindo o banco. Por isso `p_banco`
  -- existe aqui: sem ele o pacote so alcanca os quatro online.
  --
  -- Cadastra as credenciais do banco UMA vez e guarda o token bapi_ em g_token.
  -- O token so e devolvido nesta chamada: guarde-o se for reusar entre sessoes.
  --   POST /credenciais
  FUNCTION cadastrar_credenciais(p_tenant IN VARCHAR2, p_provider IN VARCHAR2,
                                 p_credenciais_json IN CLOB,
                                 p_banco IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

  -- Cobranca REGISTRADA na API do banco — POST /cobranca.
  -- Exige g_token do MESMO tenant+banco (o token e amarrado aos dois).
  --   registrar_cobranca(..., p_provider => 'on',  p_banco => 'c6')
  --   registrar_cobranca(..., p_provider => 'off', p_banco => 'banco_brasil')
  FUNCTION registrar_cobranca(p_tenant IN VARCHAR2, p_provider IN VARCHAR2,
                              p_boleto IN t_boleto,
                              p_account_config_json IN VARCHAR2 DEFAULT '{}',
                              p_banco IN VARCHAR2 DEFAULT NULL)
    RETURN t_cobranca;

  -- Resultado do link de pagamento com cartao (checkout)
  TYPE t_checkout IS RECORD (
    id         VARCHAR2(100),
    url        VARCHAR2(1000),
    status     VARCHAR2(30),
    expira_em  VARCHAR2(40)
  );

  -- Link de pagamento com CARTAO — POST /checkout.
  -- Nenhum dado de cartao passa por aqui: o PAN e digitado no dominio do banco.
  -- `p_com_pix` oferece Pix no MESMO link (QR gerado pelo banco).
  --
  -- p_idempotency_key: mande sempre que houver botao humano na frente. Sem ela,
  -- duplo clique cria DOIS links para a mesma venda. Derive da venda
  -- ('venda-'||id), nunca de SYSTIMESTAMP — chave nova a cada clique nao
  -- protege de nada.
  -- `p_valor` maior que zero e `p_redirect_url` ABSOLUTA (http:// ou https://):
  -- quem publica essa URL e o banco, na pagina dele -- relativa la resolve para
  -- o dominio do banco. A API recusa os dois casos com 422.
  FUNCTION criar_checkout(p_tenant IN VARCHAR2, p_valor IN NUMBER,
                          p_descricao IN VARCHAR2 DEFAULT NULL,
                          p_parcelas IN NUMBER DEFAULT 1,
                          p_com_pix IN BOOLEAN DEFAULT FALSE,
                          p_referencia IN VARCHAR2 DEFAULT NULL,
                          p_redirect_url IN VARCHAR2 DEFAULT NULL,
                          p_idempotency_key IN VARCHAR2 DEFAULT NULL,
                          p_provider IN VARCHAR2 DEFAULT 'c6',
                          p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout;

  -- Status do link — GET /checkout/{id}. `liquidado` e o unico que da baixa;
  -- `erro` e cartao recusado (o LINK acabou, a divida nao).
  FUNCTION consultar_checkout(p_tenant IN VARCHAR2, p_checkout_id IN VARCHAR2,
                              p_provider IN VARCHAR2 DEFAULT 'c6',
                              p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout;

  -- Cancela o link — DELETE /checkout/{id}
  FUNCTION cancelar_checkout(p_tenant IN VARCHAR2, p_checkout_id IN VARCHAR2,
                             p_provider IN VARCHAR2 DEFAULT 'c6',
                             p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout;

  -- Remessa CNAB (texto) — POST /api/remessa
  FUNCTION gerar_remessa(p_bank IN VARCHAR2, p_tipo IN VARCHAR2,
                         p_payload IN CLOB) RETURN CLOB;

  -- Retorno CNAB -> JSON — POST /api/retorno
  FUNCTION processar_retorno(p_bank IN VARCHAR2, p_tipo IN VARCHAR2,
                             p_arquivo IN CLOB) RETURN CLOB;

  -- Lote assíncrono: cria o job e devolve o job_id — POST /jobs/boletos
  FUNCTION criar_job_lote(p_tenant IN VARCHAR2, p_boletos_json IN CLOB,
                          p_idempotency_key IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

  -- Estado do job (JSON) — GET /jobs/boletos/{job_id}
  FUNCTION consultar_job(p_tenant IN VARCHAR2, p_job_id IN VARCHAR2) RETURN CLOB;

  -- Saúde da API
  FUNCTION healthcheck RETURN BOOLEAN;

END cobranca_api;
/

CREATE OR REPLACE PACKAGE BODY cobranca_api AS

  --------------------------------------------------------------------------
  -- Helpers HTTP (UTL_HTTP — funciona com ou sem APEX instalado)
  --------------------------------------------------------------------------
  PROCEDURE p_config_wallet IS
  BEGIN
    IF g_base_url LIKE 'https:%' AND g_wallet IS NOT NULL THEN
      UTL_HTTP.set_wallet(g_wallet, g_wallet_pw);
    END IF;
  END p_config_wallet;

  FUNCTION f_get_clob(p_path IN VARCHAR2) RETURN CLOB IS
    l_req   UTL_HTTP.req;
    l_resp  UTL_HTTP.resp;
    l_buf   VARCHAR2(32767);
    l_out   CLOB;
  BEGIN
    p_config_wallet;
    DBMS_LOB.createtemporary(l_out, TRUE);
    l_req := UTL_HTTP.begin_request(g_base_url || p_path, 'GET');
    UTL_HTTP.set_header(l_req, 'Accept', 'application/json');
    IF g_token IS NOT NULL THEN
      UTL_HTTP.set_header(l_req, 'Authorization', 'Bearer ' || g_token);
    END IF;
    l_resp := UTL_HTTP.get_response(l_req);
    BEGIN
      LOOP
        UTL_HTTP.read_text(l_resp, l_buf, 32767);
        DBMS_LOB.writeappend(l_out, LENGTH(l_buf), l_buf);
      END LOOP;
    EXCEPTION
      WHEN UTL_HTTP.end_of_body THEN NULL;
    END;
    UTL_HTTP.end_response(l_resp);
    RETURN l_out;
  END f_get_clob;

  -- DELETE existe para o cancelamento do checkout; identico ao GET fora do verbo.
  FUNCTION f_delete_clob(p_path IN VARCHAR2) RETURN CLOB IS
    l_req   UTL_HTTP.req;
    l_resp  UTL_HTTP.resp;
    l_buf   VARCHAR2(32767);
    l_out   CLOB;
  BEGIN
    p_config_wallet;
    DBMS_LOB.createtemporary(l_out, TRUE);
    l_req := UTL_HTTP.begin_request(g_base_url || p_path, 'DELETE');
    UTL_HTTP.set_header(l_req, 'Accept', 'application/json');
    IF g_token IS NOT NULL THEN
      UTL_HTTP.set_header(l_req, 'Authorization', 'Bearer ' || g_token);
    END IF;
    l_resp := UTL_HTTP.get_response(l_req);
    BEGIN
      LOOP
        UTL_HTTP.read_text(l_resp, l_buf, 32767);
        DBMS_LOB.writeappend(l_out, LENGTH(l_buf), l_buf);
      END LOOP;
    EXCEPTION
      WHEN UTL_HTTP.end_of_body THEN NULL;
    END;
    UTL_HTTP.end_response(l_resp);
    RETURN l_out;
  END f_delete_clob;

  FUNCTION f_get_blob(p_path IN VARCHAR2) RETURN BLOB IS
    l_req   UTL_HTTP.req;
    l_resp  UTL_HTTP.resp;
    l_raw   RAW(32767);
    l_out   BLOB;
  BEGIN
    p_config_wallet;
    DBMS_LOB.createtemporary(l_out, TRUE);
    l_req := UTL_HTTP.begin_request(g_base_url || p_path, 'GET');
    UTL_HTTP.set_header(l_req, 'Accept', 'application/pdf');
    l_resp := UTL_HTTP.get_response(l_req);
    BEGIN
      LOOP
        UTL_HTTP.read_raw(l_resp, l_raw, 32767);
        DBMS_LOB.writeappend(l_out, UTL_RAW.length(l_raw), l_raw);
      END LOOP;
    EXCEPTION
      WHEN UTL_HTTP.end_of_body THEN NULL;
    END;
    UTL_HTTP.end_response(l_resp);
    RETURN l_out;
  END f_get_blob;

  FUNCTION f_post_json(p_path IN VARCHAR2, p_body IN CLOB,
                       p_extra_header IN VARCHAR2 DEFAULT NULL,
                       p_extra_value  IN VARCHAR2 DEFAULT NULL) RETURN CLOB IS
    l_req   UTL_HTTP.req;
    l_resp  UTL_HTTP.resp;
    l_buf   VARCHAR2(32767);
    l_out   CLOB;
    l_off   NUMBER := 1;
    l_amt   NUMBER := 8000;
    l_chunk VARCHAR2(32767);
  BEGIN
    p_config_wallet;
    DBMS_LOB.createtemporary(l_out, TRUE);
    l_req := UTL_HTTP.begin_request(g_base_url || p_path, 'POST');
    UTL_HTTP.set_header(l_req, 'Content-Type', 'application/json; charset=utf-8');
    UTL_HTTP.set_header(l_req, 'Transfer-Encoding', 'chunked');
    IF g_token IS NOT NULL THEN
      UTL_HTTP.set_header(l_req, 'Authorization', 'Bearer ' || g_token);
    END IF;
    IF p_extra_header IS NOT NULL THEN
      UTL_HTTP.set_header(l_req, p_extra_header, p_extra_value);
    END IF;

    WHILE l_off <= DBMS_LOB.getlength(p_body) LOOP
      l_chunk := DBMS_LOB.substr(p_body, l_amt, l_off);
      UTL_HTTP.write_text(l_req, l_chunk);
      l_off := l_off + l_amt;
    END LOOP;

    l_resp := UTL_HTTP.get_response(l_req);
    BEGIN
      LOOP
        UTL_HTTP.read_text(l_resp, l_buf, 32767);
        DBMS_LOB.writeappend(l_out, LENGTH(l_buf), l_buf);
      END LOOP;
    EXCEPTION
      WHEN UTL_HTTP.end_of_body THEN NULL;
    END;
    UTL_HTTP.end_response(l_resp);
    RETURN l_out;
  END f_post_json;

  --------------------------------------------------------------------------
  -- Escapa um valor para dentro de string JSON.
  -- Sem isto, um nome com aspas (ex.: EMPRESA "X" LTDA) quebra o payload
  -- inteiro — a API recusa com 400 e a causa nao e obvia.
  --------------------------------------------------------------------------
  FUNCTION f_esc(p_txt IN VARCHAR2) RETURN VARCHAR2 IS
    l VARCHAR2(32767) := p_txt;
  BEGIN
    IF l IS NULL THEN RETURN ''; END IF;
    l := REPLACE(l, '\', '\\');   -- barra primeiro, senao duplica as demais
    l := REPLACE(l, '"',  '\"');
    l := REPLACE(l, CHR(13), '\r');
    l := REPLACE(l, CHR(10), '\n');
    l := REPLACE(l, CHR(9),  '\t');
    RETURN l;
  END f_esc;

  --------------------------------------------------------------------------
  -- Monta o parâmetro `data` (JSON) do contrato offline
  --------------------------------------------------------------------------
  FUNCTION f_json_boleto(p_boleto IN t_boleto) RETURN VARCHAR2 IS
  BEGIN
    RETURN '{'
      || '"agencia":"'           || p_boleto.agencia           || '",'
      || '"conta_corrente":"'    || p_boleto.conta_corrente    || '",'
      || CASE WHEN p_boleto.convenio IS NOT NULL
              THEN '"convenio":"' || p_boleto.convenio || '",' END
      || '"carteira":"'          || p_boleto.carteira          || '",'
      || '"nosso_numero":"'      || p_boleto.nosso_numero      || '",'
      || '"cedente":"' || f_esc(p_boleto.cedente) || '",'
      || '"documento_cedente":"' || p_boleto.documento_cedente || '",'
      || '"sacado":"' || f_esc(p_boleto.sacado) || '",'
      || '"sacado_documento":"'  || p_boleto.sacado_documento  || '",'
      || '"valor":'              || TO_CHAR(p_boleto.valor, 'FM9999999990.00',
                                            'NLS_NUMERIC_CHARACTERS=''.,''') || ','
      || '"data_vencimento":"'   || TO_CHAR(p_boleto.data_vencimento, 'YYYY-MM-DD') || '"'
      || '}';
  END f_json_boleto;

  --------------------------------------------------------------------------
  -- API pública
  --------------------------------------------------------------------------
  FUNCTION dados_boleto(p_boleto IN t_boleto) RETURN t_dados_boleto IS
    l_json CLOB;
    l_out  t_dados_boleto;
  BEGIN
    l_json := f_get_clob('/api/boleto/data'
                || '?bank=' || p_boleto.banco
                || '&data=' || UTL_URL.escape(f_json_boleto(p_boleto), TRUE));
    APEX_JSON.parse(l_json);
    l_out.nosso_numero           := APEX_JSON.get_varchar2('nosso_numero');
    l_out.nosso_numero_formatado := APEX_JSON.get_varchar2('nosso_numero_formatado');
    l_out.nosso_numero_dv        := APEX_JSON.get_varchar2('nosso_numero_dv');
    l_out.codigo_barras          := APEX_JSON.get_varchar2('codigo_barras');
    l_out.linha_digitavel        := APEX_JSON.get_varchar2('linha_digitavel');
    RETURN l_out;
  END dados_boleto;

  FUNCTION gerar_boleto_pdf(p_boleto IN t_boleto) RETURN BLOB IS
  BEGIN
    RETURN f_get_blob('/api/boleto'
             || '?bank=' || p_boleto.banco
             || '&type=pdf'
             || '&data=' || UTL_URL.escape(f_json_boleto(p_boleto), TRUE));
  END gerar_boleto_pdf;

  --------------------------------------------------------------------------
  -- Cobranca ONLINE (API do banco): credencial -> token bapi_ -> cobranca
  --------------------------------------------------------------------------
  FUNCTION cadastrar_credenciais(p_tenant IN VARCHAR2, p_provider IN VARCHAR2,
                                 p_credenciais_json IN CLOB,
                                 p_banco IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
    l_resp CLOB;
  BEGIN
    l_resp := f_post_json('/credenciais',
                TO_CLOB('{"tenant_id":"' || f_esc(p_tenant) || '",'
                        || '"provider":"' || f_esc(p_provider) || '",'
                        || CASE WHEN p_banco IS NOT NULL
                                THEN '"banco":"' || f_esc(p_banco) || '",' END
                        || '"credentials":') || p_credenciais_json || TO_CLOB('}'));
    APEX_JSON.parse(l_resp);
    g_token := APEX_JSON.get_varchar2('token');
    RETURN g_token;
  END cadastrar_credenciais;

  FUNCTION registrar_cobranca(p_tenant IN VARCHAR2, p_provider IN VARCHAR2,
                              p_boleto IN t_boleto,
                              p_account_config_json IN VARCHAR2 DEFAULT '{}',
                              p_banco IN VARCHAR2 DEFAULT NULL)
    RETURN t_cobranca IS
    l_resp CLOB;
    l_out  t_cobranca;
    l_val  VARCHAR2(40);
  BEGIN
    -- 424 = o BANCO recusou a credencial (nao e erro do servico).
    -- 403 = o token nao pertence a este tenant+banco: o bapi_ e amarrado
    --       aos dois, entao token do C6 em rota Sicoob e recusado de proposito.
    l_val := TO_CHAR(p_boleto.valor, 'FM9999999990.00',
                     'NLS_NUMERIC_CHARACTERS=''.,''');
    l_resp := f_post_json('/cobranca',
      TO_CLOB('{'
        || '"tenant_id":"' || f_esc(p_tenant)   || '",'
        || '"provider":"'  || f_esc(p_provider) || '",'
        || CASE WHEN p_banco IS NOT NULL
                THEN '"banco":"' || f_esc(p_banco) || '",' END
        || '"account_config":' || p_account_config_json || ','
        || '"cobranca":{'
        ||   '"valor":' || l_val || ','
        ||   '"vencimento":"' || TO_CHAR(p_boleto.data_vencimento, 'YYYY-MM-DD') || '",'
        ||   '"seu_numero":"' || f_esc(p_boleto.nosso_numero) || '",'
        ||   '"pagador":{"nome":"' || f_esc(p_boleto.sacado) || '",'
        ||                '"documento":"' || f_esc(p_boleto.sacado_documento) || '"}'
        || '}}'));
    APEX_JSON.parse(l_resp);
    l_out.id              := APEX_JSON.get_varchar2('id');
    l_out.status          := APEX_JSON.get_varchar2('status');
    l_out.linha_digitavel := APEX_JSON.get_varchar2('linha_digitavel');
    l_out.codigo_barras   := APEX_JSON.get_varchar2('codigo_barras');
    l_out.pix_copia_cola  := APEX_JSON.get_varchar2('pix_copia_cola');
    RETURN l_out;
  END registrar_cobranca;

  --------------------------------------------------------------------------
  -- Checkout — link de pagamento com cartao (e Pix no mesmo link)
  --
  -- Nao ha campo de cartao em lugar nenhum daqui, de proposito: o PAN e
  -- digitado no dominio do banco e o escopo PCI-DSS fica la.
  --------------------------------------------------------------------------
  FUNCTION f_checkout_out(p_resp IN CLOB) RETURN t_checkout IS
    l_out t_checkout;
  BEGIN
    APEX_JSON.parse(p_resp);
    l_out.id        := APEX_JSON.get_varchar2('id');
    l_out.url       := APEX_JSON.get_varchar2('url');
    l_out.status    := APEX_JSON.get_varchar2('status');
    l_out.expira_em := APEX_JSON.get_varchar2('expira_em');
    RETURN l_out;
  END f_checkout_out;

  FUNCTION criar_checkout(p_tenant IN VARCHAR2, p_valor IN NUMBER,
                          p_descricao IN VARCHAR2 DEFAULT NULL,
                          p_parcelas IN NUMBER DEFAULT 1,
                          p_com_pix IN BOOLEAN DEFAULT FALSE,
                          p_referencia IN VARCHAR2 DEFAULT NULL,
                          p_redirect_url IN VARCHAR2 DEFAULT NULL,
                          p_idempotency_key IN VARCHAR2 DEFAULT NULL,
                          p_provider IN VARCHAR2 DEFAULT 'c6',
                          p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout IS
    l_body CLOB;
    l_ck   VARCHAR2(4000);
  BEGIN
    l_ck := '"valor":' || TO_CHAR(p_valor, 'FM9999999990.00',
                                  'NLS_NUMERIC_CHARACTERS=''.,''')
         || ',"tipo":"credito"'
         || ',"parcelas":' || NVL(p_parcelas, 1);
    -- A API exige juros_por quando parcelas > 1. O default dela ja e `loja`,
    -- mas explicitar evita descobrir a regra por 422 em producao.
    IF NVL(p_parcelas, 1) > 1 THEN
      l_ck := l_ck || ',"juros_por":"loja"';
    END IF;
    IF p_com_pix THEN
      l_ck := l_ck || ',"pix":true';
    END IF;
    IF p_descricao IS NOT NULL THEN
      l_ck := l_ck || ',"descricao":"' || f_esc(p_descricao) || '"';
    END IF;
    IF p_referencia IS NOT NULL THEN
      l_ck := l_ck || ',"external_reference_id":"' || f_esc(p_referencia) || '"';
    END IF;
    IF p_redirect_url IS NOT NULL THEN
      l_ck := l_ck || ',"redirect_url":"' || f_esc(p_redirect_url) || '"';
    END IF;

    l_body := TO_CLOB('{"tenant_id":"' || f_esc(p_tenant) || '",'
                      || '"provider":"' || f_esc(p_provider) || '",'
                      || CASE WHEN p_banco IS NOT NULL
                              THEN '"banco":"' || f_esc(p_banco) || '",' END
                      || '"checkout":{' || l_ck || '}}');

    -- Reenvio com a mesma chave devolve o MESMO link, sem criar outro no banco.
    -- Mesma chave com corpo diferente e 422 — a chave identifica UMA requisicao.
    IF p_idempotency_key IS NOT NULL THEN
      RETURN f_checkout_out(f_post_json('/checkout', l_body,
                                        'Idempotency-Key', p_idempotency_key));
    END IF;
    RETURN f_checkout_out(f_post_json('/checkout', l_body));
  END criar_checkout;

  FUNCTION consultar_checkout(p_tenant IN VARCHAR2, p_checkout_id IN VARCHAR2,
                              p_provider IN VARCHAR2 DEFAULT 'c6',
                              p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout IS
  BEGIN
    RETURN f_checkout_out(
      f_get_clob('/checkout/' || UTL_URL.escape(p_checkout_id)
                 || '?tenant_id=' || UTL_URL.escape(p_tenant)
                 || '&provider='  || UTL_URL.escape(p_provider)
                 || CASE WHEN p_banco IS NOT NULL
                         THEN '&banco=' || UTL_URL.escape(p_banco) END));
  END consultar_checkout;

  FUNCTION cancelar_checkout(p_tenant IN VARCHAR2, p_checkout_id IN VARCHAR2,
                             p_provider IN VARCHAR2 DEFAULT 'c6',
                             p_banco IN VARCHAR2 DEFAULT NULL) RETURN t_checkout IS
  BEGIN
    RETURN f_checkout_out(
      f_delete_clob('/checkout/' || UTL_URL.escape(p_checkout_id)
                    || '?tenant_id=' || UTL_URL.escape(p_tenant)
                    || '&provider='  || UTL_URL.escape(p_provider)
                    || CASE WHEN p_banco IS NOT NULL
                            THEN '&banco=' || UTL_URL.escape(p_banco) END));
  END cancelar_checkout;

  FUNCTION gerar_remessa(p_bank IN VARCHAR2, p_tipo IN VARCHAR2,
                         p_payload IN CLOB) RETURN CLOB IS
  BEGIN
    -- /api/remessa espera multipart; via JSON use /api/render/remessa
    RETURN f_post_json('/api/render/remessa',
             TO_CLOB('{"bank":"' || p_bank || '","type":"' || p_tipo || '","data":')
             || p_payload || TO_CLOB('}'));
  END gerar_remessa;

  FUNCTION processar_retorno(p_bank IN VARCHAR2, p_tipo IN VARCHAR2,
                             p_arquivo IN CLOB) RETURN CLOB IS
  BEGIN
    -- Requer multipart: em PL/SQL puro, prefira APEX_WEB_SERVICE.make_rest_request
    -- com p_body_blob (ver README). Mantido aqui para referência de contrato.
    RAISE_APPLICATION_ERROR(-20001,
      'Use APEX_WEB_SERVICE.make_rest_request (multipart) — ver examples/oracle/README.md');
  END processar_retorno;

  FUNCTION criar_job_lote(p_tenant IN VARCHAR2, p_boletos_json IN CLOB,
                          p_idempotency_key IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
    l_resp CLOB;
  BEGIN
    l_resp := f_post_json('/jobs/boletos',
                TO_CLOB('{"tenant_id":"' || p_tenant || '","boletos":')
                || p_boletos_json || TO_CLOB('}'),
                CASE WHEN p_idempotency_key IS NOT NULL THEN 'Idempotency-Key' END,
                p_idempotency_key);
    APEX_JSON.parse(l_resp);
    RETURN APEX_JSON.get_varchar2('job_id');
  END criar_job_lote;

  FUNCTION consultar_job(p_tenant IN VARCHAR2, p_job_id IN VARCHAR2) RETURN CLOB IS
  BEGIN
    RETURN f_get_clob('/jobs/boletos/' || p_job_id || '?tenant_id=' || p_tenant);
  END consultar_job;

  FUNCTION healthcheck RETURN BOOLEAN IS
    l_json CLOB;
  BEGIN
    l_json := f_get_clob('/health');
    APEX_JSON.parse(l_json);
    RETURN APEX_JSON.get_varchar2('status') = 'ok';
  EXCEPTION
    WHEN OTHERS THEN RETURN FALSE;
  END healthcheck;

END cobranca_api;
/
