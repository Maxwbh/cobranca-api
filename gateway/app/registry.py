# Roteador de providers + resolução de credenciais (request > cofre).
from __future__ import annotations

import base64
import binascii
import json
import os
from typing import Any

from app.core.vault import Vault
from app.providers.base import BankProvider
from app.providers.offline_engine import PyCobrancaProvider
from app.providers.c6 import C6Provider
from app.providers.inter import InterProvider
from app.providers.itau import ItauProvider
from app.providers.sicoob import SicoobProvider
from app.schemas import Banco, PROVIDER_LEGADO_BANCO, Provider, eh_offline

# --- os dois eixos, cada um no seu mapa ---------------------------------------
#
# ANTES: `_PROVIDERS` casava o nome do banco com a classe REST, e `_OFFLINE_BANK`
# traduzia o mesmo nome para o slug da engine. O banco aparecia nos dois, e o
# caminho em nenhum — ele era inferido do nome. Agora `provider` diz o CAMINHO
# (on/off) e `banco` diz a INSTITUIÇÃO; estes mapas respondem "esse banco tem
# esse caminho?" sem ambiguidade.

# Caminho ON: banco → classe do provider REST.
_REST_POR_BANCO: dict[Banco, type[BankProvider]] = {
    Banco.c6: C6Provider,
    Banco.sicoob: SicoobProvider,
    Banco.inter: InterProvider,
    Banco.itau: ItauProvider,
}

# Caminho OFF: banco → slug do layout na engine. O nome canônico do C6 é `c6`,
# mas a engine o chama de `banco_c6`; a tradução mora aqui e não vaza para o
# contrato.
_SLUG_ENGINE: dict[Banco, str] = {
    Banco.c6: "banco_c6",
    **{b: b.value for b in Banco if b not in (Banco.c6, Banco.inter)},
}
# O Inter NÃO está aqui de propósito: a engine não tem o layout 077. Sem
# caminho OFF, `provider=off&banco=inter` é recusado com a lista de quem tem —
# cair em outro banco emitiria boleto REGISTRADO NO LUGAR ERRADO, que é falha
# silenciosa e cara.

# Compatibilidade: o roteador antigo mapeava Provider→classe. Mantido porque
# testes e rotas ainda referenciam, e porque `build_rest_provider` usa.
_PROVIDERS: dict[Provider, type[BankProvider]] = {
    Provider.pycobranca: PyCobrancaProvider,
    Provider.off: PyCobrancaProvider,
    **{p: _REST_POR_BANCO[b] for p, b in PROVIDER_LEGADO_BANCO.items()},
}
_OFFLINE_BANK: dict[Provider, str] = {
    p: _SLUG_ENGINE[b] for p, b in PROVIDER_LEGADO_BANCO.items() if b in _SLUG_ENGINE
}


class CaminhoInvalido(ValueError):
    """Combinação caminho×banco que não existe. O router traduz para 422."""


def bancos_do_caminho(provider: Provider) -> list[str]:
    fonte = _SLUG_ENGINE if eh_offline(provider) else _REST_POR_BANCO
    return sorted(b.value for b in fonte)


def resolver_caminho(provider: Provider, banco: Banco | None,
                     account_config: dict[str, Any] | None = None) -> tuple[Provider, Banco]:
    """(caminho, banco) a partir do que veio no request.

    Aceita as duas formas: a nova (`provider=on|off` + `banco`) e a legada (o
    nome do banco no `provider`). A legada não pode simplesmente sumir — há
    integração em produção e um roteiro de homologação já enviado ao banco com
    esses payloads.
    """
    if provider in PROVIDER_LEGADO_BANCO:          # `provider=c6` → on + c6
        return Provider.on, PROVIDER_LEGADO_BANCO[provider]

    caminho = Provider.off if eh_offline(provider) else Provider.on
    if banco is None:
        # No caminho OFF o banco sempre pôde vir no `account_config.bank` — é
        # como a engine sempre foi chamada, e continua valendo.
        bruto = (account_config or {}).get("bank") or (account_config or {}).get("banco")
        if bruto:
            try:
                banco = Banco("c6" if bruto == "banco_c6" else str(bruto))
            except ValueError as e:
                raise CaminhoInvalido(
                    f"banco '{bruto}' não é tratado; use um destes: "
                    f"{', '.join(bancos_do_caminho(caminho))}") from e
        else:
            raise CaminhoInvalido(
                f"informe o `banco` (caminho '{caminho.value}'); "
                f"disponíveis: {', '.join(bancos_do_caminho(caminho))}")

    fonte = _SLUG_ENGINE if caminho is Provider.off else _REST_POR_BANCO
    if banco not in fonte:
        raise CaminhoInvalido(
            f"banco '{banco.value}' não tem caminho '{caminho.value}'; "
            f"com '{caminho.value}': {', '.join(bancos_do_caminho(caminho))}")
    return caminho, banco


