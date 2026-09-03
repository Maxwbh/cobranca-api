# Validação do Pix Automático: o que o catálogo promete e o que as rotas fazem.
#
# O roteiro de campo (`scripts/validar_pix_automatico.py`) só roda com segredo de
# sandbox, então a regra dele — o que cada resposta PROVA — ficaria sem teste.
# Aqui ela é exercitada sem rede, junto com as duas travas que a validação
# levantou: banco sem a capacidade responde 422 (e não 500), e catálogo e rota
# não podem discordar.
import importlib.util
import pathlib

import pytest

_RAIZ = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "validar_pix_automatico", _RAIZ / "scripts" / "validar_pix_automatico.py")
validador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validador)


REC = {"contrato": "CT-1", "devedor": {"nome": "Jose", "documento": "12345678909"},
       "periodicidade": "MENSAL", "data_inicial": "2026-09-01", "valor_fixo": "50.00",
       "politica_retentativa": "PERMITE_3R_7D"}


@pytest.fixture
def creds_itau(monkeypatch):
    monkeypatch.setenv("ITAU_REGISTERED_READY", "true")
    monkeypatch.setenv("VAULT__empresa1__itau__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__itau__sandbox_token", "tok")


# --- a regra do roteiro: 2xx não é sinônimo de prova ---------------------------


def test_2xx_com_json_e_suportado():
    assert validador.classificar(201, {"idRec": "RR1", "status": "CRIADA"}) == "suportado"


def test_2xx_com_corpo_nao_json_nao_prova_nada():
    """O caso real: o WAF do Sicoob devolveu HTML e a evidência registrou `201`.

    O `OAuthMtlsClient` embrulha corpo não-JSON em `{"conteudo": ...}` para não
    perder a resposta — e o 2xx atravessava como sucesso. Página de bloqueio não
    é recurso criado.
    """
    html = {"conteudo": "<html><head><title>Request Rejected</title></head></html>"}
    assert validador.classificar(201, html) == "nao_provado"
    assert validador.classificar(200, {"raw": html}) == "nao_provado"


def test_recusa_do_banco_e_fronteira_de_capacidade_sao_coisas_diferentes():
    assert validador.classificar(400, {"detail": "conta sem Pix Automático contratado"}) == "recusado"
    assert validador.classificar(
        422, {"detail": "banco 'itau' não oferece Pix Automático; use ..."}) == "nao_oferecido"


def test_veredito_do_banco_e_o_pior_do_conjunto():
    """Sem `rec` não há ciclo: falhar na criação não é suporte parcial."""
    casos = [{"caso": "PA_01", "veredito": "recusado"}, {"caso": "PA_03", "veredito": "suportado"}]
    assert validador._veredito_do_banco(casos) == "recusado"
    casos = [{"caso": "PA_01", "veredito": "suportado"}, {"caso": "PA_02", "veredito": "sem_massa"}]
    assert validador._veredito_do_banco(casos) == "suportado"
    casos = [{"caso": "PA_01", "veredito": "suportado"}, {"caso": "PA_07", "veredito": "nao_provado"}]
    assert validador._veredito_do_banco(casos) == "parcial"


# --- banco sem a capacidade: 422 com destino, nunca 500 -------------------------


def test_banco_sem_pix_automatico_responde_422(client, creds_itau):
    """Antes disto o Itaú devolvia 500 em todas as rotas de /pix-automatico.

    `AttributeError` dentro do handler vira erro interno — o serviço se acusando
    de defeito onde há fronteira de capacidade do banco.
    """
    body = {"tenant_id": "empresa1", "provider": "on", "banco": "itau", "recorrencia": REC}
    r = client.post("/pix-automatico/recorrencias", json=body)
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "banco 'itau'" in detalhe          # o banco, não o caminho `on`
    assert "c6" in detalhe and "sicoob" in detalhe  # e para onde ir


_TXID = "COBR" + "0" * 22   # 26 caracteres, dentro do padrao BACEN


