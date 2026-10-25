# Extrato de conta — revisao da rota.
#
# A rota unifica a CHAMADA, nao o formato: os tres bancos devolvem shapes
# diferentes e a resposta e repassada crua. O que se mede aqui e o que a rota
# recusa antes da rede, e o que ela promete na spec.
import pytest


def _params(**kw):
    p = {"tenant_id": "empresa1", "provider": "on", "banco": "c6",
         "start_date": "2026-01-01", "end_date": "2026-01-31"}
    p.update(kw)
    return p


@pytest.fixture
def sem_rede(monkeypatch):
    chamadas = []

    def fake_request(self, method, path, json=None, params=None, **kw):
        chamadas.append({"path": path, "params": params})
        return {"transactions": []}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return chamadas


@pytest.fixture
def bancos_no_cofre(monkeypatch):
    for banco in ("c6", "sicoob", "inter", "itau"):
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_id", "cid")
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_secret", "sec")
        monkeypatch.setenv(f"{banco.upper()}_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__sicoob__access_token", "tok")


def test_banco_sem_extrato_responde_422_e_nao_500(client, bancos_no_cofre, sem_rede):
    """O Itau nao tem API de conta -- e o `GET /bancos` ja dizia isso. A rota nao
    checava capacidade: AttributeError virava 500 "Internal Server Error" em 21
    bytes."""
    r = client.get("/extrato", params=_params(banco="itau"))
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "itau" in detalhe and "ofx" in detalhe.lower()
    assert sem_rede == []


def test_os_tres_bancos_com_extrato_continuam_respondendo(client, bancos_no_cofre, sem_rede):
    for banco in ("c6", "sicoob", "inter"):
        r = client.get("/extrato", params=_params(banco=banco))
        assert r.status_code == 200, f"{banco}: {r.text}"
    assert len(sem_rede) == 3


@pytest.mark.parametrize("valor", ["01/01/2026", "amanha", "", "2026-13-45", "2026-01"])
def test_data_que_nao_e_data_nao_chega_ao_banco(client, bancos_no_cofre, sem_rede, valor):
    """`start_date`/`end_date` eram `str` livres. No C6 e no Inter o texto seguia
    para o banco como veio; no Sicoob estourava o `fromisoformat` e a mensagem de
    parsing do Python vazava no 422 ("Invalid isoformat string"). Tres respostas
    diferentes para o mesmo erro do chamador."""
    r = client.get("/extrato", params=_params(start_date=valor))
    assert r.status_code == 422, r.text
    assert sem_rede == []


def test_periodo_invertido_e_recusado(client, bancos_no_cofre, sem_rede):
    r = client.get("/extrato", params=_params(start_date="2026-01-31", end_date="2026-01-01"))
    assert r.status_code == 422, r.text
    assert "invertido" in r.json()["detail"]
    assert sem_rede == []


def test_numero_conta_chega_ao_sicoob(client, bancos_no_cofre, sem_rede):
    """O router passava `account_config={}` e o provider do Sicoob le a conta
    dali: toda consulta ia com `numeroContaCorrente: 0`, sem o chamador ter onde
    informar a conta. O sandbox aceitou porque e mock (devolve dado fabricado)."""
    r = client.get("/extrato", params=_params(banco="sicoob", numero_conta=123456))
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["params"]["numeroContaCorrente"] == 123456


def test_sem_numero_conta_o_comportamento_antigo_e_preservado(client, bancos_no_cofre, sem_rede):
    """Omitido, segue `0` — o que a rota mandava sempre. A correcao abre o
    caminho sem mudar quem ja chamava."""
    r = client.get("/extrato", params=_params(banco="sicoob"))
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["params"]["numeroContaCorrente"] == 0


def test_extrato_sicoob_multi_mes_continua_422_do_banco(client, bancos_no_cofre, sem_rede):
    """A regra mensal e do Sicoob e mora no provider dele — nao virou regra da
    rota, que serve tres bancos com janelas diferentes."""
    r = client.get("/extrato", params=_params(banco="sicoob", start_date="2026-01-01",
                                              end_date="2026-02-01"))
    assert r.status_code == 422, r.text
    assert "mensal" in r.json()["detail"]


def test_a_spec_diz_que_a_resposta_e_crua_do_banco(client):
    """`response_model=dict` prometia "objeto qualquer", sem exemplo — e aqui nao
    da para normalizar: os tres shapes sao diferentes de verdade. Entao a spec
    diz isso, com um exemplo de cada."""
    op = client.get("/openapi.json").json()["paths"]["/extrato"]["get"]
    conteudo = op["responses"]["200"]["content"]["application/json"]
    assert "crua" in conteudo["schema"]["description"].lower()
    assert set(conteudo["examples"]) == {"c6", "sicoob", "inter"}
