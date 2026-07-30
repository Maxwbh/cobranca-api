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
