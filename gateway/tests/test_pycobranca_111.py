# O que a pyCobranca 1.1.1 mudou, medido contra a engine.
#
# Cada prova aqui nasceu de uma medicao, nao da leitura do CHANGELOG: a engine
# ganhou o Inter, separou Bolepix de QR avulso, passou a avisar quando le o
# retorno com layout de reserva e a descrever a ocorrencia por banco. Tres
# dessas mudancas chegavam ate a fronteira e paravam ali.
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from app.core import pycob

FIXTURES = Path(__file__).resolve().parents[2] / "postman" / "fixtures"

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

#: EMV de cobv, no formato que os bancos devolvem ao registrar a cobranca.
EMV_DO_BANCO = (
    "00020101021226870014br.gov.bcb.pix2565qrcode.exemplo.com.br/pix/v2/cobv/"
    "9d36b84f-c70b-478f-b95c-12729bd97542520400005303986540515.005802BR"
    "5913EMPRESA TESTE6008BRASILIA62070503***6304ABCD"
)


# --- Bolepix nao e' QR avulso -------------------------------------------------

def test_qr_montado_da_chave_nao_liquida_o_titulo():
    """A diferenca entre os dois QR e' dinheiro, e a API nao a dizia.

    O BR Code montado a partir de `chave_pix` e' ESTATICO: quem paga credita a
    chave, mas o banco nao sabe que aquele PIX quitou este boleto — o titulo
    fica em aberto, com risco de segunda cobranca ou de protesto de titulo ja
    pago. Bolepix exige QR dinamico, gerado pelo banco no registro.
    """
    d = pycob.dados_boleto("banco_brasil", {**BASE, "chave_pix": "11222333000181"})
    assert d["pix_copia_cola"], "sem copia-e-cola nao ha o que conferir"
    assert d["pix_vinculado"] is False


def test_emv_do_banco_e_bolepix_de_verdade():
    d = pycob.dados_boleto("banco_brasil", {**BASE, "pix_copia_cola": EMV_DO_BANCO})
    assert d["pix_copia_cola"] == EMV_DO_BANCO, "o EMV do banco vai como veio"
    assert d["pix_vinculado"] is True


def test_boleto_sem_pix_nao_afirma_nem_nega():
    """`False` diria 'tem QR e ele nao liquida' — que e' outra coisa."""
    assert pycob.dados_boleto("banco_brasil", BASE)["pix_vinculado"] is None


def test_o_emv_do_banco_tem_precedencia_sobre_a_chave():
    """E' o que fecha o ciclo entre os dois caminhos: registra no `on`, pega o
    copia-e-cola da resposta e renderiza o PDF no `off` com o QR que liquida."""
    d = pycob.dados_boleto("banco_brasil", {
        **BASE, "chave_pix": "11222333000181", "pix_copia_cola": EMV_DO_BANCO})
    assert d["pix_copia_cola"] == EMV_DO_BANCO
    assert d["pix_vinculado"] is True


def test_o_pdf_e_o_json_dizem_a_mesma_coisa():
    """`emitir_boleto` e `dados_boleto` sao caminhos diferentes para o mesmo
    titulo — divergir aqui seria imprimir um QR e reportar outro."""
    for extra in ({}, {"chave_pix": "11222333000181"}, {"pix_copia_cola": EMV_DO_BANCO}):
        _, info = pycob.emitir_boleto("banco_brasil", {**BASE, **extra})
        assert info["pix_vinculado"] == pycob.dados_boleto(
            "banco_brasil", {**BASE, **extra})["pix_vinculado"]


def test_observacao_do_pix_chega_ao_br_code():
    d = pycob.dados_boleto("banco_brasil", {
        **BASE, "chave_pix": "11222333000181", "pix_observacao": "Mensalidade 09/2027"})
    assert "Mensalidade 09/2027" in d["pix_copia_cola"]


def test_txid_vazio_sai_do_nosso_numero_e_nao_como_ausente():
    """Ia `***`, e o credito chegava orfao na conciliacao por OFX."""
    d = pycob.dados_boleto("banco_brasil", {**BASE, "chave_pix": "11222333000181"})
    assert "***" not in d["pix_copia_cola"]
    assert BASE["nosso_numero"] in d["pix_copia_cola"]


