import httpx
import pytest
import respx

from app.core import forwarder, outbox


@pytest.fixture
def sem_espera(monkeypatch):
    """Backoff zero — o teste quer a mecânica da fila, não o relógio."""
    monkeypatch.setattr(outbox, "BACKOFF", (0, 0, 0))


# --- o evento deixa de sumir ------------------------------------------------------

@respx.mock
def test_falha_de_entrega_vai_para_a_fila(monkeypatch):
    """Era o TODO do forwarder: consumidor fora do ar por 30s e o evento SUMIA."""
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    respx.post("https://consumidor.test/hook").mock(return_value=httpx.Response(500))

    assert forwarder.forward_event({"event": "cobranca.atualizada", "id": "X1"}) is False
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 1


@respx.mock
def test_erro_de_rede_tambem_enfileira(monkeypatch):
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    respx.post("https://consumidor.test/hook").mock(side_effect=httpx.ConnectError("recusado"))

    assert forwarder.forward_event({"event": "x"}) is False
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 1


@respx.mock
def test_entrega_de_primeira_nao_enfileira(monkeypatch):
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    respx.post("https://consumidor.test/hook").mock(return_value=httpx.Response(200))

    assert forwarder.forward_event({"event": "x"}) is True
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 0


def test_sem_destino_nao_enfileira(monkeypatch):
    monkeypatch.delenv("EVENT_WEBHOOK_URL", raising=False)
    assert forwarder.forward_event({"event": "x"}) is False
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 0


# --- re-tentativa -----------------------------------------------------------------

@respx.mock
def test_consumidor_volta_e_o_evento_sai(monkeypatch, sem_espera):
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    rota = respx.post("https://consumidor.test/hook")

    rota.mock(return_value=httpx.Response(503))
    forwarder.forward_event({"event": "cobranca.atualizada", "id": "X9"})
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 1

    rota.mock(return_value=httpx.Response(200))
    assert outbox.drenar(forwarder.entregar) == 1
    assert outbox.get_outbox().contar(outbox.PENDENTE) == 0
    assert outbox.get_outbox().contar(outbox.ENTREGUE) == 1


@respx.mock
def test_a_assinatura_continua_valida_na_re_tentativa(monkeypatch, sem_espera):
    """O outbox guarda o CORPO serializado, não o dict: reserializar poderia
    trocar a ordem das chaves e invalidar a assinatura que o consumidor confere."""
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    monkeypatch.setenv("EVENT_WEBHOOK_SECRET", "segredo")
    rota = respx.post("https://consumidor.test/hook")

    rota.mock(return_value=httpx.Response(500))
    forwarder.forward_event({"event": "cobranca.atualizada", "id": "X2", "status": "liquidado"})
    corpo_primeira = rota.calls.last.request.content

    rota.mock(return_value=httpx.Response(200))
    outbox.drenar(forwarder.entregar)
    reenvio = rota.calls.last.request

    assert reenvio.content == corpo_primeira
    assert reenvio.headers["x-signature"] == forwarder.sign(reenvio.content, "segredo")


@respx.mock
def test_desiste_depois_do_limite(monkeypatch, sem_espera):
    """A fila não cresce para sempre: destino morto vira `desistiu`, com o
    último erro guardado para quem for investigar."""
    monkeypatch.setenv("EVENT_WEBHOOK_URL", "https://consumidor.test/hook")
    respx.post("https://consumidor.test/hook").mock(return_value=httpx.Response(500))

    forwarder.forward_event({"event": "x"})  # tentativa 1 (inline)
    for _ in range(outbox.max_tentativas()):
        outbox.drenar(forwarder.entregar)

    ob = outbox.get_outbox()
    assert ob.contar(outbox.PENDENTE) == 0
    assert ob.contar(outbox.DESISTIU) == 1


@respx.mock
def test_um_destino_ruim_nao_trava_a_fila(monkeypatch, sem_espera):
    """O drenador não pode morrer no primeiro item que explode."""
    monkeypatch.setenv("EVENT_WEBHOOK_SECRET", "")
    ob = outbox.get_outbox()
    ob.enfileirar(url="https://morto.test/hook", secret="", corpo=b'{"event":"a"}')
    ob.enfileirar(url="https://vivo.test/hook", secret="", corpo=b'{"event":"b"}')

    respx.post("https://morto.test/hook").mock(side_effect=httpx.ConnectError("nada"))
    respx.post("https://vivo.test/hook").mock(return_value=httpx.Response(200))

    assert outbox.drenar(forwarder.entregar) == 1
    assert ob.contar(outbox.ENTREGUE) == 1
    assert ob.contar(outbox.PENDENTE) == 1


def test_backoff_respeita_a_espera(monkeypatch):
    """Sem o `sem_espera`: recém-enfileirado não é drenado no mesmo instante."""
    ob = outbox.get_outbox()
    ob.enfileirar(url="https://x.test/h", secret="", corpo=b"{}")
    assert ob.pendentes() == []


# --- dedup da entrada -------------------------------------------------------------

def test_ja_visto_e_verdadeiro_so_na_segunda():
    ob = outbox.get_outbox()
    marca = outbox.impressao("c6", "t1", b'{"id":"1"}')
    assert ob.ja_visto(marca, "c6", "t1") is False
    assert ob.ja_visto(marca, "c6", "t1") is True


