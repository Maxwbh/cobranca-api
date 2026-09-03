# `provider` = CAMINHO (on|off) e `banco` = INSTITUIÇÃO.
#
# Antes os dois eixos viviam num campo só: "qual banco" era o `provider` quando
# online e o `account_config.bank` quando offline, e por isso não existia forma
# de dizer "esse banco, pelo outro caminho". O que estes testes fixam é
# exatamente a fronteira nova — inclusive as combinações que NÃO existem, que
# são as que precisam falhar alto (emitir boleto pelo banco errado é falha
# silenciosa e cara).
import pytest


def _conta_engine(**extra) -> dict:
    """Convênio mínimo que a engine exige para calcular o código de barras."""
    base = {"agencia": "3073", "conta_corrente": "12345", "convenio": "1234567",
            "carteira": "109", "cedente": "Empresa Teste LTDA",
            "documento_cedente": "11222333000181"}
    base.update(extra)
    return base


def _corpo(provider, banco=None, **extra) -> dict:
    corpo = {
        "tenant_id": "empresa1", "provider": provider,
        "account_config": _conta_engine(),
        "cobranca": {"valor": "150.00", "vencimento": "2026-12-31",
                     "nosso_numero": "123", "seu_numero": "PED-1",
                     "pagador": {"nome": "Joao da Silva", "documento": "529.982.247-25",
                                 "endereco": {"logradouro": "Rua Teste", "numero": "126A",
                                              "cidade": "Sete Lagoas", "uf": "MG",
                                              "cep": "35.700-000"}}},
    }
    if banco is not None:
        corpo["banco"] = banco
    corpo.update(extra)
    return corpo


def _sem_rede(monkeypatch):
    """Registra as chamadas HTTP ao banco — e prova quando não houve nenhuma."""
    calls = []

    def fake(self, method, path, json=None, params=None):
        calls.append({"method": method, "path": path})
        return {"id_boleto": "X-1", "status": "EM_ABERTO"}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    return calls


# --- o caminho OFF leva o banco junto -----------------------------------------

def test_off_com_banco_emite_pela_engine(client, monkeypatch):
    calls = _sem_rede(monkeypatch)
    r = client.post("/cobranca", json=_corpo("off", "itau"))
    assert r.status_code == 201, r.text
    assert calls == [], "caminho off não fala com banco"
    assert r.json()["codigo_barras"].startswith("341")


def test_off_traduz_c6_para_o_slug_da_engine(client, monkeypatch):
    """`banco=c6` no caminho off vira `banco_c6` — a tradução é nossa, não do contrato."""
    _sem_rede(monkeypatch)
    r = client.post("/cobranca", json=_corpo("off", "c6", account_config=_conta_engine(carteira="10")))
    assert r.status_code == 201, r.text
    assert r.json()["codigo_barras"].startswith("336")


def test_off_ainda_aceita_o_banco_no_account_config(client, monkeypatch):
    """Forma antiga (`account_config.bank`) segue valendo: é como a engine sempre
    foi chamada, e há integração em produção que só conhece ela."""
    _sem_rede(monkeypatch)
    corpo = _corpo("off", account_config=_conta_engine(bank="itau"))
    assert client.post("/cobranca", json=corpo).status_code == 201


def test_off_sem_banco_recusa_dizendo_quais_existem(client):
    r = client.post("/cobranca", json=_corpo("off"))
    assert r.status_code == 422
    detalhe = r.json()["detail"]
    assert "informe o `banco`" in detalhe and "itau" in detalhe


# --- combinações que não existem falham alto ---------------------------------

def test_on_em_banco_sem_api_recusa(client):
    """`on` + Bradesco não é "ainda não implementado" silencioso: é 422 com a
    lista de quem tem API — cair na engine aqui seria emitir um boleto que o
    integrador acha que está registrado no banco."""
    r = client.post("/cobranca", json=_corpo("on", "bradesco"))
    assert r.status_code == 422
    assert "não tem caminho 'on'" in r.json()["detail"]


def test_off_no_inter_emite(client):
    """O Inter era o único banco com `on` e sem `off`, porque a engine não tinha
    o layout 077 — e ser recusado ali era o certo: cair noutro banco emitiria um
    boleto registrado no lugar errado.

    A pyCobrança 1.1.1 implementou o Inter, então o caminho `off` passa a
    existir e a recusa deixa de fazer sentido.
    """
    r = client.post("/cobranca", json=_corpo("off", "inter"))
    assert r.status_code == 201, r.text


def test_banco_desconhecido_no_account_config_recusa(client):
    corpo = _corpo("off", account_config=_conta_engine(bank="banco_inexistente"))
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 422
    assert "não é tratado" in r.json()["detail"]


# --- apelido legado: o nome do banco no `provider` ----------------------------

def test_nome_do_banco_no_provider_equivale_a_on_mais_banco(client, monkeypatch):
    """`provider=c6` == `provider=on&banco=c6`. Há roteiro de homologação já
    enviado ao banco com esses payloads: quebrar aqui quebra fora."""
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    legado = _sem_rede(monkeypatch)
    assert client.post("/cobranca", json=_corpo("c6")).status_code == 201
    novo = list(legado)
    legado.clear()
    assert client.post("/cobranca", json=_corpo("on", "c6")).status_code == 201
    assert [c["path"] for c in legado] == [c["path"] for c in novo]


