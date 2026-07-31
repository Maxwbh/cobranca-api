"""
Testes para tipos TypedDict
"""
import sys
import pytest

# Importar tipos
from cobranca_api.types import (
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


class TestBoletoDataDict:
    """Testes para BoletoDataDict"""

    def test_minimal_boleto_data(self):
        """Testa dados mínimos de boleto"""
        data: BoletoDataDict = {
            'agencia': '3073',
            'conta_corrente': '12345678',
            'nosso_numero': '123456789',
            'valor': 150.00,
            'cedente': 'Empresa LTDA',
            'documento_cedente': '12345678000199',
            'sacado': 'Cliente',
            'sacado_documento': '12345678901'
        }

        assert data['agencia'] == '3073'
        assert data['valor'] == 150.00
        assert data['cedente'] == 'Empresa LTDA'

    def test_full_boleto_data(self):
        """Testa dados completos de boleto"""
        data: BoletoDataDict = {
            'agencia': '3073',
            'conta_corrente': '12345678',
            'nosso_numero': '123456789',
            'valor': 150.00,
            'cedente': 'Empresa LTDA',
            'documento_cedente': '12345678000199',
            'sacado': 'Cliente',
            'sacado_documento': '12345678901',
            'convenio': '01234567',
            'carteira': '18',
            'data_vencimento': '2025/12/31',
            'instrucao1': 'Não receber após vencimento'
        }

        assert data['convenio'] == '01234567'
        assert data['carteira'] == '18'
        assert 'instrucao1' in data


class TestBoletoResponseDict:
    """Testes para BoletoResponseDict"""

    def test_minimal_response(self):
        """Testa resposta mínima"""
        response: BoletoResponseDict = {
            'bank': 'banco_brasil',
            'nosso_numero': '12345678-9',
            'codigo_barras': '00191234567890123456789012345678901234567890',
            'valor': 150.00,
            'cedente': 'Empresa',
            'sacado': 'Cliente'
        }

        assert response['bank'] == 'banco_brasil'
        assert len(response['codigo_barras']) == 44

    def test_full_response(self):
        """Testa resposta completa"""
        response: BoletoResponseDict = {
            'bank': 'banco_brasil',
            'nosso_numero': '12345678-9',
            'codigo_barras': '00191234567890123456789012345678901234567890',
            'valor': 150.00,
            'cedente': 'Empresa',
            'sacado': 'Cliente',
            'linha_digitavel': '00191.23456 78901.234567 89012.345678 9 01234567890123',
            'nosso_numero_dv': '9'
        }

        assert 'linha_digitavel' in response
        assert response['nosso_numero_dv'] == '9'


class TestValidationResultDict:
    """Testes para ValidationResultDict"""

    def test_valid_result(self):
        """Testa resultado de validação bem sucedida"""
        result: ValidationResultDict = {
            'valid': True,
            'message': 'Dados válidos'
        }

        assert result['valid'] is True

    def test_invalid_result(self):
        """Testa resultado de validação com erro"""
        result: ValidationResultDict = {
            'valid': False,
            'validation_errors': {
                'nosso_numero': ['não pode ficar em branco']
            }
        }

        assert result['valid'] is False
        assert 'validation_errors' in result


class TestHealthCheckDict:
    """Testes para HealthCheckDict"""

    def test_health_check(self):
        """Testa resposta de health check"""
        health: HealthCheckDict = {
            'status': 'OK'
        }

        assert health['status'] == 'OK'


class TestNossoNumeroDict:
    """Testes para NossoNumeroDict"""

    def test_nosso_numero(self):
        """Testa resposta de nosso número"""
        result: NossoNumeroDict = {
            'nosso_numero': '12345678-9',
            'nosso_numero_dv': '9',
            'codigo_barras': '00191234567890123456789012345678901234567890'
        }

        assert result['nosso_numero'] == '12345678-9'
        assert result['nosso_numero_dv'] == '9'


class TestRemessaRequestDict:
    """Testes para RemessaRequestDict"""

    def test_remessa_request(self):
        """Testa dados de remessa"""
        pagamento: RemessaPagamentoDict = {
            'nosso_numero': '123456789',
            'valor': 150.00,
            'data_vencimento': '2025/12/31',
            'sacado': 'Cliente',
            'sacado_documento': '12345678901'
        }

        remessa: RemessaRequestDict = {
            'bank': 'banco_brasil',
            'type': '240',
            'empresa_mae': 'Empresa LTDA',
            'documento_cedente': '12345678000199',
            'agencia': '3073',
            'conta_corrente': '12345678',
            'pagamentos': [pagamento]
        }

        assert remessa['bank'] == 'banco_brasil'
        assert remessa['type'] == '240'
        assert len(remessa['pagamentos']) == 1


class TestRetornoResponseDict:
    """Testes para RetornoResponseDict"""

    def test_retorno_response(self):
        """Testa resposta de retorno"""
        item: RetornoItemDict = {
            'nosso_numero': '123456789',
            'valor_titulo': 150.00,
            'valor_pago': 150.00,
            'data_credito': '2025/12/31',
            'codigo_ocorrencia': '06',
            'motivo_ocorrencia': 'Liquidação Normal'
        }

        retorno: RetornoResponseDict = {
            'bank': 'banco_brasil',
            'type': '240',
            'total_registros': 1,
            'items': [item]
        }

        assert retorno['bank'] == 'banco_brasil'
        assert len(retorno['items']) == 1
        assert retorno['items'][0]['valor_pago'] == 150.00


class TestTypeImports:
    """Testes de importação dos tipos"""

    def test_import_from_main_module(self):
        """Testa importação do módulo principal"""
        from cobranca_api import (
            BoletoDataDict,
            BoletoResponseDict,
            ValidationResultDict,
            HealthCheckDict,
            NossoNumeroDict
        )

        # Verificar que são tipos válidos
        assert BoletoDataDict is not None
        assert BoletoResponseDict is not None

    def test_types_are_typed_dicts(self):
        """Testa que os tipos são TypedDict"""
        # Verificar que são classes
        assert isinstance(BoletoDataDict, type)
        assert isinstance(BoletoResponseDict, type)

        # Verificar anotações
        assert hasattr(BoletoDataDict, '__annotations__')
        assert 'agencia' in BoletoDataDict.__annotations__
        assert 'valor' in BoletoDataDict.__annotations__
