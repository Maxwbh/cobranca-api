"""
Testes para BoletoClient
"""
import json
import pytest
import responses
from responses import matchers

from cobranca_api import BoletoClient
from cobranca_api.exceptions import (
    BoletoAPIError,
    BoletoValidationError,
    BoletoConnectionError,
    BoletoTimeoutError
)


class TestBoletoClientInit:
    """Testes de inicialização do cliente"""

    def test_init_default_values(self, base_url):
        """Testa valores padrão"""
        client = BoletoClient(base_url)
        assert client.base_url == base_url
        assert client.timeout == 30
        assert client.verify_ssl is True

    def test_init_custom_values(self, base_url):
        """Testa valores customizados"""
        client = BoletoClient(base_url, timeout=60, retries=5, verify_ssl=False)
        assert client.timeout == 60
        assert client.verify_ssl is False

    def test_init_removes_trailing_slash(self):
        """Testa remoção de barra final da URL"""
        client = BoletoClient("http://example.com/")
        assert client.base_url == "http://example.com"

    def test_repr(self, client):
        """Testa representação string"""
        assert "BoletoClient" in repr(client)
        assert "localhost" in repr(client)


class TestHealthCheck:
    """Testes para health check"""

    @responses.activate
    def test_health_check_success(self, client, base_url):
        """Testa health check bem sucedido"""
        responses.add(
            responses.GET,
            f"{base_url}/api/health",
            json={"status": "OK"},
            status=200
        )

        result = client.health_check()
        assert result["status"] == "OK"

    @responses.activate
    def test_health_check_server_error(self, client, base_url):
        """Testa health check com erro do servidor"""
        responses.add(
            responses.GET,
            f"{base_url}/api/health",
            json={"error": "Internal Server Error"},
            status=500
        )

        with pytest.raises(BoletoAPIError) as exc_info:
            client.health_check()
        assert exc_info.value.status_code == 500


class TestValidate:
    """Testes para validação de boleto"""

    @responses.activate
    def test_validate_success(self, client, base_url, valid_boleto_data):
        """Testa validação bem sucedida"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto/validate",
            json={"valid": True, "message": "Dados válidos"},
            status=200
        )

        result = client.validate("banco_brasil", valid_boleto_data)
        assert result["valid"] is True

    @responses.activate
    def test_validate_invalid_data(self, client, base_url, invalid_boleto_data):
        """Testa validação com dados inválidos"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto/validate",
            json={
                "valid": False,
                "validation_errors": {"nosso_numero": ["não pode ficar em branco"]}
            },
            status=400
        )

        with pytest.raises(BoletoValidationError):
            client.validate("banco_brasil", invalid_boleto_data)


class TestGetBoletoData:
    """Testes para obter dados do boleto"""

    @responses.activate
    def test_get_boleto_data_success(self, client, base_url, valid_boleto_data):
        """Testa obtenção de dados bem sucedida"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto/data",
            json={
                "bank": "banco_brasil",
                "nosso_numero": "12345678-9",
                "codigo_barras": "00191234567890123456789012345678901234567890",
                "linha_digitavel": "00191.23456 78901.234567 89012.345678 9 01234567890123",
                "valor": 150.00,
                "cedente": "Empresa Teste LTDA",
                "sacado": "Cliente Teste"
            },
            status=200
        )

        result = client.get_boleto_data("banco_brasil", valid_boleto_data)

        assert result.bank == "banco_brasil"
        assert result.nosso_numero == "12345678-9"
        assert result.codigo_barras is not None
        assert result.linha_digitavel is not None
        assert result.valor == 150.00


class TestGenerateBoleto:
    """Testes para geração de boleto"""

    @responses.activate
    def test_generate_boleto_pdf(self, client, base_url, valid_boleto_data):
        """Testa geração de PDF"""
        pdf_content = b"%PDF-1.4 fake pdf content"
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto",
            body=pdf_content,
            status=200,
            content_type="application/pdf"
        )

        result = client.generate_boleto("banco_brasil", valid_boleto_data, "pdf")

        assert result == pdf_content
        assert result.startswith(b"%PDF")

    @responses.activate
    def test_generate_boleto_invalid_data(self, client, base_url, invalid_boleto_data):
        """Testa geração com dados inválidos"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto",
            json={"error": "Dados inválidos", "validation_errors": {}},
            status=400
        )

        with pytest.raises(BoletoValidationError):
            client.generate_boleto("banco_brasil", invalid_boleto_data)


class TestGetNossoNumero:
    """Testes para obter nosso número"""

    @responses.activate
    def test_get_nosso_numero_success(self, client, base_url, valid_boleto_data):
        """Testa obtenção de nosso número"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto/nosso_numero",
            json={
                "nosso_numero": "12345678-9",
                "nosso_numero_dv": "9",
                "codigo_barras": "00191234567890123456789012345678901234567890"
            },
            status=200
        )

        result = client.get_nosso_numero("banco_brasil", valid_boleto_data)

        assert "nosso_numero" in result
        assert result["nosso_numero"] == "12345678-9"


class TestErrorHandling:
    """Testes para tratamento de erros"""

    @responses.activate
    def test_connection_error(self, base_url):
        """Testa erro de conexão"""
        # Não adiciona resposta para simular conexão recusada
        client = BoletoClient(base_url, timeout=1, retries=0)

        with pytest.raises(BoletoConnectionError):
            client.health_check()

    @responses.activate
    def test_server_error_500(self, client, base_url):
        """Testa erro 500"""
        responses.add(
            responses.GET,
            f"{base_url}/api/health",
            json={"error": "Internal Server Error"},
            status=500
        )

        with pytest.raises(BoletoAPIError) as exc_info:
            client.health_check()

        assert exc_info.value.status_code == 500

    @responses.activate
    def test_validation_error_400(self, client, base_url, invalid_boleto_data):
        """Testa erro 400 de validação"""
        responses.add(
            responses.GET,
            f"{base_url}/api/boleto/validate",
            json={"error": "Dados inválidos"},
            status=400
        )

        with pytest.raises(BoletoValidationError) as exc_info:
            client.validate("banco_brasil", invalid_boleto_data)

        assert exc_info.value.status_code == 400
