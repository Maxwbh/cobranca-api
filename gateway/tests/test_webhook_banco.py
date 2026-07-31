# Capacidades opcionais de provider: banco que NÃO implementa tem de responder
# 422 com alternativa, nunca 500.
#
# Métodos como cadastrar_webhook (/v1/webhooks) e os de Bolepix (/v2/bank_slips)
# existem só no C6 — não estão na BankProvider. Chamar direto num provider que
# não implementa levanta AttributeError e vira 500 sem mensagem útil.
import pytest


@pytest.fixture
def sicoob_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__sicoob__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__sicoob__client_secret", "sec")


CORPO = {"tenant_id": "empresa1", "provider": "sicoob",
         "url": "https://consumidor.exemplo.com/webhook", "service": "BANK_SLIP"}
QUERY = {"tenant_id": "empresa1", "provider": "sicoob", "service": "BANK_SLIP"}


def test_cadastrar_em_banco_sem_suporte_nao_da_500(client, sicoob_env):
    r = client.post("/config/webhook-banco", json=CORPO)
    assert r.status_code == 422, r.text
    assert "não oferece cadastro de webhook" in r.json()["detail"]


def test_consultar_em_banco_sem_suporte_nao_da_500(client, sicoob_env):
    r = client.get("/config/webhook-banco", params=QUERY)
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str), r.text  # o 422 tem de ser o NOSSO


def test_remover_em_banco_sem_suporte_nao_da_500(client, sicoob_env):
    r = client.delete("/config/webhook-banco", params=QUERY)
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str), r.text  # o 422 tem de ser o NOSSO


def test_mensagem_aponta_a_alternativa(client, sicoob_env):
    """O erro tem de dizer PARA ONDE ir, não só que falhou."""
    detalhe = client.post("/config/webhook-banco", json=CORPO).json()["detail"]
    assert "/config/webhook-pix" in detalhe
    assert "sicoob" in detalhe


def test_provider_offline_continua_422(client):
    """Rota REST: provider offline segue barrado (não regride para 500)."""
    r = client.post("/config/webhook-banco", json={**CORPO, "provider": "pycobranca"})
    assert r.status_code == 422, r.text


# --- Bolepix (exclusivo C6) ---------------------------------------------------

# Campos conforme BolepixCobranca: `vencimento` (nao data_vencimento) e
# `descricao` sao OBRIGATORIOS. Com o payload errado o pydantic rejeita antes
# da checagem de capacidade e o 422 vem pelo motivo errado — o teste passaria
# sem exercitar nada.
BOLEPIX = {"tenant_id": "empresa1", "provider": "sicoob", "account_config": {},
           "bolepix": {"valor": "10.00", "vencimento": "2027-12-30",
                        "descricao": "Assinatura HML",
                        "pagador": {"nome": "Joao da Silva",
                                    "documento": "52998224725"}}}


def test_criar_bolepix_em_banco_sem_suporte_nao_da_500(client, sicoob_env):
    r = client.post("/bolepix", json=BOLEPIX)
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    # `detail` string = erro NOSSO; lista = erro de schema do pydantic, o que
    # significaria que o payload nem chegou na checagem de capacidade.
    assert isinstance(detalhe, str), f"422 veio da validacao de schema: {detalhe}"
    assert "Bolepix" in detalhe
    assert "c6" in detalhe


@pytest.mark.parametrize("metodo,rota", [
    ("get", "/bolepix/ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ("get", "/bolepix/ABCDEFGHIJKLMNOPQRSTUVWXYZ/pdf"),
    ("delete", "/bolepix/ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
])
def test_bolepix_consultas_em_banco_sem_suporte_nao_dao_500(client, sicoob_env, metodo, rota):
    r = getattr(client, metodo)(rota, params={"tenant_id": "empresa1", "provider": "sicoob"})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], str), r.text  # o 422 tem de ser o NOSSO
