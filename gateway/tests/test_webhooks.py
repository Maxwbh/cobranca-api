import pytest

from app.core import outbox


# --- normalização (modo aberto, declarado) ----------------------------------------

def test_webhook_c6_normaliza(client, webhook_aberto):
    r = client.post("/webhooks/c6", json={"id": "C6-1", "status": "PAID"})
    assert r.status_code == 200
    data = r.json()
    assert data["event"] == "cobranca.atualizada"
    assert data["id"] == "C6-1"
    assert data["status"] == "liquidado"


def test_webhook_sicoob_normaliza_pix(client, webhook_aberto):
    r = client.post("/webhooks/sicoob", json={"txid": "abc123", "valor": "50.00"})
    assert r.status_code == 200
    data = r.json()
    assert data["event"] == "pix.recebido"
    assert data["id"] == "abc123"
    assert data["status"] == "liquidado"


def test_webhook_de_banco_sem_normalizador_nao_responde_200(client, webhook_aberto):
    """Antes: 200 com `event: "ignorado"`. E 200 diz ao banco "recebi, pode
    parar de reentregar" -- o evento sumia em silencio. Quem nao tem
    normalizador (o Itau, hoje) precisa falhar alto, para o erro de cadastro
    aparecer no painel do banco em vez de virar pagamento perdido."""
    r = client.post("/webhooks/itau", json={"x": 1})
    assert r.status_code == 422, r.text
    assert "c6" in r.text and "sicoob" in r.text and "inter" in r.text


def test_webhook_c6_faz_push_do_evento(client, webhook_aberto, monkeypatch):
    capturado = {}

    def fake_forward(event, *, url=None, secret=None):
        capturado.update(event)
        return True

    monkeypatch.setattr("app.routers.webhooks.forward_event", fake_forward)

    r = client.post("/webhooks/c6", json={"id": "C6-7", "status": "PAID"})
    assert r.status_code == 200
    # o evento normalizado foi encaminhado ao consumidor
    assert capturado["id"] == "C6-7"
    assert capturado["status"] == "liquidado"


def test_webhook_c6_pix_normaliza_por_txid(client, webhook_aberto):
    r = client.post("/webhooks/c6", json={"txid": "TX9", "status": "CONCLUIDA"})
    assert r.status_code == 200
    data = r.json()
    assert data["event"] == "pix.atualizada"
    assert data["id"] == "TX9"
    assert data["status"] == "liquidado"


def test_webhook_c6_pix_automatico_normaliza(client, webhook_aberto):
    r = client.post("/webhooks/c6", json={"idRec": "RR1", "status": "ATIVA"})
    assert r.json()["event"] == "pix_automatico.recorrencia"
    r = client.post("/webhooks/c6", json={"idRec": "RR1", "txid": "TX1", "status": "CONCLUIDA"})
    data = r.json()
    assert data["event"] == "pix_automatico.cobranca"
    assert data["status"] == "liquidado"


def test_webhook_por_tenant_roteia_para_o_consumidor_dono(client, webhook_aberto, monkeypatch):
    monkeypatch.setenv("SUB__sistemaA__URL", "https://sistema-1.test/hook")
    monkeypatch.setenv("SUB__sistemaA__SECRET", "segA")
    destino = {}

    def fake_forward(event, *, url=None, secret=None):
        destino["url"] = url
        destino["secret"] = secret
        return True

    monkeypatch.setattr("app.routers.webhooks.forward_event", fake_forward)

    r = client.post("/webhooks/c6/sistemaA", json={"id": "C6-9", "status": "PAID"})
    assert r.status_code == 200
    assert destino == {"url": "https://sistema-1.test/hook", "secret": "segA"}


# --- autenticidade ----------------------------------------------------------------