@pytest.mark.parametrize("metodo,rota,kw", [
    ("get", "/pix-automatico/recorrencias", {"params": {"inicio": "2026-08-01T00:00:00Z",
                                                        "fim": "2026-08-31T00:00:00Z"}}),
    ("get", "/pix-automatico/recorrencias/RR1", {}),
    ("patch", "/pix-automatico/recorrencias/RR1", {"json": {"status": "CANCELADA"}}),
    ("get", "/pix-automatico/solicitacoes/SC1", {}),
    ("patch", "/pix-automatico/solicitacoes/SC1", {"json": {"status": "CANCELADA"}}),
    ("post", "/pix-automatico/locations", {}),
    ("get", "/pix-automatico/locations/1", {}),
    ("delete", "/pix-automatico/locations/1/recorrencia", {}),
    ("get", "/pix-automatico/cobrancas", {"params": {"inicio": "2026-08-01T00:00:00Z",
                                                     "fim": "2026-08-31T00:00:00Z"}}),
    # txid do BACEN: 26-35 caracteres. `T1` era o que o teste mandava, e o
    # 422 vinha do PATTERN, nao da capacidade -- passando pelo motivo errado.
    ("get", f"/pix-automatico/cobrancas/{_TXID}", {}),
    ("patch", f"/pix-automatico/cobrancas/{_TXID}", {"json": {"status": "CANCELADA"}}),
    ("post", f"/pix-automatico/cobrancas/{_TXID}/retentativa/2027-09-10", {}),
    ("put", "/pix-automatico/config/webhooks", {"json": {"url_recorrencia": "https://x/y"}}),
])
def test_nenhuma_rota_de_pix_automatico_devolve_500(client, creds_itau, metodo, rota, kw):
    params = {"tenant_id": "empresa1", "provider": "on", "banco": "itau", **kw.pop("params", {})}
    r = getattr(client, metodo)(rota, params=params, **kw)
    assert r.status_code == 422, f"{metodo.upper()} {rota} -> {r.status_code}: {r.text[:200]}"
    assert "não oferece Pix Automático" in r.json()["detail"]


# --- catálogo e rota não podem discordar ---------------------------------------


def test_catalogo_e_rota_dizem_a_mesma_coisa(client, monkeypatch):
    """Quem o `GET /bancos` promete tem de responder — e quem ele não promete, 422.

    Catálogo prometendo e rota recusando é o defeito caro: o consumidor escolhe
    o banco pela vitrine.
    """
    calls = []

    def fake_request(self, method, path, json=None, params=None):
        calls.append(path)
        return {"idRec": "RR1", "status": "CRIADA"}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    catalogo = client.get("/bancos").json()["bancos"]
    for banco in catalogo:
        if banco["tipo"] != "rest":
            continue
        bid = banco["id"]
        monkeypatch.setenv(f"{bid.upper()}_REGISTERED_READY", "true")
        monkeypatch.setenv(f"VAULT__empresa1__{bid}__client_id", "cid")
        monkeypatch.setenv(f"VAULT__empresa1__{bid}__client_secret", "sec")
        r = client.post("/pix-automatico/recorrencias",
                        json={"tenant_id": "empresa1", "provider": "on", "banco": bid,
                              "recorrencia": REC})
        promete = "pix_automatico" in banco["capacidades"]
        assert (r.status_code == 201) is promete, (
            f"{bid}: catálogo diz {promete}, rota respondeu {r.status_code} — {r.text[:200]}")
        if promete:
            continue
        # A recusa tem DOIS motivos e eles não são a mesma frase. "Não oferece"
        # vale para quem não herda o dialeto (Itaú) — sabemos que não tem. Para
        # quem herda e ninguém confirmou no banco (Inter), dizer "não oferece"
        # trocaria uma promessa sem lastro por uma negativa sem lastro; ali o
        # erro diz "não foi confirmado" e nomeia a flag que libera.
        detalhe = r.json()["detail"]
        nao_confirmadas = banco.get("capacidades_nao_confirmadas") or {}
        if "pix_automatico" in nao_confirmadas:
            assert "não foi confirmado" in detalhe, f"{bid}: {detalhe}"
            assert nao_confirmadas["pix_automatico"] in detalhe, f"{bid}: {detalhe}"
        else:
            assert "não oferece Pix Automático" in detalhe, f"{bid}: {detalhe}"


# --- revisao de /pix-automatico -----------------------------------------------------

from datetime import date, timedelta  # noqa: E402


def _q(**kw):
    p = {"tenant_id": "empresa1", "provider": "on", "banco": "c6"}
    p.update(kw)
    return p