def test_provider_legado_pycobranca_continua_offline(client, monkeypatch):
    _sem_rede(monkeypatch)
    corpo = _corpo("pycobranca", account_config=_conta_engine(bank="itau"))
    assert client.post("/cobranca", json=corpo).status_code == 201


# --- o gate de homologação é do BANCO, não do caminho ------------------------

def test_on_sem_flag_rebaixa_para_a_engine(client, monkeypatch):
    monkeypatch.delenv("ITAU_REGISTERED_READY", raising=False)
    calls = _sem_rede(monkeypatch)
    r = client.post("/cobranca", json=_corpo("on", "itau"))
    assert r.status_code == 201
    assert calls == [], "banco não homologado não recebe chamada"
    assert r.json()["codigo_barras"].startswith("341")


def test_on_com_flag_chama_o_banco(client, monkeypatch):
    monkeypatch.setenv("ITAU_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__itau__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__itau__client_secret", "sec")
    calls = _sem_rede(monkeypatch)
    assert client.post("/cobranca", json=_corpo("on", "itau")).status_code == 201
    assert len(calls) == 1 and calls[0]["method"] == "POST"


# --- rotas de consulta aceitam os dois eixos ---------------------------------

@pytest.mark.parametrize("rota,metodo", [("/cobranca/X-1", "get"), ("/cobranca/X-1", "delete")])
def test_consulta_e_baixa_aceitam_provider_mais_banco(client, monkeypatch, rota, metodo):
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    calls = _sem_rede(monkeypatch)
    r = getattr(client, metodo)(rota, params={"tenant_id": "empresa1", "provider": "on",
                                              "banco": "c6"})
    assert r.status_code == 200, r.text
    assert len(calls) == 1


def test_alterar_aceita_provider_mais_banco(client, monkeypatch):
    """A rota `PUT` recebia `banco` na chamada sem ter o parâmetro na assinatura —
    `NameError` em tempo de request. Fica um teste para não voltar."""
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    calls = _sem_rede(monkeypatch)
    r = client.put("/cobranca/X-1", json={"valor": "10.00"},
                   params={"tenant_id": "empresa1", "provider": "on", "banco": "c6"})
    assert r.status_code == 200, r.text
    assert len(calls) == 1


# --- catálogo: o que o banco faz × o que ESTA instalação faz ------------------

def test_catalogo_diz_o_caminho_efetivo_da_instalacao(client, monkeypatch):
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    monkeypatch.delenv("ITAU_REGISTERED_READY", raising=False)
    dados = client.get("/bancos").json()
    assert set(dados["caminhos"]) >= {"on", "off"}
    bancos = {b["id"]: b for b in dados["bancos"]}

    c6 = bancos["c6"]
    assert c6["registrado_pronto"] is True and c6["caminho_efetivo"] == "on"
    assert c6["fallback_offline"] == "banco_c6"

    itau = bancos["itau"]
    assert itau["registrado_pronto"] is False
    assert itau["caminho_efetivo"] == "off", "sem a flag, `on` emite pela engine"
    assert itau["flag"] == "ITAU_REGISTERED_READY"

    # O Inter não tinha para onde cair enquanto a engine não tinha o layout 077.
    # Com a 1.1.1 ele passa a existir nos dois caminhos, como o C6, o Sicoob e
    # o Itaú — e o catálogo é onde isso aparece para quem integra.
    assert bancos["inter"]["fallback_offline"] == "inter"
    assert bancos["inter"]["caminhos"] == ["on", "off"]


# --- credencial pertence ao BANCO, não ao caminho ----------------------------

@pytest.fixture
def cofre_isolado(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CREDENTIAL_DB_PATH", str(tmp_path / "creds.db"))


def _token(client, provider, banco=None) -> str:
    corpo = {"tenant_id": "empresa1", "provider": provider,
             "credentials": {"client_id": "cid", "client_secret": "sec"}}
    if banco:
        corpo["banco"] = banco
    r = client.post("/credenciais", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_token_do_modelo_novo_vale_no_apelido_legado(client, cofre_isolado, monkeypatch):
    """Cadastrar com `on`+`c6` e usar com `provider=c6` é a MESMA credencial —
    senão a migração exigiria reemitir todo token já distribuído."""
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    usados = {}

    def fake(self, method, path, json=None, params=None):
        usados["client_id"] = self.client_id
        return {"id": "X-1"}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    token = _token(client, "on", "c6")
    r = client.post("/cobranca", json=_corpo("c6"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert usados["client_id"] == "cid"


def test_token_de_um_banco_nao_abre_outro(client, cofre_isolado, monkeypatch):
    """Com `provider=on` guardando pelo caminho, C6 e Sicoob do mesmo tenant
    cairiam na mesma chave e um token abriria os dois. A chave é o banco."""
    monkeypatch.setenv("SICOOB_REGISTERED_READY", "true")
    _sem_rede(monkeypatch)
    token = _token(client, "on", "c6")
    r = client.post("/cobranca", json=_corpo("on", "sicoob"),
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text