def test_webhook_token_valida_quando_configurado(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_TOKEN__C6", "s3gr3do")

    # sem token -> 401 (nada é encaminhado)
    assert client.post("/webhooks/c6", json={"id": "1", "status": "PAID"}).status_code == 401
    # token errado -> 401
    r = client.post("/webhooks/c6?token=errado", json={"id": "1", "status": "PAID"})
    assert r.status_code == 401
    # token certo (query) -> 200
    r = client.post("/webhooks/c6?token=s3gr3do", json={"id": "1", "status": "PAID"})
    assert r.status_code == 200
    # token certo (header), corpo diferente para não cair no dedup -> 200
    r = client.post("/webhooks/c6", json={"id": "2", "status": "PAID"},
                    headers={"x-webhook-token": "s3gr3do"})
    assert r.status_code == 200


def test_webhook_sem_token_configurado_recusa(client, monkeypatch):
    """Fail-closed. Antes esta rota ACEITAVA: quem descobrisse a URL postava
    `{"status":"PAID"}` e o gateway empurrava `liquidado` ao consumidor assinado
    com a NOSSA chave — que autentica este serviço, não o banco."""
    monkeypatch.delenv("WEBHOOK_TOKEN__C6", raising=False)
    monkeypatch.delenv("WEBHOOK_ALLOW_UNAUTHENTICATED", raising=False)

    r = client.post("/webhooks/c6", json={"id": "1", "status": "PAID"})
    assert r.status_code == 401
    assert "WEBHOOK_TOKEN__C6" in r.json()["detail"]


def test_webhook_sem_token_nao_encaminha_nada(client, monkeypatch):
    """O 401 tem de ser ANTES do push — recusar e mesmo assim notificar o
    consumidor seria o pior dos dois mundos."""
    monkeypatch.delenv("WEBHOOK_TOKEN__C6", raising=False)
    monkeypatch.delenv("WEBHOOK_ALLOW_UNAUTHENTICATED", raising=False)
    chamadas = []
    monkeypatch.setattr("app.routers.webhooks.forward_event",
                        lambda e, **kw: chamadas.append(e))

    client.post("/webhooks/c6", json={"id": "1", "status": "PAID"})
    assert chamadas == []


def test_escape_explicito_reabre(client, monkeypatch):
    """O modo antigo continua alcançável — só não é mais o default."""
    monkeypatch.delenv("WEBHOOK_TOKEN__C6", raising=False)
    monkeypatch.setenv("WEBHOOK_ALLOW_UNAUTHENTICATED", "1")
    assert client.post("/webhooks/c6", json={"id": "1", "status": "PAID"}).status_code == 200


# --- dedup de reentrega -----------------------------------------------------------

def test_reentrega_identica_nao_chega_duas_vezes_ao_consumidor(client, webhook_aberto,
                                                              monkeypatch):
    """O banco reentrega até receber 2xx. Sem dedup o consumidor dá baixa N vezes."""
    empurrados = []
    monkeypatch.setattr("app.routers.webhooks.forward_event",
                        lambda e, **kw: empurrados.append(e) or True)

    corpo = {"id": "C6-DUP", "status": "PAID"}
    primeira = client.post("/webhooks/c6", json=corpo)
    segunda = client.post("/webhooks/c6", json=corpo)

    # as duas respondem 2xx: reentrega é comportamento correto do banco
    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert primeira.json()["event"] == "cobranca.atualizada"
    assert segunda.json()["event"] == "duplicado"
    assert len(empurrados) == 1


def test_dedup_e_por_tenant(client, webhook_aberto, monkeypatch):
    """Mesmo corpo para tenants diferentes são eventos diferentes."""
    empurrados = []
    monkeypatch.setattr("app.routers.webhooks.forward_event",
                        lambda e, **kw: empurrados.append(e) or True)

    corpo = {"id": "C6-T", "status": "PAID"}
    assert client.post("/webhooks/c6/sistemaA", json=corpo).json()["event"] != "duplicado"
    assert client.post("/webhooks/c6/sistemaB", json=corpo).json()["event"] != "duplicado"
    assert len(empurrados) == 2


def test_corpos_diferentes_nao_sao_duplicados(client, webhook_aberto):
    assert client.post("/webhooks/c6", json={"id": "A", "status": "PAID"}
                       ).json()["event"] == "cobranca.atualizada"
    assert client.post("/webhooks/c6", json={"id": "B", "status": "PAID"}
                       ).json()["event"] == "cobranca.atualizada"


# --- confirmação no banco ---------------------------------------------------------

def _cofre_com_credencial(monkeypatch):
    monkeypatch.setattr("app.routers.webhooks.get_vault",
                        lambda: type("V", (), {"get_credentials": lambda s, t, p: {"client_id": "x"}})())


def test_liquidado_forjado_e_corrigido_pelo_banco(client, webhook_aberto, monkeypatch):
    """A defesa que não depende de o banco documentar assinatura: para o status
    que move dinheiro, perguntamos à fonte, e a resposta dela prevalece."""
    from app.schemas import CobrancaOut, Status

    _cofre_com_credencial(monkeypatch)
    monkeypatch.setattr("app.providers.c6.C6Provider.consultar",
                        lambda self, cid: CobrancaOut(id=cid, status=Status.pendente))

    r = client.post("/webhooks/c6/sistemaA", json={"id": "C6-FORJADO", "status": "PAID"})
    d = r.json()
    assert d["confirmado"] is False
    assert d["status"] == "pendente"  # vale o banco, não o corpo recebido


def test_liquidado_verdadeiro_sai_confirmado(client, webhook_aberto, monkeypatch):
    from app.schemas import CobrancaOut, Status

    _cofre_com_credencial(monkeypatch)
    monkeypatch.setattr("app.providers.c6.C6Provider.consultar",
                        lambda self, cid: CobrancaOut(id=cid, status=Status.liquidado))

    d = client.post("/webhooks/c6/sistemaA", json={"id": "C6-OK", "status": "PAID"}).json()
    assert d["confirmado"] is True
    assert d["status"] == "liquidado"


def test_sem_credencial_no_cofre_segue_sem_confirmar(client, webhook_aberto, monkeypatch):
    """`null` é honesto: ninguém verificou. Não inventamos `true`."""
    monkeypatch.setattr("app.routers.webhooks.get_vault",
                        lambda: type("V", (), {"get_credentials": lambda s, t, p: {}})())
    d = client.post("/webhooks/c6/sistemaA", json={"id": "C6-X", "status": "PAID"}).json()
    assert d["confirmado"] is None
    assert d["status"] == "liquidado"


def test_banco_fora_do_ar_nao_derruba_a_notificacao(client, webhook_aberto, monkeypatch):
    def explode(self, cid):
        raise RuntimeError("banco fora do ar")

    _cofre_com_credencial(monkeypatch)
    monkeypatch.setattr("app.providers.c6.C6Provider.consultar", explode)

    r = client.post("/webhooks/c6/sistemaA", json={"id": "C6-Y", "status": "PAID"})
    assert r.status_code == 200
    assert r.json()["confirmado"] is None


def test_status_nao_terminal_nao_gasta_chamada_no_banco(client, webhook_aberto, monkeypatch):
    """Só o que move dinheiro é reconsultado — `pendente` não vale uma ida ao banco."""
    chamou = []
    _cofre_com_credencial(monkeypatch)
    monkeypatch.setattr("app.providers.c6.C6Provider.consultar",
                        lambda self, cid: chamou.append(cid))

    client.post("/webhooks/c6/sistemaA", json={"id": "C6-Z", "status": "REGISTERED"})
    assert chamou == []


def test_confirmacao_desligavel(client, webhook_aberto, monkeypatch):
    chamou = []
    _cofre_com_credencial(monkeypatch)
    monkeypatch.setenv("WEBHOOK_CONFIRM", "0")
    monkeypatch.setattr("app.providers.c6.C6Provider.consultar",
                        lambda self, cid: chamou.append(cid))

    d = client.post("/webhooks/c6/sistemaA", json={"id": "C6-W", "status": "PAID"}).json()
    assert chamou == []
    assert d["confirmado"] is None


# --- outbox na resposta -----------------------------------------------------------

def test_push_que_falha_marca_pendente_de_entrega(client, webhook_aberto, monkeypatch):
    """`pendente_de_entrega` distingue "ninguém quis" de "vai sair de novo"."""
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    monkeypatch.setattr("app.routers.webhooks.forward_event", lambda e, **kw: False)

    d = client.post("/webhooks/c6", json={"id": "C6-P", "status": "REGISTERED"}).json()
    assert d["pendente_de_entrega"] is True


def test_sem_consumidor_configurado_nao_marca_pendencia(client, webhook_aberto, monkeypatch):
    """Sem destino não há o que entregar — não é pendência."""
    monkeypatch.delenv("EVENT_WEBHOOK_URL", raising=False)
    d = client.post("/webhooks/c6", json={"id": "C6-Q", "status": "REGISTERED"}).json()
    assert d["pendente_de_entrega"] is None
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 0


def test_falha_no_processamento_libera_a_marca(client, webhook_aberto, monkeypatch):
    """A marca do dedup é RESERVA, não recibo. Se o processamento morre, a
    reentrega do banco tem de conseguir tentar de novo — senão um payload que
    quebre a normalização vira evento perdido: 500 na primeira, `duplicado` em
    todas as seguintes."""
    from app.providers.c6 import C6Provider

    original = C6Provider.normalizar_webhook
    chamadas = []

    def explode_na_primeira(self, headers, body):
        chamadas.append(body)
        if len(chamadas) == 1:
            raise RuntimeError("normalização quebrou")
        return original(self, headers, body)

    monkeypatch.setattr(C6Provider, "normalizar_webhook", explode_na_primeira)

    corpo = {"id": "C6-RETRY", "status": "PAID"}
    with pytest.raises(RuntimeError):
        client.post("/webhooks/c6", json=corpo)

    # a reentrega do banco não é descartada como duplicada
    r = client.post("/webhooks/c6", json=corpo)
    assert r.status_code == 200
    assert r.json()["event"] == "cobranca.atualizada"


# --- revisao de /webhooks ---------------------------------------------------------

@pytest.mark.parametrize("rota", ["/webhooks/C6", "/webhooks/C6/empresa1",
                                  "/webhooks/Sicoob", "/webhooks/INTER"])
def test_slug_do_banco_em_maiuscula_nao_engole_o_evento(client, webhook_aberto, rota):
    """O pior caminho: `_check_token` faz `.upper()` e o token BATIA, enquanto o
    `_NORMALIZERS.get("C6")` devolvia None -- o evento virava `ignorado` com
    200. Uma maiuscula na URL cadastrada no banco e toda liquidacao sumia."""
    r = client.post(rota, json={"id": "BOL-1", "status": "PAID"})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("corpo,esperado", [
    ("texto", "str"), ([1, 2, 3], "list"), (42, "int"), (True, "bool")])
def test_json_valido_de_forma_errada_nao_da_500(client, webhook_aberto, corpo, esperado):
    """`"texto"` e `[1,2,3]` estouravam dentro do normalizador: 500 nao-JSON, e o
    banco reentregando em loop um payload que nunca ia funcionar. Mesma familia
    dos 500 corrigidos nas rotas /api/*."""
    r = client.post("/webhooks/c6", json=corpo)
    assert r.status_code == 422, r.text
    assert esperado in r.json()["detail"]


def test_corpo_vazio_nao_vira_evento_de_nada(client, webhook_aberto):
    """`{}` produzia `cobranca.atualizada` com todos os campos nulos -- e esse
    evento era empurrado ao consumidor ASSINADO PELA NOSSA CHAVE."""
    r = client.post("/webhooks/c6", json={})
    assert r.status_code == 422, r.text
    assert "vazio" in r.json()["detail"]


def test_corpo_valido_continua_passando(client, webhook_aberto):
    r = client.post("/webhooks/c6", json={"id": "BOL-9", "status": "PAID"})
    assert r.status_code == 200, r.text
    assert r.json()["event"] == "cobranca.atualizada"


def test_a_spec_lista_os_bancos_que_notificam(client):
    """O slug era `str` livre: o Swagger nao dizia quais valem."""
    spec = client.get("/openapi.json").json()["paths"]
    for rota in ("/webhooks/{banco}", "/webhooks/{banco}/{tenant_id}"):
        banco = next(p for p in spec[rota]["post"]["parameters"] if p["name"] == "banco")
        assert banco["schema"]["$ref"].endswith("BancoEmissor")
    enum = client.get("/openapi.json").json()["components"]["schemas"]["BancoEmissor"]["enum"]
    assert sorted(enum) == ["c6", "inter", "sicoob"]
