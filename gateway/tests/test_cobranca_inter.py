# Banco Inter (077) — boleto Cobranca v3 + Pix BACEN.
#
# O contrato afirmado aqui veio do SDK oficial (inter-co/pj-sdk-java), nao de
# suposicao: verbos, paths, nomes de campo e os nove status do boleto.
import pytest

from app.schemas import Status


@pytest.fixture
def inter_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__inter__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__inter__client_secret", "sec")
    monkeypatch.setenv("INTER_REGISTERED_READY", "true")


def _capture(monkeypatch, *respostas):
    """Devolve as respostas em ordem; repete a ultima quando acabam."""
    calls = []
    fila = list(respostas) or [{}]

    def fake(self, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json, "params": params,
                      "headers": dict(self.default_headers)})
        return fila[min(len(calls) - 1, len(fila) - 1)]

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    return calls


def _corpo(**extra):
    base = {"tenant_id": "empresa1", "provider": "inter",
            "cobranca": {"valor": "150.00", "vencimento": "2026-12-31", "seu_numero": "PED-1",
                         "pagador": {"nome": "Joao da Silva", "documento": "12345678909",
                                     "endereco": {"logradouro": "Rua Teste", "numero": "126A",
                                                  "bairro": "Centro", "cidade": "Sete Lagoas",
                                                  "uf": "MG", "cep": "35700000"}}}}
    base.update(extra)
    return base


_CONSULTA = {
    "cobranca": {"codigoSolicitacao": "abc-123", "situacao": "A_RECEBER",
                 "valorNominal": 150.0},
    "boleto": {"linhaDigitavel": "07790001...", "codigoBarras": "07791234..."},
    "pix": {"pixCopiaECola": "00020101..."},
}


# --- emissao ----------------------------------------------------------------------

def test_emitir_traduz_o_payload_do_inter(client, inter_env, monkeypatch):
    calls = _capture(monkeypatch, {"codigoSolicitacao": "abc-123"}, _CONSULTA)
    r = client.post("/cobranca", json=_corpo())
    assert r.status_code == 201, r.text

    emissao = calls[0]
    # SEM barra final. Com ela o Inter responde 307 e o cliente nao segue
    # redirect — a emissao virava 502. O C6 EXIGE a barra (/v1/bank_slips/) e o
    # Inter recusa; este assert existe para ninguem "padronizar" os dois.
    assert emissao["method"] == "POST" and emissao["path"] == "/cobranca/v3/cobrancas"
    enviado = emissao["json"]
    assert enviado["seuNumero"] == "PED-1"
    assert enviado["valorNominal"] == 150.0
    assert enviado["dataVencimento"] == "2026-12-31"
    # BOLETO_PIX e o hibrido. `BOLETO` puro SUPRIME o QR Pix, e defaultar
    # nele perderia em silencio a funcionalidade que motivou escolher o Inter.
    assert enviado["formasRecebimento"] == "BOLETO_PIX"


def test_emitir_consulta_para_devolver_o_boleto(client, inter_env, monkeypatch):
    """A emissao do Inter devolve so o codigoSolicitacao — linha digitavel e QR
    vem da consulta. Devolver so o id seria mais rapido e deixaria o chamador
    sem o boleto, que e' o que ele pediu."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "abc-123"}, _CONSULTA)
    r = client.post("/cobranca", json=_corpo())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["id"] == "abc-123"
    assert d["linha_digitavel"] == "07790001..."
    assert d["pix_copia_cola"] == "00020101..."          # hibrido: boleto com Pix
    assert calls[1] == {"method": "GET", "path": "/cobranca/v3/cobrancas/abc-123",
                        "json": None, "params": None, "headers": {}}


def test_pagador_do_inter_e_plano(client, inter_env, monkeypatch):
    """Diferente do C6 (`payer.address.*`): endereco no mesmo nivel do nome."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "abc-123"}, _CONSULTA)
    client.post("/cobranca", json=_corpo())
    p = calls[0]["json"]["pagador"]
    assert p["cpfCnpj"] == "12345678909"
    assert p["tipoPessoa"] == "FISICA"
    assert p["endereco"] == "Rua Teste"
    assert p["numero"] == "126A"        # string: nao converte, ao contrario do C6
    assert p["bairro"] == "Centro"
    assert "address" not in p


