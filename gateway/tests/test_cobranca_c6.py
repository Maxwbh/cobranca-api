import pytest

from app.providers.c6 import C6Provider, _map_status
from app.schemas import Status


@pytest.fixture
def c6_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    # cobrança registrada do C6 pronta (senão cai no fallback brcobrança)
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    # sem pfx -> contexto SSL default, não precisa de cert real no teste


def test_c6_status_mapping():
    assert _map_status("CREATED") == Status.registrado
    assert _map_status("PAID") == Status.liquidado
    assert _map_status("CANCELLED") == Status.baixado
    assert _map_status("???") is None


def test_c6_registrar_mapeia_payload_e_normaliza(client, cobranca_payload, c6_env, monkeypatch):
    captured = {}

    def fake_request(self, method, path, json=None, params=None):
        captured.update(method=method, path=path, json=json)
        # bank_slip_create_response (boleto-bancário.yaml)
        return {
            "id": "01J3NCKY6Q99QC4D7T733D35QD",
            "our_number": "3048",
            "digitable_line": "33690.00009 03048.720001 92241.282133 5 96900000012345",
            "bar_code": "33695969000000123450000003048720009224128213",
        }

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    cobranca_payload["pagador"]["endereco"] = {
        "street": "Av. Nove de Julho", "number": 123,
        "city": "Rio de Janeiro", "state": "RJ", "zip_code": "05093000",
    }
    body = {
        "tenant_id": "empresa1",
        "provider": "c6",
        "account_config": {"billing_scheme": "21"},
        "cobranca": cobranca_payload,
    }
    r = client.post("/cobranca", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"] == "01J3NCKY6Q99QC4D7T733D35QD"
    assert data["status"] == "registrado"  # create não devolve status -> default
    assert data["linha_digitavel"].startswith("33690")

    # payload mapeado para o contrato REAL do C6 (bank_slip_create_request)
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/bank_slips/"
    sent = captured["json"]
    assert sent["external_reference_id"] == "A-1"
    assert sent["amount"] == 1000.0
    assert sent["due_date"] == "2026-07-10"
    assert sent["our_number"] == "123"
    assert sent["billing_scheme"] == "21"
    assert sent["payer"]["tax_id"] == "12345678901"
    assert sent["payer"]["address"]["zip_code"] == "05093000"


def test_c6_consultar_baixar_e_pdf(c6_env, monkeypatch):
    calls = []

    def fake_request(self, method, path, json=None, params=None):
        calls.append((method, path))
        if method == "GET":
            return {"id": "X", "status": "PAID", "base64_pdf_file": "JVBERi0="}
        return {}  # PUT /cancel -> 204 sem corpo

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    p = C6Provider(account_config={}, credentials={"client_id": "c", "client_secret": "s"})

    assert p.consultar("X").status == Status.liquidado
    assert p.pdf("X").pdf_base64 == "JVBERi0="

    out = p.baixar("X")
    assert out.status == Status.baixado
    assert ("PUT", "/v1/bank_slips/X/cancel") in calls


def test_pdf_pela_rota_http(client, c6_env, monkeypatch):
    """A rota GET /cobranca/{id}/pdf nunca era exercitada por HTTP -- so o metodo
    do provider. Router, auth e traducao de erro dela ficavam sem cobertura."""
    calls = []

    def fake(self, method, path, json=None, params=None):
        calls.append(path)
        return {"id": "X", "status": "CREATED", "base64_pdf_file": "JVBERi0="}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    r = client.get("/cobranca/X/pdf", params={"tenant_id": "empresa1", "provider": "c6"})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_base64"] == "JVBERi0="
    assert calls[0] == "/v1/bank_slips/X"


def test_pdf_em_provider_offline_recusa(client, c6_env):
    """O caminho offline gera o PDF na hora; nao ha boleto registrado para buscar."""
    r = client.get("/cobranca/X/pdf", params={"tenant_id": "empresa1", "provider": "pycobranca"})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("entrada,numero,complemento", [
    ("412", 412, None),
    (412, 412, None),
    ("126A", 126, "A"),
    ("126.A", 126, "A"),
    ("126 -A", 126, "A"),
    ("126-A/2", 126, "A/2"),
    ("S/N", 0, None),
    ("s/nº", 0, None),
    ("Sem Número", 0, None),
    ("Fundos", 0, "Fundos"),
])
def test_numero_do_endereco_vira_inteiro_sem_perder_o_sufixo(
        client, c6_env, monkeypatch, entrada, numero, complemento):
    """O /v1/bank_slips exige `number` numerico e recusa a string com 400.

    Numero de endereco chega como texto em quase todo cadastro brasileiro, e
    "126A" e' tao comum quanto "412". O sufixo vai para o `complement`: perder
    o "A" mudaria o endereco de entrega do boleto. Sem digito nenhum ("S/N") vira
    0, a convencao brasileira para imovel sem numero: faz o boleto sair, em vez
    de o banco recusar o registro por um campo que o cadastro nunca vai ter."""
    calls = []

    def fake(self, method, path, json=None, params=None):
        calls.append(json)
        return {"id": "X", "status": "CREATED"}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    r = client.post("/cobranca", json={
        "tenant_id": "empresa1", "provider": "c6",
        "cobranca": {
            "valor": "10.00", "vencimento": "2026-12-31", "seu_numero": "1",
            "pagador": {"nome": "Teste", "documento": "12345678909",
                        "endereco": {"logradouro": "Rua Presidente Kennedy",
                                     "numero": entrada, "cidade": "Sete Lagoas",
                                     "uf": "MG", "cep": "35700000"}},
        }})
    assert r.status_code < 300, r.text
    address = calls[0]["payer"]["address"]
    assert address["number"] == numero
    assert address.get("complement") == complemento


# --- 201 + Location ---------------------------------------------------------------

def test_registrar_devolve_201_com_location_seguivel(client, c6_env, monkeypatch):
    """O Location so vale se der para segui-lo: GET /cobranca/{id} exige
    tenant_id e provider, entao sem os dois o header aponta para um 422."""
    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request",
                        lambda self, method, path, json=None, params=None: {
                            "id": "01K", "status": "CREATED", "digitable_line": "336x"})
    r = client.post("/cobranca", json={
        "tenant_id": "empresa1", "provider": "c6",
        "cobranca": {"valor": "10.00", "vencimento": "2026-12-31", "seu_numero": "1",
                     "pagador": {"nome": "T", "documento": "12345678909"}}})
    assert r.status_code == 201, r.text
    assert r.headers["Location"] == "/cobranca/01K?tenant_id=empresa1&provider=c6"

    seguido = client.get(*r.headers["Location"].split("?", 1)[:1],
                         params=dict(p.split("=") for p in
                                     r.headers["Location"].split("?", 1)[1].split("&")))
    assert seguido.status_code == 200, seguido.text


