"""
Fixtures compartilhadas para testes
"""
import pytest
from cobranca_api import BoletoClient


@pytest.fixture
def base_url():
    """URL base para testes"""
    return "http://localhost:8000"


@pytest.fixture
def client(base_url):
    """Cliente configurado para testes"""
    return BoletoClient(base_url, timeout=5, retries=1)


@pytest.fixture
def valid_boleto_data():
    """Dados válidos de boleto do Banco do Brasil"""
    return {
        "agencia": "3073",
        "conta_corrente": "12345678",
        "convenio": "01234567",
        "carteira": "18",
        "nosso_numero": "12345678",
        "numero_documento": "DOC-001",
        "cedente": "Empresa Teste LTDA",
        "documento_cedente": "12345678000199",
        "sacado": "Cliente Teste",
        "sacado_documento": "12345678901",
        "valor": 150.00,
        "data_vencimento": "2025/12/31",
        "aceite": "N",
        "especie_documento": "DM"
    }


@pytest.fixture
def valid_sicoob_data():
    """Dados válidos de boleto do Sicoob"""
    return {
        "agencia": "4327",
        "conta_corrente": "12345678",
        "convenio": "123456",
        "carteira": "1",
        "nosso_numero": "1234567",
        "numero_documento": "DOC-002",
        "cedente": "Empresa Sicoob LTDA",
        "documento_cedente": "12345678000199",
        "sacado": "Cliente Sicoob",
        "sacado_documento": "12345678901",
        "valor": 250.00,
        "data_vencimento": "2025/12/31",
        "aceite": "N",
        "especie_documento": "DM"
    }


@pytest.fixture
def invalid_boleto_data():
    """Dados inválidos de boleto (sem nosso_numero)"""
    return {
        "agencia": "3073",
        "conta_corrente": "12345678",
        "cedente": "Empresa Teste",
        "documento_cedente": "12345678000199",
        "sacado": "Cliente",
        "sacado_documento": "12345678901",
        "valor": 100.00
        # Faltando nosso_numero
    }
