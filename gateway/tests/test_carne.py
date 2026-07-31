# Carnê: registra N parcelas no banco (REST) e monta o PDF 3-vias na engine
# pyCobranca (in-process — sem HTTP para o engine).
from app.clients import engine


def test_carne_registra_parcelas_e_monta_pdf(client, cobranca_payload, monkeypatch):
    # credenciais do tenant no cofre (pfx vazio -> contexto SSL default)
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")  # usa o fluxo registrado

    counter = {"n": 0}

    def fake_request(self, method, path, json=None):
        counter["n"] += 1
        return {"id": f"C6-{counter['n']}", "status": "REGISTERED", "digitableLine": "00190..."}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    render_recebido = {}

    def fake_render_carne(bank, boletos):
        render_recebido["bank"] = bank
        render_recebido["boletos"] = boletos
        return {"pdf_base64": "JVBERi0xCg=="}

    monkeypatch.setattr(engine, "render_carne", fake_render_carne)

    body = {
        "tenant_id": "empresa1",
        "provider": "c6",
        "account_config": {"agencia": "0001", "conta": "123"},
        "bank": "banco_c6",
        "parcelas": [cobranca_payload, {**cobranca_payload, "nosso_numero": "2"}],
    }
    r = client.post("/carne", json=body)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["carne_pdf_base64"] == "JVBERi0xCg=="
    assert len(data["cobrancas"]) == 2
    assert [c["id"] for c in data["cobrancas"]] == ["C6-1", "C6-2"]

    # o render recebeu 2 boletos com o banco offline correspondente
    assert render_recebido["bank"] == "banco_c6"
    assert len(render_recebido["boletos"]) == 2


def test_carne_offline_gera_pdf_real(client, cobranca_payload):
    # caminho 100% offline: pyCobranca gera o carnê de verdade
    conta = {"bank": "banco_brasil", "agencia": "3073", "conta_corrente": "12345678",
             "convenio": "1234567", "carteira": "18", "cedente": "Empresa Teste LTDA",
             "documento_cedente": "11222333000181"}
    pagador = {"nome": "Joao da Silva", "documento": "52998224725"}
    body = {"tenant_id": "x", "provider": "pycobranca", "account_config": conta,
            "bank": "banco_brasil",
            "parcelas": [{**cobranca_payload, "pagador": pagador},
                          {**cobranca_payload, "nosso_numero": "2", "pagador": pagador}]}
    r = client.post("/carne", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["carne_pdf_base64"].startswith("JVBER")


# O teto de lote valia so para /api/boleto/multi. Como o carne renderiza pelo
# mesmo pdf_multi e tambem de forma sincrona, dava para passar do limite so
# trocando de endpoint -- conferido contra a producao: 201 boletos recusados
# no multi (413) e aceitos no carne (200).
_DADOS_LOTE = {
    "valor": 150.0, "cedente": "Aurora Servicos Empresariais LTDA",
    "documento_cedente": "47816329000199", "sacado": "Vitoria Gabriela Emanuelly Ramos",
    "sacado_documento": "77044362109", "agencia": "3073", "conta_corrente": "12345678",
    "convenio": "1234567", "carteira": "18", "data_vencimento": "2027-12-30",
}


def _boletos(n):
    return [{**_DADOS_LOTE, "nosso_numero": str(30000 + i),
             "numero_documento": f"CAR-{i:04d}"} for i in range(n)]


def test_carne_recusa_lote_acima_do_limite(client):
    from app.routers.offline import LOTE_MAX  # noqa: PLC0415
    r = client.post("/api/render/carne",
                    json={"bank": "banco_brasil", "boletos": _boletos(LOTE_MAX + 1)})
    assert r.status_code == 413, r.text
    corpo = r.json()
    assert corpo["recebidos"] == LOTE_MAX + 1
    assert str(LOTE_MAX) in corpo["error"]


def test_carne_no_limite_continua_aceito(client):
    from app.routers.offline import LOTE_MAX  # noqa: PLC0415
    r = client.post("/api/render/carne",
                    json={"bank": "banco_brasil", "boletos": _boletos(LOTE_MAX)})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_base64"]


def test_limite_do_carne_e_o_mesmo_do_multi(client, monkeypatch):
    # Os dois caminhos sincronos leem LOTE_MAX_ITENS: mudar a variavel de
    # ambiente tem de mover os dois juntos, senao a inconsistencia volta.
    import importlib

    from app import routers
    monkeypatch.setenv("LOTE_MAX_ITENS", "3")
    importlib.reload(routers.offline)
    assert routers.offline.LOTE_MAX == 3
    monkeypatch.delenv("LOTE_MAX_ITENS")
    importlib.reload(routers.offline)
