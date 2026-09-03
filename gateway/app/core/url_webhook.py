# Validação da URL que o BANCO vai chamar.
#
# Não é a mesma coisa que validar uma URL qualquer. Esta URL é registrada na
# infraestrutura do banco e é ELE quem faz a requisição — de fora, pela internet
# pública, com o evento de pagamento no corpo. Duas consequências:
#
#   1. destino inalcançável de fora (localhost, 10.x, 169.254.169.254) é aceito
#      com `200` e o cadastro PARECE feito. O cliente só descobre que nunca
#      recebeu notificação quando um pagamento se perde;
#   2. `http://` põe valor, pagador e id da cobrança em claro no caminho.
#
# Ambos passavam: `javascript:alert(1)`, `""` e `nao-e-url` também.
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

#: Afrouxa a regra para homologação local (túnel http, host interno). Default
#: estrito, como no `WEBHOOK_ALLOW_UNAUTHENTICATED`: a flag existe para abrir,
#: não para fechar.
FLAG_PERMISSIVA = "WEBHOOK_URL_PERMITE_LOCAL"

_HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _permissiva() -> bool:
    return (os.environ.get(FLAG_PERMISSIVA) or "").strip().lower() in ("1", "true", "yes")


def validar_url_webhook(url: str) -> str:
    """Devolve a URL ou levanta `ValueError` dizendo o que está errado.

    `ValueError` e não `HTTPException` porque roda dentro do schema pydantic —
    quem chama traduz. A mensagem diz o motivo, não só que recusou."""
    partes = urlparse(url or "")
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValueError(
            "url deve ser uma URL http(s) completa (ex.: "
            "https://api.suaempresa.com.br/webhooks/c6/seu_tenant)")

    permissiva = _permissiva()
    if partes.scheme == "http" and not permissiva:
        raise ValueError(
            "url do webhook precisa ser https: quem chama é o banco, pela internet, "
            "com valor, pagador e id da cobrança no corpo. Em homologação local, "
            f"{FLAG_PERMISSIVA}=1 libera http")

    host = (partes.hostname or "").lower()
    if not permissiva and _nao_alcancavel_de_fora(host):
        raise ValueError(
            f"'{host}' não é alcançável a partir do banco — o cadastro seria aceito e "
            "a notificação nunca chegaria. Use o endereço público do seu gateway "
            f"(ou {FLAG_PERMISSIVA}=1 em homologação local)")
    return url


def _nao_alcancavel_de_fora(host: str) -> bool:
    if not host or host in _HOSTS_LOCAIS or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # nome de domínio: só o DNS do banco sabe, e não é nossa conta
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
