# Push de eventos normalizados para um CONSUMIDOR downstream (qualquer projeto).
#
# A Cobranca-API é um produto standalone: cada sistema consumidor registra um webhook e recebe o evento normalizado via POST assinado
# (HMAC-SHA256), validável de forma timing-safe (hmac.compare_digest).
#
# Esquema de assinatura (o consumidor valida igual):
#   header  X-Signature: sha256=<hex(hmac_sha256(secret, raw_body))>
#   body    JSON compacto (separators sem espaço), UTF-8
#
# Destino: por padrão um webhook global (EVENT_WEBHOOK_URL / EVENT_WEBHOOK_SECRET),
# mas forward_event aceita override por chamada — base para callback por tenant
# (multi-consumidor) quando o mapeamento webhook->tenant estiver pronto.
#
# ENTREGA: a primeira tentativa é inline (o caso comum entrega e acaba aqui). Se
# ela falhar, o evento vai para o outbox e o drenador re-tenta com backoff —
# antes disso, um consumidor fora do ar por 30s custava o evento inteiro. O
# webhook do banco continua não podendo quebrar por causa do push: falha vira
# fila, nunca exceção que suba.
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx

from app.core import outbox


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def entregar(url: str, secret: str, body: bytes) -> bool:
    """POST assinado, uma tentativa. True se o consumidor aceitou (2xx/3xx).

    A assinatura é recalculada sobre os MESMOS bytes a cada tentativa — por isso
    o outbox guarda o corpo serializado, e não o dict: reserializar poderia
    trocar a ordem das chaves e invalidar a assinatura que o consumidor confere.
    """
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Signature"] = sign(body, secret)
    with httpx.Client(timeout=10.0) as c:
        r = c.post(url, content=body, headers=headers)
        return r.status_code < 400


def forward_event(event: dict[str, Any], *, url: str | None = None,
                  secret: str | None = None) -> bool:
    """Encaminha o evento ao consumidor downstream. True se entregue de primeira.

    `url`/`secret` permitem override por chamada (ex.: callback por tenant),
    caindo no global EVENT_WEBHOOK_URL / EVENT_WEBHOOK_SECRET. No-op (False) se
    não houver destino.

    **False não significa mais evento perdido**: quando há destino e a entrega
    falha, o evento fica no outbox para re-tentativa. Use `pendente_de_entrega`
    no retorno de `/webhooks` para distinguir "ninguém quis" de "vai de novo".
    """
    url = url or os.environ.get("EVENT_WEBHOOK_URL", "")
    if not url:
        return False

    secret = secret if secret is not None else os.environ.get("EVENT_WEBHOOK_SECRET", "")
    body = outbox.evento_para_corpo(event)

    try:
        if entregar(url, secret, body):
            return True
        erro = "resposta não-2xx do consumidor"
    except httpx.HTTPError as e:
        erro = f"{type(e).__name__}: {e}"

    _enfileirar(url, secret, body, erro)
    return False


def _enfileirar(url: str, secret: str, body: bytes, erro: str) -> None:
    """Guarda para re-tentar. Nunca levanta: o webhook do banco tem de responder
    2xx mesmo se o nosso próprio disco estiver ruim — senão o banco reentrega e
    o problema vira dois."""
    try:
        outbox.get_outbox().enfileirar(url=url, secret=secret, corpo=body)
        outbox.iniciar_drenador(entregar)
    except Exception:  # noqa: BLE001
        pass
