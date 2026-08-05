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
    """So o logradouro seguia para a engine: numero, bairro, cidade, UF e CEP
    eram descartados em silencio, apesar de o CNAB ter posicao para todos.
    Boleto com rua e sem numero e' endereco incompleto, e saia assim mesmo."""
    d = _payload_offline({"logradouro": "Rua Presidente Kennedy", "numero": "126A",
                          "bairro": "Canaa", "cidade": "Sete Lagoas", "uf": "MG",
                          "cep": "35701206"})
    assert d["sacado_endereco"] == "Rua Presidente Kennedy, 126A"
    assert d["sacado_bairro"] == "Canaa"
    assert d["sacado_cidade"] == "Sete Lagoas"
    assert d["sacado_uf"] == "MG"
    assert d["sacado_cep"] == "35701206"


def test_offline_aceita_o_endereco_em_ingles():
    """O schema aceita as duas grafias; quem consome nao deveria adivinhar qual."""
    d = _payload_offline({"street": "Av. Teste", "number": 100, "neighborhood": "Centro",
                          "city": "Sao Paulo", "state": "SP", "zip_code": "01000000"})
    assert d["sacado_endereco"] == "Av. Teste, 100"
    assert d["sacado_bairro"] == "Centro"


def test_offline_nao_converte_numero_para_inteiro():
    """A conversao "126A" -> 126 e' exigencia do /v1/bank_slips do C6 e mora no
    provider que a sofre. Aqui `endereco_sacado` e' texto livre: converter
    quebraria o endereco sem nenhum banco pedindo."""
    assert _payload_offline({"logradouro": "Rua X", "numero": "S/N"})["sacado_endereco"] \
        == "Rua X, S/N"


def test_offline_sem_endereco_nao_inventa_campo():
    d = _payload_offline({})
    assert not [k for k in d if k.startswith("sacado_") and k != "sacado_documento"]
