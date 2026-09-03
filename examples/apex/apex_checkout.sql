--------------------------------------------------------------------------------
-- Oracle APEX — link de pagamento com CARTÃO (e Pix no mesmo link)
--
-- Este é o padrão de balcão: a página cria o link, mostra o QR/URL para o
-- pagador e acompanha o status até liquidar. Nenhum dado de cartão passa pelo
-- APEX nem por esta API — o PAN é digitado no domínio do banco, e o escopo
-- PCI-DSS fica lá. Não existe campo de cartão nesta página, de propósito.
--
-- Duas coisas que separam isto de um POST comum, e que são o motivo do
-- exemplo existir:
--
--   1) `Idempotency-Key` no botão. Sem ela, duplo clique cria DOIS links para
--      a mesma venda — e nada impede o pagador de pagar os dois. Em página de
--      APEX com botão, isso não é hipótese: é terça-feira.
--
--   2) O status vem do BANCO, não da volta do pagador. O `redirect_url` traz
--      o navegador de volta, mas quem confirma pagamento é a consulta (ou o
--      webhook). Confiar no retorno do browser é confiar no cliente.
--
-- Itens de página esperados (renomeie conforme a sua aplicação):
--   P30_VENDA_ID, P30_VALOR, P30_PARCELAS, P30_DESCRICAO, P30_COM_PIX,
--   P30_CHECKOUT_ID, P30_CHECKOUT_URL, P30_STATUS
-- Itens de aplicação: G_COBRANCA_API_URL, G_TENANT_ID, G_BAPI_TOKEN (protegido)
--------------------------------------------------------------------------------

--==============================================================================
-- 1) PROCESS (On Submit) — cria o link de pagamento
--==============================================================================
DECLARE
  l_body CLOB;
  l_resp CLOB;
BEGIN
  APEX_JSON.initialize_clob_output;
  APEX_JSON.open_object;
  APEX_JSON.write('tenant_id', :G_TENANT_ID);
  APEX_JSON.write('provider',  'c6');           -- hoje só o C6 oferece link hospedado
  APEX_JSON.open_object('checkout');
  APEX_JSON.write('valor',     TO_CHAR(:P30_VALOR, 'FM9999999990.00',
                                       'NLS_NUMERIC_CHARACTERS=''.,'''));
  APEX_JSON.write('tipo',      'credito');
  -- `parcelas` é TETO, e a política é SUA: a API não tem valor mínimo de
  -- parcela e repassa o número ao banco como veio. Com "até 3x, mínimo R$100",
  -- calcule aqui — mandar 3 fixo numa venda de R$90 oferece 3 × R$30 ao
  -- pagador, e o banco não vai barrar isso por você:
  --   GREATEST(1, LEAST(3, FLOOR(:P30_VALOR / 100)))
  APEX_JSON.write('parcelas',  NVL(:P30_PARCELAS, 1));
  -- `juros_por` é obrigatório quando parcelas > 1; o default da API é `loja`,
  -- mas explicitar aqui evita descobrir a regra por 422 em produção.
  IF NVL(:P30_PARCELAS, 1) > 1 THEN
    APEX_JSON.write('juros_por', 'loja');
  END IF;
  IF :P30_COM_PIX = 'Y' THEN
    APEX_JSON.write('pix', TRUE);               -- QR Pix no MESMO link, gerado pelo banco
  END IF;
  APEX_JSON.write('descricao', :P30_DESCRICAO);
  -- `external_reference_id` amarra o link à venda: é por ele que a conciliação
  -- e o webhook reencontram o registro daqui.
  APEX_JSON.write('external_reference_id', :P30_VENDA_ID);
  -- ABSOLUTA, e por isso o HOST_URL na frente: `APEX_PAGE.get_url` sozinho
  -- devolve `f?p=...` relativo, e quem publica essa URL e o BANCO, na pagina
  -- dele -- caminho relativo la resolve para o dominio do banco, nao para o
  -- seu. A API recusa o que nao comeca com http:// ou https:// (422).
  APEX_JSON.write('redirect_url',
    APEX_UTIL.host_url(p_option => 'APEX_PATH') ||
    APEX_PAGE.get_url(p_application => :APP_ID, p_page => :APP_PAGE_ID,
                      p_items => 'P30_VENDA_ID', p_values => :P30_VENDA_ID));
  APEX_JSON.close_object;
  APEX_JSON.close_object;
  l_body := APEX_JSON.get_clob_output;
  APEX_JSON.free_output;

  APEX_WEB_SERVICE.g_request_headers.DELETE;
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Content-Type';
  APEX_WEB_SERVICE.g_request_headers(1).value := 'application/json';
  APEX_WEB_SERVICE.g_request_headers(2).name  := 'Authorization';
  APEX_WEB_SERVICE.g_request_headers(2).value := 'Bearer ' || :G_BAPI_TOKEN;
  -- A CHAVE. Derivada da venda, não de SYSTIMESTAMP: chave nova a cada clique
  -- não protege de nada. Reenvio devolve o MESMO link, sem tocar no banco.
  APEX_WEB_SERVICE.g_request_headers(3).name  := 'Idempotency-Key';
  APEX_WEB_SERVICE.g_request_headers(3).value := 'venda-' || :P30_VENDA_ID;

  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/checkout',
              p_http_method => 'POST',
              p_body        => l_body);

  IF APEX_WEB_SERVICE.g_status_code NOT IN (200, 201) THEN
    -- 422 aqui costuma ser payload (parcelas sem juros_por, endereço incompleto
    -- do pagador) ou chave de idempotência reusada com outro corpo. O `detail`
    -- da API diz qual campo — mostrar ele poupa uma ida ao log.
    APEX_JSON.parse(l_resp);
    APEX_ERROR.add_error(
      p_message          => 'Não foi possível criar o link (HTTP '
                            || APEX_WEB_SERVICE.g_status_code || '): '
                            || APEX_JSON.get_varchar2('detail'),
      p_display_location => APEX_ERROR.c_inline_in_notification);
    RETURN;
  END IF;

  APEX_JSON.parse(l_resp);
  :P30_CHECKOUT_ID  := APEX_JSON.get_varchar2('id');
  :P30_CHECKOUT_URL := APEX_JSON.get_varchar2('url');
  :P30_STATUS       := APEX_JSON.get_varchar2('status');   -- 'pendente'

  UPDATE vendas
     SET checkout_id  = :P30_CHECKOUT_ID,
         checkout_url = :P30_CHECKOUT_URL,
         status_pgto  = :P30_STATUS
   WHERE id = :P30_VENDA_ID;