def test_cnpj_vira_pessoa_juridica(client, inter_env, monkeypatch):
    """`tipoPessoa` sai do tamanho do documento — o chamador ja informou isso
    implicitamente, e exigir o campo de novo e' pedir para divergir."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "x"}, _CONSULTA)
    corpo = _corpo()
    corpo["cobranca"]["pagador"]["documento"] = "11222333000181"
    client.post("/cobranca", json=corpo)
    assert calls[0]["json"]["pagador"]["tipoPessoa"] == "JURIDICA"


# --- consulta, PDF e cancelamento -------------------------------------------------

def test_cancelar_e_post_com_motivo(client, inter_env, monkeypatch):
    """No Inter cancelar e' POST /{id}/cancelar com motivo obrigatorio — nao
    DELETE nem PUT, como nos outros dois providers."""
    calls = _capture(monkeypatch, {})
    r = client.delete("/cobranca/abc-123", params={"tenant_id": "empresa1", "provider": "inter"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "baixado"
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/cobranca/v3/cobrancas/abc-123/cancelar"
    assert calls[0]["json"]["motivoCancelamento"] == "SOLICITADO_PELO_BENEFICIARIO"


def test_pdf_usa_a_rota_dedicada(client, inter_env, monkeypatch):
    calls = _capture(monkeypatch, {"pdf": "JVBERi0="})
    r = client.get("/cobranca/abc-123/pdf",
                   params={"tenant_id": "empresa1", "provider": "inter"})
    assert r.status_code == 200, r.text
    assert r.json()["pdf_base64"] == "JVBERi0="
    assert calls[0]["path"] == "/cobranca/v3/cobrancas/abc-123/pdf"


# --- os nove status ---------------------------------------------------------------

@pytest.mark.parametrize("inter,esperado", [
    ("A_RECEBER", Status.registrado),
    ("EM_PROCESSAMENTO", Status.pendente),
    ("RECEBIDO", Status.liquidado),
    ("CANCELADO", Status.baixado),
    ("EXPIRADO", Status.expirado),
    ("FALHA", Status.erro),
    # Decisoes de produto, tomadas explicitamente:
    ("ATRASADO", Status.registrado),         # vencido ainda e' pagavel
    ("MARCADO_RECEBIDO", Status.liquidado),  # baixa manual do beneficiario
    ("PROTESTO", Status.registrado),         # segue em aberto; protesto e' etapa
])
def test_os_nove_status_do_inter_cabem_nos_seis_nossos(client, inter_env, monkeypatch,
                                                       inter, esperado):
    """Nenhum status novo foi preciso.

    `MARCADO_RECEBIDO` vira `liquidado` porque a pergunta do consumidor e'
    "posso liberar?" e o banco diz que sim; quem concilia por extrato tem o
    valor cru em `raw`. `PROTESTO` vira `registrado` e NAO um setimo status:
    criar um obrigaria todo consumidor a tratar um caso que so o Inter tem."""
    _capture(monkeypatch, {"cobranca": {"codigoSolicitacao": "abc", "situacao": inter}})
    r = client.get("/cobranca/abc", params={"tenant_id": "empresa1", "provider": "inter"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == esperado.value


# --- conta corrente ---------------------------------------------------------------

def test_conta_corrente_vira_header_quando_informada(client, inter_env, monkeypatch):
    """`x-conta-corrente` e' a mesma armadilha do numeroCliente do Sicoob:
    identificador de conta que nao vai no path nem no corpo."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "x"}, _CONSULTA)
    corpo = _corpo(account_config={"conta_corrente": "123456"})
    client.post("/cobranca", json=corpo)
    assert calls[0]["headers"]["x-conta-corrente"] == "123456"


def test_sem_conta_corrente_o_header_nao_vai_vazio(client, inter_env, monkeypatch):
    """Header vazio e' pior que header ausente: foi o que fez o Sicoob recusar
    toda consulta com `numeroCliente=`."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "x"}, _CONSULTA)
    client.post("/cobranca", json=_corpo())
    assert "x-conta-corrente" not in calls[0]["headers"]


# --- Pix: herdado do dialeto BACEN ------------------------------------------------

def test_pix_usa_a_base_do_inter_sem_codigo_novo(client, inter_env, monkeypatch):
    """O Pix do Inter e' BACEN puro: o mixin ja faz tudo, so muda o prefixo."""
    calls = _capture(monkeypatch, {"txid": "T1", "status": "ATIVA"})
    r = client.post("/pix", json={"tenant_id": "empresa1", "provider": "inter",
                                  "account_config": {"chave_pix": "k"},
                                  "pix": {"valor": "1.00"}})
    assert r.status_code == 201, r.text
    assert calls[0]["path"] == "/pix/v2/cob"


# --- webhook ----------------------------------------------------------------------

def test_webhook_do_inter_normaliza_a_situacao(client, monkeypatch, webhook_aberto):
    r = client.post("/webhooks/inter", json={
        "cobranca": {"codigoSolicitacao": "abc-123", "situacao": "RECEBIDO",
                     "valorNominal": 150.0, "dataHoraSituacao": "2026-08-04T10:00:00Z"}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["event"] == "cobranca.atualizada"
    assert d["id"] == "abc-123"
    assert d["status"] == "liquidado"


# --- fronteira: o fallback offline passou a existir -------------------------------

def test_inter_sem_flag_cai_no_proprio_layout_e_nao_no_de_outro(client, monkeypatch):
    """O Inter era o único banco `on` sem `off`: a engine não tinha o layout 077,
    e cair no fallback teria emitido um boleto REGISTRADO NO BANCO ERRADO.

    A pyCobrança 1.1.1 implementou o 077, então o fallback passa a cair no
    layout **do próprio Inter** — o mesmo que o Itaú já fazia. O que continua
    valendo é a fronteira: o boleto sai pela engine do Inter ou não sai.
    """
    monkeypatch.delenv("INTER_REGISTERED_READY", raising=False)
    r = client.post("/cobranca", json=_corpo(tenant_id="fantasma"))
    assert r.status_code == 201, r.text
    # tenant fantasma não tem conta configurada: a engine recusa, e o que volta
    # são os erros do layout DO INTER — a carteira 110 é dele, e de mais nenhum.
    erros = r.json()["raw"]["validation_errors"]
    assert any("110" in e for e in erros), erros


def test_boleto_puro_e_opt_in_nao_o_default(client, inter_env, monkeypatch):
    """Quem quer boleto SEM Pix pede explicitamente. Verificado no sandbox:
    `BOLETO` devolve `pix: null`; `BOLETO_PIX` devolve o copia-e-cola."""
    calls = _capture(monkeypatch, {"codigoSolicitacao": "x"}, _CONSULTA)
    client.post("/cobranca", json=_corpo(account_config={"formas_recebimento": "BOLETO"}))
    assert calls[0]["json"]["formasRecebimento"] == "BOLETO"
