# Registro de assinantes (consumidores downstream) — MULTI-SISTEMA.
#
# Vários sistemas podem acoplar à Cobranca-API. Cada tenant pertence a um
# consumidor, que registra um callback (URL + secret) para receber os eventos
# daquele tenant. Quando um evento chega, resolvemos o callback do tenant e
# fazemos o push só para o consumidor dono.
#
# Convenção (dev/EnvSubscriptions):
#   SUB__<tenant_id>__URL     e   SUB__<tenant_id>__SECRET
# Sem callback por tenant, cai no destino global EVENT_WEBHOOK_URL/SECRET.
#
# Em produção, trocar por um store real (DB) — interface estável abaixo.
from __future__ import annotations

import os


def resolve_callback(tenant_id: str | None) -> tuple[str, str] | None:
    """Retorna (url, secret) do consumidor para o tenant, ou o global, ou None."""
    if tenant_id:
        url = os.environ.get(f"SUB__{tenant_id}__URL")
        if url:
            return url, os.environ.get(f"SUB__{tenant_id}__SECRET", "")

    url = os.environ.get("EVENT_WEBHOOK_URL")
    if url:
        return url, os.environ.get("EVENT_WEBHOOK_SECRET", "")

    return None
