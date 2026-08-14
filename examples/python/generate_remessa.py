import os
import sys
import urllib.request
import urllib.error
import json

REMESSA_URL = 'http://localhost:8000/api/remessa'
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_output'))
os.makedirs(OUTPUT_DIR, exist_ok=True)

FALHAS = []

# Formato padrão de pagamento esperado pela API (via FieldMapper)
PAGAMENTO_C6 = {
    "nosso_numero": "12345678",
    "data_vencimento": "2026/12/31",
    "valor": 1500.00,
    "nome_sacado": "Joao da Silva",
    "documento_sacado": "12345678909",
    "endereco_sacado": "Rua Teste, 100",
    "bairro_sacado": "Centro",
    "cep_sacado": "01000000",
    "cidade_sacado": "Sao Paulo",
    "uf_sacado": "SP"
}

PAGAMENTO_SICOOB = {
    "nosso_numero": "7890",
    "data_vencimento": "2026/12/31",
    "valor": 2500.00,
    "nome_sacado": "Maria Santos",
    "documento_sacado": "98765432100",
    "endereco_sacado": "Av. Principal, 50",
    "bairro_sacado": "Centro",
    "cep_sacado": "20000000",
    "cidade_sacado": "Rio de Janeiro",
    "uf_sacado": "RJ"
}

# Banco C6 — CNAB 400 (único tipo suportado)
# codigo_beneficiario: código do cedente fornecido pelo C6 (10 dígitos)
DATA_C6 = {
    "empresa_mae": "Empresa C6 LTDA",
    "documento_cedente": "33445566000186",
    "agencia": "0001",
    "conta_corrente": "1234567",
    "digito_conta": "0",
    "carteira": "10",
    "codigo_beneficiario": "0012345678",
    "pagamentos": [PAGAMENTO_C6]
}

# Sicoob — CNAB 240 (único tipo suportado)
DATA_SICOOB = {
    "empresa_mae": "Cooperativa Teste",
    "documento_cedente": "98765432000198",
    "agencia": "4327",
    "conta_corrente": "417270",
    "convenio": "229385",
    "carteira": "1",
    "pagamentos": [PAGAMENTO_SICOOB]
}

def generate_remessa(name, bank, cnab_type, data):
    """Gera arquivo de remessa via POST /api/remessa com upload de arquivo JSON."""
    import tempfile, io

    # Grava dados em arquivo temporário
    tmp_path = os.path.join(OUTPUT_DIR, f"_tmp_{name}.json")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    url = f"{REMESSA_URL}?bank={bank}&type={cnab_type}"
    
    # Monta multipart/form-data manualmente
    boundary = "------------------------abcdef1234567890"
    with open(tmp_path, 'rb') as f:
        file_content = f.read()
    
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="data"; filename="{name}.json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode('utf-8') + file_content + f"\r\n--{boundary}--\r\n".encode('utf-8')

    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode('utf-8')
            filename = f"remessa_{name}_{cnab_type}.rem"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] Gerada: {filename} ({len(content)} bytes)")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        FALHAS.append(f"{name} {cnab_type}: HTTP {e.code} — {err_body[:200]}")
        print(f"[ERR] {name} {cnab_type}: HTTP {e.code} — {err_body}")
    finally:
        os.remove(tmp_path)

print(f"Gerando arquivos de remessa em {OUTPUT_DIR}...")
generate_remessa("c6",    "banco_c6", "cnab400", DATA_C6)
generate_remessa("sicoob","sicoob",   "cnab240", DATA_SICOOB)
# Sem isto o script sai 0 mesmo quando nenhuma remessa foi gerada — em CI, um
# verde que não significa nada.
if FALHAS:
    print(f"\nFALHOU: {len(FALHAS)} remessa(s) não geradas.")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)

print("Concluído!")
