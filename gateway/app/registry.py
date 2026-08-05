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
from app.providers.sicoob import SicoobProvider
from app.schemas import Provider, eh_offline

_PROVIDERS: dict[Provider, type[BankProvider]] = {
    Provider.pycobranca: PyCobrancaProvider,
    Provider.c6: C6Provider,
    Provider.sicoob: SicoobProvider,
    Provider.inter: InterProvider,
}

# Slug do banco na engine offline para o fallback (método antigo).
_OFFLINE_BANK: dict[Provider, str] = {
    Provider.c6: "banco_c6",
    Provider.sicoob: "sicoob",
}
# O Inter (077) NÃO entra aqui de propósito: a engine offline não tem o layout
# dele. Sem fallback, `provider=inter` sem credencial falha dizendo isso; com
# fallback para outro banco, sairia um boleto REGISTRADO NO BANCO ERRADO — que
# é falha silenciosa e cara. Ausência aqui é a decisão, não esquecimento.


def registered_ready(provider: Provider) -> bool:
    """Indica se a cobrança REGISTRADA (API do banco) está homologada e pronta.

    Enquanto C6/Sicoob não estão 100%, o padrão é `False` → cai no método antigo
    (offline via pyCobranca). Liga por banco com `C6_REGISTERED_READY=true` /
    `SICOOB_REGISTERED_READY=true` após a homologação.
    """
    if eh_offline(provider):
        return True
    return os.environ.get(f"{provider.value.upper()}_REGISTERED_READY", "").lower() in ("1", "true", "yes")


def build_provider(
    *,
    provider: Provider,
    tenant_id: str,
    account_config: dict[str, Any],
    vault: Vault,
    credentials: dict[str, Any] | None = None,
) -> BankProvider:
    # Fallback: C6/Sicoob ainda não 100% → trata pelo método antigo (offline
    # via pyCobrança), sem precisar de credencial de banco.
    if provider in _OFFLINE_BANK and not registered_ready(provider):
        cfg = {**account_config, "bank": account_config.get("bank") or _OFFLINE_BANK[provider]}
        return PyCobrancaProvider(account_config=cfg, credentials={})

    klass = _PROVIDERS[provider]
    # o caminho offline (pyCobrança) não precisa de credencial de banco.
    # Credenciais vindas NO REQUEST têm prioridade (nada gravado no servidor);
    # o cofre (VAULT__*) é o fallback para quem prefere provisionar no ambiente.
    creds: dict[str, Any] = {}
    if not eh_offline(provider):
        creds = credentials or vault.get_credentials(tenant_id, provider.value)
    return klass(account_config=account_config, credentials=creds)


def build_rest_provider(
    *,
    provider: Provider,
    tenant_id: str,
    account_config: dict[str, Any],
    vault: Vault,
    credentials: dict[str, Any] | None = None,
) -> BankProvider:
    """Provider REST direto, SEM fallback offline.

    Pix dinâmico e conciliação só existem na API do banco — não há equivalente
    CNAB para cair. `pycobranca` aqui é erro de contrato (o router
    traduz para 422). Credenciais do request têm prioridade sobre o cofre (só memória).
    """
    if eh_offline(provider):
        raise ValueError(
            f"operação exige provider REST (ex: c6); {provider.value} é offline/CNAB"
        )
    klass = _PROVIDERS[provider]
    creds = credentials or vault.get_credentials(tenant_id, provider.value)
    return klass(account_config=account_config, credentials=creds)


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
