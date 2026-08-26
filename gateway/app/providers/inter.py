# Provider Banco Inter (077) — Cobrança v3 + Pix (BACEN) via API REST.
#
# Contrato extraído do SDK OFICIAL do banco (inter-co/pj-sdk-java):
#   Constants.java            — bases, paths e URL do token
#   BillingSdk.java           — operações e verbos (cancelar é POST, não DELETE)
#   BillingIssueRequest.java  — payload da emissão
#   Person.java               — pagador PLANO (endereço não aninhado)
#   BillingSituation.java     — os nove status do boleto
#
# Autenticação:
#   - OAuth2 client_credentials + mTLS, token em POST {base}/oauth/v2/token
#   - header `x-conta-corrente` quando a aplicação enxerga mais de uma conta
#   - certificado válido por 1 ANO, sem renovação in-place: vence e a
#     integração para. É risco de operação, não de código.
#
# APIs:
#   - Cobrança v3: /cobranca/v3/cobrancas — boleto híbrido (BOLETO/PIX) com PDF
#   - Pix: /pix/v2 — PADRÃO BACEN, idêntico ao C6 e ao Sicoob → herdado dos
#     mixins; aqui só muda PIX_BASE.
#   - Banking v2: /banking/v2/extrato
#
# Pix Automático: não consta no SDK oficial, mas o banco EXPÕE. A spec OpenAPI
# publicada (swagger-api-pix-automatico) usa a mesma base /pix/v2 e traz /rec,
# /solicrec, /cobr, /locrec e os dois webhooks — as 17 chamadas do mixin batem
# uma a uma. Inventário em docs/homologacao/evidencia-pix-automatico-inter.json.
# Restrição do BACEN: só para CNPJ com 6+ meses de atividade.
#
# Validado no sandbox em 04/08/2026: emissão, consulta, PDF, cancelamento,
# webhook e extrato fecham em 2xx, e o banco ECOA o que foi enviado (seuNumero,
# valor e vencimento voltam iguais) — comportamento real, não mock de schema.
from __future__ import annotations

import os
from typing import Any

from app.clients.oauth_mtls import OAuthMtlsClient
from app.providers.bacen_pix import BacenPixAutomaticoMixin, BacenPixMixin, BacenPixRecebidosMixin
from app.providers.base import BankProvider
from app.schemas import Cobranca, CobrancaOut, Pagador, Status, WebhookEvent

INTER_BASE = os.environ.get("INTER_BASE_URL", "https://cdpj.partners.bancointer.com.br")
INTER_AUTH = os.environ.get("INTER_AUTH_URL", f"{INTER_BASE}/oauth/v2/token")
# Sandbox do banco (há um, ao contrário do que o roadmap supunha):
#   INTER_BASE_URL=https://cdpj-sandbox.partners.uatinter.co
INTER_SCOPES = [
    "boleto-cobranca.read", "boleto-cobranca.write",
    "cob.read", "cob.write", "cobv.read", "cobv.write",
    "lotecobv.read", "lotecobv.write", "pix.read", "pix.write",
    "payloadlocation.read", "payloadlocation.write",
    "webhook.read", "webhook.write", "extrato.read",
    # Pix Automático. Sem eles os paths certos morriam na AUTORIZAÇÃO: o token
    # sai sem o escopo e toda chamada volta 403 — falha que não se parece com
    # "faltou escopo". Os nomes saem da spec do próprio banco, versionada em
    # `docs/homologacao/evidencia-pix-automatico-inter.json`.
    "rec.read", "rec.write", "solicrec.read", "solicrec.write",
    "cobr.read", "cobr.write", "webhookrec.read", "webhookrec.write",
    "webhookcobr.read", "webhookcobr.write",
    "payloadlocationrec.read", "payloadlocationrec.write",
]
# Pagamentos (pagamento-boleto.*, pagamento-darf.*, pagamento-lote.*,
# pagamento-pix.*, webhook-banking.*) ficam de fora do token de propósito: são
# saída de dinheiro, e o produto é cobrança. Pedir escopo que não se usa amplia
# o estrago de um vazamento de credencial sem entregar nada.

_BILLING = "/cobranca/v3/cobrancas"


