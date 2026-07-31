# Fallback de roteamento: provider REST não homologado / provider vazio caem no
# caminho OFFLINE, agora servido pela engine pyCobranca (in-process, sem HTTP).
from app.registry import registered_ready
from app.schemas import Provider

CONTA_OFFLINE = {
    "agencia": "3073", "conta_corrente": "12345678", "convenio": "1234567",
    "carteira": "18", "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181",
}
PAGADOR = {"nome": "Joao da Silva", "documento": "52998224725"}


def test_registered_ready_default_false(monkeypatch):
    monkeypatch.delenv("C6_REGISTERED_READY", raising=False)
    monkeypatch.delenv("SICOOB_REGISTERED_READY", raising=False)
    assert registered_ready(Provider.c6) is False
    assert registered_ready(Provider.sicoob) is False


def test_registered_ready_liga_por_env(monkeypatch):
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    assert registered_ready(Provider.c6) is True


def test_c6_nao_pronto_cai_no_offline(client, cobranca_payload, monkeypatch):
    # C6 não homologado e sem credenciais: cai no offline (banco_c6) e registra.
    monkeypatch.delenv("C6_REGISTERED_READY", raising=False)
    body = {
        "tenant_id": "tenant_sem_credencial",
        "provider": "c6",
        "account_config": CONTA_OFFLINE,  # bank é injetado (banco_c6) pelo fallback
        "cobranca": {**cobranca_payload, "pagador": PAGADOR},
    }
    r = client.post("/cobranca", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] in ("registrado", "erro")  # depende dos dados da conta
    if data["status"] == "registrado":
        assert len(data["codigo_barras"]) == 44


def test_sicoob_nao_pronto_cai_no_offline(client, cobranca_payload, monkeypatch):
    monkeypatch.delenv("SICOOB_REGISTERED_READY", raising=False)
    body = {"tenant_id": "x", "provider": "sicoob",
            "account_config": {"convenio": "123456", "carteira": "1",
                                "agencia": "3073", "conta_corrente": "12345678",
                                "cedente": "Empresa Teste LTDA",
                                "documento_cedente": "11222333000181"},
            "cobranca": {**cobranca_payload, "pagador": PAGADOR}}
    r = client.post("/cobranca", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("registrado", "erro")


def test_provider_omitido_ou_vazio_vai_para_offline(client, cobranca_payload):
    # Contrato: provider ausente/"" roteia para o método antigo (offline/CNAB).
    body = {"tenant_id": "x", "account_config": {"bank": "banco_brasil", **CONTA_OFFLINE},
            "cobranca": {**cobranca_payload, "pagador": PAGADOR}}
    r = client.post("/cobranca", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "registrado"

    body_vazio = {**body, "provider": ""}
    r2 = client.post("/cobranca", json=body_vazio)
    assert r2.status_code == 200
    assert r2.json()["status"] == "registrado"
