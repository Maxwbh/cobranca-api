# Conciliação C6 Pay (/v1/c6pay/statement) — recebíveis e transações.
import pytest


@pytest.fixture
def c6_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")


def test_recebiveis(client, c6_env, monkeypatch):
    captured = {}

    def fake_request(self, method, path, json=None, params=None):
        captured.update(method=method, path=path, params=params)
        return {
            "page": 1, "last_page": 3, "items": 120,
            "receivables": [
                {"receivable_id": "R1", "gross_amount": 100.0, "net_amount": 97.0, "expected_date": "2026-07-20"},
            ],
        }

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    r = client.get("/conciliacao/recebiveis", params={
        "tenant_id": "empresa1", "provider": "c6",
        "start_date": "2026-07-01", "end_date": "2026-07-15", "page": 1, "size": 50,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["page"] == 1 and data["last_page"] == 3 and data["total_items"] == 120
    assert data["items"][0]["receivable_id"] == "R1"

    assert captured["path"] == "/v1/c6pay/statement/receivables"
    assert captured["params"] == {"start_date": "2026-07-01", "end_date": "2026-07-15", "page": 1, "size": 50}


def test_transacoes(client, c6_env, monkeypatch):
    monkeypatch.setattr(
        "app.clients.oauth_mtls.OAuthMtlsClient.request",
        lambda self, method, path, json=None, params=None: {
            "page": 1, "last-page": 1, "transactions": [{"id": "T1", "status": "APPROVED"}],
        },
    )
    r = client.get("/conciliacao/transacoes", params={
        "tenant_id": "empresa1", "provider": "c6", "start_date": "2026-07-01", "end_date": "2026-07-15",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["last_page"] == 1  # aceita o alias last-page do /transactions
    assert data["items"][0]["id"] == "T1"


def test_conciliacao_provider_offline_retorna_422(client, c6_env):
    r = client.get("/conciliacao/recebiveis", params={
        "tenant_id": "empresa1", "provider": "pycobranca", "start_date": "2026-07-01", "end_date": "2026-07-15",
    })
    assert r.status_code == 422


# --- revisao de /conciliacao ------------------------------------------------------

def _params(**kw):
    p = {"tenant_id": "empresa1", "provider": "on", "banco": "c6",
         "start_date": "2026-07-01", "end_date": "2026-07-15"}
    p.update(kw)
    return p


@pytest.fixture
def sem_rede(monkeypatch):
    """Qualquer ida ao banco falha o teste: o que se mede aqui e' o que a rota
    recusa ANTES da rede."""
    chamadas = []

    def fake_request(self, method, path, json=None, params=None):
        chamadas.append(path)
        return {"page": 1, "last_page": 1, "receivables": [], "transactions": []}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return chamadas


@pytest.mark.parametrize("banco", ["sicoob", "inter", "itau"])
@pytest.mark.parametrize("rota", ["/conciliacao/recebiveis", "/conciliacao/transacoes"])
def test_banco_sem_conciliacao_responde_422_e_nao_500(client, monkeypatch, sem_rede, banco, rota):
    """A rota nao usava `exige_capacidade`: o AttributeError/NotImplementedError
    virava 500 "Internal Server Error" em 21 bytes -- no caminho que o
    `GET /bancos` ja descrevia como exclusivo do C6."""
    monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_id", "cid")
    monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_secret", "sec")
    monkeypatch.setenv(f"{banco.upper()}_REGISTERED_READY", "true")
    r = client.get(rota, params=_params(banco=banco))
    assert r.status_code == 422, r.text
    assert "c6" in r.json()["detail"].lower()
    assert sem_rede == []


def test_capacidade_herdada_da_base_nao_conta_como_suportada(client):
    """A causa do 500: `exige_capacidade` so olhava `getattr is None`, e a
    `BankProvider` DECLARA `listar_recebiveis`/`listar_transacoes` levantando
    NotImplementedError. Herdar a declaracao passava na checagem.

    O criterio agora e o mesmo do `GET /bancos` (sobrescrito = suportado), entao
    o catalogo vira previsao exata do 422 em vez de descricao paralela."""
    from app.providers.base import BankProvider
    from app.providers.c6 import C6Provider
    from app.providers.sicoob import SicoobProvider
    from app.routers._capacidades import implementa

    for metodo in ("listar_recebiveis", "listar_transacoes"):
        assert hasattr(BankProvider, metodo), "o teste so faz sentido se a base declara"
        assert implementa(C6Provider, metodo)
        assert not implementa(SicoobProvider, metodo)

    bancos = {b["id"]: b.get("capacidades", []) for b in client.get("/bancos").json()["bancos"]}
    assert "conciliacao_cartao" in bancos["c6"]
    assert "conciliacao_cartao" not in bancos["sicoob"]


@pytest.mark.parametrize("valor", ["01/07/2026", "amanha", "", "2026-13-45", "2026-07"])
def test_data_que_nao_e_data_nao_chega_ao_banco(client, c6_env, sem_rede, valor):
    """`start_date`/`end_date` eram `str` livres: `amanha` e `""` seguiam para a
    API do C6 tal como chegaram."""
    r = client.get("/conciliacao/recebiveis", params=_params(start_date=valor))
    assert r.status_code == 422, r.text
    assert sem_rede == []


def test_periodo_invertido_e_recusado(client, c6_env, sem_rede):
    """O mais silencioso dos tres: o banco responde lista vazia para periodo
    invertido, e quem chama le isso como 'nao houve movimento'."""
    r = client.get("/conciliacao/recebiveis",
                   params=_params(start_date="2026-07-15", end_date="2026-07-01"))
    assert r.status_code == 422, r.text
    assert "invertido" in r.json()["detail"]
    assert sem_rede == []


def test_janela_acima_de_60_dias_e_recusada_aqui(client, c6_env, sem_rede):
    """O limite de 60 dias e' do C6 e estava so na descricao do parametro: um ano
    de periodo ia inteiro para o banco e voltava como erro dele."""
    r = client.get("/conciliacao/recebiveis",
                   params=_params(start_date="2026-01-01", end_date="2026-12-31"))
    assert r.status_code == 422, r.text
    assert "60" in r.json()["detail"]
    assert sem_rede == []


def test_janela_de_exatos_60_dias_continua_valendo(client, c6_env, sem_rede):
    r = client.get("/conciliacao/recebiveis",
                   params=_params(start_date="2026-01-01", end_date="2026-03-02"))
    assert r.status_code == 200, r.text
    assert sem_rede != []


@pytest.mark.parametrize("page,size", [(0, 50), (-5, 50), (1, 0), (1, -1), (1, 101)])
def test_paginacao_fora_da_faixa_nao_chega_ao_banco(client, c6_env, sem_rede, page, size):
    """`page` nao tinha piso e `size` so tinha teto: page=-5 e size=0 iam para o
    banco como vieram."""
    r = client.get("/conciliacao/recebiveis", params=_params(page=page, size=size))
    assert r.status_code == 422, r.text
    assert sem_rede == []
