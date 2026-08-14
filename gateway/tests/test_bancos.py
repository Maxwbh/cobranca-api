# Catálogo /bancos + autenticação unificada entre os bancos.


def test_bancos_lista_capacidades_reais(client):
    r = client.get("/bancos")
    assert r.status_code == 200
    data = r.json()
    bancos = {b["id"]: b for b in data["bancos"]}
    assert set(bancos) == {"c6", "sicoob", "inter", "itau", "pycobranca"}

    # capacidades refletem o código (introspecção)
    assert "pix_automatico" in bancos["c6"]["capacidades"]
    assert "pix_automatico" in bancos["sicoob"]["capacidades"]
    assert "bolepix" in bancos["c6"]["capacidades"]
    assert "bolepix" not in bancos["sicoob"]["capacidades"]  # exclusivo C6
    assert "extrato" in bancos["sicoob"]["capacidades"]      # paridade nova
    assert "carne" in bancos["pycobranca"]["capacidades"]
    assert len(bancos["pycobranca"]["bancos_cnab"]) == 18

    # mecanismo da API é único (bapi_); o ESQUEMA de credenciais é próprio por banco
    assert "bapi_" in data["autenticacao_api"]["cadastro"]
    assert "pfx_base64" in bancos["c6"]["credentials"]          # esquema C6
    assert "access_token" in bancos["sicoob"]["credentials"]     # esquema Sicoob
    assert bancos["c6"]["credentials"] != bancos["sicoob"]["credentials"]


def test_mecanismo_da_api_igual_nos_dois_bancos(client, monkeypatch):
    """O mecanismo (recebe -> armazena -> Bearer bapi_) é o MESMO nos 2 bancos,
    ainda que cada banco tenha o próprio esquema de parâmetros."""
    chamadas = []

    def fake_request(self, method, path, json=None, params=None):
        chamadas.append({"path": path, "token": self.token()})
        return {"txid": "T", "status": "ATIVA", "pixCopiaECola": "000201..."}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    for prov in ("c6", "sicoob"):
        body = {"tenant_id": "t", "provider": prov,
                "account_config": {"chave_pix": "k"}, "pix": {"valor": "1.00"},
                "credentials": {"client_id": "cid", "access_token": "tok-estatico-sandbox"}}
        r = client.post("/pix", json=body)
        assert r.status_code == 201, (prov, r.text)

    # o token estático foi usado direto (sem fluxo OAuth) em AMBOS
    assert [c["token"] for c in chamadas] == ["tok-estatico-sandbox"] * 2


def test_extrato_sicoob_mapeia_mes_ano(client, monkeypatch):
    monkeypatch.setenv("VAULT__t__sicoob__client_id", "cid")
    monkeypatch.setenv("VAULT__t__sicoob__client_secret", "s")
    captured = {}

    def fake_request(self, method, path, json=None, params=None):
        captured.update(path=path, params=params)
        return {"resultado": {"saldoAtual": "100.00"}}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    r = client.get("/extrato", params={"tenant_id": "t", "provider": "sicoob",
                                       "start_date": "2026-07-01", "end_date": "2026-07-15"})
    assert r.status_code == 200, r.text
    assert captured["path"] == "/conta-corrente/v4/extrato/7/2026"
    assert captured["params"]["diaInicial"] == 1 and captured["params"]["diaFinal"] == 15

    # multi-mês -> 422 com mensagem clara
    r = client.get("/extrato", params={"tenant_id": "t", "provider": "sicoob",
                                       "start_date": "2026-06-15", "end_date": "2026-07-15"})
    assert r.status_code == 422
    assert "mesmo mês" in r.json()["detail"]


def test_catalogo_anuncia_checkout_so_no_banco_que_oferece(client):
    """O catálogo e' como o consumidor DESCOBRE o que cada banco faz, e a rota de
    checkout existia sem aparecer nele.

    So o C6 lista `checkout_cartao` -- e' a decisao 4 virada em dado: cartao
    existe onde a instituicao OFERECE, e o catalogo tem de dizer onde."""
    bancos = {b["id"]: b["capacidades"] for b in client.get("/bancos").json()["bancos"]}
    assert "checkout_cartao" in bancos["c6"]
    assert "checkout_cartao" not in bancos["sicoob"]
    assert "checkout_cartao" not in bancos["pycobranca"]


def test_inter_nao_anuncia_capacidade_que_nao_tem(client):
    """O Inter herda os mixins BACEN, entao Pix vem de graca — mas boleto com
    cartao e conciliacao de cartao sao do C6, e o catalogo nao pode sugerir
    que existam aqui."""
    inter = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}["inter"]
    assert inter["codigo_banco"] == "077"
    for tem in ("boleto", "boleto_pdf", "boleto_baixa", "pix", "extrato", "webhook_banco"):
        assert tem in inter["capacidades"], tem
    for nao_tem in ("checkout_cartao", "conciliacao_cartao", "bolepix", "boleto_alteracao"):
        assert nao_tem not in inter["capacidades"], nao_tem
