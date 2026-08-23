# Campo fora do contrato e erro, nao sobra.
#
# O descarte silencioso era o mecanismo por tras de quase toda a familia de
# defeitos deste modulo: o campo entrava no payload, nao era nome de nada, e
# sumia -- com `200` e um boleto que nao tem o que o chamador achou que tinha.
# `numero_docmento` produzia um titulo sem numero de documento e nada na
# resposta dizia que faltava. A engine fechou a mesma fronteira em
# `contracts.boleto_de_api`.
from __future__ import annotations

import json

import pytest

from app.core import pycob

BANCO = "banco_brasil"
BASE = {
    "valor": 150.0,
    "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Joao da Silva",
    "sacado_documento": "52998224725",
    "agencia": "3073",
    "conta_corrente": "12345678",
    "convenio": "1234567",
    "carteira": "18",
    "nosso_numero": "123",
    "data_vencimento": "2027-12-30",
}


def test_campo_desconhecido_e_recusado():
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "cor_favorita": "azul"})
    assert "'cor_favorita'" in exc.value.erros[0]


def test_erro_de_digitacao_ganha_sugestao():
    """Quase todo caso e typo: apontar o campo certo resolve mais rapido que
    listar os quarenta aceitos."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "numero_docmento": "NF-1"})
    assert "numero_documento" in exc.value.erros[0]


def test_o_erro_lista_o_que_o_banco_aceita():
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "xyz": "1"})
    listagem = exc.value.erros[-1]
    assert "nosso_numero" in listagem and "carteira" in listagem


def test_o_campo_que_sumia_agora_acusa(client):
    """O caso concreto: `numero_docmento` produzia um boleto sem o numero do
    documento, com 200, e nada apontava a falta."""
    r = client.get("/api/boleto/data", params={
        "bank": BANCO, "data": json.dumps({**BASE, "numero_docmento": "NF-1"})})
    assert r.status_code == 400, r.text
    assert any("numero_docmento" in e for e in r.json()["validation_errors"])


def test_nome_nativo_da_engine_continua_valendo():
    """`conta` e `conta_corrente` sao o mesmo campo em vocabularios diferentes;
    recusar o nativo quebraria quem ja o usa."""
    nativo = {k: v for k, v in BASE.items() if k != "conta_corrente"}
    a = pycob.dados_boleto(BANCO, {**nativo, "conta": "12345678"})
    b = pycob.dados_boleto(BANCO, BASE)
    assert a["codigo_barras"] == b["codigo_barras"]


def test_as_duas_grafias_com_valores_diferentes_sao_recusadas():
    """A ordem do dicionario decidia qual sobrevivia: um dos dois valores ia
    para o boleto e o outro sumia, sem erro -- e nos dois casos e o numero da
    conta que se esta errando."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "conta": "99999999"})
    assert "mesmo campo" in exc.value.erros[0]


def test_campo_deprecado_vazio_continua_sendo_ausencia():
    """`emv: ""` e ausencia, nao intencao -- e o campo esta documentado."""
    pycob.dados_boleto(BANCO, {**BASE, "emv": ""})


def test_campo_deprecado_preenchido_mantem_a_mensagem_propria():
    """Recusa por 'desconhecido' seria pior que a explicacao que ja existia."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "emv": "0002..."})
    assert "chave_pix" in exc.value.erros[0]


def test_identificador_de_lote_nao_e_campo_desconhecido():
    """`seu_numero` e `external_id` identificam o ITEM dentro do lote -- e de
    onde sai o `item_id` que acusa parcela duplicada."""
    pycob.dados_boleto(BANCO, {**BASE, "seu_numero": "P-01", "external_id": "X1"})


def test_flag_devolve_o_comportamento_antigo(monkeypatch):
    """Escotilha para quem descobrir em producao que mandava um campo a mais.
    Nao e para ficar ligada: sai na 3.0.0."""
    monkeypatch.setenv(pycob.FLAG_CAMPO_DESCONHECIDO, "1")
    d = pycob.dados_boleto(BANCO, {**BASE, "cor_favorita": "azul"})
    assert d["codigo_barras"]


def test_account_config_nao_e_contrato_fechado():
    """O blob e por provider, por decisao de projeto: um tenant guarda no mesmo
    lugar as chaves do caminho online e as do offline. Recusar culparia o
    chamador por uma montagem nossa."""
    import datetime

    from app.providers.offline_engine import _to_engine_payload
    from app.schemas import Cobranca, Pagador

    c = Cobranca(valor="10.00", vencimento=datetime.date(2027, 12, 31), seu_numero="1",
                 pagador=Pagador(nome="Teste", documento="12345678909"))
    d = _to_engine_payload(c, {"bank": BANCO, "cooperativa": "3073",
                               "numeroCliente": "99", "carteira": "18"})
    assert d["carteira"] == "18"
    assert "cooperativa" not in d and "numeroCliente" not in d
    pycob.construir_boleto(BANCO, d)  # nao levanta


def test_blob_com_as_duas_grafias_prefere_a_do_contrato():
    """O mesmo `account_config` carrega os dois lados: no C6 `conta` e a conta
    do REST, na engine e o que o contrato chama de `conta_corrente`."""
    import datetime

    from app.providers.offline_engine import _to_engine_payload
    from app.schemas import Cobranca, Pagador

    c = Cobranca(valor="10.00", vencimento=datetime.date(2027, 12, 31), seu_numero="1",
                 pagador=Pagador(nome="Teste", documento="12345678909"))
    d = _to_engine_payload(c, {"bank": BANCO, "conta": "123",
                               "conta_corrente": "12345678"})
    assert d["conta_corrente"] == "12345678" and "conta" not in d
