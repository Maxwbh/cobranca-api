# Quando a integração para de funcionar sozinha.
#
# O certificado mTLS dos bancos vale um ano e NÃO tem renovação in-place: vence,
# e toda chamada passa a falhar no handshake — de uma vez, sem aviso, sem nada
# no código ter mudado. É risco de operação, e a API tinha zero visibilidade
# sobre ele: o material entrava cifrado no cofre e ninguém mais olhava.
#
# Só metadado derivado sai daqui. A chave privada e o segredo NUNCA aparecem —
# `core/vault.py`: "NUNCA logar credencial/certificado".
from __future__ import annotations

import base64
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

#: Dias antes do vencimento em que o certificado passa a ser reportado como
#: `expirando`. Trinta é o prazo em que ainda dá para pedir, receber e trocar o
#: certificado sem parada — abaixo disso a renovação vira urgência.
DIAS_DE_ALERTA = 30


@dataclass(frozen=True)
class Certificado:
    """O que dá para dizer de um certificado sem revelar nada dele."""

    #: `ok`, `expirando`, `expirado` ou `ilegivel`.
    situacao: str
    titular: str | None = None
    emissor: str | None = None
    valido_de: str | None = None
    valido_ate: str | None = None
    dias_restantes: int | None = None
    formato: str | None = None
    detalhe: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _pem(valor: str) -> bytes:
    """Aceita PEM cru ou o mesmo material em base64 — como o cliente HTTP faz."""
    texto = (valor or "").strip()
    if "-----BEGIN" in texto:
        return texto.encode()
    try:
        return base64.b64decode(texto, validate=True)
    except Exception:
        return texto.encode()


def _nome(x509_nome) -> str:
    from cryptography.x509.oid import NameOID

    partes = x509_nome.get_attributes_for_oid(NameOID.COMMON_NAME)
    return partes[0].value if partes else x509_nome.rfc4514_string()


def _do_x509(cert, formato: str, hoje: date) -> Certificado:
    fim = cert.not_valid_after_utc.date()
    dias = (fim - hoje).days
    situacao = "expirado" if dias < 0 else ("expirando" if dias <= DIAS_DE_ALERTA else "ok")
    return Certificado(
        situacao=situacao,
        titular=_nome(cert.subject),
        emissor=_nome(cert.issuer),
        valido_de=cert.not_valid_before_utc.date().isoformat(),
        valido_ate=fim.isoformat(),
        dias_restantes=dias,
        formato=formato,
    )


def descrever(credenciais: dict[str, Any], *, hoje: date | None = None) -> Certificado | None:
    """Metadado do certificado das credenciais, ou `None` quando não há.

    Lê o par PEM (`cert_pem`) ou o PKCS12 (`pfx_base64`) — os dois formatos que
    os bancos entregam. Certificado ilegível vira `situacao="ilegivel"` em vez
    de exceção: a rota que chama isto é de diagnóstico, e derrubá-la esconderia
    justamente o caso que ela existe para mostrar.
    """
    hoje = hoje or datetime.now(timezone.utc).date()
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError:  # pragma: no cover - cryptography é dependência do projeto
        return None

    if credenciais.get("cert_pem"):
        try:
            return _do_x509(x509.load_pem_x509_certificate(_pem(credenciais["cert_pem"])),
                            "pem", hoje)
        except Exception as e:
            return Certificado(situacao="ilegivel", formato="pem",
                               detalhe=f"não foi possível ler o certificado: {type(e).__name__}")

    if credenciais.get("pfx_base64"):
        senha = (credenciais.get("pfx_password") or "").encode() or None
        try:
            _, cert, _ = pkcs12.load_key_and_certificates(
                base64.b64decode(credenciais["pfx_base64"]), senha)
            if cert is None:
                return Certificado(situacao="ilegivel", formato="pkcs12",
                                   detalhe="PKCS12 sem certificado")
            return _do_x509(cert, "pkcs12", hoje)
        except Exception as e:
            detalhe = "senha do PKCS12 incorreta ou ausente" if "mac" in str(e).lower() \
                else f"não foi possível abrir o PKCS12: {type(e).__name__}"
            return Certificado(situacao="ilegivel", formato="pkcs12", detalhe=detalhe)

    return None


def par_confere(credenciais: dict[str, Any]) -> bool | None:
    """A chave privada é a DESTE certificado? `None` quando não dá para dizer.

    O erro que isto pega é o de sempre em troca de certificado: o `.crt` novo
    com o `.key` antigo. O handshake falha com uma mensagem de TLS que não
    aponta o par trocado, e a investigação começa pelo lugar errado — foi o que
    quase aconteceu aqui, com dois certificados diferentes no mesmo pacote.
    """
    if not (credenciais.get("cert_pem") and credenciais.get("key_pem")):
        return None
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        cert = x509.load_pem_x509_certificate(_pem(credenciais["cert_pem"]))
        chave = serialization.load_pem_private_key(_pem(credenciais["key_pem"]), password=None)
        return cert.public_key().public_numbers() == chave.public_key().public_numbers()
    except Exception:
        return None


def cnpj_do_titular(cert: Certificado | None) -> str | None:
    """CNPJ que o banco carimbou no CN, quando há.

    Os bancos nomeiam o titular como `<RAZAOSOCIAL><CNPJ>-<host>`; o host diz o
    AMBIENTE. Devolver o CNPJ separado é o que deixa quem opera conferir num
    olhar que carregou o certificado certo — a confusão que motivou este módulo
    foi exatamente um pacote com dois, de CNPJs e ambientes diferentes.
    """
    if not cert or not cert.titular:
        return None
    achado = re.search(r"(\d{14})", cert.titular)
    return achado.group(1) if achado else None
