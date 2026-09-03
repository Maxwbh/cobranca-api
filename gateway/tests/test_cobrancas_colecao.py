# Coleção e sumário de cobranças — `GET /cobrancas` e `/cobrancas/sumario`.
#
# Cobre BC-104..BC-110 da matriz em postman/README.md.
#
# Tudo aqui é conferido contra a spec do próprio Inter
# (`swagger-cobranca-bolepix`): os nomes dos parâmetros, o vocabulário fechado
# dos filtros, a base 0 da paginação e o formato da resposta do sumário. Não há
# e2e: exigiria conta com movimento no período, e o que se quer provar é o
# contrato, não o extrato de ninguém.
import pytest


@pytest.fixture
def inter_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__inter__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__inter__client_secret", "sec")
    monkeypatch.setenv("INTER_REGISTERED_READY", "true")


@pytest.fixture
def c6_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")


_LISTA = {"totalPaginas": 3, "totalElementos": 57, "tamanhoPagina": 25,
          "primeiraPagina": False, "ultimaPagina": False, "numeroDeElementos": 25,
          "cobrancas": [{"cobranca": {"seuNumero": "A-1", "situacao": "A_RECEBER"}}]}

#: O Inter devolve **array na raiz** no sumário — não objeto.
_SUMARIO = [{"situacao": "A_RECEBER", "quantidade": 2, "valor": 300.0},
            {"situacao": "RECEBIDO", "quantidade": 1, "valor": 50.0}]


def _capture(monkeypatch, lista=None, sumario=None):
    calls = []

    def fake_request(self, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "params": params})
        if path.endswith("/sumario"):
            return _SUMARIO if sumario is None else sumario
        return _LISTA if lista is None else lista

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return calls


def _params(**ck):
    base = {"tenant_id": "empresa1", "provider": "inter",
            "inicio": "2027-01-01", "fim": "2027-01-31"}
    base.update(ck)
    return base


# --- BC-104 · coleção -------------------------------------------------------------

def test_lista_usa_a_rota_e_o_periodo_do_banco(client, inter_env, monkeypatch):
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas", params=_params())
    assert r.status_code == 200, r.text
    assert r.json()["totalElementos"] == 57  # passthrough: nomes do banco
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/cobranca/v3/cobrancas"
    assert calls[0]["params"]["dataInicial"] == "2027-01-01"
    assert calls[0]["params"]["dataFinal"] == "2027-01-31"


# --- BC-105 · paginação 1-based -> 0-based ----------------------------------------

@pytest.mark.parametrize("pagina,no_banco", [(1, 0), (2, 1), (7, 6)])
def test_pagina_do_contrato_vira_pagina_do_inter(client, inter_env, monkeypatch,
                                                 pagina, no_banco):
    """O erro que este teste existe para impedir não dá erro nenhum.

    O resto da API pagina a partir de 1 e o Inter a partir de 0: repassar a
    página crua devolve a SEGUNDA para quem pediu a primeira, com `200` e corpo
    plausível. Some-se a primeira página inteira da conciliação sem uma linha de
    log.
    """
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas", params=_params(pagina=pagina, tamanho=25))
    assert r.status_code == 200, r.text
    assert calls[0]["params"]["paginacao.paginaAtual"] == no_banco
    assert calls[0]["params"]["paginacao.itensPorPagina"] == 25


def test_pagina_zero_e_recusada_antes_do_banco(client, inter_env, monkeypatch):
    """Sem o `ge=1`, `pagina=0` viraria `max(-1, 0) == 0` e devolveria a
    primeira página — aceitando calado um número que o contrato não tem."""
    _capture(monkeypatch)
    assert client.get("/cobrancas", params=_params(pagina=0)).status_code == 422


def test_tamanho_respeita_o_teto_do_banco(client, inter_env, monkeypatch):
    """1000 é o `maximum` da spec do Inter; acima disso quem responde é o banco,
    com `400` que não diz qual campo passou do limite."""
    _capture(monkeypatch)
    assert client.get("/cobrancas", params=_params(tamanho=1000)).status_code == 200
    assert client.get("/cobrancas", params=_params(tamanho=1001)).status_code == 422


# --- BC-106 · filtros traduzidos --------------------------------------------------

def test_filtros_saem_com_o_nome_do_inter(client, inter_env, monkeypatch):
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas", params=_params(
        situacao="A_RECEBER", seu_numero="A-1", pagador="Fulano",
        documento_pagador="12345678901", filtrar_data_por="EMISSAO",
        tipo_cobranca="SIMPLES", ordenar_por="DATA_VENCIMENTO", tipo_ordenacao="DESC"))
    assert r.status_code == 200, r.text
    assert calls[0]["params"] == {
        "dataInicial": "2027-01-01", "dataFinal": "2027-01-31",
        "paginacao.paginaAtual": 0, "paginacao.itensPorPagina": 50,
        "situacao": "A_RECEBER", "seuNumero": "A-1", "pessoaPagadora": "Fulano",
        "cpfCnpjPessoaPagadora": "12345678901", "filtrarDataPor": "EMISSAO",
        "tipoCobranca": "SIMPLES", "ordenarPor": "DATA_VENCIMENTO", "tipoOrdenacao": "DESC"}


def test_filtro_vazio_nao_vai_ao_banco(client, inter_env, monkeypatch):
    """Mandar `situacao=` cru filtraria por situação vazia — zero resultados que
    parecem ausência de movimento."""
    calls = _capture(monkeypatch)
    assert client.get("/cobrancas", params=_params(situacao="")).status_code == 200
    assert "situacao" not in calls[0]["params"]


# --- BC-107 · vocabulário fechado -------------------------------------------------

