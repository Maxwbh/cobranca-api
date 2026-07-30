"""
Tipos TypedDict para tipagem estática do cliente Boleto CNAB.

Este módulo fornece tipos TypedDict para melhorar a experiência de
desenvolvimento com autocompletar e verificação de tipos estáticos.

Compatível com Python 3.8+ usando typing_extensions.
"""
from typing import List, Optional, Union
import sys

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:
    from typing_extensions import NotRequired, TypedDict


# =============================================================================
# Tipos para Boleto
# =============================================================================

class BoletoDataDict(TypedDict, total=False):
    """
    Dados para geração de boleto bancário.

    Campos obrigatórios:
        agencia: Número da agência (sem dígito)
        conta_corrente: Número da conta corrente
        nosso_numero: Nosso número do boleto
        valor: Valor do boleto em reais
        cedente: Nome do cedente (beneficiário)
        documento_cedente: CNPJ/CPF do cedente
        sacado: Nome do sacado (pagador)
        sacado_documento: CNPJ/CPF do sacado

    Campos opcionais:
        convenio: Número do convênio
        carteira: Código da carteira
        data_vencimento: Data de vencimento (formato: YYYY/MM/DD)
        instrucao1-7: Instruções do boleto

    Example:
        >>> data: BoletoDataDict = {
        ...     'agencia': '3073',
        ...     'conta_corrente': '12345678',
        ...     'nosso_numero': '123456789',
        ...     'valor': 150.00,
        ...     'cedente': 'Empresa LTDA',
        ...     'documento_cedente': '12345678000199',
        ...     'sacado': 'Cliente',
        ...     'sacado_documento': '12345678901'
        ... }
    """
    # Campos obrigatórios
    agencia: str
    conta_corrente: str
    nosso_numero: str
    valor: float
    cedente: str
    documento_cedente: str
    sacado: str
    sacado_documento: str

    # Campos opcionais
    convenio: NotRequired[str]
    carteira: NotRequired[str]
    numero_documento: NotRequired[str]
    documento_numero: NotRequired[str]
    data_vencimento: NotRequired[str]
    data_documento: NotRequired[str]
    sacado_endereco: NotRequired[str]
    cedente_endereco: NotRequired[str]
    moeda: NotRequired[str]
    especie: NotRequired[str]
    especie_documento: NotRequired[str]
    aceite: NotRequired[str]
    local_pagamento: NotRequired[str]
    instrucao1: NotRequired[str]
    instrucao2: NotRequired[str]
    instrucao3: NotRequired[str]
    instrucao4: NotRequired[str]
    instrucao5: NotRequired[str]
    instrucao6: NotRequired[str]
    instrucao7: NotRequired[str]


class BoletoResponseDict(TypedDict, total=False):
    """
    Resposta da API com dados calculados do boleto.

    Campos sempre presentes:
        bank: Código do banco
        nosso_numero: Nosso número formatado
        codigo_barras: Código de barras (44 dígitos)
        valor: Valor do boleto
        cedente: Nome do cedente
        sacado: Nome do sacado

    Campos opcionais (dependem do banco):
        linha_digitavel: Linha digitável formatada
        nosso_numero_dv: Dígito verificador do nosso número
        agencia_conta_boleto: Agência/conta formatados para boleto
    """
    # Campos principais
    bank: str
    nosso_numero: str
    codigo_barras: str
    valor: float
    cedente: str
    sacado: str

    # Campos opcionais
    linha_digitavel: NotRequired[str]
    nosso_numero_dv: NotRequired[str]
    agencia_conta_boleto: NotRequired[str]
    codigo_barras_segunda_parte: NotRequired[str]
    carteira: NotRequired[str]
    numero_documento: NotRequired[str]
    valor_documento: NotRequired[float]
    data_vencimento: NotRequired[str]
    data_documento: NotRequired[str]
    data_processamento: NotRequired[str]
    documento_cedente: NotRequired[str]
    sacado_documento: NotRequired[str]
    agencia: NotRequired[str]
    conta_corrente: NotRequired[str]
    convenio: NotRequired[str]


class ValidationResultDict(TypedDict, total=False):
    """Resultado da validação de boleto."""
    valid: bool
    message: NotRequired[str]
    validation_errors: NotRequired[dict]


