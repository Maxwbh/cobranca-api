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


# --- revisao de /config ------------------------------------------------------------

@pytest.fixture
def bancos_no_cofre(monkeypatch):
    for banco in ("c6", "sicoob", "inter", "itau"):
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_id", "cid")
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_secret", "sec")
        monkeypatch.setenv(f"{banco.upper()}_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__sicoob__access_token", "tok")


@pytest.fixture
def sem_rede(monkeypatch):
    chamadas = []

    def fake_request(self, method, path, json=None, params=None, **kw):
        chamadas.append({"m": method, "path": path, "json": json, "params": params})
        return {"ok": True}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return chamadas


_URL_OK = "https://api.minhaempresa.com.br/webhooks/c6/empresa1"


def _pix(**kw):
    corpo = {"tenant_id": "empresa1", "provider": "on", "banco": "c6",
             "chave": "financeiro@empresa.com.br", "url": _URL_OK}
    corpo.update(kw)
    return corpo


@pytest.mark.parametrize("metodo,args", [
    ("put", {"json": None}), ("get", {"params": None}), ("delete", {"params": None})])
def test_webhook_pix_em_banco_sem_pix_nao_da_500(client, bancos_no_cofre, sem_rede,
                                                 metodo, args):
    """As tres rotas de /config/webhook-pix nao checavam capacidade: o Itau nao
    tem dialeto BACEN e o AttributeError virava 500 nao-JSON."""
    if metodo == "put":
        r = client.put("/config/webhook-pix", json=_pix(banco="itau"))
    else:
        r = getattr(client, metodo)("/config/webhook-pix", params={
            "tenant_id": "empresa1", "provider": "on", "banco": "itau",
            "chave": "financeiro@empresa.com.br"})
    assert r.status_code == 422, r.text
    assert "itau" in r.json()["detail"]
    assert sem_rede == []


def test_mensagem_de_capacidade_diz_o_banco_e_nao_o_caminho(client, bancos_no_cofre,
                                                            sem_rede):
    """`exige_capacidade` recebia o `provider` no lugar do banco: com o modelo de
    dois eixos a mensagem saia "banco 'on' nao oferece" -- exatamente o que o
    helper documenta que nao pode acontecer."""
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "itau", "url": _URL_OK})
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "banco 'itau'" in detalhe
    assert "banco 'on'" not in detalhe


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "nao-e-url", "", "ftp://x.com/y",
    "http://meu.site/webhooks",              # sem TLS
    "http://localhost:8000/webhooks",        # o banco nunca alcanca
    "https://127.0.0.1/webhooks",
    "https://10.0.0.5/webhooks",
    "https://169.254.169.254/latest/meta-data/",
])
def test_url_que_o_banco_nao_consegue_chamar_e_recusada(client, bancos_no_cofre,
                                                        sem_rede, url):
    """Quem chama essa URL e o BANCO, de fora, pela internet. Destino local era
    aceito com 200 e o cadastro PARECIA feito -- o cliente so descobre que nao
    recebe notificacao quando um pagamento se perde. E `http://` poe valor,
    pagador e id da cobranca em claro."""
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6", "url": url})
    assert r.status_code == 422, r.text
    assert sem_rede == []


def test_url_publica_https_passa(client, bancos_no_cofre, sem_rede):
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6", "url": _URL_OK})
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["json"]["url"] == _URL_OK


def test_flag_libera_destino_local_para_homologacao(client, bancos_no_cofre, sem_rede,
                                                    monkeypatch):
    """Default estrito e flag que ABRE — como no WEBHOOK_ALLOW_UNAUTHENTICATED.
    Sem isso, quem testa com tunel http local nao teria caminho."""
    monkeypatch.setenv("WEBHOOK_URL_PERMITE_LOCAL", "1")
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6",
        "url": "http://localhost:8000/webhooks/c6/empresa1"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("service", ["QUALQUER_COISA", "", "bank_slip"])
def test_service_fora_do_vocabulario_do_banco_e_recusado(client, bancos_no_cofre,
                                                         sem_rede, service):
    """`service` era `str` livre: `QUALQUER_COISA` e `""` iam ao banco."""
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6",
        "url": _URL_OK, "service": service})
    assert r.status_code == 422, r.text
    assert sem_rede == []


@pytest.mark.parametrize("service", ["BANK_SLIP", "CHECKOUT"])
def test_os_dois_services_do_c6_continuam_valendo(client, bancos_no_cofre, sem_rede,
                                                  service):
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6",
        "url": _URL_OK, "service": service})
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["json"]["service"] == service


def test_corpo_do_webhook_pix_tem_schema(client, bancos_no_cofre, sem_rede):
    """Era `body: dict`: o Swagger nao descrevia campo nenhum e campo com nome
    errado passava calado."""
    r = client.put("/config/webhook-pix", json=_pix(chave_pix="typo@x.com"))
    assert r.status_code == 422, r.text
    assert sem_rede == []

    spec = client.get("/openapi.json").json()
    corpo = spec["paths"]["/config/webhook-pix"]["put"]["requestBody"]
    assert corpo["content"]["application/json"]["schema"]["$ref"].endswith("WebhookPixIn")


@pytest.mark.parametrize("campo", ["tenant_id", "chave", "url"])
def test_campo_vazio_no_webhook_pix_continua_recusado(client, bancos_no_cofre, sem_rede,
                                                      campo):
    """O corpo antigo (dict livre) recusava os tres VAZIOS na mao. Ao trocar por
    schema, a validacao se perdeu: string vazia passava e ia ao banco. Foi a
    regressao do Postman que mostrou (BC-044 saiu de 422 para 424)."""
    r = client.put("/config/webhook-pix", json=_pix(**{campo: ""}))
    assert r.status_code == 422, r.text
    assert sem_rede == []


def test_webhook_pix_valido_chega_ao_banco(client, bancos_no_cofre, sem_rede):
    r = client.put("/config/webhook-pix", json=_pix())
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["json"] == {"webhookUrl": _URL_OK}