@pytest.mark.parametrize("campo,valor", [
    ("situacao", "ABERTO"),          # o Inter chama de A_RECEBER
    ("tipo_cobranca", "AVULSA"),
    ("filtrar_data_por", "LIQUIDACAO"),
    ("ordenar_por", "DATA"),
    ("tipo_ordenacao", "CRESCENTE"),
])
def test_valor_fora_do_vocabulario_do_banco_para_aqui(client, inter_env, monkeypatch,
                                                      campo, valor):
    """`400` do banco não diz que a palavra é que está errada. O 422 daqui diz,
    e ainda lista as aceitas."""
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas", params=_params(**{campo: valor}))
    assert r.status_code == 422, r.text
    assert valor in r.json()["detail"] and "não existe no Inter" in r.json()["detail"]
    assert not calls, "não deveria ter ido ao banco"


def test_o_vocabulario_conferido_e_o_da_spec_do_inter():
    """Se o banco ampliar a lista, o teste cai junto com a realidade — é o
    ponto: a conferência não pode ficar mais estreita que o banco e recusar
    valor legítimo."""
    from app.providers.inter import InterProvider
    assert InterProvider.VALORES_DE_FILTRO["situacao"] == (
        "RECEBIDO", "A_RECEBER", "MARCADO_RECEBIDO", "ATRASADO", "CANCELADO",
        "EXPIRADO", "FALHA_EMISSAO", "EM_PROCESSAMENTO", "PROTESTO")
    # Todo campo com vocabulário fechado tem de estar no mapa de tradução.
    assert set(InterProvider.VALORES_DE_FILTRO) <= set(InterProvider.FILTROS_COBRANCA)


# --- BC-108 · sumário -------------------------------------------------------------

def test_sumario_embrulha_o_array_do_banco(client, inter_env, monkeypatch):
    """O Inter devolve array na raiz. Repassado cru, a rota estourava `500` com
    corpo perfeitamente legítimo do banco — foi assim que este caso apareceu."""
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas/sumario", params=_params())
    assert r.status_code == 200, r.text
    assert r.json() == {"sumario": _SUMARIO}
    assert calls[0]["path"] == "/cobranca/v3/cobrancas/sumario"


def test_sumario_nao_pagina_nem_ordena(client, inter_env, monkeypatch):
    """A spec do sumário não tem paginação nem ordenação: mandar mesmo assim é
    parâmetro ignorado pelo banco com cara de aceito."""
    calls = _capture(monkeypatch)
    assert client.get("/cobrancas/sumario", params=_params(
        situacao="RECEBIDO")).status_code == 200
    assert calls[0]["params"] == {"dataInicial": "2027-01-01", "dataFinal": "2027-01-31",
                                 "situacao": "RECEBIDO"}


# --- BC-109 · período -------------------------------------------------------------

def test_periodo_invertido_para_antes_do_banco(client, inter_env, monkeypatch):
    """Invertido o banco responde lista vazia, que quem chama lê como "não houve
    movimento" — o pior erro possível numa conciliação."""
    calls = _capture(monkeypatch)
    r = client.get("/cobrancas", params=_params(inicio="2027-02-01", fim="2027-01-01"))
    assert r.status_code == 422, r.text
    assert "invertido" in r.json()["detail"]
    assert not calls


@pytest.mark.parametrize("fim,esperado", [("2027-04-01", 200), ("2027-04-02", 422)])
def test_janela_maxima_de_noventa_dias(client, inter_env, monkeypatch, fim, esperado):
    _capture(monkeypatch)
    assert client.get("/cobrancas", params=_params(fim=fim)).status_code == esperado


def test_a_janela_vale_tambem_no_sumario(client, inter_env, monkeypatch):
    """Sumário sem paginação é o convite mais fácil a varrer a base inteira."""
    _capture(monkeypatch)
    r = client.get("/cobrancas/sumario", params=_params(fim="2027-12-31"))
    assert r.status_code == 422, r.text


# --- BC-110 · quem não oferece ----------------------------------------------------

@pytest.mark.parametrize("rota", ["/cobrancas", "/cobrancas/sumario"])
def test_banco_sem_colecao_diz_quem_tem(client, c6_env, monkeypatch, rota):
    """`422` nomeando o banco que oferece — nunca `500`, e nunca `200` vazio."""
    calls = _capture(monkeypatch)
    r = client.get(rota, params=_params(provider="c6"))
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "não oferece" in detalhe and "inter" in detalhe
    assert not calls


def test_o_catalogo_anuncia_a_capacidade_em_quem_a_tem(client, inter_env, c6_env):
    """`GET /bancos` é onde quem integra decide a quem perguntar.

    Rota que existe e catálogo que não a menciona = capacidade invisível; o
    contrário — anunciar em quem não tem — manda o integrador direto ao 422.
    """
    bancos = {b["id"]: b.get("capacidades") or [] for b in client.get("/bancos").json()["bancos"]}
    assert {"cobranca_listagem", "cobranca_sumario"} <= set(bancos["inter"])
    for outro in ("c6", "sicoob", "itau"):
        assert not [c for c in bancos[outro] if c.startswith("cobranca_")], outro


@pytest.mark.parametrize("rota", ["/cobrancas", "/cobrancas/sumario"])
def test_no_caminho_offline_a_rota_diz_que_e_do_caminho_on(client, rota):
    """Offline não tem coleção: o estado vem do arquivo de retorno. O erro
    aponta o caminho certo em vez de deixar o 404 do banco falar."""
    r = client.get(rota, params=_params(provider="off", banco="inter"))
    assert r.status_code == 422, r.text
    assert "caminho ON" in r.json()["detail"]
