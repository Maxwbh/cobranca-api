# Carnê: registra N parcelas no banco (REST) e monta o PDF 3-vias na engine
# pyCobranca (in-process — sem HTTP para o engine).
from app.clients import engine

_PAG = {"nome": "Joao da Silva", "documento": "52998224725"}


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
        # O `account_config` do carne carrega OS DOIS lados: o que o C6 REST
        # precisa para registrar e o que a engine precisa para desenhar. Sem os
        # campos de desenho o registro acontecia e o render falhava depois --
        # com 500 e N boletos ja vivos no banco.
        "account_config": {"agencia": "0001", "conta": "123", "conta_corrente": "1234567",
                           "convenio": "1234567", "carteira": "10",
                           "cedente": "Empresa Teste LTDA",
                           "documento_cedente": "11222333000181"},
        "bank": "banco_c6",
        # `seu_numero` distinto por parcela: o fixture repetia o mesmo em todas,
        # e duas parcelas com o MESMO identificador sao o mesmo titulo duas
        # vezes -- no carne uma sobrescrevia a outra no PDF.
        # CPF valido: o do fixture nao passa no digito verificador, e a engine
        # descartava a parcela em silencio ao desenhar.
        "parcelas": [{**cobranca_payload, "pagador": _PAG},
                     {**cobranca_payload, "nosso_numero": "2", "seu_numero": "A-2",
                      "pagador": _PAG}],
    }
    r = client.post("/carne", json=body)
    assert r.status_code == 201, r.text
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
                          {**cobranca_payload, "nosso_numero": "2", "seu_numero": "A-2",
                           "pagador": pagador}]}
    r = client.post("/carne", json=body)
    assert r.status_code == 201, r.text
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


# O carne ACEITAVA parcela duplicada e imprimia a duplicata: bloco de 12 com a
# 8a copiando a 5a saia com 12 paginas e 11 documentos distintos. Em reemissao
# de contrato (blocos de 12/24/36 remontados a cada ciclo) e o erro mais
# provavel -- e o efeito e a parcela sobrescrita nunca ser cobrada.
def test_carne_recusa_parcela_duplicada(client):
    bloco = _boletos(12)
    bloco[7] = dict(bloco[4])            # parcela 8 vira copia da 5
    r = client.post("/api/render/carne",
                    json={"bank": "banco_brasil", "boletos": bloco})
    assert r.status_code == 422, r.text
    dup = r.json()["duplicados"]
    assert dup == [{"item_id": "CAR-0004", "indices": [4, 7]}]


def test_carne_sem_duplicata_continua_aceito(client):
    r = client.post("/api/render/carne",
                    json={"bank": "banco_brasil", "boletos": _boletos(12)})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_base64"]


def test_carne_sem_identificador_nao_acusa_duplicidade(client):
    # Sem external_id/seu_numero/numero_documento o id cai no indice, que nunca
    # colide. Comportamento anterior, preservado.
    base = {k: v for k, v in _DADOS_LOTE.items()}
    r = client.post("/api/render/carne", json={
        "bank": "banco_brasil",
        "boletos": [dict(base, nosso_numero=str(40000 + i)) for i in range(3)]})
    assert r.status_code == 200, r.text


# --- revisao de POST /carne -------------------------------------------------------
#
# O carne do GATEWAY renderiza pelo mesmo pdf_multi do /api/render/carne, mas
# entrava por outra porta: as guardas que aquela rota ganhou (teto, duplicata,
# dado invalido) nunca valeram aqui. E, ao contrario dela, aqui o erro chega
# DEPOIS de registrar N boletos no banco.
import base64

import pytest

_CONTA = {"agencia": "3073", "conta_corrente": "12345678", "convenio": "1234567",
          "carteira": "18", "cedente": "Empresa Teste LTDA",
          "documento_cedente": "11222333000181"}

def _corpo(n=2, **kw):
    parcelas = [{"valor": "100.00", "vencimento": "2026-07-10", "nosso_numero": str(i + 1),
                 "seu_numero": f"A-{i+1}", "pagador": _PAG} for i in range(n)]
    corpo = {"tenant_id": "empresa1", "provider": "off", "banco": "banco_brasil",
             "parcelas": parcelas, "account_config": dict(_CONTA)}
    corpo.update(kw)
    return corpo


def test_carne_sem_bank_desenha_pelo_banco(client):
    """`bank` era obrigatorio e era o mesmo fato escrito duas vezes. O layout sai
    do `banco`, que ja e o eixo da API inteira."""
    r = client.post("/carne", json=_corpo(2))
    assert r.status_code == 201, r.text
    assert r.json()["carne_pdf_base64"].startswith("JVBER")


