# Provider Itaú Unibanco (341) — ESQUELETO. Ver docs/development/itau-rest.md.
#
# O que aqui é CONFIRMADO pela documentação pública do portal:
#   - auth é OAuth2 `client_credentials` + mTLS, token em
#     POST https://sts.itau.com.br/api/oauth/token — o mesmo fluxo do C6, então
#     o `OAuthMtlsClient` serve sem código novo;
#   - o token vale 5 MINUTOS (o cache do cliente respeita `expires_in`);
#   - o certificado é dinâmico (CSR assinado pelo banco), entregue como
#     .crt + .key — igual ao Inter, não PKCS12;
#   - a API de cobrança devolve linha digitável e código de barras, NÃO o PDF.
#
# O que NÃO é público (exige conta no portal) e por isso está isolado no bloco
# CONTRATO A CONFIRMAR: URLs base de cobrança, paths de emissão/instrução e o
# payload. Nada disso foi inventado como se fosse verdade — os nomes abaixo são
# provisórios, saem por variável de ambiente e o provider fica DESLIGADO por
# padrão (`ITAU_REGISTERED_READY`), caindo na engine offline, que já emite o
# layout 341 há muito tempo.
#
# Também de propósito, e não por esquecimento:
#   - `pdf()` NÃO é sobrescrito. O banco não devolve PDF; quem renderiza é a
#     engine. Sobrescrever declararia a capacidade `boleto_pdf` no `GET /bancos`
#     e mentiria para quem consulta o catálogo.
#   - os mixins BACEN NÃO são herdados ainda. Há relato de divergências no Pix
#     do Itaú (credenciais, métodos e headers); herdar agora declararia `pix`,
#     `pix_lote` e `pix_automatico` sem nada por trás.
from __future__ import annotations

import os
from typing import Any

from app.clients.oauth_mtls import OAuthMtlsClient
from app.providers.base import BankProvider
from app.schemas import Cobranca, CobrancaOut, Pagador, Status

# --- confirmado (portal público) ----------------------------------------------
ITAU_AUTH = os.environ.get("ITAU_AUTH_URL", "https://sts.itau.com.br/api/oauth/token")
# Fluxo JWT alternativo, se o convênio exigir:
#   https://sts.itau.com.br/as/token.oauth2 com
#   grant_type=urn:ietf:params:oauth:grant-type:client_credentials

# --- CONTRATO A CONFIRMAR (catálogo exige login) ------------------------------
# Tudo abaixo sai por env justamente para poder ser corrigido sem alterar código
# quando o catálogo abrir — e para que um valor errado seja visível em
# configuração, não escondido numa constante.
ITAU_BASE = os.environ.get("ITAU_BASE_URL", "https://api.itau.com.br")
_BOLETOS = os.environ.get("ITAU_PATH_BOLETOS", "/cash_management/v2/boletos")
ITAU_SCOPES = [s for s in os.environ.get("ITAU_SCOPES", "").split() if s] or [
    # Nomes citados na documentação pública das APIs de cobrança.
    "cash_management/emissaocobranca.write",
    "cash_management/instrucaocobranca.write",
    "cash-boletos-consulta_titulo",
]