END;

--==============================================================================
-- 2) AJAX Callback "ATUALIZAR_CHECKOUT" — Dynamic Action com timer (5s)
--
--    Mesmo padrão do apex_lote_job.sql: a página não trava esperando. A
--    diferença é o critério de parada — aqui o timer roda até o status sair de
--    `pendente`, e o Dynamic Action deve desligar o intervalo quando isso
--    acontecer, senão a página fica consultando o banco para sempre.
--==============================================================================
DECLARE
  l_resp CLOB;
BEGIN
  APEX_WEB_SERVICE.g_request_headers.DELETE;
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Authorization';
  APEX_WEB_SERVICE.g_request_headers(1).value := 'Bearer ' || :G_BAPI_TOKEN;

  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/checkout/' || :P30_CHECKOUT_ID,
              p_http_method => 'GET',
              p_parm_name   => APEX_UTIL.string_to_table('tenant_id:provider'),
              p_parm_value  => APEX_UTIL.string_to_table(:G_TENANT_ID || ':c6'));

  -- JSON cru para o Dynamic Action ler {status, url, expira_em}
  SYS.HTP.p(l_resp);
END;

--==============================================================================
-- 3) Baixa da venda — só quando o BANCO diz liquidado
--
--    Chame no mesmo callback acima ou num process separado. O ponto é onde a
--    condição está: `status = 'liquidado'` vindo da consulta, nunca do retorno
--    do navegador. O pagador pode fechar a aba antes de voltar, e pode voltar
--    sem ter pago.
--==============================================================================
DECLARE
  l_resp   CLOB;
  l_status VARCHAR2(30);
BEGIN
  APEX_WEB_SERVICE.g_request_headers.DELETE;
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Authorization';
  APEX_WEB_SERVICE.g_request_headers(1).value := 'Bearer ' || :G_BAPI_TOKEN;

  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/checkout/' || :P30_CHECKOUT_ID,
              p_http_method => 'GET',
              p_parm_name   => APEX_UTIL.string_to_table('tenant_id:provider'),
              p_parm_value  => APEX_UTIL.string_to_table(:G_TENANT_ID || ':c6'));
  APEX_JSON.parse(l_resp);
  l_status := APEX_JSON.get_varchar2('status');

  :P30_STATUS := l_status;

  IF l_status = 'liquidado' THEN
    UPDATE vendas
       SET status_pgto = 'liquidado',
           pago_em     = SYSTIMESTAMP
     WHERE id = :P30_VENDA_ID
       AND status_pgto != 'liquidado';    -- idempotente: dar baixa duas vezes não
  ELSIF l_status = 'erro' THEN
    -- Cartão recusado é `erro`, não `baixado`: o LINK se esgotou, a dívida não.
    -- Quem decide se a venda segue em aberto é você, que conhece o contrato.
    :P30_STATUS := 'erro';
  END IF;
END;