@pytest.fixture
def c6_pronto(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")


@pytest.fixture
def sem_rede(monkeypatch):
    chamadas = []

    def fake_request(self, method, path, json=None, params=None, **kw):
        chamadas.append({"path": path, "json": json, "params": params})
        return {"ok": True}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return chamadas


@pytest.mark.parametrize("rota", ["/pix-automatico/recorrencias", "/pix-automatico/cobrancas"])
@pytest.mark.parametrize("inicio,fim", [
    ("amanha", "hoje"), ("", ""), ("2026-01-01", "nao-e-data"),
    ("2026-01-31T00:00:00Z", "2026-01-01T00:00:00Z"),   # invertido
])
def test_periodo_invalido_nao_chega_ao_banco(client, c6_pronto, sem_rede, rota, inicio, fim):
    """`inicio`/`fim` eram `str` cruas com "RFC3339" so no docstring: `amanha` e
    `""` seguiam para o BACEN como chegaram. E periodo invertido volta lista
    vazia, que quem chama le como "nao houve movimento"."""
    r = client.get(rota, params=_q(inicio=inicio, fim=fim))
    assert r.status_code == 422, r.text
    assert sem_rede == []


def test_periodo_valido_segue_com_a_string_original(client, c6_pronto, sem_rede):
    """A string nao e reformatada: o dialeto aceita `Z` e `+00:00`, e normalizar
    aqui trocaria um problema por outro."""
    r = client.get("/pix-automatico/cobrancas",
                   params=_q(inicio="2026-01-01T00:00:00Z", fim="2026-01-31T23:59:59Z"))
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["params"] == {"inicio": "2026-01-01T00:00:00Z",
                                      "fim": "2026-01-31T23:59:59Z"}


@pytest.mark.parametrize("txid", ["abc", "COM-HIFEN-NO-MEIO-DO-TXID1", "A" * 40])
def test_txid_fora_do_padrao_bacen_nao_chega_ao_banco(client, c6_pronto, sem_rede, txid):
    """O txid do cobr e o mesmo da cob/cobv, e a regra valia so la."""
    assert client.get(f"/pix-automatico/cobrancas/{txid}", params=_q()).status_code == 422
    assert client.patch(f"/pix-automatico/cobrancas/{txid}", params=_q(),
                        json={"status": "CANCELADA"}).status_code == 422
    assert sem_rede == []


def test_data_da_retentativa_precisa_ser_data(client, c6_pronto, sem_rede):
    """`amanha` ia inteiro para a URL do banco."""
    txid = _TXID
    assert client.post(f"/pix-automatico/cobrancas/{txid}/retentativa/amanha",
                       params=_q()).status_code == 422
    assert sem_rede == []


def test_cobranca_do_ciclo_nao_e_agendada_para_o_passado(client, c6_pronto, sem_rede):
    """Vencimento cinco dias atras era aceito com 201 e seguia para o banco.
    A antecedencia de 2 dias fica como AVISO na descricao: nao esta claro se o
    BACEN conta dia corrido ou util, e travar errado impediria agendamento que o
    banco aceita. O passado nao tem essa ambiguidade."""
    ontem = (date.today() - timedelta(days=1)).isoformat()
    r = client.put(f"/pix-automatico/cobrancas/{_TXID}", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6",
        "cobranca": {"id_rec": "RR1", "valor": "10.00", "data_vencimento": ontem}})
    assert r.status_code == 422, r.text
    assert sem_rede == []

    amanha = (date.today() + timedelta(days=1)).isoformat()
    ok = client.put(f"/pix-automatico/cobrancas/{_TXID}", json={
        "tenant_id": "empresa1", "provider": "on", "banco": "c6",
        "cobranca": {"id_rec": "RR1", "valor": "10.00", "data_vencimento": amanha}})
    assert ok.status_code == 201, ok.text


@pytest.mark.parametrize("rota", [
    "/pix-automatico/recorrencias/RR1", "/pix-automatico/solicitacoes/SC1"])
def test_patch_sem_campo_nenhum_nao_vai_ao_banco(client, c6_pronto, sem_rede, rota):
    """PATCH vazio e no-op — e ia para o banco assim mesmo."""
    assert client.patch(rota, params=_q(), json={}).status_code == 422
    assert sem_rede == []


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "nao-e-url", "http://localhost:8000/x",
    "https://169.254.169.254/x", "https://10.1.2.3/x"])
def test_url_de_webhook_que_o_banco_nao_alcanca_e_recusada(client, c6_pronto, sem_rede, url):
    """Mesma regra do /config/webhook-*: quem chama e o BANCO, de fora. Aqui a
    URL era repassada crua, e a notificacao do debito nunca chegaria."""
    r = client.put("/pix-automatico/config/webhooks", params=_q(),
                   json={"url_recorrencia": url})
    assert r.status_code == 422, r.text
    assert "url_recorrencia" in r.json()["detail"]
    assert sem_rede == []


def test_url_publica_https_continua_valendo(client, c6_pronto, sem_rede):
    url = "https://api.minhaempresa.com.br/webhooks/pixaut/rec"
    r = client.put("/pix-automatico/config/webhooks", params=_q(),
                   json={"url_recorrencia": url})
    assert r.status_code == 200, r.text
    assert sem_rede[-1]["json"] == {"webhookUrl": url}


def test_a_spec_descreve_o_corpo_do_patch_e_dos_webhooks(client):
    """Os quatro corpos livres apareciam como "objeto qualquer", sem um campo
    nem um exemplo. O dict continua livre (o PATCH do BACEN e subconjunto
    variavel por jornada) — o que faltava era a spec dizer o que cabe ali."""
    spec = client.get("/openapi.json").json()["paths"]
    for rota in ("/pix-automatico/recorrencias/{id_rec}",
                 "/pix-automatico/solicitacoes/{id_solic}",
                 "/pix-automatico/cobrancas/{txid}"):
        corpo = spec[rota]["patch"]["requestBody"]["content"]["application/json"]
        assert corpo["schema"]["minProperties"] == 1
        assert "cancelar" in corpo["examples"]
    wh = spec["/pix-automatico/config/webhooks"]["put"]["requestBody"]["content"]["application/json"]
    assert set(wh["schema"]["properties"]) == {"url_recorrencia", "url_cobranca"}
