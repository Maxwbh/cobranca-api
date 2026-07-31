--------------------------------------------------------------------------------
-- Pré-requisitos de rede (executar como DBA, UMA vez)
-- Libera o schema da aplicação a chamar a Cobranca-API por HTTP/HTTPS.
--------------------------------------------------------------------------------

-- 1) ACL de rede (Oracle 12c+)
BEGIN
  DBMS_NETWORK_ACL_ADMIN.append_host_ace(
    host => 'SEU-SERVICO.onrender.com',   -- troque pelo seu host
    ace  => xs$ace_type(
              privilege_list => xs$name_list('http', 'connect', 'resolve'),
              principal_name => 'MEU_SCHEMA', -- schema dono do pacote
              principal_type => xs_acl.ptype_db));
END;
/

-- 2) HTTPS: wallet com a cadeia de certificados do host
--    No servidor do banco de dados:
--      orapki wallet create -wallet /u01/app/oracle/wallet -pwd <senha> -auto_login
--      orapki wallet add -wallet /u01/app/oracle/wallet -trusted_cert \
--             -cert cadeia.crt -pwd <senha>
--
--    Depois, libere a wallet para o schema:
BEGIN
  DBMS_NETWORK_ACL_ADMIN.append_wallet_ace(
    wallet_path => 'file:/u01/app/oracle/wallet',
    ace         => xs$ace_type(
                     privilege_list => xs$name_list('use_client_certificates',
                                                    'use_passwords'),
                     principal_name => 'MEU_SCHEMA',
                     principal_type => xs_acl.ptype_db));
END;
/

-- 3) Teste rápido (deve imprimir {"status":"ok"})
SET SERVEROUTPUT ON
DECLARE
  l_resp CLOB;
BEGIN
  UTL_HTTP.set_wallet('file:/u01/app/oracle/wallet');
  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => 'https://SEU-SERVICO.onrender.com/health',
              p_http_method => 'GET');
  DBMS_OUTPUT.put_line(l_resp);
END;
/

-- Autonomous Database (ADB): a wallet já vem configurada; basta a ACL do host
-- via DBMS_CLOUD ou o append_host_ace acima.
