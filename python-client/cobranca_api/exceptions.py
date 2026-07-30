"""
Exceções personalizadas para o cliente Boleto CNAB
"""


class BoletoAPIError(Exception):
    """Erro genérico da API"""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self):
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class BoletoValidationError(BoletoAPIError):
    """Erro de validação dos dados do boleto"""
    pass


class BoletoConnectionError(BoletoAPIError):
    """Erro de conexão com a API"""
    pass


class BoletoTimeoutError(BoletoAPIError):
    """Timeout na requisição"""
    pass