def test_cancelar_ja_cancelado_devolve_baixado(client, c6_env, monkeypatch):
    """Cancelamento nao e' idempotente no C6, e o _cip_retry re-tenta enquanto a
    CIP processa: a primeira chamada e' aceita, a CIP conclui, e a re-tentativa
    encontra o registro em CANCELLED. Quem chamou pediu que a cobranca ficasse
    cancelada -- e ela esta. Devolver erro faria o consumidor tentar de novo
    para sempre, e fez a homologacao registrar falha onde a operacao funcionou."""
    import httpx

    def fake(self, method, path, json=None, params=None):
        req = httpx.Request(method, f"https://banco{path}")
        resp = httpx.Response(422, json={
            "detail": "Cannot update boleto:(number=01K) with status CANCELLED."}, request=req)
        raise httpx.HTTPStatusError("422", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    r = client.delete("/cobranca/01K", params={"tenant_id": "empresa1", "provider": "c6"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "baixado"
    assert "já estava cancelado" in r.json()["raw"]["observacao"]


def test_cancelar_com_outro_erro_do_banco_nao_e_engolido(client, c6_env, monkeypatch):
    """A tolerancia e' estreita de proposito: so o ja-cancelado. Qualquer outra
    recusa tem de continuar chegando ao chamador."""
    import httpx

    def fake(self, method, path, json=None, params=None):
        req = httpx.Request(method, f"https://banco{path}")
        resp = httpx.Response(422, json={"detail": "Boleto liquidado nao pode ser cancelado"},
                              request=req)
        raise httpx.HTTPStatusError("422", request=req, response=resp)

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    r = client.delete("/cobranca/01K", params={"tenant_id": "empresa1", "provider": "c6"})
    assert r.status_code == 422, r.text
    assert "liquidado" in r.text