# --- retorno CNAB: o aviso e o sentido da ocorrencia ---------------------------

def _com_outro_banco(origem: Path, codigo: str) -> bytes:
    """O mesmo arquivo, com outro codigo de banco no header (posicoes 77-79)."""
    linhas = origem.read_bytes().decode("latin-1").splitlines()
    cabecalho = linhas[0][:76] + codigo + linhas[0][79:]
    return "\r\n".join([cabecalho] + linhas[1:]).encode("latin-1")


def test_layout_de_reserva_aparece_na_resposta(tmp_path):
    """A falha mais perigosa do parsing e' a que produz saida plausivel.

    Sem o mapa do banco, a engine le com um layout generico: o arquivo sai
    inteiro, com campos que podem ter vindo de outras posicoes, e nenhum erro e'
    levantado. Ela avisa; a API engolia o aviso e devolvia 200.
    """
    arq = _com_outro_banco(FIXTURES / "retorno_cnab400_bb.ret", "745")  # Citibank
    itens = pycob.parse_retorno(arq, "cnab400")
    assert itens, "o arquivo continua sendo lido — o aviso nao interrompe"
    assert all(i["layout_generico"] is True for i in itens)


def test_banco_com_mapa_proprio_nao_levanta_a_suspeita():
    itens = pycob.parse_retorno((FIXTURES / "retorno_cnab400_bb.ret").read_bytes(),
                                "cnab400")
    assert all(i["layout_generico"] is False for i in itens)


def test_a_ocorrencia_e_descrita_pelo_banco_do_arquivo():
    """O mesmo codigo significa o oposto em bancos diferentes.

    O `40` e' *baixa por ter sido liquidado* no mapa geral e *baixa de titulo
    protestado* no Safra. Numa conciliacao, um e' titulo pago e o outro e'
    titulo protestado. A engine passou a aceitar o banco em
    `descreve_ocorrencia`; sem repassa-lo, a API lia o sentido errado.
    """
    arq = Path("/home/user/pycobranca/tests/fixtures/retorno_safra_cnab400.ret")
    if not arq.exists():
        pytest.skip("fixture do Safra vem do repositorio da engine")
    por_codigo = {i["codigo_ocorrencia"]: i["motivo_ocorrencia"]
                  for i in pycob.parse_retorno(arq.read_bytes(), "cnab400", bank="safra")}
    assert por_codigo["40"] == "Baixa de título protestado"


def test_retorno_de_outro_banco_e_recusado():
    """`bank` era exigido na rota e NUNCA lido: subir o retorno do banco errado
    devolvia 200 com os campos lidos pelo layout de outro banco."""
    arq = _com_outro_banco(FIXTURES / "retorno_cnab400_bb.ret", "341")  # Itau
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.parse_retorno(arq, "cnab400", bank="banco_brasil")
    assert "itau" in exc.value.erros[0] and "banco_brasil" in exc.value.erros[0]


def test_sem_bank_no_request_o_arquivo_manda():
    """A rota nao exige coerencia que o arquivo ja resolve: sem `bank`, le."""
    itens = pycob.parse_retorno((FIXTURES / "retorno_cnab400_bb.ret").read_bytes(),
                                "cnab400")
    assert itens


# --- encargos: a unidade e' do LAYOUT, nao do gosto de quem manda -------------

CONTA_BB = {"empresa_mae": "E", "documento_cedente": "11222333000181",
            "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
            "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
            "sequencial_remessa": 1}
CONTA_INTER = {"empresa_mae": "E", "documento_cedente": "11222333000181",
               "agencia": "0001", "conta_corrente": "123456", "digito_conta": "7",
               "carteira": "110", "sequencial_remessa": 1}


def _pagamento(nosso_numero: str, **encargos):
    return [{"nosso_numero": nosso_numero, "data_vencimento": "2027-12-31",
             "valor": 1500.0, "sacado": "Joao", "sacado_documento": "52998224725",
             "sacado_endereco": "R1", "sacado_bairro": "C", "sacado_cidade": "SP",
             "sacado_uf": "SP", "sacado_cep": "01000000", **encargos}]


