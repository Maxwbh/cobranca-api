# O `BoletoData` da doc contra o `BoletoData` da engine.
#
# A doc desta API envelheceu por OMISSAO, nao por erro: a engine ganhava campo,
# o gateway passava a aceita-lo, e a pagina nao dizia nada. Foi assim que nove
# campos especificos de banco ficaram de fora -- e no Citibank, sem `portfolio`,
# o codigo de barras sai com o campo livre zerado, valido em estrutura e errado
# no destino, sem levantar erro.
#
# Aqui a comparacao e feita contra o contrato que a propria engine publica. Se
# a proxima versao acrescentar um campo, este arquivo fica vermelho com o nome
# dele em vez de o campo entrar calado.
from __future__ import annotations

import pathlib

import pytest
import yaml
from pycobranca.contracts import CAMPOS_POR_BANCO, CONTRATO, TOTALIZADORES

from app.core import pycob

SPEC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"

#: Campos do contrato da engine que NAO pertencem ao `data` de um boleto.
#:
#: `itens` e `fatura` sao o corpo da fatura e entram na raiz de
#: `POST /api/render/fatura`, nao dentro de `data`.
#:
#: Os cinco da faixa FEBRABAN a engine sabe desenhar, e o produto nao expoe:
#: desconto, multa e juros dependem da DATA DO PAGAMENTO, entao quem preenche a
#: faixa e o caixa, no ato. A regra impressa vai em `instrucoes` e os parametros
#: vao na remessa CNAB, que e o arquivo que o banco processa. Enviar um dos
#: cinco no boleto responde 400 — coberto por `test_schema_fechado.py`.
FORA_DO_BOLETO = {"itens", "fatura", *TOTALIZADORES}


def _documentados() -> set[str]:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    return set(spec["components"]["schemas"]["BoletoData"]["properties"])


def _da_engine() -> set[str]:
    return set(CONTRATO["schemas"]["BoletoData"]["properties"]) - FORA_DO_BOLETO


def test_todo_campo_do_contrato_da_engine_esta_documentado():
    faltando = sorted(_da_engine() - _documentados())
    assert not faltando, (
        "campos que a engine expoe no contrato e o BoletoData da doc nao cita: "
        f"{faltando}")


def test_todo_campo_documentado_e_aceito_de_fato():
    """Doc que promete campo sem consumidor foi a familia de defeitos anterior.

    Os tres deprecados respondem 400 com a explicacao -- estao documentados
    como recusados, entao contam como tratados.
    """
    recusados = {"emv", "pix_label", "fonte_ttf"}
    # Campo especifico de banco so precisa ser entendido por ALGUM banco: o
    # `portfolio` e do Citibank, o `posto` do Sicredi.
    aceitos_por_algum: set[str] = set()
    for slug in pycob.bancos_suportados():
        aceitos_por_algum |= pycob.campos_aceitos(slug)
    orfaos = sorted(_documentados() - aceitos_por_algum - recusados)
    assert not orfaos, (
        f"documentados e recusados como desconhecidos por TODOS os bancos: {orfaos}")




@pytest.mark.parametrize("campo", sorted(CAMPOS_POR_BANCO))
def test_campo_especifico_de_banco_documentado(campo):
    assert campo in _documentados()


def test_apelido_do_contrato_e_o_da_engine():
    """As quatro traducoes de nome saem da engine, nao de uma copia daqui.

    `documento_cedente`/`cedente_documento` inverte as palavras: e o tipo de
    detalhe em que duas listas escritas a mao acabam discordando, e o erro sai
    como boleto sem o documento do cedente.
    """
    from pycobranca.contracts import NOMES_DO_CONTRATO
    assert pycob.NOMES_DO_CONTRATO == dict(NOMES_DO_CONTRATO)

