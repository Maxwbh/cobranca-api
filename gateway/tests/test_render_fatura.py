# Fatura: corpo livre (itens/blocos) no topo + boleto abaixo, num só PDF.
#
# O endpoint é PASSTHROUGH para o engine pyCobrança (`render_fatura_pdf`): o
# gateway não soma nem calcula — só repassa `data` (boleto) + `itens`/`fatura`.
# Exige a engine instalada (Python >= 3.12).
import base64

DADOS_BB = {
    "valor": 379.80,
    "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Joao da Silva",
    "sacado_documento": "52998224725",
    "agencia": "3073",
    "conta_corrente": "12345678",
    "convenio": "1234567",
    "carteira": "18",
    "nosso_numero": "123",
    "data_vencimento": "2027-12-30",
}


def test_render_fatura_nivel1_itens_gera_pdf(client):
    body = {"bank": "banco_brasil", "data": DADOS_BB,
            "itens": [{"descricao": "Mensalidade", "quantidade": 2, "valor_unitario": 199.90},
                      {"descricao": "Desconto fidelidade", "quantidade": 1, "valor": -20.00}]}
    r = client.post("/api/render/fatura", json=body)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["linha_digitavel"] and corpo["codigo_barras"]
    assert base64.b64decode(corpo["pdf_base64"])[:4] == b"%PDF"


def test_render_fatura_nivel2_blocos_gera_pdf(client):
    body = {"bank": "banco_brasil", "data": DADOS_BB,
            "fatura": {"titulo": "FATURA DE CONSUMO",
                       "blocos": [{"tipo": "campos", "itens": [["Período", "01/08 a 31/08"]]},
                                  {"tipo": "separador"},
                                  {"tipo": "total", "rotulo": "Total da fatura", "valor": 379.80}]}}
    r = client.post("/api/render/fatura", json=body)
    assert r.status_code == 200, r.text
    assert base64.b64decode(r.json()["pdf_base64"])[:4] == b"%PDF"


def test_render_fatura_sem_corpo_e_so_o_boleto(client):
    # Sem itens nem fatura: o engine devolve o boleto sozinho (passthrough).
    r = client.post("/api/render/fatura", json={"bank": "banco_brasil", "data": DADOS_BB})
    assert r.status_code == 200, r.text
    assert base64.b64decode(r.json()["pdf_base64"])[:4] == b"%PDF"


def test_render_fatura_boleto_invalido_retorna_400(client):
    r = client.post("/api/render/fatura", json={
        "bank": "banco_brasil", "data": {"cedente": "X"},  # faltam campos do boleto
        "itens": [{"descricao": "A", "valor_unitario": 10}]})
    assert r.status_code == 400
    assert "validation_errors" in r.json()


def test_render_fatura_nivel3_desenhar_via_rest_e_recusado(client):
    # O que a API não consegue fazer, ela recusa — não repassa ao engine.
    # `desenhar` é um callback Python; por JSON só chegaria um valor inútil.
    r = client.post("/api/render/fatura", json={
        "bank": "banco_brasil", "data": DADOS_BB,
        "fatura": {"desenhar": "qualquer coisa"}})
    assert r.status_code == 400
    assert "desenhar" in r.json()["error"].lower()


def test_render_fatura_nivel3_desenhar_funciona_na_engine():
    # Documenta a fronteira: o nível 3 EXISTE na engine (in-process), só não
    # é expressável via REST. Aqui passa um callable de verdade ao `pdf_fatura`.
    from app.core import pycob

    chamado = {}

    def desenhar(tela, info):
        chamado["ok"] = True
        tela.avanca(4)

    pdf = pycob.pdf_fatura("banco_brasil", DADOS_BB, {"fatura": {"desenhar": desenhar}})
    assert pdf[:4] == b"%PDF"
    assert chamado.get("ok"), "o callback do nível 3 deveria ter sido chamado"
