# O que acompanha o PDF na resposta.
#
# O PDF sozinho nao fecha a integracao: quem recebe precisa dos numeros para
# registrar a cobranca e conciliar o pagamento depois. Duas coisas faltavam.
#
# 1) `pix_copia_cola`. O campo existe em `CobrancaOut` e e preenchido por C6,
#    Inter e Sicoob no caminho ON. No caminho OFF voltava `null` -- com o QR
#    Bolepix impresso no PDF. A engine tem o EMV pronto em `contexto_render()`;
#    ninguem o lia. Pagador de celular nao escaneia a propria tela: sem o texto
#    ao lado do QR, o Bolepix nao e pagavel na maior parte dos casos reais.
#
# 2) Os dados por parcela do carne. `pdf_multi` ja calculava linha digitavel e
#    nosso numero de cada parcela, e `/api/render/carne` devolvia so o PDF.
from __future__ import annotations

import base64
import io
import json

import pytest
from pypdf import PdfReader

from app.core import pycob

BANCO = "banco_brasil"
BASE = {
    "valor": 150.0,
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
COM_PIX = {**BASE, "chave_pix": "11222333000181"}

CONTA = {"bank": BANCO, "agencia": "3073", "conta_corrente": "12345678",
         "convenio": "1234567", "carteira": "18", "cedente": "Empresa Teste LTDA",
         "documento_cedente": "11222333000181", "chave_pix": "11222333000181"}


def _texto(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def _e_br_code(emv: str) -> bool:
    """BR Code do BACEN: comeca no payload format indicator e fecha no CRC16."""
    return (emv.startswith("000201") and "br.gov.bcb.pix" in emv
            and emv[-8:-4] == "6304" and len(emv[-4:]) == 4)


# ------------------------------------------------------------- copia-e-cola
def test_boleto_com_qr_devolve_o_copia_e_cola():
    pdf, info = pycob.emitir_boleto(BANCO, COM_PIX)
    assert "PIX" in _texto(pdf).upper(), "o PDF nem tem QR — o caso nao esta sendo exercido"
    assert _e_br_code(info["pix_copia_cola"]), info["pix_copia_cola"]


def test_boleto_sem_chave_nao_inventa_copia_e_cola():
    _pdf, info = pycob.emitir_boleto(BANCO, BASE)
    assert info["pix_copia_cola"] is None


def test_cobranca_offline_devolve_o_mesmo_campo_que_o_caminho_online(client):
    """`pix_copia_cola` e do contrato, nao do provider.

    C6, Inter e Sicoob preenchem; o offline devolvia `null` emitindo o QR.
    """
    r = client.post("/cobranca", json={
        "tenant_id": "t1", "provider": "off", "banco": BANCO, "account_config": CONTA,
        "cobranca": {"valor": "150.00", "vencimento": "2027-12-30", "nosso_numero": "123",
                     "pagador": {"nome": "Joao", "documento": "52998224725"}}})
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert _e_br_code(corpo["pix_copia_cola"] or ""), corpo.get("pix_copia_cola")
    assert "PIX" in _texto(base64.b64decode(corpo["pdf_base64"])).upper()


@pytest.mark.parametrize("rota,corpo", [
    ("/api/render/boleto", {"bank": BANCO, "data": COM_PIX}),
    ("/api/render/fatura", {"bank": BANCO, "data": COM_PIX,
                            "itens": [{"descricao": "Mensalidade", "valor": "150,00"}]}),
])
def test_rotas_de_render_devolvem_o_copia_e_cola(client, rota, corpo):
    r = client.post(rota, json=corpo)
    assert r.status_code == 200, r.text
    assert _e_br_code(r.json()["pix_copia_cola"])


def test_pdf_binario_leva_o_copia_e_cola_no_header(client):
    """Aqui o corpo e o PDF: o header e o unico caminho que sobra.

    O BR Code e ASCII por especificacao — a engine normaliza o nome do
    beneficiario —, entao cabe em header HTTP sem codificacao extra.
    """
    r = client.get("/api/boleto", params={"bank": BANCO, "type": "pdf",
                                          "data": json.dumps(COM_PIX)})
    assert r.status_code == 200
    emv = r.headers.get("X-Pix-Copia-Cola")
    assert emv and _e_br_code(emv)
    assert emv.isascii(), "header nao-ASCII quebraria clientes HTTP"


def test_txid_longo_no_bolepix_responde_400_e_nao_500():
    """Dois campos chamados `txid`, com limites incompativeis.

    O do Bolepix vai DENTRO do BR Code estatico e aceita ate 25 alfanumericos;
    o do Pix cob/cobv exige de 26 a 35 -- e o proprio schema desta API cobra
    esse minimo na outra rota. Copiar um para o outro e o caminho natural de
    quem usa as duas, e devolvia 500: `PixInvalido` nao e `BoletoInvalido` e
    escapava dos handlers, entao o erro do chamador virava erro do servidor.
    """
    longo = "PEDIDO2027000000000000004242"  # 28 — valido como txid de cob
    assert len(longo) > 25
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.emitir_boleto(BANCO, {**COM_PIX, "txid": longo})
    msg = "; ".join(exc.value.erros)
    assert "25" in msg and "26 a 35" in msg


def test_txid_dentro_do_limite_do_bolepix_e_aceito():
    _pdf, info = pycob.emitir_boleto(BANCO, {**COM_PIX, "txid": "PEDIDO000000000042"})
    assert "PEDIDO000000000042" in info["pix_copia_cola"]


def test_sem_pix_o_header_nao_aparece(client):
    r = client.get("/api/boleto", params={"bank": BANCO, "type": "pdf",
                                          "data": json.dumps(BASE)})
    assert "X-Pix-Copia-Cola" not in r.headers


# ------------------------------------------------------------ dados do carne
def test_carne_devolve_os_dados_de_cada_parcela(client):
    parcelas = [{**COM_PIX, "nosso_numero": str(300 + i), "numero_documento": f"P-{i}"}
                for i in range(3)]
    r = client.post("/api/render/carne", json={"bank": BANCO, "boletos": parcelas})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["pdf_base64"][:4] == base64.b64encode(b"%PDF")[:4].decode()
    itens = corpo["itens"]
    assert len(itens) == 3, "uma entrada por parcela"
    for i, item in enumerate(itens):
        assert item["status"] == "completed"
        assert item["nosso_numero"] == str(300 + i)
        assert item["linha_digitavel"]
        assert item["codigo_barras"]
    # cada parcela e um titulo distinto: linhas digitaveis nao se repetem
    assert len({i["linha_digitavel"] for i in itens}) == 3


def test_carne_nao_perde_a_identidade_da_parcela(client):
    """`item_id` e o que liga a parcela do PDF ao registro do cliente."""
    parcelas = [{**BASE, "nosso_numero": str(400 + i), "numero_documento": f"CTR-{i:02d}"}
                for i in range(2)]
    r = client.post("/api/render/carne", json={"bank": BANCO, "boletos": parcelas})
    assert [i["item_id"] for i in r.json()["itens"]] == ["CTR-00", "CTR-01"]


# ------------------------------------------------- uma montagem, uma verdade
def test_pdf_e_dados_saem_do_mesmo_boleto():
    """`emitir_boleto` monta o titulo uma vez.

    Antes eram duas construcoes — `dados_boleto` e `pdf_boleto` —, o que alem
    de repetir o trabalho deixava o papel e o JSON saindo de objetos
    diferentes, sem nada garantindo que descreviam o mesmo boleto.
    """
    pdf, info = pycob.emitir_boleto(BANCO, COM_PIX)
    texto = _texto(pdf)
    assert info["linha_digitavel"] in texto.replace("\n", "")
    assert info["nosso_numero"] in texto
