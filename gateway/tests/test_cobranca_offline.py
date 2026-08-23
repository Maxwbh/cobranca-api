# Caminho canônico POST /cobranca com provider offline (pyCobranca in-process).
def test_cobranca_offline_registra_com_pycobranca(client, cobranca_payload):
    body = {
        "tenant_id": "empresa1",
        "provider": "pycobranca",
        "account_config": {"bank": "banco_brasil", "agencia": "3073",
                            "conta_corrente": "12345678", "convenio": "1234567",
                            "carteira": "18", "cedente": "Empresa Teste LTDA",
                            "documento_cedente": "11222333000181"},
        "cobranca": {**cobranca_payload, "pagador": {"nome": "Joao da Silva",
                                                       "documento": "52998224725"}},
    }
    r = client.post("/cobranca", json=body)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "registrado"
    assert len(d["codigo_barras"]) == 44
    assert d["pdf_base64"].startswith("JVBER")


def test_cobranca_offline_dados_invalidos_vira_erro(client, cobranca_payload):
    body = {"tenant_id": "empresa1", "provider": "pycobranca",
            "account_config": {"bank": "banco_brasil"},
            "cobranca": cobranca_payload}
    r = client.post("/cobranca", json=body)
    assert r.status_code == 201
    assert r.json()["status"] == "erro"


def test_provider_antigo_brcobranca_e_rejeitado(client, cobranca_payload):
    """A v2 nao carrega o vocabulario da v1: `brcobranca` nao existe mais e tem
    de ser recusado na validacao, nao silenciosamente aceito."""
    corpo = {"tenant_id": "empresa1", "provider": "brcobranca",
             "account_config": {"bank": "banco_brasil"},
             "cobranca": cobranca_payload}
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 422, r.text
    assert "pycobranca" in r.text  # o erro lista os valores validos


def test_provider_omitido_cai_no_offline(client, cobranca_payload):
    """Contrato v1.x: sem `provider`, roteia para o caminho offline."""
    corpo = {"tenant_id": "empresa1",
             "account_config": {"bank": "banco_brasil", "agencia": "3073",
                                 "conta_corrente": "12345678", "convenio": "1234567",
                                 "carteira": "18", "cedente": "Empresa Teste LTDA",
                                 "documento_cedente": "11222333000181"},
             "cobranca": {**cobranca_payload,
                          "pagador": {"nome": "Joao da Silva", "documento": "52998224725"}}}
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "registrado"


# --- endereco do sacado -----------------------------------------------------------

def _payload_offline(endereco):
    import datetime

    from app.providers.offline_engine import _to_engine_payload
    from app.schemas import Cobranca, Pagador

    c = Cobranca(valor="10.00", vencimento=datetime.date(2026, 12, 31), seu_numero="1",
                 pagador=Pagador(nome="Teste", documento="12345678909", endereco=endereco))
    return _to_engine_payload(c, {"bank": "341"})


def test_offline_carrega_o_endereco_inteiro_do_sacado():
    """O endereco vai inteiro para a engine -- numa linha, que e o que o
    boleto tem.

    Bairro, cidade, UF e CEP chegaram a ser enviados como campos proprios
    (`sacado_bairro`, `sacado_cidade`...) e o construtor do titulo NAO tem
    esses campos: descartava os quatro, um por um, em silencio. Aquelas
    posicoes existem no CNAB, nao no boleto. O papel saia com rua e numero e
    mais nada."""
    d = _payload_offline({"logradouro": "Rua Presidente Kennedy", "numero": "126A",
                          "bairro": "Canaa", "cidade": "Sete Lagoas", "uf": "MG",
                          "cep": "35701206"})
    assert d["sacado_endereco"] == (
        "Rua Presidente Kennedy, 126A, Canaa, Sete Lagoas, MG, CEP 35701206")
    assert not [c for c in d if c.startswith("sacado_") and c != "sacado_endereco"
                and c != "sacado_documento"], "campo que o titulo nao tem"


def test_offline_aceita_o_endereco_em_ingles():
    """O schema aceita as duas grafias; quem consome nao deveria adivinhar qual."""
    d = _payload_offline({"street": "Av. Teste", "number": 100, "neighborhood": "Centro",
                          "city": "Sao Paulo", "state": "SP", "zip_code": "01000000"})
    assert d["sacado_endereco"] == "Av. Teste, 100, Centro, Sao Paulo, SP, CEP 01000000"


def test_endereco_do_sacado_chega_ao_papel():
    """A assercao que faltava: os testes olhavam o payload, e era o CONSTRUTOR
    que descartava. Payload certo com boleto errado passava."""
    import base64
    import io

    from pypdf import PdfReader

    from app.core import pycob
    d = _payload_offline({"logradouro": "Rua Presidente Kennedy", "numero": "126A",
                          "bairro": "Canaa", "cidade": "Sete Lagoas", "uf": "MG",
                          "cep": "35701206"})
    d |= {"cedente": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
          "agencia": "3073", "conta_corrente": "12345678", "convenio": "1234567",
          "carteira": "18", "nosso_numero": "123"}
    pdf, _info = pycob.emitir_boleto("banco_brasil", d)
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    achatado = texto.replace("\n", " ")
    for pedaco in ("Canaa", "Sete Lagoas", "MG", "35701206"):
        assert pedaco in achatado, f"{pedaco!r} nao chegou ao boleto"
    assert base64.b64encode(pdf[:4]).decode()  # PDF de verdade


def test_offline_nao_converte_numero_para_inteiro():
    """A conversao "126A" -> 126 e' exigencia do /v1/bank_slips do C6 e mora no
    provider que a sofre. Aqui `endereco_sacado` e' texto livre: converter
    quebraria o endereco sem nenhum banco pedindo."""
    assert _payload_offline({"logradouro": "Rua X", "numero": "S/N"})["sacado_endereco"] \
        == "Rua X, S/N"


def test_offline_sem_endereco_nao_inventa_campo():
    d = _payload_offline({})
    assert not [k for k in d if k.startswith("sacado_") and k != "sacado_documento"]
