# Provider OFFLINE — engine pyCobranca (100% Python, in-process).
#
# Nova Versão: a conexão com o Banking Core BrCobrança (Ruby) foi
# DESCONTINUADA. O caminho offline/CNAB/carnê passa a ser resolvido pela
# biblioteca pyCobranca dentro do próprio processo (sem HTTP, sem sidecar).
# Sem segredo aqui.
from __future__ import annotations

import base64
from typing import Any

from app.core import pycob
from app.providers.base import BankProvider
from app.schemas import Cobranca, CobrancaOut, Status


class PyCobrancaProvider(BankProvider):
    """LegacyProvider do catálogo: emite boleto/CNAB offline via pyCobranca."""

    def registrar(self, cobranca: Cobranca) -> CobrancaOut:
        bank = self.account_config.get("bank", "")
        dados = _to_engine_payload(cobranca, self.account_config)
        try:
            info = pycob.dados_boleto(bank, dados)
            pdf = pycob.pdf_boleto(bank, dados)
        except pycob.DadosInvalidos as e:
            return CobrancaOut(status=Status.erro, raw={"validation_errors": e.erros})
        return CobrancaOut(
            id=info["nosso_numero"],
            status=Status.registrado,
            linha_digitavel=info["linha_digitavel"],
            codigo_barras=info["codigo_barras"],
            pdf_base64=base64.b64encode(pdf).decode(),
            raw=info,
        )

    # Offline não tem consulta/baixa online (conciliação via retorno/OFX).
    def consultar(self, cobranca_id: str) -> CobrancaOut:
        return CobrancaOut(id=cobranca_id, status=Status.pendente,
                           raw={"hint": "offline: conciliar via retorno/OFX"})

    def baixar(self, cobranca_id: str) -> CobrancaOut:
        return CobrancaOut(id=cobranca_id, status=Status.baixado,
                           raw={"hint": "offline: baixa via remessa CNAB"})



def _to_engine_payload(cobranca: Cobranca, account_config: dict[str, Any]) -> dict[str, Any]:
    pagador = cobranca.pagador
    dados: dict[str, Any] = {
        "valor": float(cobranca.valor),
        "data_vencimento": cobranca.vencimento.isoformat(),
        "nosso_numero": cobranca.nosso_numero,
        "numero_documento": cobranca.seu_numero,
        "sacado": pagador.nome,
        "sacado_documento": pagador.documento,
        **{k: v for k, v in account_config.items() if k != "bank"},
    }
    endereco = pagador.endereco or {}
    if endereco.get("logradouro"):
        dados["sacado_endereco"] = endereco["logradouro"]
    return {k: v for k, v in dados.items() if v not in (None, "")}
