# Checkout C6 — link de pagamento com cartao.
#
# Cobre os cenarios BC-081..BC-087 e NEG-008..NEG-011 da matriz de
# rastreabilidade em postman/README.md (secao "Cartao no C6").
#
# Nao ha e2e de pagamento: ninguem paga link de cartao por script -- o PAN e
# digitado na pagina do C6, e e exatamente isso que a decisao 3 quer. Chegar a
# PAID e roteiro manual de homologacao. Aqui fica o que da para afirmar sem
# banco: payload, mapeamento de status e as restricoes que a decisao 3 exige que
# sejam CODIGO, nao paragrafo.
import pytest

from app.schemas import Status


@pytest.fixture
def c6_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")


def _capture(monkeypatch, response=None):
    calls = []

    def fake_request(self, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json, "params": params})
        return response or {}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)
    return calls


def _body(**ck):
    base = {"valor": "150.00"}
    base.update(ck)
    return {"tenant_id": "empresa1", "provider": "c6", "checkout": base}


_CRIADO = {"id": "chk_1", "url": "https://checkout.c6bank.info/chk_1",
           "status": "CREATED", "expiration_date_time": "2026-08-10T12:00:00"}


# --- BC-081 · criar link ----------------------------------------------------------

def test_criar_link_devolve_url(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(descricao="Pedido 42"))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["url"] == "https://checkout.c6bank.info/chk_1"
    assert data["status"] == "pendente"  # CREATED nao e "registrado": nada foi pago
    sent = calls[0]["json"]
    assert calls[0]["path"] == "/v1/checkouts/"
    assert sent["amount"] == 150.0
    assert sent["payment"]["card"] == {"type": "CREDIT", "installments": 1}
    assert "pix" not in sent["payment"]  # so quando pedido


# --- BC-082 · Pix no mesmo link ---------------------------------------------------

def test_pix_no_mesmo_link_usa_chave_auto(client, c6_env, monkeypatch):
    """O spec do C6 so aceita key=AUTO no checkout: o QR e gerado pelo banco.
    Nao ha chave do cliente para passar aqui, ao contrario do Bolepix."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(pix=True))
    assert r.status_code == 201, r.text
    assert calls[0]["json"]["payment"]["pix"] == {"key": "AUTO"}


# --- BC-083 · consultar -----------------------------------------------------------

@pytest.mark.parametrize("c6,normalizado", [
    ("CREATED", Status.pendente),
    ("IN PROGRESS", Status.pendente),
    ("AUTHORIZED, CONFIRMATION PENDING", Status.pendente),
    ("CONFIRMATION REQUESTED", Status.pendente),
    ("CANCELLATION REQUESTED", Status.pendente),
    ("PAID", Status.liquidado),
    ("CANCELLED", Status.baixado),
    ("EXPIRED", Status.expirado),
    ("DECLINED", Status.erro),
    ("ERROR", Status.erro),
])
def test_consultar_normaliza_todo_status_do_spec(client, c6_env, monkeypatch, c6, normalizado):
    """Os dez status do spec cabem no enum -- nenhum status novo foi preciso.

    DECLINED e ERROR viram `erro`, nao `baixado`: baixado afirma que a cobranca
    foi encerrada, e cartao recusado nao encerrou nada -- o link se esgotou, a
    divida nao."""
    _capture(monkeypatch, {"id": "chk_1", "status": c6})
    r = client.get("/checkout/chk_1", params={"tenant_id": "empresa1"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == normalizado.value


# --- BC-084 · cancelar ------------------------------------------------------------

def test_cancelar_usa_put_e_devolve_baixado(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, {})
    r = client.delete("/checkout/chk_1", params={"tenant_id": "empresa1"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "baixado"
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/v1/checkouts/chk_1/cancel"


# --- BC-085 · parcelado -----------------------------------------------------------

def test_parcelado_traduz_juros_por_para_interest_type(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(parcelas=6, juros_por="loja"))
    assert r.status_code == 201, r.text
    card = calls[0]["json"]["payment"]["card"]
    assert card["installments"] == 6
    assert card["interest_type"] == "BY_SELLER"


def test_juros_por_default_e_loja(client, c6_env, monkeypatch):
    """Decisao 1: BY_SELLER e o default, para o chamador nao precisar repeti-lo
    em toda requisicao. Quem quiser o contrario manda juros_por=emissor."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(parcelas=3))
    assert r.status_code == 201, r.text
    assert calls[0]["json"]["payment"]["card"]["interest_type"] == "BY_SELLER"