def chave_credencial(provider: Provider, banco: Banco | None = None) -> str:
    """Chave sob a qual a credencial daquele tenant é guardada e procurada.

    É o BANCO, sempre. Credencial pertence à instituição, não ao caminho: com o
    `provider` virando `on`, guardar por ele colocaria C6 e Sicoob do mesmo
    tenant na MESMA chave — o token de um abriria o outro.

    Para o apelido legado a chave não muda (`provider=c6` → `c6`), então token
    emitido antes desta mudança continua valendo.
    """
    if banco is not None:
        return banco.value
    if provider in PROVIDER_LEGADO_BANCO:
        return PROVIDER_LEGADO_BANCO[provider].value
    return provider.value


def registered_ready(alvo: Provider | Banco) -> bool:
    """A cobrança REGISTRADA daquele banco já está homologada e liberada?

    É propriedade do BANCO, não do caminho: liga com `C6_REGISTERED_READY=true`,
    `ITAU_REGISTERED_READY=true`… Enquanto `False`, o caminho ON é rebaixado
    para a engine — proteção para quem sobe o container antes de homologar.

    Aceita `Provider` (forma legada, ainda usada em testes e rotas) e `Banco`.
    """
    if isinstance(alvo, Provider):
        if eh_offline(alvo):
            return True
        alvo = PROVIDER_LEGADO_BANCO.get(alvo) or Banco(alvo.value)
    return os.environ.get(f"{alvo.value.upper()}_REGISTERED_READY", "").lower() in ("1", "true", "yes")


def build_provider(
    *,
    provider: Provider,
    tenant_id: str,
    account_config: dict[str, Any],
    vault: Vault,
    credentials: dict[str, Any] | None = None,
    banco: Banco | None = None,
) -> BankProvider:
    """Monta o provider a partir do CAMINHO (`provider`) e do BANCO (`banco`)."""
    caminho, banco = resolver_caminho(provider, banco, account_config)

    if caminho is Provider.off:
        cfg = {**account_config, "bank": _SLUG_ENGINE[banco]}
        return PyCobrancaProvider(account_config=cfg, credentials={})

    # ON pedido, mas o banco ainda não homologado: rebaixa para a engine quando
    # existe layout. Sem layout (Inter), segue ON e a falta de credencial vira
    # 424 — que é o diagnóstico certo, em vez de emitir pelo banco errado.
    if not registered_ready(banco) and banco in _SLUG_ENGINE:
        cfg = {**account_config, "bank": _SLUG_ENGINE[banco]}
        return PyCobrancaProvider(account_config=cfg, credentials={})

    # Credenciais do request têm prioridade (nada gravado no servidor); o cofre
    # (VAULT__*) é o fallback de quem prefere provisionar no ambiente.
    creds = credentials or vault.get_credentials(tenant_id, banco.value)
    return _REST_POR_BANCO[banco](account_config=account_config, credentials=creds)


def build_rest_provider(
    *,
    provider: Provider,
    tenant_id: str,
    account_config: dict[str, Any],
    vault: Vault,
    credentials: dict[str, Any] | None = None,
    banco: Banco | None = None,
) -> BankProvider:
    """Provider REST direto, SEM rebaixar para a engine.

    Pix dinâmico e conciliação só existem na API do banco — não há equivalente
    CNAB para cair. Caminho OFF aqui é erro de contrato (o router traduz para
    422). Credenciais do request têm prioridade sobre o cofre (só memória).
    """
    if eh_offline(provider):
        raise CaminhoInvalido(
            "operação só existe no caminho ON (API do banco); "
            f"bancos com ON: {', '.join(bancos_do_caminho(Provider.on))}")
    _, banco = resolver_caminho(provider, banco, account_config)
    creds = credentials or vault.get_credentials(tenant_id, banco.value)
    return _REST_POR_BANCO[banco](account_config=account_config, credentials=creds)


def credentials_from_header(value: str | None) -> dict[str, Any] | None:
    """Decodifica o header `X-Bank-Credentials` (JSON em base64) das rotas GET/DELETE.

    Mesmo contrato do campo `credentials` do corpo: {client_id, client_secret,
    pfx_base64, pfx_password}. Vive só na memória do request; nunca é logado
    nem persistido. Retorna None se o header não veio.
    """
    if not value:
        return None
    try:
        data = json.loads(base64.b64decode(value))
    except (binascii.Error, ValueError) as e:
        raise ValueError("X-Bank-Credentials inválido (esperado JSON em base64)") from e
    if not isinstance(data, dict):
        raise ValueError("X-Bank-Credentials deve conter um objeto JSON")
    return data
