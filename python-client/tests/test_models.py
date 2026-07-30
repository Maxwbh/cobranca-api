"""
Testes para modelos de dados
"""
import pytest
from cobranca_api.models import BoletoData, BoletoResponse


class TestBoletoData:
    """Testes para BoletoData"""

    def test_create_minimal(self):
        """Testa criação com campos mínimos"""
        data = BoletoData(
            agencia="1234",
            conta_corrente="12345678",
            nosso_numero="123",
            valor=100.00,
            cedente="Empresa",
            documento_cedente="12345678000199",
            sacado="Cliente",
            sacado_documento="12345678901"
        )

        assert data.agencia == "1234"
        assert data.valor == 100.00
        assert data.aceite == "N"  # valor padrão

    def test_create_with_optional_fields(self):
        """Testa criação com campos opcionais"""
        data = BoletoData(
            agencia="1234",
            conta_corrente="12345678",
            nosso_numero="123",
            valor=100.00,
            cedente="Empresa",
            documento_cedente="12345678000199",
            sacado="Cliente",
            sacado_documento="12345678901",
            convenio="123456",
            carteira="18",
            data_vencimento="2025/12/31",
            instrucao1="Não receber após vencimento"
        )

        assert data.convenio == "123456"
        assert data.carteira == "18"
        assert data.instrucao1 == "Não receber após vencimento"

    def test_to_dict_removes_none(self):
        """Testa que to_dict remove valores None"""
        data = BoletoData(
            agencia="1234",
            conta_corrente="12345678",
            nosso_numero="123",
            valor=100.00,
            cedente="Empresa",
            documento_cedente="12345678000199",
            sacado="Cliente",
            sacado_documento="12345678901"
        )

        result = data.to_dict()

        # Campos None não devem estar presentes
        assert "convenio" not in result or result.get("convenio") is not None
        assert "agencia" in result
        assert result["agencia"] == "1234"

    def test_to_dict_preserves_values(self):
        """Testa que to_dict preserva valores"""
        data = BoletoData(
            agencia="1234",
            conta_corrente="12345678",
            nosso_numero="123",
            valor=150.50,
            cedente="Empresa LTDA",
            documento_cedente="12345678000199",
            sacado="João Silva",
            sacado_documento="12345678901",
            convenio="654321"
        )

        result = data.to_dict()

        assert result["valor"] == 150.50
        assert result["cedente"] == "Empresa LTDA"
        assert result["convenio"] == "654321"


class TestBoletoResponse:
    """Testes para BoletoResponse"""

    def test_create_minimal(self):
        """Testa criação com campos mínimos"""
        response = BoletoResponse(
            bank="banco_brasil",
            nosso_numero="12345678-9",
            codigo_barras="00191234567890123456789012345678901234567890",
            valor=100.00,
            cedente="Empresa",
            sacado="Cliente"
        )

        assert response.bank == "banco_brasil"
        assert response.nosso_numero == "12345678-9"
        assert len(response.codigo_barras) == 44

    def test_create_with_optional_fields(self):
        """Testa criação com campos opcionais"""
        response = BoletoResponse(
            bank="sicoob",
            nosso_numero="1234567-8",
            codigo_barras="75691234567890123456789012345678901234567890",
            valor=250.00,
            cedente="Empresa Sicoob",
            sacado="Cliente Sicoob",
            linha_digitavel="75691.23456 78901.234567 89012.345678 9 01234567890123",
            carteira="1",
            agencia="4327"
        )

        assert response.linha_digitavel is not None
        assert response.carteira == "1"
        assert response.agencia == "4327"

    def test_str_representation(self):
        """Testa representação string"""
        response = BoletoResponse(
            bank="banco_brasil",
            nosso_numero="12345678-9",
            codigo_barras="00191234567890123456789012345678901234567890",
            valor=150.00,
            cedente="Empresa",
            sacado="Cliente",
            linha_digitavel="00191.23456 78901.234567 89012.345678 9 01234567890123"
        )

        str_repr = str(response)

        assert "BANCO_BRASIL" in str_repr
        assert "12345678-9" in str_repr
        assert "R$ 150.00" in str_repr

    def test_str_without_linha_digitavel(self):
        """Testa representação quando linha_digitavel é None"""
        response = BoletoResponse(
            bank="test_bank",
            nosso_numero="123",
            codigo_barras="12345678901234567890123456789012345678901234",
            valor=100.00,
            cedente="Empresa",
            sacado="Cliente"
        )

        str_repr = str(response)
        assert "N/A" in str_repr
