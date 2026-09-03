# O certificado que o banco ENTREGA tem de servir sem conversão.
#
# O cliente HTTP sempre aceitou os dois formatos — PKCS12 e o par PEM
# (.crt + .key). Os providers é que decidiam o que repassar, e C6 e Sicoob só
# repassavam o PFX. Em produção o C6 entrega PEM: o material do banco era
# inutilizável aqui e obrigava um `openssl pkcs12 -export` antes da primeira
# chamada — passo manual, com a chave privada trafegando por linha de comando.
from __future__ import annotations

import inspect

import pytest

from app.clients.oauth_mtls import OAuthMtlsClient
from app.providers.c6 import C6Provider
from app.providers.inter import InterProvider

#: Provider que fala mTLS com o banco.
COM_MTLS = [("c6", C6Provider), ("inter", InterProvider)]


@pytest.mark.parametrize(("nome", "klass"), COM_MTLS, ids=[n for n, _ in COM_MTLS])
def test_o_provider_repassa_o_par_pem(nome, klass):
    """`_client()` tem de encaminhar `cert_pem`/`key_pem`, não só o PFX."""
    fonte = inspect.getsource(klass._client)
    for campo in ("cert_pem", "key_pem"):
        assert campo in fonte, f"{nome} não repassa `{campo}`"


@pytest.mark.parametrize(("nome", "klass"), COM_MTLS, ids=[n for n, _ in COM_MTLS])
def test_o_pfx_continua_valendo(nome, klass):
    """Quem já converteu não pode ser quebrado pela correção."""
    fonte = inspect.getsource(klass._client)
    assert "pfx_base64" in fonte and "pfx_password" in fonte


def test_o_cliente_aceita_os_dois_formatos():
    """A capacidade sempre esteve aqui — o que faltava era o provider usá-la."""
    parametros = set(inspect.signature(OAuthMtlsClient.__init__).parameters)
    assert {"cert_pem", "key_pem", "pfx_base64", "pfx_password"} <= parametros


@pytest.mark.parametrize(("nome", "klass"), COM_MTLS, ids=[n for n, _ in COM_MTLS])
def test_o_esquema_do_catalogo_anuncia_o_que_o_provider_aceita(client, nome, klass):
    """Catálogo prometendo menos do que a rota aceita é o mesmo defeito de
    prometer mais: quem lê `GET /bancos` para montar o cadastro converteria o
    certificado à toa — ou concluiria que não dá.
    """
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    esquema = bancos[nome]["credentials"]
    for campo in ("cert_pem", "key_pem", "pfx_base64"):
        assert campo in esquema, f"o esquema do {nome} não cita `{campo}`"