class HealthCheckDict(TypedDict):
    """Resultado do health check da API."""
    status: str


class NossoNumeroDict(TypedDict, total=False):
    """Resultado da geração do nosso número."""
    nosso_numero: str
    nosso_numero_dv: NotRequired[str]
    codigo_barras: NotRequired[str]
    linha_digitavel: NotRequired[str]


# =============================================================================
# Tipos para Remessa CNAB
# =============================================================================

class RemessaPagamentoDict(TypedDict, total=False):
    """
    Dados de um pagamento na remessa CNAB.

    Similar a BoletoDataDict mas com campos específicos para remessa.
    """
    # Identificação
    nosso_numero: str
    numero_documento: NotRequired[str]

    # Valores
    valor: float
    valor_iof: NotRequired[float]
    valor_abatimento: NotRequired[float]
    valor_desconto: NotRequired[float]
    valor_mora: NotRequired[float]
    valor_multa: NotRequired[float]

    # Datas
    data_vencimento: str
    data_documento: NotRequired[str]
    data_desconto: NotRequired[str]

    # Sacado
    sacado: str
    sacado_documento: str
    sacado_endereco: NotRequired[str]
    sacado_cidade: NotRequired[str]
    sacado_uf: NotRequired[str]
    sacado_cep: NotRequired[str]

    # Instruções
    instrucao1: NotRequired[str]
    instrucao2: NotRequired[str]
    codigo_protesto: NotRequired[str]
    dias_protesto: NotRequired[int]


class RemessaRequestDict(TypedDict, total=False):
    """
    Dados para geração de arquivo de remessa CNAB.

    Example:
        >>> remessa: RemessaRequestDict = {
        ...     'bank': 'banco_brasil',
        ...     'type': '240',
        ...     'empresa_mae': 'Empresa LTDA',
        ...     'agencia': '3073',
        ...     'conta_corrente': '12345678',
        ...     'pagamentos': [...]
        ... }
    """
    # Configuração
    bank: str
    type: str  # '240' ou '400'

    # Dados da empresa
    empresa_mae: str
    documento_cedente: str
    agencia: str
    conta_corrente: str
    digito_conta: NotRequired[str]

    # Opcionais
    convenio: NotRequired[str]
    carteira: NotRequired[str]
    sequencial_remessa: NotRequired[int]

    # Pagamentos
    pagamentos: List[RemessaPagamentoDict]


# =============================================================================
# Tipos para Retorno CNAB
# =============================================================================

class RetornoItemDict(TypedDict, total=False):
    """Item de retorno CNAB processado."""
    # Identificação
    nosso_numero: str
    numero_documento: NotRequired[str]

    # Valores
    valor_titulo: NotRequired[float]
    valor_pago: NotRequired[float]
    valor_tarifa: NotRequired[float]
    valor_juros: NotRequired[float]
    valor_desconto: NotRequired[float]

    # Datas
    data_ocorrencia: NotRequired[str]
    data_credito: NotRequired[str]
    data_vencimento: NotRequired[str]

    # Status
    codigo_ocorrencia: NotRequired[str]
    motivo_ocorrencia: NotRequired[str]


class RetornoResponseDict(TypedDict, total=False):
    """Resposta do processamento de retorno CNAB."""
    bank: str
    type: str
    data_arquivo: NotRequired[str]
    total_registros: NotRequired[int]
    items: List[RetornoItemDict]


# =============================================================================
# Tipos Auxiliares
# =============================================================================

# Bancos suportados
BankCode = str
"""
Código do banco suportado. Valores comuns:
- 'banco_brasil'
- 'caixa'
- 'itau'
- 'bradesco'
- 'santander'
- 'sicoob'
- 'sicredi'
- 'unicred'
- 'banrisul'
- 'ailos'
"""

# Tipos de arquivo
FileType = str
"""
Tipo de arquivo para geração de boleto:
- 'pdf': Arquivo PDF (padrão)
- 'jpg': Imagem JPEG
- 'png': Imagem PNG
- 'tif': Imagem TIFF
"""

# Tipos de CNAB
CnabType = str
"""
Tipo de arquivo CNAB:
- '240': CNAB 240 posições
- '400': CNAB 400 posições
"""