def test_carne_com_bank_divergente_do_banco_e_recusado(client):
    """Parcelas registradas num banco e carne desenhado como OUTRO: o documento
    nao e pagavel, e saia com 201. O registry ja trata emitir pelo banco errado
    como falha silenciosa e cara -- aqui era so nao conferir dois campos."""
    r = client.post("/carne", json=_corpo(2, bank="caixa"))
    assert r.status_code == 422, r.text
    assert "caixa" in r.json()["detail"] and "banco_brasil" in r.json()["detail"]


def test_carne_de_banco_sem_layout_na_engine_e_recusado(client, monkeypatch):
    """O Inter nao tem layout 077 na engine. Sem esta guarda, `bank` livre
    desenhava o carne com a marca de outro banco."""
    monkeypatch.setenv("VAULT__empresa1__inter__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__inter__client_secret", "sec")
    r = client.post("/carne", json=_corpo(2, provider="on", banco="inter", bank="itau"))
    assert r.status_code == 422, r.text
    assert "inter" in r.json()["detail"]


def test_carne_sem_parcela_nao_e_500(client):
    """`parcelas: []` levantava IndexError na engine: 500 com corpo de 21 bytes,
    nao-JSON -- quem chamou nao tinha como saber o que estava errado."""
    r = client.post("/carne", json=_corpo(0))
    assert r.status_code == 422, r.text


def test_carne_recusa_parcela_duplicada_no_gateway(client):
    """Mesma regra do /api/render/carne, que por aqui nao valia: a parcela
    sobrescrita some do bloco e nunca e cobrada."""
    corpo = _corpo(2)
    corpo["parcelas"][1]["seu_numero"] = "A-1"
    r = client.post("/carne", json=corpo)
    assert r.status_code == 422, r.text
    assert "duplicado" in r.json()["detail"]


def test_carne_recusa_lote_acima_do_teto_no_gateway(client):
    """O teto existia nas duas rotas /api/* e nao aqui — e aqui o lote grande
    ainda faz N idas ao banco antes do OOM."""
    r = client.post("/carne", json=_corpo(201))
    assert r.status_code == 413, r.text
    assert "200" in r.json()["detail"]


def test_parcela_invalida_nao_some_do_carne_em_silencio(client):
    """pdf_multi e TOLERANTE: descarta o item invalido e monta o resto. O
    resultado por item era jogado fora, entao 3 parcelas entravam, 2 saiam
    desenhadas e a resposta era 201 -- o pagador nunca recebe o boleto de uma
    parcela que continua sendo cobrada."""
    corpo = _corpo(3)
    corpo["parcelas"][1]["nosso_numero"] = "9" * 30   # excede o convenio do BB
    r = client.post("/carne", json=corpo)
    assert r.status_code == 422, r.text
    assert "parcela 1" in r.json()["detail"]


def test_recusa_vem_antes_de_registrar_no_banco(client, monkeypatch):
    """A ordem e a correcao: tudo que da para recusar e recusado ANTES do
    primeiro `registrar`. Depois dele existe boleto no banco, e um erro ali
    deixa titulo vivo que a resposta nao menciona."""
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    chamadas = []

    def fake_request(self, method, path, json=None):
        chamadas.append(path)
        return {"id": f"C6-{len(chamadas)}", "status": "REGISTERED"}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    corpo = _corpo(3, provider="on", banco="c6")
    corpo["parcelas"][1]["seu_numero"] = "A-1"        # duplicata

    r = client.post("/carne", json=corpo)
    assert r.status_code == 422, r.text
    assert chamadas == [], "recusou depois de registrar no banco"


def test_carne_aceita_token_do_credenciais(client, monkeypatch):
    """A rota nao lia `Authorization`: o caminho de credencial que a documentacao
    chama de recomendado simplesmente nao existia aqui. Token invalido tem de
    falhar alto, e nao cair no cofre em silencio."""
    r = client.post("/carne", json=_corpo(1),
                    headers={"Authorization": "Bearer bapi_naoexiste"})
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("faltando", ["cedente", "carteira"])
def test_dado_que_a_engine_recusa_vira_422_e_nao_500(client, faltando):
    """DadosInvalidos escapava do handler: 500 com corpo nao-JSON."""
    corpo = _corpo(2)
    corpo["account_config"].pop(faltando)
    r = client.post("/carne", json=corpo)
    assert r.status_code == 422, r.text
    assert "parcela 0" in r.json()["detail"]


def test_carne_valido_continua_com_uma_pagina_por_tres_parcelas(client):
    """O carne e 3 vias por A4: a contagem de paginas e o que prova que nenhuma
    parcela sumiu no caminho."""
    r = client.post("/carne", json=_corpo(6))
    assert r.status_code == 201, r.text
    pdf = base64.b64decode(r.json()["carne_pdf_base64"])
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") == 2
