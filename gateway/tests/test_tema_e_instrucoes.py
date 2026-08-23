# Campos que a documentacao anunciava e o boleto nunca recebia.
#
# Sete campos de tema visual estavam no `BoletoData` com a frase "Suportado pela
# engine pyCobranca", e NENHUM chegava ao PDF: nao sao campos do construtor do
# banco, entao caiam no descarte silencioso de campo desconhecido, e o gateway
# nunca montava o bloco `tema` que o renderizador de fato le. Mesma historia com
# `instrucao1`..`instrucao6`: documentadas, e o boleto saia sem instrucao
# alguma. Nos dois casos, `200` e um PDF identico ao de um payload sem elas.
#
# A assercao aqui e sobre o PAPEL: le-se o texto do PDF gerado. Era o unico
# jeito de o defeito aparecer -- toda verificacao anterior olhava bytes.
from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader

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


def _texto(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


# --------------------------------------------------------------- tema visual
def test_faixa_de_marca_sai_no_papel():
    """Os quatro campos de tema, do payload ate a tinta."""
    texto = _texto(pycob.pdf_boleto(BANCO, {
        **BASE,
        "logo_empresa": "LAGOAREAL",
        "cor_marca": "006B3F",
        "rodape_contato": "financeiro@exemplo.com.br",
        "marca_dagua": "COPIASEMVALORFISCAL",
    }))
    for esperado in ("LAGOAREAL", "financeiro@exemplo.com.br", "COPIASEMVALORFISCAL"):
        assert esperado in texto, f"{esperado!r} nao chegou ao PDF"


def test_selo_de_parcela_sai_no_papel():
    texto = _texto(pycob.pdf_boleto(BANCO, {
        **BASE, "logo_empresa": "LAGOAREAL",
        "parcela_atual": 3, "total_parcelas": 12}))
    assert "Parcela 3/12" in texto


def test_sem_campo_de_tema_o_boleto_nao_ganha_faixa():
    """Nao ligar a faixa por engano em quem nunca pediu tema."""
    assert pycob.tema_do_payload(BASE) is None


def test_cor_sem_cerquilha_e_a_forma_documentada_e_precisa_funcionar():
    """A doc mandava enviar "sem #" e dava `006B3F` de exemplo.

    E justamente a forma com que o reportlab levanta la no fundo do render: com
    o tema ligado sem normalizacao, o exemplo da propria documentacao viraria
    500. As duas formas tem de valer.
    """
    assert pycob.tema_do_payload({"cor_marca": "006B3F"})["cor"] == "#006B3F"
    assert pycob.tema_do_payload({"cor_marca": "#006B3F"})["cor"] == "#006B3F"
    pycob.pdf_boleto(BANCO, {**BASE, "cor_marca": "006B3F"})


def test_cor_invalida_e_recusada_com_nome_do_campo():
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.tema_do_payload({"cor_marca": "verde"})
    assert "cor_marca" in exc.value.erros[0]


def test_logo_empresa_e_texto_e_nao_caminho_de_arquivo():
    """A doc dizia "Path de arquivo (PNG/JPG) acessivel ao servidor".

    A engine desenha o valor como TEXTO na faixa de marca. Ligar o tema sem esta
    checagem faria o boleto sair com "/assets/logo.png" escrito na marca -- e
    ler arquivo do servidor a partir do payload nunca foi o contrato.
    """
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.tema_do_payload({"logo_empresa": "/assets/logo.png"})
    assert "TEXTO da marca" in exc.value.erros[0]


@pytest.mark.parametrize("modelo", ["classico", "carne"])
def test_modelo_que_ignora_tema_recusa_em_vez_de_aceitar_calado(modelo):
    """Medido: o classico e o carne nao desenham o bloco `tema`.

    Aceitar e descartar seria repetir exatamente o defeito que este arquivo
    documenta.
    """
    dados = {**BASE, "logo_empresa": "LAGOAREAL"}
    with pytest.raises(pycob.DadosInvalidos) as exc:
        if modelo == "carne":
            pycob.pdf_multi([{**dados, "bank": BANCO}], template="carne",
                            tolerante=False)
        else:
            pycob.pdf_boleto(BANCO, dados, template=modelo)
    assert "faixa de marca" in "; ".join(exc.value.erros)


def test_fatura_desenha_a_faixa_porque_monta_o_boleto_moderno():
    pdf = pycob.pdf_fatura(BANCO, {**BASE, "logo_empresa": "LAGOAREAL"},
                           {"itens": [{"descricao": "Mensalidade", "valor": "150,00"}]})
    assert "LAGOAREAL" in _texto(pdf)


def test_fonte_ttf_e_recusado_por_nao_ter_consumidor():
    """Estava documentado como "Suportado pela engine" e nao existe suporte.

    Nem aqui nem la: a pyCobranca lista `fonte_ttf` entre os campos que ignora
    na construcao. Aceitar seria a terceira temporada do mesmo enredo.
    """
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.pdf_boleto(BANCO, {**BASE, "fonte_ttf": "/assets/Roboto.ttf"})
    assert "fonte_ttf" in exc.value.erros[0]


# ------------------------------------------------------- instrucoes numeradas
def test_instrucoes_numeradas_chegam_ao_papel():
    """`instrucao1`..`instrucao6` eram documentadas e sumiam."""
    texto = _texto(pycob.pdf_boleto(BANCO, {
        **BASE,
        "instrucao1": "PRIMEIRALINHADAINSTRUCAO",
        "instrucao2": "SEGUNDALINHADAINSTRUCAO",
        "instrucao5": "QUINTALINHADAINSTRUCAO",
    }))
    for esperado in ("PRIMEIRALINHADAINSTRUCAO", "SEGUNDALINHADAINSTRUCAO",
                     "QUINTALINHADAINSTRUCAO"):
        assert esperado in texto, f"{esperado!r} nao chegou ao PDF"


def test_instrucoes_numeradas_mantem_a_ordem_dos_numeros():
    boleto = pycob.construir_boleto(BANCO, {
        **BASE, "instrucao3": "TERCEIRA", "instrucao1": "PRIMEIRA"})
    assert boleto.instrucoes == ["PRIMEIRA", "TERCEIRA"]


def test_as_duas_formas_no_mesmo_payload_sao_recusadas():
    """Uma delas seria descartada em silencio -- de novo."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.construir_boleto(BANCO, {
            **BASE, "instrucoes": ["A"], "instrucao1": "B"})
    assert "`instrucao1`" in exc.value.erros[0]


def test_instrucao_numerada_passa_pela_mesma_guarda_de_tamanho():
    """Nao adianta ligar o campo e deixar o excedente sumir do outro jeito."""
    cabe = pycob.largura_de_instrucao("moderno", False)
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.pdf_boleto(BANCO, {**BASE, "instrucao1": "X" * (cabe + 1)})
    assert "caracteres por linha" in "; ".join(exc.value.erros)


def test_rota_de_render_entrega_o_tema(client):
    r = client.post("/api/render/boleto", json={
        "bank": BANCO, "data": {**BASE, "logo_empresa": "LAGOAREAL"}})
    assert r.status_code == 200, r.text
    assert "LAGOAREAL" in _texto(base64.b64decode(r.json()["pdf_base64"]))
