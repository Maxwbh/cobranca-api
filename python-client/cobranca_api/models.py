"""
Modelos de dados para o cliente Boleto CNAB
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any


@dataclass
class BoletoData:
    """
    Dados para geração de boleto.

    Exemplo:
        >>> data = BoletoData(
        ...     agencia='3073',
        ...     conta_corrente='12345678',
        ...     nosso_numero='123',
        ...     valor=1500.00,
        ...     cedente='Empresa LTDA',
        ...     documento_cedente='12345678000100',
        ...     sacado='João Silva',
        ...     sacado_documento='12345678900'
        ... )
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
    convenio: Optional[str] = None
    carteira: Optional[str] = None
    numero_documento: Optional[str] = None
    documento_numero: Optional[str] = None
    data_vencimento: Optional[str] = None
    data_documento: Optional[str] = None
    sacado_endereco: Optional[str] = None
    cedente_endereco: Optional[str] = None
    moeda: str = '9'
    especie: str = 'R$'
    especie_documento: str = 'DM'
    aceite: str = 'N'
    local_pagamento: str = 'Pagavel em qualquer banco ate o vencimento'
    instrucao1: Optional[str] = None
    instrucao2: Optional[str] = None
    instrucao3: Optional[str] = None
    instrucao4: Optional[str] = None
    instrucao5: Optional[str] = None
    instrucao6: Optional[str] = None
    instrucao7: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário, omitindo valores None"""
        return {
            k: v for k, v in self.__dict__.items()
            if v is not None
        }


@dataclass
class BoletoResponse:
    """
    Resposta da API com dados do boleto.

    Attributes:
        bank: Código do banco
        nosso_numero: Nosso número formatado
        codigo_barras: Código de barras completo
        linha_digitavel: Linha digitável (pode ser None em alguns bancos)
        valor: Valor do boleto
        cedente: Nome do cedente
        sacado: Nome do sacado
        # ... outros campos
    """
    bank: str
    nosso_numero: str
    codigo_barras: str
    valor: float
    cedente: str
    sacado: str

    # Campos opcionais
    linha_digitavel: Optional[str] = None
    nosso_numero_dv: Optional[str] = None
    agencia_conta_boleto: Optional[str] = None
    codigo_barras_segunda_parte: Optional[str] = None
    carteira: Optional[str] = None
    numero_documento: Optional[str] = None
    valor_documento: Optional[float] = None
    data_vencimento: Optional[str] = None
    data_documento: Optional[str] = None
    data_processamento: Optional[str] = None
    documento_cedente: Optional[str] = None
    sacado_documento: Optional[str] = None
    agencia: Optional[str] = None
    conta_corrente: Optional[str] = None
    convenio: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"Boleto {self.bank.upper()}\n"
            f"  Nosso Número: {self.nosso_numero}\n"
            f"  Código de Barras: {self.codigo_barras}\n"
            f"  Linha Digitável: {self.linha_digitavel or 'N/A'}\n"
            f"  Valor: R$ {self.valor:.2f}"
        )