--==============================================================================
-- 4) Região com o link e o QR (PL/SQL Dynamic Content)
--==============================================================================
BEGIN
  IF :P30_CHECKOUT_URL IS NULL THEN
    RETURN;
  END IF;
  SYS.HTP.p('<div style="text-align:center">');
  SYS.HTP.p('<a href="' || APEX_ESCAPE.html_attribute(:P30_CHECKOUT_URL) ||
            '" target="_blank" class="t-Button t-Button--hot">Pagar</a>');
  -- O QR abaixo é do LINK (cartão + Pix, se pedido). Renderizado no cliente
  -- para não depender de biblioteca de imagem no banco.
  SYS.HTP.p('<div id="qr-checkout" data-url="' ||
            APEX_ESCAPE.html_attribute(:P30_CHECKOUT_URL) || '"></div>');
  SYS.HTP.p('</div>');
END;

--==============================================================================
-- 5) Cancelar o link (Process On Submit, botão "Cancelar cobrança")
--==============================================================================
DECLARE
  l_resp CLOB;
BEGIN
  APEX_WEB_SERVICE.g_request_headers.DELETE;
  APEX_WEB_SERVICE.g_request_headers(1).name  := 'Authorization';
  APEX_WEB_SERVICE.g_request_headers(1).value := 'Bearer ' || :G_BAPI_TOKEN;

  l_resp := APEX_WEB_SERVICE.make_rest_request(
              p_url         => :G_COBRANCA_API_URL || '/checkout/' || :P30_CHECKOUT_ID,
              p_http_method => 'DELETE',
              p_parm_name   => APEX_UTIL.string_to_table('tenant_id:provider'),
              p_parm_value  => APEX_UTIL.string_to_table(:G_TENANT_ID || ':c6'));

  APEX_JSON.parse(l_resp);
  :P30_STATUS := APEX_JSON.get_varchar2('status');   -- 'baixado'
  UPDATE vendas SET status_pgto = :P30_STATUS WHERE id = :P30_VENDA_ID;
END;

--==============================================================================
-- 6) ALTERNATIVA AO POLLING — receber o webhook em ORDS
--
--    O polling da seção 2 resolve a tela aberta. Para dar baixa com a tela
--    FECHADA (o pagador paga o link três horas depois, em casa), o caminho é o
--    webhook: a Cobranca-API empurra o evento para um endpoint ORDS seu.
--
--    Cadastre o destino em POST /config/webhook-banco com service=CHECKOUT, e
--    aponte SUB__<tenant>__URL para o handler abaixo.
--==============================================================================
-- ORDS: POST /pagamentos/eventos
--
-- DECLARE
--   l_corpo      CLOB := :body_text;
--   l_assinatura VARCHAR2(200) := :x_signature;   -- header X-Signature
--   l_esperada   VARCHAR2(200);
--   l_ref        VARCHAR2(100);
--   l_status     VARCHAR2(30);
--   l_confirmado VARCHAR2(10);
-- BEGIN
--   -- VALIDE A ASSINATURA ANTES DE OLHAR O CORPO. Sem isto, qualquer um que
--   -- descubra a URL posta {"status":"liquidado"} e a sua venda é baixada de
--   -- graça. O segredo é o SUB__<tenant>__SECRET.
--   l_esperada := 'sha256=' || LOWER(RAWTOHEX(
--       DBMS_CRYPTO.mac(UTL_RAW.cast_to_raw(l_corpo),
--                       DBMS_CRYPTO.hmac_sh256,
--                       UTL_RAW.cast_to_raw(f_segredo_do_tenant))));
--   IF l_assinatura IS NULL OR l_assinatura != l_esperada THEN
--     :status_code := 401;
--     RETURN;
--   END IF;
--
--   APEX_JSON.parse(l_corpo);
--   l_status     := APEX_JSON.get_varchar2('status');
--   l_confirmado := APEX_JSON.get_varchar2('confirmado');
--   l_ref        := APEX_JSON.get_varchar2('raw.external_reference_id');
--
--   -- `confirmado = false` significa que o gateway reconsultou o banco e o
--   -- banco DISCORDOU do corpo recebido: o `status` que chegou já é o do banco.
--   -- `null` significa que ninguém verificou — trate como aviso, não como baixa.
--   IF l_status = 'liquidado' AND NVL(l_confirmado, 'false') = 'true' THEN
--     UPDATE vendas SET status_pgto = 'liquidado', pago_em = SYSTIMESTAMP
--      WHERE external_reference_id = l_ref AND status_pgto != 'liquidado';
--   END IF;
--
--   -- Responda 2xx SEMPRE que tiver processado: a Cobranca-API re-tenta com
--   -- backoff enquanto não receber 2xx, e reentrega repetida do MESMO evento
--   -- chega deduplicada. O `AND status_pgto != 'liquidado'` acima é o seu
--   -- cinto de segurança para o resto.
--   :status_code := 200;
-- END;
