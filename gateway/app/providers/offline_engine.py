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



def _to_engine_payload(cobranca: Cobranca, account_config: dict[str, Any],
                       bank: str | None = None) -> dict[str, Any]:
    """Monta o `data` da engine a partir da cobrança e do `account_config`.

    O `account_config` é **blob por provider**, por decisão de projeto: um
    tenant pode guardar no mesmo lugar as chaves do caminho online (do Sicoob,
    por exemplo: `cooperativa`, `numeroCliente`) e as do offline. Só o que se
    aplica a ESTE banco é repassado — o resto não é erro de quem chama, é o
    blob sendo blob, e recusar culparia o chamador por uma montagem nossa.

    Já o `data` que o cliente declara em `/api/*` é contrato fechado: lá campo
    desconhecido é recusado, em `construir_boleto`.
    """
    pagador = cobranca.pagador
    dados: dict[str, Any] = {
        "valor": float(cobranca.valor),
        "data_vencimento": cobranca.vencimento.isoformat(),
        "nosso_numero": cobranca.nosso_numero,
        "numero_documento": cobranca.seu_numero,
        "sacado": pagador.nome,
        "sacado_documento": pagador.documento,
        "sacado_endereco": _endereco_do_sacado(pagador.endereco or {}),
        **_do_account_config(account_config, bank),
    }
    return {k: v for k, v in dados.items() if v not in (None, "")}


def _do_account_config(account_config: dict[str, Any],
                       bank: str | None = None) -> dict[str, Any]:
    """As chaves do blob que este banco entende.

    O mesmo blob costuma carregar OS DOIS lados — o que a API do banco precisa
    para registrar e o que a engine precisa para desenhar —, e os dois usam
    `conta` com significados diferentes: no C6 é a conta do REST, na engine é o
    que o contrato chama de `conta_corrente`. Quando as duas grafias aparecem,
    vale a do **contrato**: é a que foi escrita para a engine.
    """
    # O `bank` vem de quem chama quando o caminho já o resolveu — é o caso do
    # /carne, que sabe o banco pelo `provider`/`banco` e não o repete no blob.
    # Sem isto o filtro desligava justamente ali, e o `account_config`
    # chegava cru na fronteira estrita: o chamador levava 400 por uma chave do
    # blob, que é a acusação que este filtro existe para evitar.
    try:
        aceitos = pycob.campos_aceitos(bank or account_config.get("bank", ""))
    except pycob.DadosInvalidos:
        aceitos = None
    dados = {k: v for k, v in account_config.items()
             if k != "bank" and (aceitos is None or k in aceitos)}
    for contrato, nativo in pycob.NOMES_DO_CONTRATO.items():
        if contrato in dados:
            dados.pop(nativo, None)
    return dados


def _endereco_do_sacado(end: dict[str, Any]) -> str | None:
    """Endereço do pagador numa linha — que é o que o boleto tem.

    Aqui NÃO se converte o número para inteiro, ao contrário do C6: o
    `sacado_endereco` da engine é texto livre, então "126A" e "S/N" entram como
    estão. A conversão é exigência do /v1/bank_slips e mora no provider que a
    sofre.

    Bairro, cidade, UF e CEP eram enviados como campos próprios —
    `sacado_bairro`, `sacado_cidade`… — e o boleto **não tem** esses campos: o
    construtor os descartava, um por um, em silêncio. Aquelas posições existem
    no CNAB, não no título. O boleto sai com rua e número e mais nada, e o
    pagador impresso mora numa cidade que o papel não diz.

    Concatenar é o que o formato permite e é como um boleto de verdade imprime
    (o exemplo da própria doc: "Rua Padre Feijó, 873, Jardim Vila Boa, Goiânia,
    GO, CEP 74360390").
    """
    partes = [
        ", ".join(p for p in (end.get("logradouro") or end.get("street"),
                              str(end.get("numero") or end.get("number") or "") or None)
                  if p),
        end.get("bairro") or end.get("neighborhood"),
        end.get("cidade") or end.get("city"),
        end.get("uf") or end.get("state"),
    ]
    cep = end.get("cep") or end.get("zip_code")
    if cep:
        partes.append(f"CEP {cep}")
    linha = ", ".join(p for p in partes if p)
    return linha or None