def test_emissor_traduz_para_by_issuer(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(parcelas=3, juros_por="emissor"))
    assert r.status_code == 201, r.text
    assert calls[0]["json"]["payment"]["card"]["interest_type"] == "BY_ISSUER"


def test_a_vista_nao_manda_interest_type(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(parcelas=1))
    assert r.status_code == 201, r.text
    assert "interest_type" not in calls[0]["json"]["payment"]["card"]


def test_debito_traduz_tipo(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(tipo="debito"))
    assert r.status_code == 201, r.text
    assert calls[0]["json"]["payment"]["card"]["type"] == "DEBIT"


# --- NEG-008 · capacidade por provider --------------------------------------------

def test_provider_sem_link_hospedado_recebe_422_dizendo_para_onde_ir(client, monkeypatch):
    """Decisao 4: cartao existe onde a instituicao OFERECE. Quem nao oferece
    responde 422 pelo exige_capacidade, como ja acontece com o Bolepix -- nao 500,
    nao silencio."""
    monkeypatch.setenv("VAULT__empresa1__sicoob__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__sicoob__client_secret", "sec")
    monkeypatch.setenv("SICOOB_REGISTERED_READY", "true")
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json={"tenant_id": "empresa1", "provider": "sicoob",
                                       "checkout": {"valor": "150.00"}})
    assert r.status_code == 422, r.text
    assert "c6" in r.json()["detail"].lower()
    assert calls == []


# --- NEG-009 / NEG-010 · a decisao 3 como codigo ----------------------------------

@pytest.mark.parametrize("campo,valor", [
    ("save_card", True),          # NEG-009 — tokenizar e guardar meio de pagamento
    ("capture", False),           # captura em duas fases, fora de escopo
    ("captured_amount", 100),     # idem
    ("public_key", "x"),          # NEG-010 — checkout transparente
    ("card_number", "4111"),      # PAN no nosso dominio
])
def test_campo_fora_de_escopo_e_recusado_e_nao_chega_ao_banco(client, c6_env, monkeypatch, campo, valor):
    """A decisao 3 so e real se o campo NAO existir no schema.

    Se o corpo fosse repassado sem filtro, bastaria um chamador mandar
    save_card=true para o token entrar no fluxo -- e a decisao de nao guardar
    dado de cartao teria sido revogada por um cliente, sem ninguem revisar.
    Documentar nao segura isso; ausencia de campo, sim."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(**{campo: valor}))
    assert r.status_code == 422, r.text
    assert calls == []


def test_nao_existe_rota_de_checkout_transparente(client):
    """NEG-010: /authorize, /capture e /generate/public-key existem no spec do C6
    e NAO sao expostos -- decisao de produto, nao limitacao."""
    for rota in ("/checkout/authorize", "/checkout/chk_1/capture",
                 "/checkout/generate/public-key"):
        r = client.post(rota, json={})
        assert r.status_code in (404, 405), f"{rota} respondeu {r.status_code}"


# --- NEG-011 · parcelamento sem juros_por -----------------------------------------

def test_parcelado_com_juros_por_nulo_e_422_nosso(client, c6_env, monkeypatch):
    """O C6 exige interest_type quando installments > 1. Anular explicitamente e
    o unico jeito de chegar sem ele -- e a recusa e 422 daqui, nao 400 do banco."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(parcelas=6, juros_por=None))
    assert r.status_code == 422, r.text
    assert calls == []


# --- endereço do pagador (a armadilha já conhecida do Bolepix) --------------------

def test_pagador_sem_endereco_completo_recusa_antes_do_banco(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(
        pagador={"nome": "Jose", "documento": "12345678909",
                 "endereco": {"logradouro": "Av. X", "numero": 100, "cidade": "Sete Lagoas"}}))
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert "state" in detalhe and "zip_code" in detalhe
    assert "city" not in detalhe  # alias pt-BR aceito
    assert calls == []


