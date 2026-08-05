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


def test_aceita_cert_e_key_em_pem_separado(tmp_path):
    """O Banco Inter entrega .crt + .key, nao PKCS12. Sem este caminho,
    integrar exigiria rodar `openssl pkcs12 -export` antes da primeira
    chamada — atrito que a API absorve."""
    from app.clients.oauth_mtls import OAuthMtlsClient

    cert, key = _par_pem()
    ctx = OAuthMtlsClient._build_ssl_context("", "", cert_pem=cert, key_pem=key)
    assert ctx.get_ca_certs() is not None  # contexto construiu sem erro


def test_aceita_o_mesmo_pem_em_base64():
    """Quem cola o conteudo do arquivo manda PEM cru; quem automatiza manda
    base64. Exigir um formato faria metade errar, e o handshake que falha nao
    diz qual metade."""
    import base64

    from app.clients.oauth_mtls import OAuthMtlsClient

    cert, key = _par_pem()
    b64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
    ctx = OAuthMtlsClient._build_ssl_context("", "", cert_pem=b64(cert), key_pem=b64(key))
    assert ctx is not None


def test_lixo_no_campo_pem_nao_vira_contexto_sem_certificado():
    """Valor invalido nao pode degradar em silencio para 'sem mTLS': o banco
    recusaria com erro que nao aponta para a credencial."""
    from app.clients.oauth_mtls import OAuthMtlsClient

    assert OAuthMtlsClient._pem("nao é pem nem base64 %%%") is None
    assert OAuthMtlsClient._pem("") is None


def _par_pem() -> tuple[str, str]:
    """Gera um par autoassinado em memoria — nao usa certificado de verdade."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "teste")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - datetime.timedelta(days=1))
            .not_valid_after(agora + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.TraditionalOpenSSL,
                              serialization.NoEncryption()).decode())
