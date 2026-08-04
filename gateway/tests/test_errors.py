def test_cobranca_sem_credencial_retorna_424_nao_500(client, cobranca_payload, monkeypatch):
    # No caminho REGISTRADO (provider pronto), credencial ausente -> 424 (não 500).
    monkeypatch.setenv("SICOOB_REGISTERED_READY", "true")
    body = {
        "tenant_id": "nao-provisionado",
        "provider": "sicoob",
        "account_config": {},
        "cobranca": cobranca_payload,
    }
    r = client.post("/cobranca", json=body)
    assert r.status_code == 424
    assert "cofre" in r.json()["detail"]


def test_cobranca_payload_invalido_retorna_422(client):
    # falta pagador/valor -> validação do pydantic
    r = client.post("/cobranca", json={"tenant_id": "x", "provider": "c6", "cobranca": {}})
    assert r.status_code == 422


# Erro do BANCO (upstream) nunca pode virar 500 genérico.
def test_erro_403_do_banco_vira_424(client, monkeypatch):
    import httpx

    def falha_403(self, method, path, json=None):
        req = httpx.Request("POST", "https://banco.exemplo/v1/auth")
        resp = httpx.Response(403, json={"error": "forbidden"}, request=req)
        raise httpx.HTTPStatusError("403", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", falha_403)
    monkeypatch.setenv("VAULT__t__c6__client_id", "a")
    monkeypatch.setenv("VAULT__t__c6__client_secret", "b")
    r = client.post("/pix", json={"tenant_id": "t", "provider": "c6",
                                   "account_config": {"chave_pix": "x"},
                                   "pix": {"valor": "10.00"}})
    assert r.status_code == 424
    assert r.json()["upstream"]["status"] == 403


def test_erro_500_do_banco_vira_502(client, monkeypatch):
    import httpx

    def falha_500(self, method, path, json=None):
        req = httpx.Request("GET", "https://banco.exemplo/v1/x")
        resp = httpx.Response(500, text="boom", request=req)
        raise httpx.HTTPStatusError("500", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", falha_500)
    monkeypatch.setenv("VAULT__t__c6__client_id", "a")
    monkeypatch.setenv("VAULT__t__c6__client_secret", "b")
    r = client.post("/pix", json={"tenant_id": "t", "provider": "c6",
                                   "account_config": {"chave_pix": "x"},
                                   "pix": {"valor": "10.00"}})
    assert r.status_code == 502


def _com_erro_do_banco(client, monkeypatch, status, *, body=None, headers=None):
    """Faz o banco responder `status` e devolve a resposta que o gateway emite."""
    import httpx

    def falha(self, method, path, json=None, params=None):
        req = httpx.Request("POST", "https://banco.exemplo/v1/x")
        resp = httpx.Response(status, json=body or {"erro": "x"},
                              headers=headers or {}, request=req)
        raise httpx.HTTPStatusError(str(status), request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", falha)
    monkeypatch.setenv("VAULT__t__c6__client_id", "a")
    monkeypatch.setenv("VAULT__t__c6__client_secret", "b")
    return client.post("/pix", json={"tenant_id": "t", "provider": "c6",
                                     "account_config": {"chave_pix": "x"},
                                     "pix": {"valor": "10.00"}})


# A familia inteira: erro que o CHAMADOR conserta responde 4xx; erro do banco,
# 5xx. Antes so 401/403 escapavam do 502, e todo o resto virava "bad gateway".
def test_400_e_422_do_banco_viram_422(client, monkeypatch):
    for upstream in (400, 422):
        r = _com_erro_do_banco(client, monkeypatch, upstream)
        assert r.status_code == 422, (upstream, r.text)
        assert r.json()["upstream"]["status"] == upstream  # diagnostico preservado


def test_404_do_banco_vira_404(client, monkeypatch):
    r = _com_erro_do_banco(client, monkeypatch, 404)
    assert r.status_code == 404
    assert r.json()["upstream"]["status"] == 404


def test_409_do_banco_vira_409(client, monkeypatch):
    r = _com_erro_do_banco(client, monkeypatch, 409)
    assert r.status_code == 409


def test_429_do_banco_vira_429_e_repassa_retry_after(client, monkeypatch):
    r = _com_erro_do_banco(client, monkeypatch, 429, headers={"Retry-After": "30"})
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "30"


def test_status_nao_mapeado_continua_502(client, monkeypatch):
    # 418 nao esta na tabela: o default protege contra status inesperado do banco.
    r = _com_erro_do_banco(client, monkeypatch, 418)
    assert r.status_code == 502
    assert r.json()["upstream"]["status"] == 418


def test_timeout_do_banco_vira_504(client, monkeypatch):
    import httpx

    def timeout(self, method, path, json=None):
        raise httpx.ConnectTimeout("tempo esgotado",
                                    request=httpx.Request("GET", "https://banco.exemplo/x"))

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", timeout)
    monkeypatch.setenv("VAULT__t__c6__client_id", "a")
    monkeypatch.setenv("VAULT__t__c6__client_secret", "b")
    r = client.post("/pix", json={"tenant_id": "t", "provider": "c6",
                                   "account_config": {"chave_pix": "x"},
                                   "pix": {"valor": "10.00"}})
    assert r.status_code == 504


def test_erro_no_endpoint_de_token_vira_424_e_nao_422(client, monkeypatch):
    """O Inter devolve 400 para client_credentials invalido, e o mapa geral
    traduzia isso como "o banco recusou os dados enviados" — mandando quem
    integra cacar defeito no payload quando o problema e' a credencial."""
    import httpx

    monkeypatch.setenv("VAULT__t1__inter__client_id", "cid")
    monkeypatch.setenv("VAULT__t1__inter__client_secret", "errado")
    monkeypatch.setenv("INTER_REGISTERED_READY", "true")

    def fake(self):
        req = httpx.Request("POST", "https://cdpj-sandbox.partners.uatinter.co/oauth/v2/token")
        resp = httpx.Response(400, text="", request=req)
        raise httpx.HTTPStatusError("400", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.token", fake)
    r = client.get("/cobranca/abc", params={"tenant_id": "t1", "provider": "inter"})
    assert r.status_code == 424, r.text
    assert "credenciais" in r.json()["detail"]


def test_erro_400_fora_do_token_continua_sendo_payload(client, monkeypatch):
    """A regra e' estreita: so o endpoint de autenticacao. 400 numa rota de
    negocio continua significando dado recusado."""
    import httpx

    monkeypatch.setenv("VAULT__t1__inter__client_id", "cid")
    monkeypatch.setenv("VAULT__t1__inter__client_secret", "sec")
    monkeypatch.setenv("INTER_REGISTERED_READY", "true")

    def fake(self, method, path, json=None, params=None):
        req = httpx.Request(method, f"https://cdpj-sandbox.partners.uatinter.co{path}")
        resp = httpx.Response(400, json={"detail": "campo invalido"}, request=req)
        raise httpx.HTTPStatusError("400", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    r = client.get("/cobranca/abc", params={"tenant_id": "t1", "provider": "inter"})
    assert r.status_code == 422, r.text
    assert "recusou os dados" in r.json()["detail"]