MULTA_EM_VALOR = {"codigo_multa": "1", "valor_multa": 25.0, "data_multa": "2028-01-01"}
DESCONTO_PERCENTUAL = {"cod_desconto": "4", "percentual_desconto": 10.0,
                       "data_desconto": "2027-12-26"}
MORA_MENSAL = {"tipo_mora": "2", "percentual_mora": 1.0}


@pytest.mark.parametrize("encargo", [MULTA_EM_VALOR, DESCONTO_PERCENTUAL, MORA_MENSAL],
                         ids=["multa em valor", "desconto %", "mora mensal %"])
def test_o_inter_expressa_os_tres_encargos_nas_duas_unidades(encargo):
    """O Inter tem os DOIS campos de cada encargo (itens 10/11, 14/15 e 30/31 do
    registro tipo 1) e escolhe pelo codigo. E' o unico layout 400 que tem."""
    remessa = pycob.gerar_remessa(
        "inter", "cnab400", {**CONTA_INTER, "pagamentos": _pagamento("1234567890", **encargo)})
    assert {len(l) for l in remessa.splitlines()} == {400}


@pytest.mark.parametrize("cnab_type,nosso_numero", [("cnab400", "123456789"),
                                                     ("cnab240", "123456789")])
@pytest.mark.parametrize("encargo,campo", [(MULTA_EM_VALOR, "valor_multa"),
                                           (DESCONTO_PERCENTUAL, "percentual_desconto")],
                         ids=["valor_multa", "percentual_desconto"])
def test_encargo_sem_posicao_no_layout_e_recusado(cnab_type, nosso_numero, encargo, campo):
    """`valor_multa` e `percentual_desconto` entraram no `Pagamento` da engine
    1.1.1 e passaram a ser ACEITOS pela assinatura — mas so o Inter os grava.

    Medido A/B em todos os layouts: gerar o arquivo com dois valores diferentes
    do campo e comparar byte a byte. Nos demais o valor entra e some, e o titulo
    vai ao banco sem o encargo que o cliente pediu.
    """
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.gerar_remessa("banco_brasil", cnab_type,
                            {**CONTA_BB, "pagamentos": _pagamento(nosso_numero, **encargo)})
    assert campo in exc.value.erros[0]


def test_a_mora_percentual_continua_valendo_no_240():
    """A guarda nao pode virar recusa geral: no CNAB 240 a mora percentual e' o
    normal, e vale para todos os bancos."""
    remessa = pycob.gerar_remessa(
        "banco_brasil", "cnab240", {**CONTA_BB, "pagamentos": _pagamento("123456789", **MORA_MENSAL)})
    assert remessa.splitlines()


def test_o_erro_diz_quem_grava_o_campo():
    """Recusar sem dizer a alternativa manda o integrador adivinhar."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.gerar_remessa("banco_brasil", "cnab400",
                            {**CONTA_BB, "pagamentos": _pagamento("123456789", **MULTA_EM_VALOR)})
    erro = exc.value.erros[0]
    assert "inter" in erro, erro
    assert "percentual_multa" in erro, erro


# --- o Inter como 19o banco offline -------------------------------------------

def test_o_inter_emite_boleto_pela_engine():
    """Nao existia caminho `off` para o 077 e a recusa era o certo: cair noutro
    banco emitiria boleto registrado no lugar errado."""
    d = pycob.dados_boleto("inter", {
        **BASE, "agencia": "0001", "conta_corrente": "123456", "convenio": "123456",
        "carteira": "110", "nosso_numero": "1234567890"})
    assert len(d["codigo_barras"]) == 44
    assert d["codigo_barras"].startswith("077")


def test_a_carteira_112_do_inter_e_recusada():
    """Na 112 quem numera e' o banco: o nosso numero so existe no retorno, e
    aceitar aqui produziria um titulo com numero que o Inter nao reconhece."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto("inter", {
            **BASE, "agencia": "0001", "conta_corrente": "123456", "convenio": "123456",
            "carteira": "112", "nosso_numero": "1234567890"})
    assert "110" in exc.value.erros[0]
