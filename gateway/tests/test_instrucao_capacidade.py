# A guarda de instrucoes contra a engine de verdade.
#
# O gateway media a caixa de instrucoes UMA vez e guardava o numero numa
# constante: `MAX_LINHAS_INSTRUCAO = 7`, com o comentario afirmando ser
# "identico com e sem PIX". Valia para a versao medida. A moldura muda de
# altura conforme o modelo e conforme haja Bolepix, e quando a engine mexeu no
# layout a constante ficou para tras SEM NADA ACUSAR -- o gateway seguiu
# aceitando uma linha a mais do que o modelo imprimia, que e exatamente a perda
# silenciosa que a guarda existe para impedir.
#
# Aqui a medicao e refeita contra a engine instalada. Se o layout mudar, este
# arquivo fica vermelho com o numero novo no lugar de o texto sumir do PDF de
# alguem.
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from app.core import pycob

MARCA = "QVXZLINHA"

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

#: Instrucao real, em maiusculas -- que e como quase toda instrucao de boleto
#: chega. `LARGURA_INSTRUCAO` esta calibrada nisto: o limite da engine e em
#: PONTOS, entao uma linha inteira de "M" cabe menos e uma de "l" cabe mais.
PROSA = "APOS O VENCIMENTO COBRAR MULTA DE 2% E JUROS DE 1% AO MES PRO RATA DIE"

COMBINACOES = [(modelo, pix) for modelo in ("classico", "moderno", "carne")
               for pix in (False, True)]


def _texto(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def _render(modelo: str, tem_pix: bool, instrucoes: list[str]) -> str:
    """Desenha pelo mesmo caminho do produto e devolve o texto do PDF."""
    dados = {**BASE, "instrucoes": instrucoes}
    if tem_pix:
        dados["chave_pix"] = "11222333000181"
    if modelo == "carne":
        pdf, _ = pycob.pdf_multi([{**dados, "bank": BANCO}], template="carne")
    else:
        pdf = pycob.pdf_boleto(BANCO, dados, template=modelo)
    return _texto(pdf)


@pytest.mark.parametrize(("modelo", "tem_pix"), COMBINACOES)
def test_o_limite_aceito_e_o_numero_de_linhas_que_a_engine_desenha(modelo, tem_pix):
    """Tudo que o gateway aceita tem de aparecer no papel.

    E o lado que faltava: nao adianta a constante ser conservadora se ela for
    MAIOR que a moldura -- a linha excedente nao levanta erro, simplesmente nao
    e desenhada, e o `201` diz que deu tudo certo.
    """
    cabem = pycob.linhas_de_instrucao(modelo, tem_pix)
    linhas = [f"{MARCA}{i}" for i in range(cabem)]
    texto = _render(modelo, tem_pix, linhas)
    faltando = [ln for ln in linhas if ln not in texto]
    assert not faltando, (
        f"{modelo} (pix={tem_pix}) aceita {cabem} linhas e a engine desenhou "
        f"{cabem - len(faltando)}: {faltando} sumiram do PDF sem erro")


@pytest.mark.parametrize(("modelo", "tem_pix"), COMBINACOES)
def test_uma_linha_a_mais_e_recusada_antes_de_render(modelo, tem_pix):
    """O excedente vira erro, nunca PDF menor que o pedido."""
    cabem = pycob.linhas_de_instrucao(modelo, tem_pix)
    demais = [f"{MARCA}{i}" for i in range(cabem + 1)]
    with pytest.raises(pycob.DadosInvalidos) as exc:
        _render(modelo, tem_pix, demais)
    assert f"máximo {cabem}" in "; ".join(exc.value.erros)


@pytest.mark.parametrize(("modelo", "tem_pix"), COMBINACOES)
def test_a_largura_aceita_cabe_na_moldura(modelo, tem_pix):
    """A largura aceita e largura que a engine imprime inteira.

    Ha versao da engine que corta com reticencias e versao que deixa o texto
    atravessar a coluna de valores. As duas perdem a clausula sem levantar erro;
    a guarda existe para que o excedente seja recusado antes.

    Nao e um numero so: a moldura do moderno encolhe cerca de um quarto quando
    ha Bolepix, para abrir espaco ao QR.
    """
    cabe = pycob.largura_de_instrucao(modelo, tem_pix)
    texto = _render(modelo, tem_pix, [(PROSA * 3)[:cabe]])
    assert "…" not in texto, (
        f"{modelo} (pix={tem_pix}): linha de {cabe} caracteres foi truncada pela "
        "engine — a largura medida esta alta demais")


def test_teto_e_piso_cercam_a_sonda():
    """A sonda conta o que a engine DESENHA, e desenhar nao e caber.

    Sem o teto, uma engine que imprime a 12a linha por baixo da moldura faria o
    gateway aceitar 12. Sem o piso, uma instalacao sem render devolveria zero e
    o gateway aceitaria qualquer coisa.
    """
    for modelo, tem_pix in COMBINACOES:
        cabem = pycob.linhas_de_instrucao(modelo, tem_pix)
        assert pycob._LINHAS_INSTRUCAO_PISO <= cabem <= pycob._LINHAS_INSTRUCAO_TETO


def test_sem_modelo_vale_o_teto_do_layout_mais_generoso():
    """`validar`/`dados_boleto` nao sabem qual layout o cliente vai pedir.

    Recusar ali pelo modelo mais restrito inventaria um erro que o render nao
    teria: o classico imprime mais linhas que o moderno.
    """
    generoso = max(pycob.linhas_de_instrucao(m, p)
                   for m in ("classico", "moderno") for p in (False, True))
    sem_modelo, _ = pycob._limite_de_linhas(None, False)
    assert sem_modelo == generoso
    pycob.validar(BANCO, {**BASE, "instrucoes": ["ok"] * generoso})
