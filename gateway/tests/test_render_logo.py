# Logo do banco no boleto — padrão, não opção.
#
# A engine empacota os logos por código FEBRABAN, mas a capacidade é **opt-in**:
# quem renderiza precisa preencher `boleto.logo`. O gateway não preenchia, e o
# boleto saía com a sigla em texto no lugar da marca — justo o campo pelo qual
# o pagador reconhece o documento contra o boleto do internet banking.
import io

import pytest
from pypdf import PdfReader

from app.core import pycob

BASE = {"valor": 150.0, "data_vencimento": "2026-12-31", "sacado": "Joao da Silva",
        "sacado_documento": "52998224725", "nosso_numero": "123",
        "cedente": "M&S DO BRASIL LTDA", "documento_cedente": "05230380000174",
        "agencia": "3073", "conta_corrente": "12345", "convenio": "1234567"}

# O Citibank (745) não tem PNG empacotado na engine — cai na sigla, como antes.
SEM_LOGO = {"citibank"}


def _imagens(pdf: bytes) -> int:
    return sum(len(p.images) for p in PdfReader(io.BytesIO(pdf)).pages)


def test_boleto_sai_com_a_marca_do_banco():
    pdf = pycob.pdf_boleto("itau", {**BASE, "carteira": "109"})
    assert _imagens(pdf) >= 1, "o cabeçalho do modelo moderno tem de trazer o logo"


def test_todos_os_bancos_com_logo_empacotado_recebem_o_seu():
    """Vale para os 18 — o logo entra em `construir_boleto`, por onde passam
    boleto avulso, lote, carnê e fatura. Sem massa de render por banco, que tem
    regra própria de convênio e carteira."""
    faltando = []
    for slug in pycob.bancos_suportados():
        boleto = pycob.construir_boleto(slug, BASE)
        tem = boleto.logo is not None
        if tem == (slug in SEM_LOGO):
            faltando.append((slug, boleto.codigo, tem))
    assert not faltando, f"logo divergente do esperado: {faltando}"


def test_banco_sem_logo_nao_herda_o_de_outro():
    """Cair no logo errado é pior que não ter logo: o boleto passaria a
    identificar uma instituição que não é a emissora."""
    boleto = pycob.construir_boleto("citibank", BASE)
    assert boleto.logo is None


def test_logo_do_chamador_manda():
    """Quem envia a própria imagem continua no comando — o default preenche o
    que veio vazio, não sobrescreve escolha de quem chamou."""
    proprio = b"\x89PNG\r\n\x1a\n-imagem-do-chamador"
    boleto = pycob.construir_boleto("itau", {**BASE, "logo": proprio})
    assert boleto.logo == proprio


@pytest.mark.parametrize("rota,params", [
    ("/api/boleto", {"bank": "itau", "type": "pdf"}),
])
def test_rota_offline_entrega_pdf_com_logo(client, rota, params):
    import json
    r = client.get(rota, params={**params, "data": json.dumps({**BASE, "carteira": "109"})})
    assert r.status_code == 200, r.text
    assert _imagens(r.content) >= 1


def test_render_boleto_default_e_moderno_com_logo(client):
    r = client.post("/api/render/boleto",
                    json={"bank": "itau", "data": {**BASE, "carteira": "109"}})
    assert r.status_code == 200, r.text
    import base64
    assert _imagens(base64.b64decode(r.json()["pdf_base64"])) >= 1


def test_lote_e_carne_tambem_levam_a_marca():
    """O lote e o carnê renderizam pelo mesmo caminho de construção — se o logo
    dependesse da rota, sairia boleto com marca e carnê sem."""
    itens = [{"bank": "itau", **BASE, "carteira": "109", "seu_numero": f"P{i}",
              "nosso_numero": str(120 + i)} for i in range(2)]
    lote, _ = pycob.pdf_multi(itens)
    carne, _ = pycob.pdf_multi(itens, template="carne")
    assert _imagens(lote) >= 2, "um logo por boleto"
    assert _imagens(carne) >= 1
