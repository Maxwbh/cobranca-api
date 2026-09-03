# Herdar o dialeto não é o mesmo que o banco ter a rota.
#
# `implementa()` responde "a classe tem o método", e para capacidade que vem de
# mixin isso é mais fraco do que parece: o método existe porque herdamos o
# dialeto BACEN, não porque o banco exponha as rotas. Nos dois casos a
# introspecção diz `True` — e o catálogo, que existe justamente para não
# envelhecer, passa a anunciar o que ninguém verificou.
#
# O caso que motivou foi o Pix Automático do Inter, e ele **já foi confirmado**
# (spec do próprio banco; ver `test_pix_automatico_inter.py`). Por isso
# `_NAO_CONFIRMADO` está vazio hoje, e as provas abaixo usam uma entrada
# SINTÉTICA: o mecanismo tem de continuar demonstrado mesmo com a lista vazia —
# senão ele viraria código sem prova, esperando o próximo mixin herdado por um
# banco que não o exponha.
from __future__ import annotations

import pytest

from app.routers import _capacidades
from app.routers._capacidades import (_NAO_CONFIRMADO, confirmado, disponivel,
                                      flag_de_confirmacao, implementa,
                                      nao_confirmadas)

CREDENCIAL = {"client_id": "x", "client_secret": "y", "cert_pem": "z", "key_pem": "w"}

#: Entrada de mentira sobre um banco de verdade: o Sicoob herda o mesmo mixin,
#: então serve de cobaia sem precisar de um provider de teste.
SINTETICO = {"sicoob": {"criar_recorrencia": (
    "Pix Automático",
    "entrada sintética do teste — o Sicoob está confirmado em sandbox (`PA_01`)")}}


@pytest.fixture
def gatilho(monkeypatch):
    """Liga a checagem para o Sicoob, sem tocar no estado real."""
    monkeypatch.setattr(_capacidades, "_NAO_CONFIRMADO", SINTETICO)
    return SINTETICO


def _corpo(banco: str) -> dict:
    return {
        "tenant_id": "t", "provider": "on", "banco": banco,
        "credentials": CREDENCIAL,
        "recorrencia": {
            "contrato": "CT-2027-001", "periodicidade": "MENSAL",
            "data_inicial": "2027-01-10", "valor_fixo": "150.00",
            "devedor": {"nome": "Joao da Silva", "documento": "12345678909"}},
    }


# --- o catálogo para de prometer ----------------------------------------------

def test_o_catalogo_omite_a_capacidade_nao_confirmada(client, gatilho):
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert "pix_automatico" not in bancos["sicoob"]["capacidades"]


def test_mas_diz_que_nao_sabe_em_vez_de_so_omitir(client, gatilho):
    """Omitir sem explicar faria o integrador concluir que o banco NÃO TEM, que
    é outra afirmação — e também não verificada."""
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert bancos["sicoob"]["capacidades_nao_confirmadas"] == {
        "pix_automatico": "SICOOB_PIX_AUTOMATICO_READY"}


def test_os_outros_bancos_nao_sao_afetados(client, gatilho):
    """A checagem é a exceção: quem não está na lista segue como estava."""
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    for banco in ("c6", "inter"):
        assert "pix_automatico" in bancos[banco]["capacidades"], banco
        assert not bancos[banco].get("capacidades_nao_confirmadas")


# --- a rota recusa, e diz coisa diferente de "não oferece" ---------------------

def test_a_rota_recusa_e_aponta_o_caminho(client, gatilho):
    r = client.post("/pix-automatico/recorrencias", json=_corpo("sicoob"))
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "não foi confirmado no banco 'sicoob'" in detalhe
    assert "SICOOB_PIX_AUTOMATICO_READY" in detalhe, "sem a flag, o erro é beco sem saída"


def test_nao_oferece_e_nao_confirmado_sao_mensagens_DIFERENTES(client, gatilho):
    """São afirmações diferentes e confundi-las é o defeito de origem.

    O Itaú não herda o mixin: sabemos que ele não oferece. De um banco não
    confirmado não sabemos nada — dizer "não oferece" seria trocar uma promessa
    sem lastro por uma negativa sem lastro.
    """
    do_itau = client.post("/pix-automatico/recorrencias",
                          json=_corpo("itau")).json()["detail"]
    do_outro = client.post("/pix-automatico/recorrencias",
                           json=_corpo("sicoob")).json()["detail"]
    assert "não oferece" in do_itau
    assert "não oferece" not in do_outro
    assert "não foi confirmado" in do_outro


def test_a_flag_destrava_para_quem_tem_credencial_real(client, gatilho, monkeypatch):
    """A recusa não pode virar prisão: quem tiver acesso confirma e usa, sem
    esperar por uma versão nossa. Mesmo mecanismo do `<BANCO>_REGISTERED_READY`.
    """
    monkeypatch.setenv("SICOOB_PIX_AUTOMATICO_READY", "true")
    r = client.post("/pix-automatico/recorrencias", json=_corpo("sicoob"))
    # Passou da fronteira de capacidade: o que barra agora é a credencial falsa.
    assert r.status_code == 424, r.text
    assert "confirmado" not in r.json()["detail"]


def test_com_a_flag_o_catalogo_volta_a_anunciar(client, gatilho, monkeypatch):
    """Catálogo e rota têm de concordar nos DOIS estados, não só no default —
    é a invariante que `_capacidades.py` existe para manter."""
    monkeypatch.setenv("SICOOB_PIX_AUTOMATICO_READY", "true")
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert "pix_automatico" in bancos["sicoob"]["capacidades"]
    assert not bancos["sicoob"]["capacidades_nao_confirmadas"]


# --- o estado real -------------------------------------------------------------

def test_a_lista_esta_vazia_e_isso_e_resultado():
    """Hoje nenhum banco está pendente de confirmação. O mecanismo fica porque o
    próximo mixin herdado por um banco que não o exponha cai aqui em uma linha —
    e porque a alternativa é anunciar o que ninguém verificou."""
    assert _NAO_CONFIRMADO == {}


def test_sem_entrada_na_lista_ninguem_paga_pedagio():
    """Se a checagem custasse alguma coisa aos demais bancos, estaria no caminho
    quente de toda requisição."""
    from app.providers.inter import InterProvider
    assert confirmado(None, "criar_recorrencia", "inter") is True
    assert confirmado(None, "registrar", "c6") is True
    assert nao_confirmadas("c6") == {}
    assert implementa(InterProvider, "criar_recorrencia")
    assert disponivel(InterProvider, "criar_recorrencia", "inter")


def test_a_flag_segue_o_formato_da_casa(gatilho):
    """`<BANCO>_<RECURSO>_READY`, como `<BANCO>_REGISTERED_READY`. Formato novo
    obrigaria quem opera a aprender duas convenções para a mesma decisão."""
    assert flag_de_confirmacao("sicoob", "criar_recorrencia") == \
        "SICOOB_PIX_AUTOMATICO_READY"
