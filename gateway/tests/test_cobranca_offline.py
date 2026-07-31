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
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "registrado"
    assert len(d["codigo_barras"]) == 44
    assert d["pdf_base64"].startswith("JVBER")


def test_cobranca_offline_dados_invalidos_vira_erro(client, cobranca_payload):
    body = {"tenant_id": "empresa1", "provider": "pycobranca",
            "account_config": {"bank": "banco_brasil"},
            "cobranca": cobranca_payload}
    r = client.post("/cobranca", json=body)
    assert r.status_code == 200
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
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "registrado"
