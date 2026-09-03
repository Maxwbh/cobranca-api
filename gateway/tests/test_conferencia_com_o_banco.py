# O número do banco confere com o cálculo, ou não sai boleto.
#
# Os dois caminhos passaram a se sobrepor. Registrar no `on` e renderizar o PDF
# no `off` é o ciclo que dá o QR que liquida (`pix_copia_cola`), e nele o papel
# sai de um cálculo NOSSO enquanto o título registrado é do BANCO. Divergir ali
# imprime um boleto que não corresponde ao título: papel correto em bytes,
# pagamento que não concilia — e o erro só aparece semanas depois, quando
# ninguém mais liga uma coisa à outra.
#
# Não é hipótese remota. No **Inter** o caminho `on` nunca manda nosso número —
# quem numera é o banco —, então renderizar com o próprio número produz OUTRO
# título. Sicoob sempre manda o nosso; C6 manda quando informado. Três formas
# diferentes, uma conferência só.
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import pycob

EVIDENCIA = Path(__file__).resolve().parents[2] / "docs" / "homologacao" / \
    "evidencia-sandbox-inter.json"

INTER = {
    "valor": 150.0,
    "cedente": "Empresa Exemplo LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Maria de Souza",
    "sacado_documento": "52998224725",
    "agencia": "0001",
    "conta_corrente": "123456",
    "convenio": "123456",
    "carteira": "110",
    "data_vencimento": "2027-09-10",
}
#: Nosso número que o Inter atribuiu ao registrar, no sandbox (caso `B_02`).
NUMERADO_PELO_BANCO = "2143876889"


@pytest.fixture
def do_banco() -> dict:
    """O título como o banco o registrou — a referência da conferência."""
    return pycob.dados_boleto("inter", {**INTER, "nosso_numero": NUMERADO_PELO_BANCO})


# --- o caso que motivou tudo ---------------------------------------------------

def test_renderizar_com_outro_numero_e_recusado(do_banco):
    """O cenário concreto do ciclo `on`→`off` no Inter.

    Quem registra online recebe um nosso número DO BANCO. Renderizar offline com
    o número que ele mesmo escolheu imprime um título diferente do registrado —
    e antes disto saía `200`, com PDF perfeito.
    """
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto("inter", {
            **INTER, "nosso_numero": "1234567890",
            "codigo_barras": do_banco["codigo_barras"]})
    erro = exc.value.erros[0]
    assert "não corresponderia ao título registrado" in erro
    assert "nossoNumero" in erro, "o erro tem de dizer de onde tirar o número certo"


def test_com_o_numero_do_banco_passa(do_banco):
    """A conferência não pode virar pedágio: dados certos, boleto sai."""
    d = pycob.dados_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO,
        "codigo_barras": do_banco["codigo_barras"],
        "linha_digitavel": do_banco["linha_digitavel"]})
    assert d["codigo_barras"] == do_banco["codigo_barras"]


def test_o_emv_do_banco_e_a_conferencia_convivem(do_banco):
    """É a combinação do ciclo inteiro: o QR que liquida MAIS a garantia de que
    o papel é do título certo. Uma coisa sem a outra entrega meia solução."""
    emv = ("00020101021226870014br.gov.bcb.pix2565qrcode.exemplo/pix/v2/cobv/"
           "9d36b84f520400005303986540515.005802BR5913EMPRESA TESTE6008BRASILIA"
           "62070503***6304ABCD")
    _, info = pycob.emitir_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO,
        "codigo_barras": do_banco["codigo_barras"], "pix_copia_cola": emv})
    assert info["pix_vinculado"] is True
    assert info["codigo_barras"] == do_banco["codigo_barras"]


# --- forma do valor ------------------------------------------------------------

def test_a_linha_formatada_e_aceita(do_banco):
    """A linha digitável circula com pontos e espaços — é assim que ela aparece
    na resposta do banco e no papel. Exigir a pontuação exata recusaria por
    espaço, que não é divergência de número."""
    assert " " in do_banco["linha_digitavel"], "a fixture precisa vir formatada"
    pycob.dados_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO,
        "linha_digitavel": do_banco["linha_digitavel"]})


def test_a_linha_sem_formatacao_tambem(do_banco):
    crua = "".join(c for c in do_banco["linha_digitavel"] if c.isdigit())
    pycob.dados_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO, "linha_digitavel": crua})


@pytest.mark.parametrize("vazio", ["", None])
def test_campo_vazio_continua_sendo_ausencia(vazio, do_banco):
    """`""` é "não mandei", não "confira contra vazio"."""
    pycob.dados_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO, "codigo_barras": vazio})


# --- os dois campos, e os dois caminhos ---------------------------------------

@pytest.mark.parametrize("campo", ["codigo_barras", "linha_digitavel"])
def test_os_dois_campos_conferem(campo, do_banco):
    errado = "9" * len("".join(c for c in do_banco[campo] if c.isdigit()))
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto("inter", {
            **INTER, "nosso_numero": NUMERADO_PELO_BANCO, campo: errado})
    assert f"`{campo}`" in exc.value.erros[0]