def test_number_do_endereco_precisa_ser_numerico(client, c6_env, monkeypatch):
    """O spec declara number como number. Texto vira 400 do banco; recusamos antes."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(
        pagador={"nome": "Jose", "documento": "12345678909",
                 "endereco": {"street": "Av. X", "number": "sem numero", "city": "SP",
                              "state": "SP", "zip_code": "01000000"}}))
    assert r.status_code == 422, r.text
    assert "num" in r.json()["detail"].lower()
    assert calls == []


def test_pagador_completo_vai_com_number_inteiro(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(
        pagador={"nome": "Jose", "documento": "12345678909",
                 "endereco": {"logradouro": "Av. X", "numero": "100", "cidade": "Sete Lagoas",
                              "uf": "MG", "cep": "35700000", "email": "j@x.com"}}))
    assert r.status_code == 201, r.text
    payer = calls[0]["json"]["payer"]
    assert payer["address"]["number"] == 100  # convertido, nao repassado como texto
    assert payer["address"]["city"] == "Sete Lagoas"
    assert payer["email"] == "j@x.com"


# --- BC-086 / BC-087 · webhook ----------------------------------------------------

def test_webhook_do_banco_aceita_service_checkout(client, c6_env, monkeypatch):
    """BC-086: a notificacao do checkout nao vem por callback proprio da API de
    Checkout -- o spec nao tem webhook. Vem pelo cadastro generico, com
    service=CHECKOUT. O roteiro v3.0 do banco confirma (caso C_04)."""
    calls = _capture(monkeypatch, {"id": "wh_1"})
    r = client.post("/config/webhook-banco", json={
        "tenant_id": "empresa1", "provider": "c6",
        "url": "https://meu.app/webhooks/c6", "service": "CHECKOUT"})
    assert r.status_code in (200, 201), r.text
    assert calls[0]["json"]["service"] == "CHECKOUT"


# --- BC-087 · recepcao do evento de checkout --------------------------------------

_STATUS_CHECKOUT = [
    ("CREATED", "pendente"), ("IN PROGRESS", "pendente"),
    ("AUTHORIZED, CONFIRMATION PENDING", "pendente"),
    ("CONFIRMATION REQUESTED", "pendente"), ("CANCELLATION REQUESTED", "pendente"),
    ("PAID", "liquidado"), ("CANCELLED", "baixado"), ("EXPIRED", "expirado"),
    ("DECLINED", "erro"), ("ERROR", "erro"),
]


@pytest.mark.parametrize("c6,esperado", _STATUS_CHECKOUT)
def test_webhook_de_checkout_normaliza_os_dez_status(client, webhook_aberto, c6, esperado):
    """O evento do checkout usava o mapa do BOLETO.

    Os tres que acertavam -- PAID, CANCELLED, EXPIRED -- acertavam por
    coincidencia de vocabulario; DECLINED, ERROR e os intermediarios chegavam ao
    consumidor com status NULO. Cartao recusado tem de chegar como `erro`."""
    r = client.post("/webhooks/c6", json={
        "id": "chk_1", "status": c6, "amount": 150.0,
        "emission_date_time": "2026-08-03T21:00:00",
        "expiration_date_time": "2026-08-10T21:00:00",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == esperado


def test_webhook_de_checkout_tem_evento_proprio(client, webhook_aberto):
    """`checkout.atualizado` distingue de boleto: o consumidor nao deveria
    precisar inspecionar o corpo para saber o que chegou."""
    r = client.post("/webhooks/c6", json={
        "id": "chk_1", "status": "PAID", "amount": 150.0,
        "expiration_date_time": "2026-08-10T21:00:00"})
    assert r.json()["event"] == "checkout.atualizado"


def test_webhook_de_criacao_de_checkout_e_reconhecido_sem_status_nem_data(client, webhook_aberto):
    """Corpo real que o C6 devolve ao criar o link: so `id` e `url`.

    A homologacao reentregou esse corpo na rota de webhook e ele saiu como
    `cobranca.atualizada` com status nulo -- a discriminacao exigia data de
    checkout, que a criacao nao traz. Boleto nao tem link de pagamento, entao a
    `url` sozinha ja decide."""
    r = client.post("/webhooks/c6", json={
        "id": "5d6464db-4d81-4dd1-a7d5-063b1f957a78",
        "url": "https://payment-h.c6pay.com.br/payment/5d6464db",
    })
    assert r.status_code == 200, r.text
    assert r.json()["event"] == "checkout.atualizado"


def test_webhook_de_boleto_nao_e_confundido_com_checkout(client, webhook_aberto):
    """A discriminacao e por formato, entao o caminho do boleto tem de seguir
    intacto -- inclusive quando o status coincide (PAID vale nos dois)."""
    r = client.post("/webhooks/c6", json={
        "id": "01K", "status": "PAID", "amount": 10.0, "due_date": "2026-09-03",
        "digitable_line": "336x", "bar_code": "336y", "our_number": "123",
        "payments": [{"date": "2026-08-03T10:00:00", "amount": 10.0}],
    })
    assert r.json()["event"] == "cobranca.atualizada"
    assert r.json()["status"] == "liquidado"


# --- idempotencia -----------------------------------------------------------------

def test_reenvio_com_a_mesma_chave_devolve_o_mesmo_link(client, c6_env, monkeypatch):
    """Duplo clique no botao criava DOIS links para a mesma venda, e nada impede
    o pagador de pagar os dois. Com a chave, o segundo POST nem chega no banco."""
    calls = _capture(monkeypatch, _CRIADO)
    corpo = _body(descricao="Pedido 42")
    cab = {"Idempotency-Key": "venda-42"}

    primeira = client.post("/checkout", json=corpo, headers=cab)
    segunda = client.post("/checkout", json=corpo, headers=cab)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json() == primeira.json()
    assert len(calls) == 1  # o banco viu UMA criacao


def test_mesma_chave_com_outro_corpo_e_recusada(client, c6_env, monkeypatch):
    """A chave identifica UMA requisicao. Reaproveita-la com outro payload e bug
    de quem chama -- devolver o link errado seria pior que recusar."""
    _capture(monkeypatch, _CRIADO)
    cab = {"Idempotency-Key": "venda-42"}

    client.post("/checkout", json=_body(valor="150.00"), headers=cab)
    r = client.post("/checkout", json=_body(valor="999.00"), headers=cab)

    assert r.status_code == 422
    assert "venda-42" in r.json()["detail"]


def test_chaves_diferentes_criam_links_diferentes(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    corpo = _body(descricao="Pedido 42")

    client.post("/checkout", json=corpo, headers={"Idempotency-Key": "venda-42"})
    client.post("/checkout", json=corpo, headers={"Idempotency-Key": "venda-43"})

    assert len(calls) == 2


def test_sem_chave_continua_criando(client, c6_env, monkeypatch):
    """O header e opt-in: quem nao manda mantem o comportamento de sempre."""
    calls = _capture(monkeypatch, _CRIADO)
    corpo = _body(descricao="Pedido 42")

    client.post("/checkout", json=corpo)
    client.post("/checkout", json=corpo)

    assert len(calls) == 2


def test_idempotencia_e_por_tenant(client, monkeypatch):
    """Chave igual em tenants diferentes sao pedidos diferentes."""
    monkeypatch.setenv("VAULT__empresa1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__c6__client_secret", "sec")
    monkeypatch.setenv("VAULT__empresa2__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa2__c6__client_secret", "sec")
    monkeypatch.setenv("C6_REGISTERED_READY", "true")
    calls = _capture(monkeypatch, _CRIADO)
    cab = {"Idempotency-Key": "venda-42"}

    client.post("/checkout", json=_body(), headers=cab)
    corpo2 = _body()
    corpo2["tenant_id"] = "empresa2"
    client.post("/checkout", json=corpo2, headers=cab)

    assert len(calls) == 2


def test_credencial_no_request_nao_muda_a_identidade_do_pedido(client, c6_env, monkeypatch):
    """A impressao e do `checkout`, nao do corpo inteiro: a mesma venda reenviada
    com a credencial vindo por outro caminho continua sendo a mesma venda."""
    calls = _capture(monkeypatch, _CRIADO)
    cab = {"Idempotency-Key": "venda-42"}

    client.post("/checkout", json=_body(descricao="X"), headers=cab)
    com_cred = _body(descricao="X")
    com_cred["credentials"] = {"client_id": "cid", "client_secret": "sec"}
    r = client.post("/checkout", json=com_cred, headers=cab)

    assert r.status_code == 201
    assert len(calls) == 1


# --- revisao de /checkout ---------------------------------------------------------

def test_criacao_devolve_location_que_o_cliente_consegue_seguir(client, c6_env, monkeypatch):
    """O 201 devolvia `id` e mais nada: montar a URL de consulta ficava por conta
    de quem chama, adivinhando que `tenant_id`, `provider` e `banco` sao
    obrigatorios la. Mesma correcao feita em /cobranca e /pix -- e aqui o teste
    SEGUE o header, que e o unico jeito de saber que ele funciona."""
    _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json={"tenant_id": "empresa1", "provider": "on",
                                       "banco": "c6", "checkout": {"valor": "150.00"}})
    assert r.status_code == 201, r.text
    destino = r.headers["location"]
    assert destino.startswith("/checkout/chk_1?")
    seguido = client.get(destino)
    assert seguido.status_code == 200, f"{destino} -> {seguido.status_code} {seguido.text}"
    assert seguido.json()["id"] == "chk_1"


def test_mesma_chave_em_outro_banco_nao_devolve_o_link_do_primeiro(client, monkeypatch):
    """A impressao era so do `checkout`: `banco` e `provider` ficavam de fora.

    Mesma chave, mesmo valor, OUTRO banco devolvia 201 com o link do primeiro e
    nunca chamava o segundo -- a venda parecia ter ido para uma instituicao que
    nao viu o pedido. Destino e identidade do pedido, nao detalhe de transporte."""
    for banco in ("c6", "sicoob"):
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_id", "cid")
        monkeypatch.setenv(f"VAULT__empresa1__{banco}__client_secret", "sec")
        monkeypatch.setenv(f"{banco.upper()}_REGISTERED_READY", "true")
    calls = _capture(monkeypatch, _CRIADO)
    cab = {"Idempotency-Key": "k-banco"}
    corpo = {"tenant_id": "empresa1", "provider": "on", "banco": "c6",
             "checkout": {"valor": "10.00"}}

    assert client.post("/checkout", json=corpo, headers=cab).status_code == 201
    r = client.post("/checkout", json={**corpo, "banco": "sicoob"}, headers=cab)

    assert r.status_code == 422, r.text
    assert len(calls) == 1


@pytest.mark.parametrize("valor", ["0", "0.00", "-10.00"])
def test_valor_zero_ou_negativo_nao_vira_link_de_pagamento(client, c6_env, monkeypatch, valor):
    """`amount: -10.0` chegava a sair daqui para o banco. Link de pagamento com
    valor nulo ou negativo nao e pedido possivel -- e a recusa e daqui, com o
    nome do campo, nao um 400 do banco traduzido em 422 generico."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(valor=valor))
    assert r.status_code == 422, r.text
    assert calls == []


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<script>x</script>",
                                 "nao-e-url"])