class ItauProvider(BankProvider):
    """Boleto registrado no Itaú (341).

    Enquanto `ITAU_REGISTERED_READY` não for ligado, o registry nem chega aqui:
    `provider=itau` cai na engine offline. É a mesma proteção que C6 e Sicoob
    tiveram antes da homologação.
    """

    def _client(self) -> OAuthMtlsClient:
        return OAuthMtlsClient(
            base_url=ITAU_BASE,
            auth_url=ITAU_AUTH,
            client_id=self.credencial("client_id"),
            client_secret=self.credentials.get("client_secret", ""),
            # O Itaú entrega .crt + .key (certificado dinâmico assinado por ele),
            # como o Inter. PKCS12 continua aceito para quem já converteu.
            cert_pem=self.credentials.get("cert_pem", ""),
            key_pem=self.credentials.get("key_pem", ""),
            pfx_base64=self.credentials.get("pfx_base64", ""),
            pfx_password=self.credentials.get("pfx_password", ""),
            scopes=self.credentials.get("scopes", ITAU_SCOPES),
            default_headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        """`x-itau-correlationID` é opcional, mas é o que o suporte pede.

        Sem ele, investigar uma emissão recusada vira arqueologia de log. Só é
        enviado quando o chamador informa — repetir o mesmo valor em todas as
        chamadas seria pior que não mandar.
        """
        correlation = self.account_config.get("correlation_id")
        return {"x-itau-correlationID": str(correlation)} if correlation else {}

    # --- boleto registrado -----------------------------------------------------

    def registrar(self, cobranca: Cobranca) -> CobrancaOut:
        data = self._client().request("POST", _BOLETOS, json=_payload_emissao(cobranca, self.account_config))
        return _boleto_out(None, data)

    def consultar(self, cobranca_id: str) -> CobrancaOut:
        data = self._client().request("GET", f"{_BOLETOS}/{cobranca_id}")
        return _boleto_out(cobranca_id, data)

    def alterar(self, cobranca_id: str, campos: dict[str, Any]) -> CobrancaOut:
        # Instrução de cobrança (escopo instrucaocobranca.write). O Itaú seria o
        # segundo banco com alteração online — hoje só o C6 tem.
        data = self._client().request("PATCH", f"{_BOLETOS}/{cobranca_id}", json=campos)
        return _boleto_out(cobranca_id, data)

    def baixar(self, cobranca_id: str) -> CobrancaOut:
        data = self._client().request("DELETE", f"{_BOLETOS}/{cobranca_id}")
        return CobrancaOut(id=cobranca_id, status=Status.baixado, raw=data or None)


# --- mapeamento (o trabalho real, quando o catálogo abrir) ---------------------
#
# Uma função só, de propósito: é o único lugar que muda quando o payload for
# confirmado. Os nomes de campo daqui são PROVISÓRIOS.


def _payload_emissao(cobranca: Cobranca, account_config: dict[str, Any]) -> dict[str, Any]:
    """Cobranca normalizada → corpo da emissão do Itaú.

    Estrutura provisória. O que já é decisão nossa, e não muda com o catálogo:
    o documento do pagador vai só com dígitos, o tipo de pessoa é deduzido do
    tamanho (11 = CPF, 14 = CNPJ) e agência/conta/carteira vêm do
    `account_config` — nunca do payload da cobrança.
    """
    return {
        "beneficiario": {
            "agencia": account_config.get("agencia"),
            "conta": account_config.get("conta"),
            # 109 é a carteira citada nas integrações de mercado; o convênio do
            # cliente manda, e por isso ela é configuração, não constante.
            "carteira": account_config.get("carteira", "109"),
        },
        "dado_boleto": {
            "valor": str(cobranca.valor),
            "data_vencimento": cobranca.vencimento.isoformat(),
            "nosso_numero": cobranca.nosso_numero,
            "seu_numero": cobranca.seu_numero or cobranca.nosso_numero,
            "pagador": _pagador(cobranca.pagador),
        },
    }


def _pagador(pagador: Pagador) -> dict[str, Any]:
    doc = "".join(c for c in (pagador.documento or "") if c.isdigit())
    end = pagador.endereco or {}
    dados = {
        "nome": pagador.nome,
        "documento": doc,
        "tipo_pessoa": "J" if len(doc) > 11 else "F",
        "logradouro": end.get("logradouro") or end.get("street"),
        "numero": end.get("numero") or end.get("number"),
        "bairro": end.get("bairro") or end.get("neighborhood"),
        "cidade": end.get("cidade") or end.get("city"),
        "uf": end.get("uf") or end.get("state"),
        "cep": "".join(c for c in str(end.get("cep") or end.get("zip_code") or "") if c.isdigit()),
    }
    return {k: v for k, v in dados.items() if v not in (None, "")}


def _boleto_out(cobranca_id: str | None, data: dict[str, Any]) -> CobrancaOut:
    """Resposta do Itaú → contrato normalizado.

    Lê os campos por uma lista de apelidos porque o nome exato ainda não está
    confirmado: assim, quando o catálogo abrir, o ajuste é acrescentar (ou
    remover) um apelido — e não reescrever a função. Sem PDF: o banco não manda,
    e a engine é quem renderiza.
    """
    corpo = data.get("data") or data
    return CobrancaOut(
        id=_primeiro(corpo, "id_boleto", "id", "nosso_numero") or cobranca_id,
        status=_map_status(_primeiro(corpo, "status", "situacao")) or Status.registrado,
        linha_digitavel=_primeiro(corpo, "linha_digitavel", "codigo_linha_digitavel"),
        codigo_barras=_primeiro(corpo, "codigo_barras", "codigo_barra"),
        raw=data,
    )


def _primeiro(corpo: dict[str, Any], *chaves: str) -> Any:
    for chave in chaves:
        valor = corpo.get(chave)
        if valor not in (None, ""):
            return valor
    return None


def _map_status(s: str | None) -> Status | None:
    """Status do Itaú nos seis do contrato.

    A tabela do banco ainda não está confirmada; o que está aqui são os termos
    que aparecem na documentação pública. **Status desconhecido devolve `None`**,
    e `_boleto_out` assume `registrado` — nunca `liquidado`. Errar para o lado
    de "ainda em aberto" é o único erro barato: dizer que um boleto foi pago
    quando não foi libera mercadoria de graça.
    """
    return {
        "EM_ABERTO": Status.registrado,
        "ABERTO": Status.registrado,
        "VENCIDO": Status.registrado,
        "PAGO": Status.liquidado,
        "LIQUIDADO": Status.liquidado,
        "BAIXADO": Status.baixado,
        "CANCELADO": Status.baixado,
        "EXPIRADO": Status.expirado,
    }.get((s or "").upper().replace(" ", "_").replace("-", "_"))
