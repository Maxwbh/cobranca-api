"""
Cliente Python da Cobranca-API
~~~~~~~~~~~~~~~~~~~~~~~

Cliente Python oficial para a API de geração de Boletos Bancários Brasileiros.

Uso básico:

   >>> from cobranca_api import BoletoClient
   >>> client = BoletoClient('https://api.exemplo.com')
   >>> boleto = client.generate_boleto('banco_brasil', {...})

:copyright: (c) 2025 Maxwell da Silva Oliveira - M&S do Brasil Ltda
:license: MIT, see LICENSE for more details.
"""

__title__ = 'cobranca-api-client'
__version__ = '1.4.1'
__author__ = 'Maxwell da Silva Oliveira'
__author_email__ = 'maxwbh@gmail.com'
__license__ = 'MIT'
__copyright__ = 'Copyright 2025 Maxwell da Silva Oliveira'

from .client import BoletoClient
from .exceptions import (
    BoletoAPIError,
    BoletoValidationError,
    BoletoConnectionError,
    BoletoTimeoutError
)
from .models import BoletoData, BoletoResponse
from .types import (
    BoletoDataDict,
    BoletoResponseDict,
    ValidationResultDict,
    HealthCheckDict,
    NossoNumeroDict,
    RemessaPagamentoDict,
    RemessaRequestDict,
    RetornoItemDict,
    RetornoResponseDict
)

__all__ = [
    # Cliente
    'BoletoClient',
    # Exceções
    'BoletoAPIError',
    'BoletoValidationError',
    'BoletoConnectionError',
    'BoletoTimeoutError',
    # Modelos (dataclass)
    'BoletoData',
    'BoletoResponse',
    # Tipos TypedDict
    'BoletoDataDict',
    'BoletoResponseDict',
    'ValidationResultDict',
    'HealthCheckDict',
    'NossoNumeroDict',
    'RemessaPagamentoDict',
    'RemessaRequestDict',
    'RetornoItemDict',
    'RetornoResponseDict'
]
