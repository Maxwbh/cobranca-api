"""
Testes para exceções customizadas
"""
import pytest
from cobranca_api.exceptions import (
    BoletoAPIError,
    BoletoValidationError,
    BoletoConnectionError,
    BoletoTimeoutError
)


class TestBoletoAPIError:
    """Testes para BoletoAPIError"""

    def test_create_with_message(self):
        """Testa criação com mensagem"""
        error = BoletoAPIError("Erro genérico")
        assert str(error) == "Erro genérico"
        assert error.message == "Erro genérico"
        assert error.status_code is None

    def test_create_with_status_code(self):
        """Testa criação com status code"""
        error = BoletoAPIError("Erro do servidor", 500)
        assert "[500]" in str(error)
        assert error.status_code == 500

    def test_is_exception(self):
        """Testa que é uma Exception válida"""
        error = BoletoAPIError("Test")
        assert isinstance(error, Exception)


class TestBoletoValidationError:
    """Testes para BoletoValidationError"""

    def test_inherits_from_api_error(self):
        """Testa herança de BoletoAPIError"""
        error = BoletoValidationError("Dados inválidos", 400)
        assert isinstance(error, BoletoAPIError)
        assert error.status_code == 400

    def test_can_catch_as_api_error(self):
        """Testa que pode ser capturada como BoletoAPIError"""
        with pytest.raises(BoletoAPIError):
            raise BoletoValidationError("Test", 400)


class TestBoletoConnectionError:
    """Testes para BoletoConnectionError"""

    def test_inherits_from_api_error(self):
        """Testa herança de BoletoAPIError"""
        error = BoletoConnectionError("Conexão recusada")
        assert isinstance(error, BoletoAPIError)

    def test_message_format(self):
        """Testa formato da mensagem"""
        error = BoletoConnectionError("Connection refused")
        assert "Connection refused" in str(error)


class TestBoletoTimeoutError:
    """Testes para BoletoTimeoutError"""

    def test_inherits_from_api_error(self):
        """Testa herança de BoletoAPIError"""
        error = BoletoTimeoutError("Timeout após 30s")
        assert isinstance(error, BoletoAPIError)

    def test_message_format(self):
        """Testa formato da mensagem"""
        error = BoletoTimeoutError("Timeout após 30s")
        assert "30s" in str(error)
