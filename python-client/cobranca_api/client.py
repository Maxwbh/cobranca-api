"""
Cliente principal para a API Boleto CNAB v1.4.1
"""
import base64
import json
import logging
import tempfile
import os
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from .exceptions import (
    BoletoAPIError,
    BoletoValidationError,
    BoletoConnectionError,
    BoletoTimeoutError
)
from .models import BoletoData, BoletoResponse

logger = logging.getLogger(__name__)


class BoletoClient:
    """
    Cliente Python para a API Boleto CNAB.

    Example:
        >>> client = BoletoClient('http://localhost:8000')
        >>> result = client.generate_boleto_with_data('banco_brasil', dados)
        >>> print(result['nosso_numero_formatado'])
        >>> with open('boleto.pdf', 'wb') as f:
        ...     f.write(base64.b64decode(result['content_base64']))
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        retries: int = 3,
        verify_ssl: bool = True
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        self.session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = urljoin(self.base_url, endpoint)
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('verify', self.verify_ssl)

        try:
            response = self.session.request(method, url, **kwargs)

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', response.text)
                except Exception:
                    error_msg = response.text

                if response.status_code == 400:
                    raise BoletoValidationError(error_msg, response.status_code)
                else:
                    raise BoletoAPIError(error_msg, response.status_code)

            return response

        except requests.exceptions.RetryError as e:
            raise BoletoAPIError(
                f"Servidor indisponível após múltiplas tentativas: {str(e)}",
                status_code=500
            ) from e
        except requests.Timeout as e:
            raise BoletoTimeoutError(f"Timeout após {self.timeout}s") from e
        except requests.ConnectionError as e:
            raise BoletoConnectionError(f"Erro de conexão: {str(e)}") from e

    # ==================== Consulta ====================

    def health_check(self) -> Dict[str, str]:
        """Health check da API."""
        return self._make_request('GET', '/api/health').json()

    def info(self) -> Dict[str, Any]:
        """Versão, bancos suportados e formatos."""
        return self._make_request('GET', '/api/info').json()

    def metadata(self) -> Dict[str, Any]:
        """Metadados da API e gem brcobranca."""
        return self._make_request('GET', '/api/metadata').json()

    def bancos(self) -> List[Dict[str, Any]]:
        """Lista 18 bancos com capacidades (boleto, CNAB, PIX, carteiras)."""
        return self._make_request('GET', '/api/bancos').json()

    # ==================== Boleto ====================

    def validate(self, bank: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida dados do boleto sem gerar PDF."""
        return self._make_request(
            'GET', '/api/boleto/validate',
            params={'bank': bank, 'data': json.dumps(data)}
        ).json()

    def get_boleto_data(self, bank: str, data: Dict[str, Any]) -> BoletoResponse:
        """Obtém dados calculados (nosso_numero, código barras, linha digitável)."""
        response = self._make_request(
            'GET', '/api/boleto/data',
            params={'bank': bank, 'data': json.dumps(data)}
        )
        return BoletoResponse(**response.json())

    def get_nosso_numero(self, bank: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Gera apenas nosso_numero, nosso_numero_formatado e nosso_numero_dv."""
        return self._make_request(
            'GET', '/api/boleto/nosso_numero',
            params={'bank': bank, 'data': json.dumps(data)}
        ).json()

    def generate_boleto(
        self,
        bank: str,
        data: Dict[str, Any],
        file_type: str = 'pdf',
        template: str = 'rghost'
    ) -> bytes:
        """Gera boleto como bytes (PDF/JPG/PNG/TIF). Headers X-Nosso-Numero* disponíveis."""
        response = self._make_request(
            'GET', '/api/boleto',
            params={
                'bank': bank, 'type': file_type,
                'template': template,
                'data': json.dumps(data)
            }
        )
        return response.content

    def generate_boleto_with_data(
        self,
        bank: str,
        data: Dict[str, Any],
        file_type: str = 'pdf',
        template: str = 'rghost'
    ) -> Dict[str, Any]:
        """
        Gera boleto + dados em 1 chamada (include_data=true).

        Retorna dict com nosso_numero, nosso_numero_formatado, nosso_numero_dv,
        codigo_barras, linha_digitavel, content_base64, content_type, filename.

        Example:
            >>> result = client.generate_boleto_with_data('sicoob', dados)
            >>> pdf = base64.b64decode(result['content_base64'])
            >>> nn = result['nosso_numero_formatado']
        """
        response = self._make_request(
            'GET', '/api/boleto',
            params={
                'bank': bank, 'type': file_type,
                'template': template,
                'include_data': 'true',
                'data': json.dumps(data)
            }
        )
        return response.json()

    def generate_multiple_boletos(
        self,
        boletos: List[Dict[str, Any]],
        file_type: str = 'pdf',
        template: str = 'rghost'
    ) -> bytes:
        """Gera múltiplos boletos como bytes."""
        return self._multi_request(boletos, file_type, template, include_data=False)

    def generate_multiple_boletos_with_data(
        self,
        boletos: List[Dict[str, Any]],
        file_type: str = 'pdf',
        template: str = 'rghost'
    ) -> Dict[str, Any]:
        """
        Gera múltiplos boletos + dados em 1 chamada.

        Retorna dict com total, boletos (array de metadados), content_base64.
        """
        return self._multi_request(boletos, file_type, template, include_data=True)

    # ==================== Remessa / Retorno ====================

    def generate_remessa(
        self,
        bank: str,
        cnab_type: str,
        data: Dict[str, Any],
        pix: bool = False
    ) -> bytes:
        """
        Gera arquivo de remessa CNAB.

        Args:
            bank: Código do banco
            cnab_type: 'cnab400' ou 'cnab240'
            data: Dados da remessa (incluindo pagamentos)
            pix: Se True, gera remessa com segmento PIX

        Returns:
            Bytes do arquivo CNAB
        """
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, f)
        f.close()

        try:
            with open(f.name, 'rb') as fp:
                response = self._make_request(
                    'POST',
                    f'/api/remessa?bank={bank}&type={cnab_type}&pix={str(pix).lower()}',
                    files={'data': fp}
                )
            return response.content
        finally:
            os.unlink(f.name)

    def process_retorno(
        self,
        bank: str,
        cnab_type: str,
        file_path: str
    ) -> List[Dict[str, Any]]:
        """
        Processa arquivo de retorno CNAB.

        Returns:
            Lista de pagamentos parseados
        """
        with open(file_path, 'rb') as f:
            response = self._make_request(
                'POST',
                f'/api/retorno?bank={bank}&type={cnab_type}',
                files={'data': f}
            )
        return response.json()

    # ==================== OFX ====================

    def parse_ofx(
        self,
        file_path: str,
        somente_creditos: bool = False
    ) -> Dict[str, Any]:
        """
        Parseia arquivo OFX (extrato bancário).

        Returns:
            Dict com banco, conta, transacoes, resumo
        """
        with open(file_path, 'rb') as f:
            response = self._make_request(
                'POST', '/api/ofx/parse',
                files={'file': f},
                data={'somente_creditos': str(somente_creditos).lower()}
            )
        return response.json()

    # ==================== Internos ====================

    def _multi_request(self, boletos, file_type, template, include_data):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(boletos, f)
        f.close()

        params = f'include_data=true&' if include_data else ''
        try:
            with open(f.name, 'rb') as fp:
                response = self._make_request(
                    'POST',
                    f'/api/boleto/multi?{params}template={template}',
                    data={'type': file_type},
                    files={'data': fp}
                )
            return response.json() if include_data else response.content
        finally:
            os.unlink(f.name)

    def __repr__(self) -> str:
        return f"<BoletoClient(base_url='{self.base_url}')>"
