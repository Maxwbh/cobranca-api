import os
import urllib.parse
import urllib.request
import json

API_URL = 'http://localhost:8000/api/boleto'
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_output'))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Base payloads
BASE_C6 = {
  "cedente": "Empresa C6 LTDA",
  "documento_cedente": "33445566000177",
  "sacado": "Pedro Almeida",
  "sacado_documento": "33344455566",
  "sacado_endereco": "Av. Faria Lima, 1500, Itaim Bibi, Sao Paulo, SP, CEP 04538133",
  "agencia": "0001",
  "conta_corrente": "1234567",
  "digito_conta": "0",
  "carteira": "10",
  "convenio": "100",
  "nosso_numero": "12345678",
  "numero_documento": "INV-2026-001",
  "valor": 2750.00,
  "data_vencimento": "2026/12/31",
  "moeda": "9",
  "especie": "R$",
  "especie_documento": "DM",
  "aceite": "N",
  "local_pagamento": "Pagavel em qualquer banco",
  "instrucao1": "Apos vencimento cobrar multa de 2%",
  "data_documento": "2026/04/09"
}

BASE_SICOOB = {
  "cedente": "Cooperativa Teste",
  "documento_cedente": "98765432000100",
  "sacado": "Maria Santos",
  "sacado_documento": "98765432100",
  "sacado_endereco": "Av. Principal, 50, Bairro, Rio de Janeiro, RJ, CEP 20000000",
  "agencia": "4327",
  "conta_corrente": "417270",
  "carteira": "1",
  "variacao": "01",
  "convenio": "229385",
  "nosso_numero": "7890",
  "numero_documento": "NF-2025-1234",
  "valor": 2500.00,
  "data_vencimento": "2025/12/31",
  "moeda": "9",
  "especie": "R$",
  "especie_documento": "DM",
  "aceite": "N",
  "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
  "instrucao1": "Não receber após 30 dias",
  "data_documento": "2025/11/26"
}

EMV_C6 = "00020101021226840014br.gov.bcb.pix2562payload-de-teste-c6-pix-12345678905204000053039865802BR5921Recebedor Teste C66009Sao Paulo62070503***6304ABCD"
EMV_SICOOB = "00020101021226840014br.gov.bcb.pix2562payload-de-teste-sicoob-pix-12345678905204000053039865802BR5925Recebedor Teste Sicoob6009Sao Paulo62070503***63041234"

def generate_boleto(bank, type_name, index, payload, template='prawn'):
    var_payload = payload.copy()
    var_payload['nosso_numero'] = str(int(payload['nosso_numero']) + index)
    var_payload['numero_documento'] = f"{payload['numero_documento']}-{index}"
    var_payload['valor'] = payload['valor'] + (index * 100.50)
    
    params = {
        'bank': bank,
        'type': 'pdf',
        'template': template,
        'data': json.dumps(var_payload)
    }
    
    query = urllib.parse.urlencode(params)
    url = f"{API_URL}?{query}"
    
    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                filename = f"{bank}_{type_name}_{index}.pdf"
                filepath = os.path.join(OUTPUT_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(response.read())
                print(f"[OK] Gerado: {filename} (R$ {var_payload['valor']:.2f})")
            else:
                print(f"[ERR] Falha ao gerar {bank} {type_name} {index}: {response.status}")
    except Exception as e:
        print(f"[ERR] Erro ao gerar {bank} {type_name} {index}: {e}")

print(f"Iniciando geracao de boletos de teste em {OUTPUT_DIR}...")

# 3 padrao
for i in range(1, 4):
    generate_boleto('banco_c6', 'padrao', i, BASE_C6, 'prawn')
    generate_boleto('sicoob', 'padrao', i, BASE_SICOOB, 'prawn')

# 3 pix
for i in range(1, 4):
    c6_pix = BASE_C6.copy()
    c6_pix.update({'emv': EMV_C6, 'pix_label': 'Pague com Pix C6'})
    sicoob_pix = BASE_SICOOB.copy()
    sicoob_pix.update({'emv': EMV_SICOOB, 'pix_label': 'Pague com Pix Sicoob'})
    generate_boleto('banco_c6', 'pix', i, c6_pix, 'prawn')
    generate_boleto('sicoob', 'pix', i, sicoob_pix, 'prawn')

# 3 carne
for i in range(1, 4):
    generate_boleto('banco_c6', 'carne', i, BASE_C6, 'carne')
    generate_boleto('sicoob', 'carne', i, BASE_SICOOB, 'carne')

print(f"Pronto! Todos os boletos de teste foram salvos em {OUTPUT_DIR}.")