class InterProvider(BacenPixMixin, BacenPixRecebidosMixin, BacenPixAutomaticoMixin, BankProvider):
    PIX_BASE = "/pix/v2"  # BACEN padrão, prefixo do Inter

    def _client(self) -> OAuthMtlsClient:
        # `x-conta-corrente` é a mesma armadilha do `numeroCliente` do Sicoob:
        # identificador de conta que não vai no path nem no corpo. Só é enviado
        # quando informado — aplicação de conta única não precisa dele, e mandar
        # vazio é o que fazia o Sicoob recusar toda consulta.
        headers = {}
        conta = self.account_config.get("conta_corrente") or self.credentials.get("conta_corrente")
        if conta:
            headers["x-conta-corrente"] = str(conta)
        return OAuthMtlsClient(
            base_url=INTER_BASE,
            auth_url=INTER_AUTH,
            client_id=self.credencial("client_id"),
            client_secret=self.credentials.get("client_secret", ""),
            pfx_base64=self.credentials.get("pfx_base64", ""),
            pfx_password=self.credentials.get("pfx_password", ""),
            # O Inter entrega PEM separado (.crt + .key), não PKCS12. Aceitar os
            # dois evita obrigar quem integra a converter com openssl antes da
            # primeira chamada.
            cert_pem=self.credentials.get("cert_pem", ""),
            key_pem=self.credentials.get("key_pem", ""),
            scopes=self.credentials.get("scopes", INTER_SCOPES),
            default_headers=headers,
            static_token=self.credentials.get("access_token", ""),
        )

    # --- boleto registrado (Cobrança v3) ---------------------------------------

    def registrar(self, cobranca: Cobranca) -> CobrancaOut:
        payload: dict[str, Any] = {
            "seuNumero": cobranca.seu_numero or cobranca.nosso_numero,
            "valorNominal": float(cobranca.valor),
            "dataVencimento": cobranca.vencimento.isoformat(),
            "pagador": _pagador(cobranca.pagador),
            # BOLETO_PIX é o HÍBRIDO — boleto com QR Pix no mesmo título — e é o
            # default aqui de propósito: o pagador escolhe como pagar, e é por
            # isso que o Inter foi priorizado no roadmap. `BOLETO` puro SUPRIME
            # o QR, e defaultar nele perderia a funcionalidade em silêncio.
            # (Verificado no sandbox: BOLETO devolve `pix: null`; BOLETO_PIX e a
            # ausência do campo devolvem o copia-e-cola. "PIX" sozinho é recusado.)
            "formasRecebimento": self.account_config.get("formas_recebimento", "BOLETO_PIX"),
        }
        if self.account_config.get("dias_agenda") is not None:
            payload["numDiasAgenda"] = int(self.account_config["dias_agenda"])
        if self.account_config.get("mensagem"):
            payload["mensagem"] = self.account_config["mensagem"]
        for campo, chave in (("desconto", "desconto"), ("juros", "mora"), ("multa", "multa")):
            valor = getattr(cobranca, campo)
            if valor:
                payload[chave] = valor

        # SEM barra final: o Inter responde 307 para `/cobrancas/` e o cliente
        # não segue redirect — a emissão virava 502. O C6 exige a barra, o
        # Inter recusa; copiar o padrão do vizinho foi o que quebrou.
        data = self._client().request("POST", _BILLING, json=payload)
        # A emissão devolve só o codigoSolicitacao; linha digitável e PDF vêm da
        # consulta. Devolver o id sem consultar seria mais rápido e deixaria o
        # chamador sem o boleto — que é o que ele pediu.
        codigo = data.get("codigoSolicitacao")
        if not codigo:
            return CobrancaOut(id=None, status=Status.pendente, raw=data)
        out = self.consultar(codigo)
        out.raw = {"emissao": data, "consulta": out.raw}
        return out

    def consultar(self, cobranca_id: str) -> CobrancaOut:
        data = self._client().request("GET", f"{_BILLING}/{cobranca_id}")
        return _boleto_out(cobranca_id, data)

    def pdf(self, cobranca_id: str) -> CobrancaOut:
        data = self._client().request("GET", f"{_BILLING}/{cobranca_id}/pdf")
        pdf = data.get("pdf") if isinstance(data, dict) else None
        return CobrancaOut(id=cobranca_id, status=Status.pendente, pdf_base64=pdf, raw=data)

    def baixar(self, cobranca_id: str) -> CobrancaOut:
        # Cancelamento é POST com motivo no corpo — não DELETE nem PUT. O motivo
        # é obrigatório no SDK; sem ele o banco recusa.
        motivo = self.account_config.get("motivo_cancelamento", "SOLICITADO_PELO_BENEFICIARIO")
        data = self._client().request(
            "POST", f"{_BILLING}/{cobranca_id}/cancelar", json={"motivoCancelamento": motivo})
        return CobrancaOut(id=cobranca_id, status=Status.baixado, raw=data or None)

    # --- extrato (Banking v2) --------------------------------------------------

    def extrato(self, *, start_date: str, end_date: str) -> dict[str, Any]:
        return self._client().request(
            "GET", "/banking/v2/extrato",
            params={"dataInicio": start_date, "dataFim": end_date})

    # --- webhook ---------------------------------------------------------------

    def cadastrar_webhook(self, *, url: str, service: str = "COBRANCA") -> dict[str, Any]:
        return self._client().request("PUT", f"{_BILLING}/webhook", json={"webhookUrl": url})

    def consultar_webhook(self, *, service: str = "COBRANCA") -> dict[str, Any]:
        return self._client().request("GET", f"{_BILLING}/webhook")

    def remover_webhook(self, *, service: str = "COBRANCA") -> dict[str, Any]:
        return self._client().request("DELETE", f"{_BILLING}/webhook")

    def normalizar_webhook(self, headers: dict[str, str], body: dict[str, Any]) -> WebhookEvent:
        """A notificação do Inter traz a cobrança com a situação nova.

        O Pix segue o webhook BACEN, tratado pelo mixin — aqui é só o boleto.
        """
        cobranca = body.get("cobranca") or body
        situacao = cobranca.get("situacao") or body.get("situacao")
        return WebhookEvent(
            event="cobranca.atualizada",
            id=(cobranca.get("codigoSolicitacao") or cobranca.get("seuNumero")
                or body.get("codigoSolicitacao")),
            status=_map_status(situacao),
            paid_at=cobranca.get("dataHoraSituacao") or cobranca.get("dataSituacao"),
            valor=cobranca.get("valorNominal"),
            raw=body,
        )