def test_impressao_separa_banco_tenant_e_corpo():
    corpo = b'{"id":"1"}'
    assert outbox.impressao("c6", "t1", corpo) != outbox.impressao("sicoob", "t1", corpo)
    assert outbox.impressao("c6", "t1", corpo) != outbox.impressao("c6", "t2", corpo)
    assert outbox.impressao("c6", "t1", corpo) != outbox.impressao("c6", "t1", b'{"id":"2"}')


def test_impressao_nao_confunde_fronteira_de_campo():
    """Os campos são separados por NUL — sem isso, ("ab","c") e ("a","bc")
    colidiriam e uma notificação de outro banco viraria duplicada."""
    assert outbox.impressao("ab", "c", b"{}") != outbox.impressao("a", "bc", b"{}")


# --- limpeza por idade ------------------------------------------------------------

def _envelhecer(caminho, tabela, coluna, dias):
    """Empurra todas as linhas da tabela para o passado."""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    velho = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    with sqlite3.connect(caminho) as c:
        c.execute(f"UPDATE {tabela} SET {coluna} = ?", (velho,))


def test_inbox_antigo_e_apagado(monkeypatch, tmp_path):
    """A janela de dedup só precisa cobrir a reentrega do banco, que é de horas.
    Sem limpeza, cada notificação recebida deixa uma linha para sempre."""
    ob = outbox.get_outbox()
    ob.ja_visto(outbox.impressao("c6", "t1", b'{"a":1}'), "c6", "t1")
    _envelhecer(ob.path, "webhook_inbox", "visto_em", dias=30)

    assert outbox.limpar()["inbox"] == 1
    # apagada a marca, a mesma notificação volta a ser tratada como nova
    assert ob.ja_visto(outbox.impressao("c6", "t1", b'{"a":1}'), "c6", "t1") is False


def test_inbox_recente_sobrevive():
    ob = outbox.get_outbox()
    ob.ja_visto(outbox.impressao("c6", "t1", b'{"a":1}'), "c6", "t1")
    assert outbox.limpar()["inbox"] == 0


def test_outbox_entregue_antigo_sai_e_pendente_fica(sem_espera):
    """`pendente` nunca é apagado por idade: ainda tem trabalho a fazer.
    Destino morto por semanas não pode virar evento descartado em silêncio."""
    ob = outbox.get_outbox()
    entregue = ob.enfileirar(url="https://a.test/h", secret="", corpo=b'{"e":"a"}')
    ob.enfileirar(url="https://b.test/h", secret="", corpo=b'{"e":"b"}')
    ob.marcar_entregue(entregue)
    _envelhecer(ob.path, "webhook_outbox", "atualizado_em", dias=90)

    assert outbox.limpar()["outbox"] == 1
    assert ob.contar(outbox.PENDENTE) == 1
    assert ob.contar(outbox.ENTREGUE) == 0


def test_desistiu_antigo_tambem_sai(sem_espera, monkeypatch):
    ob = outbox.get_outbox()
    evento = ob.enfileirar(url="https://a.test/h", secret="", corpo=b"{}")
    for _ in range(outbox.max_tentativas()):
        ob.marcar_falha(evento, "morto")
    assert ob.contar(outbox.DESISTIU) == 1

    _envelhecer(ob.path, "webhook_outbox", "atualizado_em", dias=90)
    assert outbox.limpar()["outbox"] == 1


def test_retencao_configuravel(monkeypatch):
    ob = outbox.get_outbox()
    ob.ja_visto(outbox.impressao("c6", "t1", b"{}"), "c6", "t1")
    _envelhecer(ob.path, "webhook_inbox", "visto_em", dias=3)

    monkeypatch.setenv("WEBHOOK_INBOX_RETENCAO_DIAS", "10")
    assert outbox.limpar()["inbox"] == 0  # 3 dias ainda está dentro de 10

    monkeypatch.setenv("WEBHOOK_INBOX_RETENCAO_DIAS", "1")
    assert outbox.limpar()["inbox"] == 1


def test_retencao_invalida_cai_no_default(monkeypatch):
    """Env com lixo não pode apagar tudo nem travar a manutenção."""
    monkeypatch.setenv("WEBHOOK_INBOX_RETENCAO_DIAS", "ontem")
    ob = outbox.get_outbox()
    ob.ja_visto(outbox.impressao("c6", "t1", b"{}"), "c6", "t1")
    assert outbox.limpar()["inbox"] == 0


def test_limpar_cobre_as_tres_tabelas():
    contas = outbox.limpar()
    assert set(contas) == {"inbox", "outbox", "idempotencia"}


def test_chave_de_idempotencia_antiga_sai():
    """Uma chave só é útil enquanto o link que ela criou for útil — o do C6
    expira em 7 dias. Passada a retenção, a mesma chave cria um checkout novo."""
    from app.core import idempotency

    store = idempotency.get_idempotency_store()
    marca = idempotency.impressao({"valor": "150.00"})
    store.guardar("empresa1", "checkout", "venda-42", marca, {"id": "chk_1", "status": "pendente"})
    assert store.buscar("empresa1", "checkout", "venda-42", marca) is not None

    _envelhecer(store.path, "idempotencia", "criado_em", dias=90)
    assert outbox.limpar()["idempotencia"] == 1
    assert store.buscar("empresa1", "checkout", "venda-42", marca) is None
