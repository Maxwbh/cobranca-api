"""O menor exemplo possível: uma cobrança pelos dois eixos.

`provider` diz o CAMINHO — `on` (API do banco) ou `off` (engine pyCobrança) — e
`banco` diz a INSTITUIÇÃO. Este script roda o caminho `off`, que não exige
credencial nem convênio no banco, e mostra o que muda para ir ao `on`.

    python generate_boleto.py            # http://localhost:8000
    API=https://meu-host python generate_boleto.py

Antes: `docker compose up --build` (ou `docker run -p 8000:8000
ghcr.io/maxwbh/cobranca-api:latest`).

Este arquivo já foi um `test_run()` que fazia `docker build` — não rodava como
script (a função nunca era chamada), buildava do diretório errado e mandava um
payload que a API recusava com 400. Exemplo que não roda ensina errado.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API", "http://localhost:8000").rstrip("/")

COBRANCA = {
    "tenant_id": "empresa_demo",
    # `off` = a engine pyCobrança, no próprio processo. Sem rede, sem convênio.
    # Para registrar NO BANCO: "provider": "on" — e aí valem credencial
    # (POST /credenciais) e a flag <BANCO>_REGISTERED_READY no servidor.
    # `GET /bancos` responde o que ESTA instalação faz com cada banco.
    "provider": "off",
    "banco": "itau",
    "account_config": {
        "agencia": "3073",
        "conta_corrente": "12345",
        "carteira": "109",
        "convenio": "1234567",
        "cedente": "M&S DO BRASIL LTDA",
        "documento_cedente": "05230380000174",
    },
    "cobranca": {
        "valor": "150.00",
        "vencimento": "2027-12-31",
        "nosso_numero": "123",
        "seu_numero": "PED-0001",
        "pagador": {"nome": "Joao da Silva", "documento": "52998224725"},
    },
}


def post(caminho: str, corpo: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{caminho}", data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # A API responde 422 dizendo PARA ONDE IR (por exemplo, quais bancos
        # têm o caminho pedido). Esconder o corpo aqui apagaria a resposta útil.
        sys.exit(f"HTTP {e.code} em {caminho}: {e.read().decode(errors='replace')[:400]}")
    except urllib.error.URLError as e:
        sys.exit(f"não consegui falar com {API} ({e.reason}). A API está no ar?")


registro = post("/cobranca", COBRANCA)
if registro.get("status") == "erro":
    sys.exit(f"a API recusou os dados: {registro.get('raw')}")

print(f"status          : {registro['status']}")
print(f"linha digitável : {registro['linha_digitavel']}")
print(f"código de barras: {registro['codigo_barras']}")

# O PDF: no caminho `off` quem desenha é a engine. No `on`, C6 e Inter devolvem
# o PDF na própria API; o Itaú não devolve — e aí `GET /cobranca/{id}/pdf`
# responde 422 apontando para cá, mandando conferir a linha digitável calculada
# contra a que o banco registrou. O código de barras é determinístico:
# renderizar com outro nosso número gera um boleto que ninguém concilia.
render = post("/api/render/boleto", {"bank": "itau", "data": {
    **COBRANCA["account_config"],
    "valor": float(COBRANCA["cobranca"]["valor"]),
    "data_vencimento": COBRANCA["cobranca"]["vencimento"],
    "nosso_numero": COBRANCA["cobranca"]["nosso_numero"],
    "sacado": COBRANCA["cobranca"]["pagador"]["nome"],
    "sacado_documento": COBRANCA["cobranca"]["pagador"]["documento"],
}})

if render["linha_digitavel"] != registro["linha_digitavel"]:
    sys.exit("DIVERGE: o PDF não corresponde à cobrança registrada — não entregue ao pagador")

destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_output")
os.makedirs(destino, exist_ok=True)
arquivo = os.path.abspath(os.path.join(destino, "boleto.pdf"))
with open(arquivo, "wb") as f:
    f.write(base64.b64decode(render["pdf_base64"]))
print(f"PDF (com o logo do banco): {arquivo}")
