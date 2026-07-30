import hashlib
import hmac
import json

import httpx
import respx

from app.core import forwarder


def test_sign_is_deterministic_hmac_sha256():
    body = b'{"a":1}'
    expected = "sha256=" + hmac.new(b"segredo", body, hashlib.sha256).hexdigest()
    assert forwarder.sign(body, "segredo") == expected


def test_forward_noop_sem_url(monkeypatch):
    monkeypatch.delenv("EVENT_WEBHOOK_URL", raising=False)
    assert forwarder.forward_event({"event": "x"}) is False


@respx.mock
def test_forward_posts_signed_event(monkeypatch):
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumer.test/webhooks/boleto-api")
    monkeypatch.setenv("EVENT_WEBHOOK_SECRET", "segredo")
    route = respx.post("https://consumer.test/webhooks/boleto-api").mock(
        return_value=httpx.Response(200)
    )

    event = {"event": "cobranca.atualizada", "id": "X1", "status": "liquidado"}
    assert forwarder.forward_event(event) is True

    sent = route.calls.last.request
    # assinatura confere com o corpo bruto enviado
    assert sent.headers["x-signature"] == forwarder.sign(sent.content, "segredo")
    assert json.loads(sent.content) == event


@respx.mock
def test_forward_override_por_chamada(monkeypatch):
    # override por chamada (callback por tenant) ignora o env global
    monkeypatch.delenv("EVENT_WEBHOOK_URL", raising=False)
    route = respx.post("https://tenant-cb.test/hook").mock(return_value=httpx.Response(204))
    ok = forwarder.forward_event({"event": "x"}, url="https://tenant-cb.test/hook", secret="s")
    assert ok is True
    assert route.calls.last.request.headers["x-signature"] == forwarder.sign(
        route.calls.last.request.content, "s"
    )


@respx.mock
def test_forward_retorna_false_em_erro(monkeypatch):
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumer.test/hook")
    respx.post("https://consumer.test/hook").mock(return_value=httpx.Response(500))
    assert forwarder.forward_event({"event": "x"}) is False
