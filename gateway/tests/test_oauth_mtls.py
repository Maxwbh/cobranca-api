import httpx
import respx

from app.clients.oauth_mtls import OAuthMtlsClient


def _make_client(pfx_b64, client_id="cid"):
    return OAuthMtlsClient(
        base_url="https://api.test",
        auth_url="https://api.test/oauth/token",
        client_id=client_id,
        client_secret="sec",
        pfx_base64=pfx_b64,
        pfx_password="secret",
        scopes=["cobranca_boletos_incluir", "cobranca_boletos_consultar"],
        default_headers={"client_id": client_id},
    )


@respx.mock
def test_authenticates_with_scopes_and_caches_token(pfx_b64):
    OAuthMtlsClient._token_cache.clear()
    auth = respx.post("https://api.test/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    )
    c = _make_client(pfx_b64, client_id="unique-a")

    assert c.token() == "tok"
    assert c.token() == "tok"  # 2ª chamada usa cache
    assert auth.call_count == 1

    # scopes vão no corpo do token como string separada por espaço
    sent_body = auth.calls.last.request.content.decode()
    assert "scope=cobranca_boletos_incluir+cobranca_boletos_consultar" in sent_body
    assert "grant_type=client_credentials" in sent_body


@respx.mock
def test_request_sends_bearer_and_extra_headers(pfx_b64):
    OAuthMtlsClient._token_cache.clear()
    respx.post("https://api.test/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    )
    ping = respx.get("https://api.test/v1/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    c = _make_client(pfx_b64, client_id="unique-b")

    assert c.request("GET", "/v1/ping") == {"ok": True}
    req = ping.calls.last.request
    assert req.headers["authorization"] == "Bearer tok"
    assert req.headers["client_id"] == "unique-b"  # header extra do Sicoob


@respx.mock
def test_request_raises_on_http_error(pfx_b64):
    OAuthMtlsClient._token_cache.clear()
    respx.post("https://api.test/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
    )
    respx.get("https://api.test/v1/boom").mock(return_value=httpx.Response(422, json={"erro": "x"}))
    c = _make_client(pfx_b64, client_id="unique-c")

    try:
        c.request("GET", "/v1/boom")
        assert False, "deveria ter levantado"
    except httpx.HTTPStatusError as e:
        assert e.response.status_code == 422


def test_build_ssl_context_loads_pkcs12(pfx_b64):
    # Sem rede: só garante que o PKCS12 vira um SSLContext válido (cert client carregado).
    c = _make_client(pfx_b64)
    import ssl

    assert isinstance(c._ssl, ssl.SSLContext)
