# Validação de campos por banco — espelha docs/api/validacao-campos.md, que por
# sua vez espelha a doc 14-validacao-campos da PyCobrança 1.0.1.
#
# O foco é o CONTRATO DE ERRO: a engine 1.0.1 valida na geração e devolve
# `BoletoInvalido.erros` — UMA entrada por campo violado. A API tem de repassar
# essa LISTA (não colapsar em string). Estes testes exercitam pela rota REST.
import json

import pytest

# Payload mínimo VÁLIDO por banco (carteira válida + campos especiais exigidos).
# Levantado empiricamente contra a engine 1.0.1 e conferido com a doc.
VALIDO = {
    "itau": {"agencia": "1234", "conta": "12345", "carteira": "109"},
    "banco_brasil": {"agencia": "1234", "conta": "12345", "convenio": "1234567", "carteira": "18"},
    "bradesco": {"agencia": "1234", "conta": "1234567", "carteira": "09"},
    "caixa": {"convenio": "123456", "carteira": "14"},
    "santander": {"convenio": "1234567", "carteira": "101"},
    "sicoob": {"agencia": "1234", "convenio": "1234567", "carteira": "1"},
    "sicredi": {"agencia": "1234", "conta": "12345", "convenio": "12345",
                "carteira": "1", "byte_idt": "2", "data_documento": "2026-01-01"},
    "banrisul": {"agencia": "1234", "convenio": "1234567", "carteira": "1"},
    "ailos": {"conta": "1234567", "convenio": "123456", "carteira": "01"},
    "unicred": {"agencia": "1234", "conta": "123456789", "carteira": "21", "digito_conta": "0"},
    "citibank": {"agencia": "1234", "convenio": "1234567890", "carteira": "3", "portfolio": "1"},
    "credisis": {"agencia": "1234", "convenio": "123456", "carteira": "18"},
    "banco_brasilia": {"agencia": "123", "conta": "1234567", "carteira": "1", "incremento": "1"},
    "banco_nordeste": {"agencia": "1234", "conta": "1234567", "carteira": "21", "digito_conta": "0"},
    "banestes": {"conta": "1234567890", "carteira": "11", "digito_conta": "0"},
    "banco_c6": {"agencia": "1234", "convenio": "123456789012", "carteira": "10"},
    # `CSB` saiu de `carteiras` na 1.1.1: o campo livre dela montava 27 posições
    # onde cabem 25, então nunca chegou a produzir um boleto válido. Corrigir
    # exige o manual do HSBC, que o banco não publica mais. Sobra a `CNR`.
    "hsbc": {"agencia": "1234", "conta": "1234567", "carteira": "CNR",
             "data_vencimento": "2027-12-31"},
    "safra": {"agencia": "1234", "conta": "12345678", "carteira": "1",
              "digito_agencia": "0", "digito_conta": "0"},
}

CAMPOS_COMUNS = {
    "nosso_numero": "1", "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181", "sacado": "Cliente",
    "sacado_documento": "52998224725", "valor": 150.0,
    "data_vencimento": "2027-12-31",
}

TODOS_OS_BANCOS = sorted(VALIDO)


def _validate(client, bank, **override):
    dados = {**CAMPOS_COMUNS, **VALIDO[bank], **override}
    return client.get("/api/boleto/validate",
                      params={"bank": bank, "data": json.dumps(dados)})


# ---------------------------------------------------------------- válido passa
@pytest.mark.parametrize("bank", TODOS_OS_BANCOS)
def test_payload_minimo_valido_passa(client, bank):
    """O mínimo-válido de cada banco (carteira + especiais certos) é aceito."""
    r = _validate(client, bank)
    assert r.status_code == 200, (bank, r.json())
    assert r.json()["valid"] is True


# ---------------------------------------------------------- carteira (conjunto)
@pytest.mark.parametrize("bank", TODOS_OS_BANCOS)
def test_carteira_invalida_recusada_em_todos_os_bancos(client, bank):
    """Carteira é um conjunto fechado — inválida é recusada e o erro LISTA as
    válidas. Vale para os 18, inclusive HSBC (carteira alfanumérica)."""
    invalida = "ZZ" if bank == "hsbc" else "999"
    r = _validate(client, bank, carteira=invalida)
    assert r.status_code == 400, (bank, r.json())
    erros = r.json()["validation_errors"]
    assert any("carteira" in e.lower() for e in erros), (bank, erros)


