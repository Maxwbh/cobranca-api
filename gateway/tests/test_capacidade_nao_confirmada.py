# Herdar o dialeto não é o mesmo que o banco ter a rota.
#
# `implementa()` responde "a classe tem o método", e para capacidade que vem de
# mixin isso é mais fraco do que parece: o método existe porque herdamos o
# dialeto BACEN, não porque o banco exponha `rec`/`solicrec`. Nos dois casos a
# introspecção diz `True` — e o catálogo, que existe justamente para não
# envelhecer, passa a anunciar o que ninguém verificou.
#
# O caso concreto é o Inter. A evidência de homologação diz, com todas as
# letras, que não dá para prometer; o `GET /bancos` prometia.
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routers._capacidades import (_NAO_CONFIRMADO, confirmado, disponivel,
                                      flag_de_confirmacao, implementa,
                                      nao_confirmadas)

EVIDENCIAS = Path(__file__).resolve().parents[2] / "docs" / "homologacao"

CREDENCIAL = {"client_id": "x", "client_secret": "y", "cert_pem": "z", "key_pem": "w"}


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

def test_o_catalogo_nao_anuncia_pix_automatico_no_inter(client):
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert "pix_automatico" not in bancos["inter"]["capacidades"]


def test_mas_diz_que_nao_sabe_em_vez_de_so_omitir(client):
    """Omitir sem explicar faria o integrador concluir que o banco NÃO TEM, que
    é outra afirmação — e também não verificada."""
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    nao = bancos["inter"]["capacidades_nao_confirmadas"]
    assert nao == {"pix_automatico": "INTER_PIX_AUTOMATICO_READY"}


def test_quem_foi_confirmado_no_sandbox_continua_anunciado(client):
    """A lista é de quem falta confirmar, não de quem usa mixin. Sem isto, a
    correção viraria uma poda cega que tira capacidade real de C6 e Sicoob."""
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    for banco in ("c6", "sicoob"):
        assert "pix_automatico" in bancos[banco]["capacidades"], banco
        assert not bancos[banco].get("capacidades_nao_confirmadas")


# --- a rota recusa, e diz coisa diferente de "não oferece" ---------------------

def test_a_rota_recusa_e_aponta_o_caminho(client):
    r = client.post("/pix-automatico/recorrencias", json=_corpo("inter"))
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "não foi confirmado no banco 'inter'" in detalhe
    assert "INTER_PIX_AUTOMATICO_READY" in detalhe, "sem a flag, o erro é beco sem saída"
    assert "c6, sicoob" in detalhe, "o erro tem de dizer para onde ir"


def test_nao_oferece_e_nao_confirmado_sao_mensagens_DIFERENTES(client):
    """São afirmações diferentes e confundi-las é o defeito de origem.

    O Itaú não herda o mixin: sabemos que ele não oferece. Do Inter não sabemos
    nada — dizer "não oferece" ali seria trocar uma promessa sem lastro por uma
    negativa sem lastro.
    """
    do_itau = client.post("/pix-automatico/recorrencias",
                          json=_corpo("itau")).json()["detail"]
    do_inter = client.post("/pix-automatico/recorrencias",
                           json=_corpo("inter")).json()["detail"]
    assert "não oferece" in do_itau
    assert "não oferece" not in do_inter
    assert "não foi confirmado" in do_inter


def test_a_flag_destrava_para_quem_tem_credencial_real(client, monkeypatch):
    """A recusa não pode virar prisão: quem tiver acesso confirma e usa, sem
    esperar por uma versão nossa. Mesmo mecanismo do `<BANCO>_REGISTERED_READY`.
    """
    monkeypatch.setenv("INTER_PIX_AUTOMATICO_READY", "true")
    r = client.post("/pix-automatico/recorrencias", json=_corpo("inter"))
    # Passou da fronteira de capacidade: o que barra agora é a credencial falsa.
    assert r.status_code == 424, r.text
    assert "confirmado" not in r.json()["detail"]


def test_com_a_flag_o_catalogo_volta_a_anunciar(client, monkeypatch):
    """Catálogo e rota têm de concordar nos DOIS estados, não só no default —
    é a invariante que `_capacidades.py` existe para manter."""
    monkeypatch.setenv("INTER_PIX_AUTOMATICO_READY", "true")
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert "pix_automatico" in bancos["inter"]["capacidades"]
    assert not bancos["inter"]["capacidades_nao_confirmadas"]


# --- a tabela é medida, não opinada -------------------------------------------

def test_o_dialeto_continua_implementado_no_inter():
    """A capacidade some do catálogo, não do código: o mixin fica, e é ele que
    torna a confirmação um teste, e não uma implementação."""
    from app.providers.inter import InterProvider
    assert implementa(InterProvider, "criar_recorrencia")
    assert not disponivel(InterProvider, "criar_recorrencia", "inter")


def test_a_lista_bate_com_a_evidencia_de_homologacao():
    """O que prende a tabela é a evidência, não a memória de quem a escreveu.

    Um banco que passou no sandbox não pode estar em `_NAO_CONFIRMADO`; um que
    não foi exercitado não pode sair dela sem uma execução nova.
    """
    for banco, metodos in _NAO_CONFIRMADO.items():
        arquivo = EVIDENCIAS / f"evidencia-sandbox-{banco}.json"
        if not arquivo.exists():
            continue
        casos = json.loads(arquivo.read_text(encoding="utf-8"))["resultados"]
        verdes = [c for c in casos if c["caso"].startswith("PA_") and c.get("ok")]
        assert not verdes, (
            f"{banco} tem caso de Pix Automático VERDE no sandbox ({verdes[:1]}) "
            f"e ainda está em _NAO_CONFIRMADO — tire-o de lá")
        assert "criar_recorrencia" in metodos


@pytest.mark.parametrize("banco", ["c6", "sicoob"])
def test_quem_esta_verde_no_sandbox_nao_pode_entrar_na_lista(banco):
    arquivo = EVIDENCIAS / f"evidencia-sandbox-{banco}.json"
    casos = json.loads(arquivo.read_text(encoding="utf-8"))["resultados"]
    verdes = [c["caso"] for c in casos if c["caso"].startswith("PA_") and c.get("ok")]
    assert verdes, f"{banco} não tem mais caso PA_ verde — reveja _NAO_CONFIRMADO"
    assert banco not in _NAO_CONFIRMADO


def test_a_flag_segue_o_formato_da_casa():
    """`<BANCO>_<RECURSO>_READY`, como `<BANCO>_REGISTERED_READY`. Formato novo
    obrigaria quem opera a aprender duas convenções para a mesma decisão."""
    assert flag_de_confirmacao("inter", "criar_recorrencia") == "INTER_PIX_AUTOMATICO_READY"


def test_banco_fora_da_lista_nao_paga_pedagio():
    """A checagem é a exceção. Se ela custasse alguma coisa para os outros
    bancos, entraria no caminho quente de toda requisição."""
    assert confirmado(None, "criar_recorrencia", "c6") is True
    assert confirmado(None, "registrar", "inter") is True
    assert nao_confirmadas("c6") == {}
