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
            # Uma montagem só. Eram duas — `dados_boleto` e `pdf_boleto` —, o
            # que além de custar o dobro deixava o PDF e o JSON saindo de
            # objetos diferentes, sem nada garantindo que descreviam o mesmo
            # boleto.
            pdf, info = pycob.emitir_boleto(bank, dados)
        except pycob.DadosInvalidos as e:
            return CobrancaOut(status=Status.erro, raw={"validation_errors": e.erros})
        return CobrancaOut(
            id=info["nosso_numero"],
            status=Status.registrado,
            linha_digitavel=info["linha_digitavel"],
            codigo_barras=info["codigo_barras"],
            # O caminho ON preenche isto em C6, Inter e Sicoob; o OFF devolvia
            # `null` mesmo emitindo o QR no PDF. Quem integra via ver o Bolepix
            # impresso e nao ter o texto para pôr ao lado dele — e pagador de
            # celular nao escaneia a propria tela.
            pix_copia_cola=info.get("pix_copia_cola"),
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
    dados.update(_endereco_do_sacado(pagador.endereco or {}))
    return {k: v for k, v in dados.items() if v not in (None, "")}


def _endereco_do_sacado(end: dict[str, Any]) -> dict[str, Any]:
    """Endereço do pagador para o motor offline.

    Aqui NÃO se converte o número para inteiro, ao contrário do C6: o
    `endereco_sacado` da engine é uma linha de texto livre ("Rua Teste, 100"),
    então "126A" e "S/N" entram como estão. A conversão é exigência do
    /v1/bank_slips e mora no provider que a sofre.

    O que existia era pior que a falta de conversão: só o logradouro seguia, e
    número, bairro, cidade, UF e CEP eram descartados em silêncio — apesar de a
    engine ter posição para todos no CNAB. Boleto com rua e sem número é
    endereço incompleto, e o registro sai assim mesmo, sem ninguém reclamar.
    """
    logradouro = end.get("logradouro") or end.get("street")
    numero = end.get("numero") or end.get("number")
    linha = f"{logradouro}, {numero}" if logradouro and numero else logradouro
    return {
        "sacado_endereco": linha,
        "sacado_bairro": end.get("bairro") or end.get("neighborhood"),
        "sacado_cidade": end.get("cidade") or end.get("city"),
        "sacado_uf": end.get("uf") or end.get("state"),
        "sacado_cep": end.get("cep") or end.get("zip_code"),
    }