# ------------------------------------------------------------ tamanho de campo
def test_agencia_acima_do_maximo_recusada(client):
    """Itaú: agência máx 4 dígitos."""
    erros = _validate(client, "itau", agencia="12345").json()["validation_errors"]
    assert any("agência" in e.lower() and "4" in e for e in erros), erros


def test_conta_acima_do_maximo_recusada(client):
    """Itaú: conta máx 5 dígitos."""
    erros = _validate(client, "itau", conta="123456").json()["validation_errors"]
    assert any("conta" in e.lower() and "5" in e for e in erros), erros


def test_brb_agencia_maximo_3(client):
    """BRB usa agência de até 3 dígitos (não 4)."""
    erros = _validate(client, "banco_brasilia", agencia="1234").json()["validation_errors"]
    assert any("agência" in e.lower() and "3" in e for e in erros), erros


# -------------------------------------------------------------- campo especial
def test_brb_incremento_obrigatorio(client):
    """BRB exige `incremento` (1–3 dígitos)."""
    dados = {**CAMPOS_COMUNS, **VALIDO["banco_brasilia"]}
    dados.pop("incremento")
    r = client.get("/api/boleto/validate",
                   params={"bank": "banco_brasilia", "data": json.dumps(dados)})
    assert r.status_code == 400
    assert any("incremento" in e.lower() for e in r.json()["validation_errors"])


# ------------------------------------------------------- tipo / valor / formato
def test_valor_deve_ser_positivo(client):
    for v in (0, -5):
        erros = _validate(client, "itau", valor=v).json()["validation_errors"]
        assert any("valor" in e.lower() and "positivo" in e.lower() for e in erros), (v, erros)


def test_documento_cedente_e_sacado_validados(client):
    e1 = _validate(client, "itau", documento_cedente="123").json()["validation_errors"]
    assert any("cedente_documento" in e.lower() for e in e1), e1
    e2 = _validate(client, "itau", sacado_documento="111").json()["validation_errors"]
    assert any("sacado_documento" in e.lower() for e in e2), e2


def test_campo_numerico_sem_digito_falha_no_minimo(client):
    """Máscara é descartada; agência só com letras não tem dígito → falha."""
    erros = _validate(client, "itau", agencia="ABCD").json()["validation_errors"]
    assert any("agência" in e.lower() for e in erros), erros


# --------------------------------------------------- o contrato: erros em LISTA
def test_multiplas_violacoes_vem_como_lista_nao_string(client):
    """O ganho da 1.0.1: cada campo violado é uma entrada. Antes o adaptador
    colapsava tudo num único string e a granularidade se perdia."""
    erros = _validate(client, "itau", agencia="12345", conta="123456",
                      carteira="999").json()["validation_errors"]
    assert isinstance(erros, list)
    assert len(erros) >= 3           # carteira + agência + conta, cada um o seu
    assert any("carteira" in e.lower() for e in erros)
    assert any("agência" in e.lower() for e in erros)
    assert any("conta" in e.lower() for e in erros)


# ---------------------------------------------------- CNPJ alfanumérico (2026)
def _cnpj_alfa(base12: str) -> str:
    """Gera o CNPJ alfanumérico completo (DV oficial: valor do char = ord−48)."""
    def _dv(seq, pesos):
        s = sum((ord(c) - 48) * p for c, p in zip(seq, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)
    d1 = _dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = _dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


def test_cnpj_alfanumerico_aceito_e_gera_boleto(client):
    """Formato alfanumérico (vigente 2026). O DV segue o algoritmo oficial."""
    # sanidade: o algoritmo reproduz o CNPJ numérico conhecido
    assert _cnpj_alfa("112223330001") == "11222333000181"
    alfa = _cnpj_alfa("12ABC34501DE")
    r = _validate(client, "itau", documento_cedente=alfa)
    assert r.status_code == 200, r.json()
    assert r.json()["valid"] is True
    # gera o código de barras (44 posições) com o documento alfanumérico
    d = client.get("/api/boleto/data",
                   params={"bank": "itau",
                           "data": json.dumps({**CAMPOS_COMUNS, **VALIDO["itau"],
                                                "documento_cedente": alfa})})
    assert d.status_code == 200, d.json()
    assert len(d.json()["codigo_barras"]) == 44


def test_cnpj_alfanumerico_dv_invalido_recusado(client):
    """A validação é real: DV errado (alfa ou numérico) é recusado."""
    for doc in ("12ABC34501DE99", "11222333000199"):
        erros = _validate(client, "itau", documento_cedente=doc).json()["validation_errors"]
        assert any("cedente_documento" in e.lower() for e in erros), (doc, erros)
