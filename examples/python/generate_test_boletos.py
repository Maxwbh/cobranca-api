import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import json

# Mesma variável dos outros scripts: `API=https://meu-host python este.py`.
# Antes só o generate_boleto.py a lia, e o README mandava usá-la nos três.
API = os.environ.get('API', 'http://localhost:8000').rstrip('/')
API_URL = f'{API}/api/boleto'
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_output'))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Base payloads
BASE_C6 = {
  "cedente": "Empresa C6 LTDA",
  "documento_cedente": "33445566000186",
  "sacado": "Pedro Almeida",
  "sacado_documento": "33344455508",
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
  "documento_cedente": "98765432000198",
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
  "data_vencimento": "2027/12/31",
  "moeda": "9",
  "especie": "R$",
  "especie_documento": "DM",
  "aceite": "N",
  "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
  "instrucao1": "Não receber após 30 dias",
  "data_documento": "2026/11/26"
}

# Bolepix: quem desenha o QR é a CHAVE, não um payload pronto. A engine monta
# o EMV a partir de `chave_pix` (+ `tipo_chave_pix`, e `txid` se você quiser
# rastrear a transação) e desenha o QR no PDF.
#
# Este script mandava `emv` e `pix_label`, herdados da era Ruby: a engine nunca
# leu nenhum dos dois, então os seis boletos "pix" saíam IDÊNTICOS aos padrão —
# 200, sem QR e sem aviso. Hoje esses campos respondem 400 apontando para cá.
PIX_C6 = {"chave_pix": "33445566000186", "tipo_chave_pix": "cnpj", "txid": "C6TESTE001"}
PIX_SICOOB = {"chave_pix": "98765432000198", "tipo_chave_pix": "cnpj", "txid": "SICOOBTESTE1"}

FALHAS = []


def generate_boleto(bank, type_name, index, payload, template='moderno'):
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
                FALHAS.append(f"{bank} {type_name} {index}: HTTP {response.status}")
                print(f"[ERR] Falha ao gerar {bank} {type_name} {index}: {response.status}")
    except urllib.error.HTTPError as e:
        # O corpo do 400 traz `validation_errors` dizendo QUAL campo recusou —
        # engolir isso obriga quem roda o exemplo a adivinhar.
        detalhe = e.read().decode(errors='replace')[:300]
        FALHAS.append(f"{bank} {type_name} {index}: HTTP {e.code} {detalhe}")
        print(f"[ERR] {bank} {type_name} {index}: HTTP {e.code} — {detalhe}")
    except Exception as e:
        FALHAS.append(f"{bank} {type_name} {index}: {e}")
        print(f"[ERR] Erro ao gerar {bank} {type_name} {index}: {e}")

print(f"Iniciando geracao de boletos de teste em {OUTPUT_DIR}...")

# 3 padrao
for i in range(1, 4):
    generate_boleto('banco_c6', 'padrao', i, BASE_C6, 'moderno')
    generate_boleto('sicoob', 'padrao', i, BASE_SICOOB, 'moderno')

# 3 pix
for i in range(1, 4):
    c6_pix = BASE_C6.copy()
    c6_pix.update(PIX_C6)
    sicoob_pix = BASE_SICOOB.copy()
    sicoob_pix.update(PIX_SICOOB)
    generate_boleto('banco_c6', 'pix', i, c6_pix, 'moderno')
    generate_boleto('sicoob', 'pix', i, sicoob_pix, 'moderno')

# Carne NAO e template de boleto: e o endpoint POST /api/render/carne, que
# recebe a lista de parcelas e devolve 3 vias por folha A4.

# O script dizia "Pronto! Todos os boletos foram salvos" e saía com 0 mesmo
# quando os 12 falhavam — quem rodasse em CI veria verde sem nenhum PDF.
if FALHAS:
    print(f"\nFALHOU: {len(FALHAS)} de 12 boletos não foram gerados.")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)

# 200 não prova QR. O defeito que estes seis boletos esconderam por meses foi
# exatamente este: status 200, arquivo gravado, e o PDF "pix" byte a byte do
# mesmo tamanho do padrão. Conferir o STATUS não pegaria; conferir o ARQUIVO
# pega — o QR ocupa uns 4 KB.
for banco in ('banco_c6', 'sicoob'):
    for i in range(1, 4):
        padrao = os.path.getsize(os.path.join(OUTPUT_DIR, f"{banco}_padrao_{i}.pdf"))
        pix = os.path.getsize(os.path.join(OUTPUT_DIR, f"{banco}_pix_{i}.pdf"))
        if pix <= padrao:
            print(f"\nFALHOU: {banco}_pix_{i}.pdf ({pix} B) não é maior que o padrão"
                  f" ({padrao} B) — o QR Pix não foi desenhado.")
            sys.exit(1)

print(f"Pronto! Os 12 boletos de teste foram salvos em {OUTPUT_DIR}.")
print("Os 6 com Pix trazem o QR — conferido pelo tamanho do arquivo.")
