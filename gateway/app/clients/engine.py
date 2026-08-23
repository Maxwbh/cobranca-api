# Cliente do engine de cobrança offline — pyCobranca (in-process).
#
# Nova Versão 100% Python: a chamada HTTP ao Banking Core BrCobrança (Ruby) foi
# DESCONTINUADA; a renderização acontece no próprio processo. A interface
# (render_boleto/render_carne) é mantida para os consumidores internos.
from __future__ import annotations

import base64
from typing import Any

from app.core import pycob


def render_boleto(bank: str, data: dict[str, Any]) -> dict[str, Any]:
    pdf, info = pycob.emitir_boleto(bank, data)
    return {
        "nosso_numero": info["nosso_numero"],
        "linha_digitavel": info["linha_digitavel"],
        "codigo_barras": info["codigo_barras"],
        "pix_copia_cola": info["pix_copia_cola"],
        "pdf_base64": base64.b64encode(pdf).decode(),
    }


def render_carne(bank: str, boletos: list[dict[str, Any]]) -> dict[str, Any]:
    # `pdf_multi` é tolerante: item inválido é descartado e o lote segue. O
    # resultado por item era jogado fora aqui, e com ele a única evidência de
    # que o carnê saiu menor do que o pedido. Quem chama decide o que fazer.
    itens = [dict(b, bank=b.get("bank") or bank) for b in boletos]
    pdf, resultados = pycob.pdf_multi(itens, template="carne")
    return {"pdf_base64": base64.b64encode(pdf).decode(), "itens": resultados}