def _pagador(pagador: Pagador) -> dict[str, Any]:
    """Pagador do Inter é PLANO — endereço no mesmo nível, sem objeto aninhado.

    Difere do C6 (`payer.address.*`) e do Sicoob. `tipoPessoa` sai do tamanho do
    documento: 11 dígitos = CPF, 14 = CNPJ. Deduzir é melhor que exigir do
    chamador um campo que ele já informou implicitamente.
    """
    doc = "".join(c for c in (pagador.documento or "") if c.isdigit())
    end = pagador.endereco or {}
    dados = {
        "cpfCnpj": doc,
        "tipoPessoa": "JURIDICA" if len(doc) > 11 else "FISICA",
        "nome": pagador.nome,
        "endereco": end.get("logradouro") or end.get("street"),
        "numero": end.get("numero") or end.get("number"),
        "complemento": end.get("complemento") or end.get("complement"),
        "bairro": end.get("bairro") or end.get("neighborhood"),
        "cidade": end.get("cidade") or end.get("city"),
        "uf": end.get("uf") or end.get("state"),
        "cep": end.get("cep") or end.get("zip_code"),
        "email": end.get("email"),
        "ddd": end.get("ddd"),
        "telefone": end.get("telefone") or end.get("phone"),
    }
    # `numero` do Inter é string, ao contrário do C6 que exige inteiro — não
    # converter aqui é deliberado: "126A" é endereço válido e cabe como está.
    return {k: (str(v) if k == "numero" and v is not None else v)
            for k, v in dados.items() if v is not None}


def _boleto_out(cobranca_id: str, data: dict[str, Any]) -> CobrancaOut:
    cobranca = data.get("cobranca") or data
    boleto = data.get("boleto") or {}
    pix = data.get("pix") or {}
    return CobrancaOut(
        id=cobranca.get("codigoSolicitacao") or cobranca_id,
        status=_map_status(cobranca.get("situacao")) or Status.registrado,
        linha_digitavel=boleto.get("linhaDigitavel"),
        codigo_barras=boleto.get("codigoBarras"),
        pix_copia_cola=pix.get("pixCopiaECola"),
        # QR dinâmico do banco: liquida o título. Ver a nota em `c6.py`.
        pix_vinculado=True if pix.get("pixCopiaECola") else None,
        raw=data,
    )


def _map_status(s: str | None) -> Status | None:
    """Os nove status do Inter nos seis do contrato normalizado.

    Duas decisões de produto, tomadas explicitamente:

    `MARCADO_RECEBIDO` → **liquidado**. É baixa manual do beneficiário, não
    liquidação pela compensação — o dinheiro pode não ter entrado. Vale
    `liquidado` porque a pergunta que o consumidor faz é "posso liberar?", e o
    banco está dizendo que sim. Quem concilia por extrato tem o valor cru em
    `raw`.

    `PROTESTO` → **registrado**, e NÃO um status novo. O título segue em aberto;
    o protesto é etapa de cobrança, não desfecho. Criar um sétimo status
    obrigaria todo consumidor a tratar um caso que só o Inter tem.

    `ATRASADO` também é `registrado`: vencido ainda é pagável.
    """
    return {
        "A_RECEBER": Status.registrado,
        "ATRASADO": Status.registrado,
        "PROTESTO": Status.registrado,
        "EM_PROCESSAMENTO": Status.pendente,
        "RECEBIDO": Status.liquidado,
        "MARCADO_RECEBIDO": Status.liquidado,
        "CANCELADO": Status.baixado,
        "EXPIRADO": Status.expirado,
        "FALHA": Status.erro,
    }.get((s or "").upper().replace(" ", "_"))
