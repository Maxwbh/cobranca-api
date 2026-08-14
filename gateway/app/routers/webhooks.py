from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request

from app.core import outbox
from app.core.forwarder import forward_event
from app.core.subscriptions import resolve_callback
from app.core.vault import get_vault
from app.providers.c6 import C6Provider
from app.providers.inter import InterProvider
from app.providers.sicoob import SicoobProvider
from app.schemas import Status, WebhookEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_NORMALIZERS = {"c6": C6Provider, "sicoob": SicoobProvider, "inter": InterProvider}

# Status que move dinheiro na ponta do consumidor: é o que ele usa para dar
# baixa. Só estes valem a ida ao banco para confirmar.
_TERMINAIS_FAVORAVEIS = {Status.liquidado}


def _flag(nome: str, default: bool = False) -> bool:
    bruto = os.environ.get(nome)
    if bruto is None:
        return default
    return bruto.strip().lower() in ("1", "true", "yes", "on")


def _check_token(banco: str, request: Request) -> None:
    """Autenticidade do webhook por token de rota (query `?token=` ou header
    `x-webhook-token`), comparado em tempo constante.

    Os bancos (C6 incluso) não documentam assinatura no payload; o padrão de
    mercado é embutir um segredo na URL cadastrada no banco — `WEBHOOK_TOKEN__<BANCO>`.

    **Fail-closed**: sem a env configurada, a rota RECUSA. Antes ela aceitava, e
    aceitar era o problema: quem descobrisse a URL postava `{"status":"PAID"}`, o
    evento saía normalizado como `liquidado` e o push ia adiante ASSINADO PELA
    NOSSA CHAVE — a assinatura autentica este gateway, não o banco, então o
    consumidor não tinha como recusar. `WEBHOOK_ALLOW_UNAUTHENTICATED=1` volta ao
    comportamento antigo, de propósito difícil de digitar por acidente.
    """
    expected = os.environ.get(f"WEBHOOK_TOKEN__{banco.upper()}", "")
    if not expected:
        if _flag("WEBHOOK_ALLOW_UNAUTHENTICATED"):
            return
        raise HTTPException(
            status_code=401,
            detail=f"webhook sem autenticação configurada: defina WEBHOOK_TOKEN__{banco.upper()}"
                   " e cadastre a URL no banco com ?token=<segredo>"
                   " (ou WEBHOOK_ALLOW_UNAUTHENTICATED=1 para aceitar sem token)",
        )
    got = request.query_params.get("token") or request.headers.get("x-webhook-token", "")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="webhook token inválido")


def _confirmar_no_banco(banco: str, tenant_id: str | None, event: WebhookEvent) -> WebhookEvent:
    """Reconsulta o banco e faz a resposta DELE prevalecer sobre o corpo recebido.

    O token de rota prova que quem postou conhece o segredo; não prova que o
    conteúdo é verdade. Esta é a defesa que não depende de o banco documentar
    assinatura: para o status que move dinheiro, perguntamos à fonte.

    Três resultados, no campo `confirmado`:
      True  — o banco confirma o status recebido
      False — o banco discorda; vale o dele, e o evento segue com o status real
      None  — não deu para perguntar (sem tenant, sem credencial no cofre, ou o
              provider não consulta esse recurso). Segue como veio, e o `None`
              diz ao consumidor que ninguém verificou.

    Desligável com `WEBHOOK_CONFIRM=0` — quem tem volume alto e confia na rede
    do banco paga uma chamada a menos por evento.
    """
    if not _flag("WEBHOOK_CONFIRM", default=True):
        return event
    if event.status not in _TERMINAIS_FAVORAVEIS or not event.id or not tenant_id:
        return event

    consultar = _consulta_para(banco, tenant_id, event)
    if consultar is None:
        return event

    try:
        real = consultar(event.id)
    except Exception:  # noqa: BLE001 — banco fora do ar não invalida a notificação
        return event

    status_real = getattr(real, "status", None)
    if status_real is None:
        return event
    if status_real == event.status:
        return event.model_copy(update={"confirmado": True})
    # Divergência: o corpo diz uma coisa, o banco diz outra. O banco é a fonte.
    return event.model_copy(update={"confirmado": False, "status": status_real})


# Cada família de evento tem o seu método de consulta — o id significa coisas
# diferentes (id de cobrança, txid, id de checkout) e não dá para chamar um só.
# `pix_automatico.*` fica de fora: o id é de recorrência, sem consulta 1-para-1.
_CONSULTA_POR_EVENTO = {
    "cobranca.": "consultar",
    "checkout.": "consultar_checkout",
    "pix.": "consultar_pix",
}


