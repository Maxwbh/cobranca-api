# Quando a integração para de funcionar sozinha.
#
# O certificado mTLS dos bancos vale um ano e NÃO tem renovação in-place: vence,
# e toda chamada passa a falhar no handshake — de uma vez, sem aviso, sem nada
# no código ter mudado. A API não tinha como responder "quando isso acontece":
# o material entrava cifrado no cofre e ninguém mais olhava.
#
# E há a pergunta irmã, que na prática dói antes: *qual* certificado está em
# uso. Os bancos entregam pacotes com mais de um, e o AMBIENTE está no host
# dentro do CN — `baas-api-sandbox` contra `baas-api`. Carregar o do ambiente
# errado só aparecia no primeiro handshake.
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core import certificado

SEGREDO = "nao-pode-vazar-jamais"


def _par(cn: str, *, dias_ate_vencer: int = 360):
    """Certificado autoassinado com o CN e a validade pedidos."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    hoje = date.today()
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_dt(hoje - timedelta(days=5)))
            .not_valid_after(_dt(hoje + timedelta(days=dias_ate_vencer)))
            .sign(chave, hashes.SHA256()))
    pem_cert = cert.public_bytes(serialization.Encoding.PEM).decode()
    pem_key = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return pem_cert, pem_key


def _dt(d: date):
    from datetime import datetime, time
    return datetime.combine(d, time(12, 0))


CN_SANDBOX = "MSDOBRASILLTDA05230380000174-baas-api-sandbox.c6bank.info"
CN_PRODUCAO = "MSDOBRASILLTDA05230380000174-baas-api.c6bank.info"


@pytest.fixture(scope="module")
def valido():
    cert, chave = _par(CN_SANDBOX)
    return {"client_id": "x", "client_secret": SEGREDO,
            "cert_pem": cert, "key_pem": chave}


# --- a pergunta que a API não sabia responder ---------------------------------

def test_diz_quando_vence(valido):
    c = certificado.descrever(valido)
    assert c.situacao == "ok"
    assert c.dias_restantes == 360
    assert c.valido_ate == (date.today() + timedelta(days=360)).isoformat()


def test_avisa_antes_de_vencer():
    """Trinta dias é o prazo em que ainda dá para pedir, receber e trocar o
    certificado sem parada. Abaixo disso a renovação vira urgência."""
    cert, chave = _par(CN_SANDBOX, dias_ate_vencer=certificado.DIAS_DE_ALERTA - 1)
    assert certificado.descrever({"cert_pem": cert, "key_pem": chave}).situacao == "expirando"


def test_no_limite_ainda_e_alerta():
    cert, _ = _par(CN_SANDBOX, dias_ate_vencer=certificado.DIAS_DE_ALERTA)
    assert certificado.descrever({"cert_pem": cert}).situacao == "expirando"


def test_um_dia_depois_do_limite_esta_ok():
    cert, _ = _par(CN_SANDBOX, dias_ate_vencer=certificado.DIAS_DE_ALERTA + 1)
    assert certificado.descrever({"cert_pem": cert}).situacao == "ok"


def test_vencido_e_vencido():
    cert, _ = _par(CN_SANDBOX, dias_ate_vencer=-1)
    c = certificado.descrever({"cert_pem": cert})
    assert c.situacao == "expirado" and c.dias_restantes < 0


# --- qual certificado está carregado ------------------------------------------

def test_o_cnpj_sai_separado(valido):
    """Para conferir num olhar que é o certificado da empresa certa."""
    assert certificado.cnpj_do_titular(certificado.descrever(valido)) == "05230380000174"


def test_o_titular_distingue_sandbox_de_producao():
    """É a única diferença entre os dois, e ela está no HOST dentro do CN.

    Foi exatamente a confusão que motivou este módulo: um pacote com dois
    certificados do mesmo CNPJ, um por ambiente, e nada na API dizendo qual
    estava em uso.
    """
    sandbox, _ = _par(CN_SANDBOX)
    producao, _ = _par(CN_PRODUCAO)
    t_sandbox = certificado.descrever({"cert_pem": sandbox}).titular
    t_producao = certificado.descrever({"cert_pem": producao}).titular
    assert "baas-api-sandbox" in t_sandbox
    assert "baas-api-sandbox" not in t_producao
    assert certificado.cnpj_do_titular(certificado.descrever({"cert_pem": sandbox})) == \
        certificado.cnpj_do_titular(certificado.descrever({"cert_pem": producao}))


def test_par_trocado_e_acusado():
    """O erro clássico da troca de certificado: `.crt` novo com `.key` antiga.

    No handshake isso vira uma mensagem de TLS que não aponta o par trocado, e a
    investigação começa pelo lugar errado.
    """
    cert_a, _ = _par(CN_SANDBOX)
    _, chave_b = _par(CN_PRODUCAO)
    assert certificado.par_confere({"cert_pem": cert_a, "key_pem": chave_b}) is False


def test_par_certo_confere(valido):
    assert certificado.par_confere(valido) is True


def test_sem_par_nao_afirma_nem_nega(valido):
    """`None` é "não dá para dizer" — diferente de `False`, que acusa erro."""
    assert certificado.par_confere({"cert_pem": valido["cert_pem"]}) is None


# --- o que não pode acontecer --------------------------------------------------

def test_certificado_ilegivel_nao_derruba_a_rota():
    """A rota que chama isto é de DIAGNÓSTICO: levantar esconderia justamente o
    caso que ela existe para mostrar."""
    c = certificado.descrever({"cert_pem": "isto não é um certificado"})
    assert c.situacao == "ilegivel" and c.detalhe


def test_pkcs12_sem_senha_explica_o_motivo():
    c = certificado.descrever({"pfx_base64": "AAAA"})
    assert c.situacao == "ilegivel" and "PKCS12" in c.detalhe


def test_sem_certificado_devolve_nada():
    """Banco sem mTLS (Sicoob com token estático) não é erro."""
    assert certificado.descrever({"client_id": "x", "access_token": "t"}) is None


# --- pela rota: o segredo não sai ----------------------------------------------

@pytest.fixture
def token(client, valido) -> str:
    r = client.post("/credenciais", json={
        "tenant_id": "hml", "provider": "on", "banco": "c6", "credentials": valido})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_o_cadastro_ja_devolve_o_certificado(client, valido):
    """É onde o erro custa menos: carregar o certificado do ambiente errado só
    aparecia no primeiro handshake, horas depois."""
    r = client.post("/credenciais", json={
        "tenant_id": "hml", "provider": "on", "banco": "c6", "credentials": valido})
    assert r.json()["certificado"]["situacao"] == "ok"
    assert r.json()["certificado"]["cnpj"] == "05230380000174"


def test_a_consulta_nao_vaza_segredo_nem_chave(client, token, valido):
    corpo = json.dumps(client.get(
        "/credenciais", headers={"Authorization": f"Bearer {token}"}).json())
    assert SEGREDO not in corpo, "o client_secret vazou na resposta"
    assert "PRIVATE KEY" not in corpo, "a chave privada vazou na resposta"
    assert valido["cert_pem"] not in corpo, "o certificado inteiro vazou na resposta"


def test_o_token_volta_mascarado(client, token):
    """Ele é exibido uma única vez, no cadastro, e o servidor não consegue
    recuperá-lo — devolvê-lo aqui seria mentira."""
    devolvido = client.get(
        "/credenciais", headers={"Authorization": f"Bearer {token}"}).json()["token"]
    assert devolvido != token
    assert set(devolvido.removeprefix("bapi_")) == {"*"}


def test_a_consulta_exige_token(client):
    assert client.get("/credenciais").status_code == 422
    assert client.get("/credenciais",
                      headers={"Authorization": "Bearer bapi_naoexiste"}).status_code == 401


def test_token_revogado_nao_consulta_mais(client, token):
    client.delete("/credenciais", headers={"Authorization": f"Bearer {token}"})
    r = client.get("/credenciais", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
