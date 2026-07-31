#!/usr/bin/env python3
"""
Exemplo básico de uso do cliente Python para geração de boletos.

Este exemplo demonstra:
- Conexão com a API
- Validação de dados
- Obtenção de dados do boleto
- Geração de PDF
"""

from cobranca_api import BoletoClient, BoletoValidationError

def main():
    # 1. Conectar à API
    # Para desenvolvimento local
    client = BoletoClient('http://localhost:8000')

    # Para produção (Render)
    # client = BoletoClient('https://sua-api.onrender.com')

    # 2. Verificar se a API está funcionando
    try:
        status = client.health_check()
        print(f"✅ API Status: {status['status']}")
    except Exception as e:
        print(f"❌ API não disponível: {e}")
        return

    # 3. Dados do boleto (Banco do Brasil)
    dados_boleto = {
        "cedente": "Empresa Exemplo LTDA",
        "documento_cedente": "12345678000100",
        "sacado": "João da Silva",
        "sacado_documento": "12345678900",
        "sacado_endereco": "Rua Exemplo, 100, Centro, São Paulo, SP, CEP 01000-000",
        "agencia": "3073",
        "conta_corrente": "12345678",
        "convenio": "01234567",  # OBRIGATÓRIO para Banco do Brasil
        "carteira": "18",
        "nosso_numero": "123",
        "numero_documento": "NF-2025-001",
        "valor": 150.00,
        "data_vencimento": "2025/12/31",
        "data_documento": "2025/11/27",
        "especie_documento": "DM",
        "aceite": "N",
        "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
        "instrucao1": "Nao receber apos o vencimento"
    }

    # 4. Validar dados antes de gerar
    print("\n🔍 Validando dados do boleto...")
    try:
        resultado = client.validate('banco_brasil', dados_boleto)
        if resultado['valid']:
            print("✅ Dados válidos!")
        else:
            print(f"❌ Dados inválidos: {resultado['errors']}")
            return
    except BoletoValidationError as e:
        print(f"❌ Erro de validação: {e}")
        return

    # 5. Obter dados completos do boleto
    print("\n📊 Obtendo dados do boleto...")
    try:
        boleto = client.get_boleto_data('banco_brasil', dados_boleto)
        print(f"✅ Nosso Número: {boleto.nosso_numero}")
        print(f"✅ Código de Barras: {boleto.codigo_barras}")
        print(f"✅ Linha Digitável: {boleto.linha_digitavel}")
    except Exception as e:
        print(f"❌ Erro ao obter dados: {e}")
        return

    # 6. Gerar PDF do boleto
    print("\n📄 Gerando PDF do boleto...")
    try:
        pdf_bytes = client.generate_boleto('banco_brasil', dados_boleto, file_type='pdf')

        # Salvar arquivo
        filename = 'boleto_exemplo.pdf'
        with open(filename, 'wb') as f:
            f.write(pdf_bytes)

        print(f"✅ PDF salvo em: {filename}")
        print(f"   Tamanho: {len(pdf_bytes) / 1024:.2f} KB")
    except Exception as e:
        print(f"❌ Erro ao gerar PDF: {e}")
        return

    print("\n🎉 Boleto gerado com sucesso!")

if __name__ == "__main__":
    main()