def test_o_pdf_tambem_confere(do_banco):
    """`emitir_boleto` é outro caminho para o mesmo título. Conferir só no JSON
    deixaria passar exatamente o que interessa: o PAPEL divergente."""
    with pytest.raises(pycob.DadosInvalidos):
        pycob.emitir_boleto("inter", {
            **INTER, "nosso_numero": "1234567890",
            "codigo_barras": do_banco["codigo_barras"]})


def test_a_rota_http_responde_400(client, do_banco):
    r = client.get("/api/boleto/data", params={"bank": "inter", "data": json.dumps({
        **INTER, "nosso_numero": "1234567890",
        "codigo_barras": do_banco["codigo_barras"]})})
    assert r.status_code == 400, r.text
    assert any("título registrado" in e for e in r.json()["validation_errors"])


def test_a_rota_de_render_tambem(client, do_banco):
    r = client.post("/api/render/boleto", json={"bank": "inter", "data": {
        **INTER, "nosso_numero": "1234567890",
        "codigo_barras": do_banco["codigo_barras"]}})
    assert r.status_code == 400, r.text


# --- o campo é conferência, não entrada ---------------------------------------

def test_o_numero_do_banco_nao_vira_o_do_boleto(do_banco):
    """Imprimir o número do banco por cima de um cálculo divergente esconderia
    dados de conta errados. O desenho continua saindo do cálculo — e é por isso
    que a divergência é 400, e não substituição silenciosa.
    """
    sem = pycob.dados_boleto("inter", {**INTER, "nosso_numero": NUMERADO_PELO_BANCO})
    com = pycob.dados_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO,
        "codigo_barras": do_banco["codigo_barras"]})
    assert sem == com, "a conferência não pode mudar o resultado"


def test_o_campo_nao_chega_a_engine():
    """A engine não conhece estes nomes: `contracts.boleto_de_api` os recusaria.
    Eles são da fronteira, e é aqui que param."""
    assert "codigo_barras" not in pycob.campos_aceitos("inter") - pycob._CAMPOS_DO_GATEWAY
    boleto = pycob.construir_boleto("inter", {
        **INTER, "nosso_numero": NUMERADO_PELO_BANCO, "codigo_barras": "0" * 44})
    assert boleto.codigo_barras.startswith("077"), "o cálculo é da engine, não do payload"


# --- vale para todos os bancos, não só o Inter --------------------------------

@pytest.mark.parametrize("banco,extra", [
    ("banco_brasil", {"agencia": "3073", "conta_corrente": "12345678",
                      "convenio": "1234567", "carteira": "18", "nosso_numero": "123"}),
    ("sicoob", {"agencia": "3069", "conta_corrente": "12345", "convenio": "1234567",
                "variacao": "01", "carteira": "1", "nosso_numero": "1234567"}),
])
def test_a_conferencia_nao_e_do_inter(banco, extra):
    """O Inter é o caso que revelou, não o escopo: qualquer banco que registre
    fora e desenhe aqui corre o mesmo risco."""
    comum = {k: v for k, v in INTER.items()
             if k not in ("agencia", "conta_corrente", "convenio", "carteira")}
    certo = pycob.dados_boleto(banco, {**comum, **extra})
    pycob.dados_boleto(banco, {**comum, **extra,
                               "codigo_barras": certo["codigo_barras"]})
    with pytest.raises(pycob.DadosInvalidos):
        pycob.dados_boleto(banco, {**comum, **extra, "codigo_barras": "9" * 44})


def test_o_inter_online_nao_manda_nosso_numero():
    """A premissa da história, presa contra o código do provider.

    Se um dia o `registrar` do Inter passar a mandar `nossoNumero`, a orientação
    do erro ("use o que o banco devolveu") vira conselho errado.
    """
    import inspect

    from app.providers.inter import InterProvider
    fonte = inspect.getsource(InterProvider.registrar)
    assert "nossoNumero" not in fonte
    assert "seuNumero" in fonte


def test_o_nosso_numero_do_sandbox_e_o_que_o_banco_atribuiu():
    """A fixture não é número inventado: veio do sandbox do Inter.

    O laço é apertado de propósito — casa com a evidência DESTA execução, não
    com "algum número do banco". Regravar a evidência sem trazer o número junto
    deixaria a fixture órfã: o comentário seguiria dizendo "veio do banco" e não
    haveria mais onde conferir. Roteiro reexecutado ⇒ atualize as duas pontas.
    """
    if not EVIDENCIA.exists():
        pytest.skip("evidência de homologação ausente")
    casos = json.loads(EVIDENCIA.read_text(encoding="utf-8"))["resultados"]
    b02 = next(c for c in casos if c["caso"] == "B_02")
    assert b02["response_body"]["raw"]["boleto"]["nossoNumero"] == NUMERADO_PELO_BANCO