def _consulta_para(banco: str, tenant_id: str, event: WebhookEvent):
    """Método de consulta do provider já com a credencial do cofre, ou None
    quando não há como perguntar (evento sem consulta, sem credencial provisionada,
    ou provider que não implementa aquele recurso)."""
    metodo = next((m for p, m in _CONSULTA_POR_EVENTO.items() if event.event.startswith(p)), None)
    if metodo is None:
        return None

    klass = _NORMALIZERS.get(banco)
    if klass is None:
        return None

    try:
        creds = get_vault().get_credentials(tenant_id, banco)
    except Exception:  # noqa: BLE001 — cofre indisponível vira "não confirmado"
        return None
    if not creds:
        return None

    fn = getattr(klass(account_config={}, credentials=creds), metodo, None)
    return fn if callable(fn) else None


async def _handle(banco: str, request: Request, tenant_id: str | None) -> WebhookEvent:
    _check_token(banco, request)
    bruto = await request.body()
    try:
        body = await request.json()
    except ValueError as e:
        raise HTTPException(status_code=422, detail="corpo do webhook não é JSON") from e

    klass = _NORMALIZERS.get(banco)
    if not klass:
        return WebhookEvent(event="ignorado", raw={"banco": banco})

    # Dedup ANTES de normalizar: o banco reentrega até receber 2xx, e sem isto o
    # consumidor recebe a mesma liquidação N vezes e dá baixa N vezes. A
    # resposta continua 2xx — reentrega é comportamento correto do banco, não erro.
    marca = _reservar(banco, tenant_id, bruto)
    if marca is _DUPLICADO:
        return WebhookEvent(event="duplicado", raw={"banco": banco})

    try:
        event = klass(account_config={}, credentials={}).normalizar_webhook(
            dict(request.headers), body)
        event = _confirmar_no_banco(banco, tenant_id, event)

        # Push assinado (HMAC) ao consumidor DONO do tenant (multi-sistema). Sem
        # tenant na rota, cai no destino global. forward_event no-op se não houver destino.
        cb = resolve_callback(tenant_id)
        entregue = forward_event(event.model_dump(), url=cb[0] if cb else None,
                                 secret=cb[1] if cb else None)
    except Exception:
        # A marca é uma RESERVA, não um recibo. Se o processamento morreu, esta
        # notificação não foi processada — soltar a marca é o que permite a
        # reentrega do banco tentar de novo. Sem isto, um payload que quebrasse a
        # normalização viraria evento perdido em silêncio: 500 na primeira,
        # `duplicado` em todas as seguintes.
        _liberar(marca)
        raise

    if cb and not entregue:
        # Não é falha da notificação: o evento está no outbox e volta a sair.
        event = event.model_copy(update={"pendente_de_entrega": True})
    return event


# Sentinela distinta de `None`: dedup desligado também devolve "siga em frente",
# mas sem marca para liberar depois.
_DUPLICADO = object()


def _reservar(banco: str, tenant_id: str | None, bruto: bytes) -> Any:
    """Reserva esta notificação. Devolve `_DUPLICADO` se já passou por aqui, a
    marca se é nova, ou None se o dedup está desligado/indisponível.

    Nunca levanta: disco ruim não pode virar 5xx, senão o banco reentrega e o
    problema dobra."""
    if not _flag("WEBHOOK_DEDUP", default=True):
        return None
    try:
        marca = outbox.impressao(banco, tenant_id, bruto)
        if outbox.get_outbox().ja_visto(marca, banco, tenant_id):
            return _DUPLICADO
        return marca
    except Exception:  # noqa: BLE001
        return None


def _liberar(marca: Any) -> None:
    if isinstance(marca, str):
        try:
            outbox.get_outbox().esquecer(marca)
        except Exception:  # noqa: BLE001
            pass


_BANCO_EMISSOR = Path(
    description="Banco que está notificando — é o slug usado na URL cadastrada nele "
                "(`c6`, `sicoob`, `inter`). Define qual `WEBHOOK_TOKEN__<BANCO>` "
                "valida a chamada. Não confundir com o parâmetro `banco` das rotas "
                "de cobrança, que é a instituição do request.",
)


@router.post("/{banco}", response_model=WebhookEvent)
async def receber(request: Request, banco: str = _BANCO_EMISSOR) -> WebhookEvent:
    """Webhook global (consumidor único / destino default).

    Exige `WEBHOOK_TOKEN__<BANCO>` (ou o opt-out explícito). **Sem tenant na
    rota não há confirmação no banco** — o cofre é por tenant; prefira a rota
    com tenant se o status precisa ser verificado."""
    return await _handle(banco, request, tenant_id=None)


@router.post("/{banco}/{tenant_id}", response_model=WebhookEvent)
async def receber_por_tenant(request: Request, tenant_id: str, banco: str = _BANCO_EMISSOR) -> WebhookEvent:
    """Webhook por tenant (multi-sistema). O banco aponta o callback de cada conta
    para esta URL; o tenant vem do path e roteia para o consumidor dono."""
    return await _handle(banco, request, tenant_id=tenant_id)
