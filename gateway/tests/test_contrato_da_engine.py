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

#: Campos do contrato da engine que NAO pertencem ao `data` de um boleto:
#: `itens` e `fatura` sao o corpo da fatura e entram na raiz de
#: `POST /api/render/fatura`, nao dentro de `data`.
FORA_DO_BOLETO = {"itens", "fatura"}


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


@pytest.mark.parametrize("campo", sorted(TOTALIZADORES))
def test_faixa_febraban_documentada(campo):
    assert campo in _documentados()


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


def test_faixa_febraban_chega_ao_papel():
    """Os cinco campos sao novos na engine: valem so se aparecerem impressos."""
    import io

    from pypdf import PdfReader
    dados = {
        "valor": 150.0, "cedente": "Empresa Teste LTDA",
        "documento_cedente": "11222333000181", "sacado": "Joao da Silva",
        "sacado_documento": "52998224725", "agencia": "3073",
        "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
        "nosso_numero": "123", "data_vencimento": "2027-12-30",
        "desconto_abatimento": 50.00, "mora_multa": 8.00,
    }
    pdf, info = pycob.emitir_boleto("banco_brasil", dados)
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "50,00" in texto and "8,00" in texto
    # 150 - 50 + 8 = 108: o total sai somado, nao em branco
    assert info["totalizadores"]["valor_cobrado"] == "108,00"
    assert "108,00" in texto


def test_sem_encargo_a_faixa_sai_em_branco():
    """Padrao de boleto comum: quem preenche a faixa e o caixa, no pagamento.

    Imprimir um total antecipado induziria o pagador a erro.
    """
    dados = {
        "valor": 150.0, "cedente": "Empresa Teste LTDA",
        "documento_cedente": "11222333000181", "sacado": "Joao da Silva",
        "sacado_documento": "52998224725", "agencia": "3073",
        "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
        "nosso_numero": "123", "data_vencimento": "2027-12-30",
    }
    _pdf, info = pycob.emitir_boleto("banco_brasil", dados)
    assert set(info["totalizadores"]) == set(TOTALIZADORES)
    assert all(v == "" for v in info["totalizadores"].values())