def test_redirect_url_sem_esquema_navegavel_e_recusada(client, c6_env, monkeypatch, url):
    """Esta URL nao fica aqui: o banco a publica na pagina DELE, na frente de
    quem esta digitando o cartao. Repassar `javascript:` era deixar esta API
    escolher o que roda no dominio do banco."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json=_body(redirect_url=url))
    assert r.status_code == 422, r.text
    assert calls == []


def test_redirect_url_http_e_https_passam(client, c6_env, monkeypatch):
    calls = _capture(monkeypatch, _CRIADO)
    for url in ("https://loja.com.br/ok", "http://localhost:8080/ok"):
        r = client.post("/checkout", json=_body(redirect_url=url))
        assert r.status_code == 201, r.text
    assert [c["json"]["redirect_url"] for c in calls] == [
        "https://loja.com.br/ok", "http://localhost:8080/ok"]


@pytest.mark.parametrize("campo,valor", [
    ("save_card", True), ("card_number", "4111111111111111"), ("public_key", "x"),
])
def test_campo_fora_de_escopo_no_topo_do_corpo_tambem_e_recusado(client, c6_env, monkeypatch,
                                                                 campo, valor):
    """O `extra=forbid` so existia dentro de `checkout`. No nivel de cima o campo
    era engolido com 201: o chamador concluia que mandou o PAN e que a API
    aceitou. A promessa de que dado de cartao nao existe aqui so vale se o campo
    for RECUSADO."""
    calls = _capture(monkeypatch, _CRIADO)
    r = client.post("/checkout", json={"tenant_id": "empresa1", "provider": "c6",
                                       "checkout": {"valor": "1.00"}, campo: valor})
    assert r.status_code == 422, r.text
    assert calls == []


def test_o_422_de_campo_recusado_nao_devolve_o_valor(client, c6_env):
    """Recusar `card_number` e devolve-lo inteiro no corpo do erro troca um
    problema por outro: o PAN sai daqui para o log de quem chamou. O nome do
    campo basta para corrigir; o valor quem enviou ja tem."""
    pan = "4111111111111111"
    r = client.post("/checkout", json={"tenant_id": "empresa1", "provider": "c6",
                                       "checkout": {"valor": "1.00"}, "card_number": pan})
    assert r.status_code == 422
    assert pan not in r.text
    assert "card_number" in r.text
