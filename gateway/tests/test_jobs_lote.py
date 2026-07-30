# Jobs de lote assíncrono (Fase 1): 202 + job_id, itens rastreáveis, estados,
# idempotência e persistência. TestClient executa BackgroundTasks ao sair do
# contexto da request — o job já está concluído na resposta seguinte.
import json

import pytest

from app.core import job_store as js

DADOS_BB = {
    "valor": 150.0, "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181", "sacado": "Joao da Silva",
    "sacado_documento": "52998224725", "agencia": "3073",
    "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
    "nosso_numero": "123", "data_vencimento": "2027-12-30", "bank": "banco_brasil",
}


@pytest.fixture(autouse=True)
def _db_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_cria_job_202_e_processa_em_background(client):
    body = {"tenant_id": "empresa1", "boletos": [DADOS_BB, {**DADOS_BB, "nosso_numero": "124"}]}
    r = client.post("/jobs/boletos", json=body)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert r.json()["status"] == js.JOB_RECEIVED and r.json()["recebidos"] == 2

    j = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["status"] == js.JOB_COMPLETED
    assert j["total"] == 2 and j["completed"] == 2 and j["failed"] == 0


def test_item_invalido_nao_cancela_o_job(client):
    body = {"tenant_id": "empresa1",
            "boletos": [DADOS_BB, {"bank": "banco_brasil", "external_id": "RUIM"}]}
    job_id = client.post("/jobs/boletos", json=body).json()["job_id"]

    j = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["status"] == js.JOB_PARTIAL
    assert j["completed"] == 1 and j["failed"] == 1

    falhas = client.get(f"/jobs/boletos/{job_id}/items",
                        params={"tenant_id": "empresa1", "status": "failed"}).json()
    assert falhas["items"][0]["item_id"] == "RUIM"
    assert falhas["items"][0]["resultado"]["errors"]


def test_job_falha_quando_nenhum_item_e_valido(client):
    body = {"tenant_id": "empresa1", "boletos": [{"bank": "banco_brasil"}]}
    job_id = client.post("/jobs/boletos", json=body).json()["job_id"]
    j = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["status"] == js.JOB_FAILED and j["failed"] == 1


def test_idempotencia_devolve_o_mesmo_job(client):
    body = {"tenant_id": "empresa1", "boletos": [DADOS_BB]}
    h = {"Idempotency-Key": "lote-2026-07-25-A"}
    r1 = client.post("/jobs/boletos", json=body, headers=h)
    r2 = client.post("/jobs/boletos", json=body, headers=h)
    assert r1.status_code == 202 and r2.status_code == 200
    assert r2.json()["job_id"] == r1.json()["job_id"]
    assert r2.json()["idempotent_replay"] is True


def test_itens_paginados_e_item_individual(client):
    body = {"tenant_id": "empresa1",
            "boletos": [{**DADOS_BB, "external_id": f"E{i}"} for i in range(3)]}
    job_id = client.post("/jobs/boletos", json=body).json()["job_id"]

    pagina = client.get(f"/jobs/boletos/{job_id}/items",
                        params={"tenant_id": "empresa1", "limite": 2}).json()
    assert pagina["total_retornado"] == 2 and pagina["limite"] == 2

    item = client.get(f"/jobs/boletos/{job_id}/items/E1",
                      params={"tenant_id": "empresa1"}).json()
    assert item["status"] == js.ITEM_COMPLETED
    assert len(item["resultado"]["codigo_barras"]) == 44


def test_isolamento_por_tenant(client):
    job_id = client.post("/jobs/boletos",
                         json={"tenant_id": "empresa1", "boletos": [DADOS_BB]}).json()["job_id"]
    r = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "OUTRO"})
    assert r.status_code == 404


def test_validacoes_de_envelope(client):
    assert client.post("/jobs/boletos", json={"boletos": [DADOS_BB]}).status_code == 422
    assert client.post("/jobs/boletos", json={"tenant_id": "x", "boletos": []}).status_code == 422


def test_limite_de_itens_por_job(client, monkeypatch):
    from app.routers import jobs

    monkeypatch.setattr(jobs, "JOB_MAX_ITENS", 2)
    r = client.post("/jobs/boletos", json={"tenant_id": "x", "boletos": [DADOS_BB] * 3})
    assert r.status_code == 413 and r.json()["recebidos"] == 3


def test_estado_persiste_entre_instancias_do_store(client):
    # store novo (como após restart) enxerga o job — estado está no banco
    job_id = client.post("/jobs/boletos",
                         json={"tenant_id": "empresa1", "boletos": [DADOS_BB]}).json()["job_id"]
    outro_store = js.get_job_store()
    assert outro_store.obter("empresa1", job_id)["status"] == js.JOB_COMPLETED


# ------------------------------------------------------------------ Fase 2
# Artefatos em disco: PDF por item, manifesto com sha256/tamanho/expiração e
# zip consolidado — doc 12: lote entrega REFERÊNCIAS, nunca base64.
def _cria_job(client, boletos):
    return client.post("/jobs/boletos",
                       json={"tenant_id": "empresa1", "boletos": boletos}).json()["job_id"]


def test_manifesto_com_hash_tamanho_e_expiracao(client):
    job_id = _cria_job(client, [DADOS_BB, {**DADOS_BB, "nosso_numero": "124",
                                            "external_id": "E2"}])
    m = client.get(f"/jobs/boletos/{job_id}/artifacts",
                   params={"tenant_id": "empresa1"}).json()
    assert m["job_id"] == job_id and m["completed"] == 2 and m["failed"] == 0
    assert len(m["arquivos"]) == 2
    for a in m["arquivos"]:
        assert len(a["sha256"]) == 64 and a["bytes"] > 1000 and a["href"].endswith(".pdf")
    assert m["expira_em"] and m["retencao_dias"] >= 1
    assert m["consolidado"]["nome"].endswith(".zip") and len(m["consolidado"]["sha256"]) == 64
    # nada de base64 no manifesto
    assert "content_base64" not in json.dumps(m)


def test_download_pdf_do_item_e_hash_confere(client):
    job_id = _cria_job(client, [{**DADOS_BB, "external_id": "ITEM-A"}])
    m = client.get(f"/jobs/boletos/{job_id}/artifacts",
                   params={"tenant_id": "empresa1"}).json()
    art = m["arquivos"][0]
    r = client.get(art["href"], params={"tenant_id": "empresa1"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF" and len(r.content) == art["bytes"]
    import hashlib

    assert hashlib.sha256(r.content).hexdigest() == art["sha256"]


def test_zip_consolidado_tem_pdfs_manifesto_e_erros(client):
    import io
    import zipfile

    job_id = _cria_job(client, [DADOS_BB, {"bank": "banco_brasil", "external_id": "RUIM"}])
    m = client.get(f"/jobs/boletos/{job_id}/artifacts",
                   params={"tenant_id": "empresa1"}).json()
    r = client.get(m["consolidado"]["href"], params={"tenant_id": "empresa1"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nomes = z.namelist()
        assert "manifest.json" in nomes and "errors.json" in nomes
        assert any(n.startswith("pdfs/") and n.endswith(".pdf") for n in nomes)
        erros = json.loads(z.read("errors.json"))
        assert erros[0]["item_id"] == "RUIM" and erros[0]["errors"]


def test_item_guarda_referencia_do_artefato(client):
    job_id = _cria_job(client, [{**DADOS_BB, "external_id": "REF-1"}])
    item = client.get(f"/jobs/boletos/{job_id}/items/REF-1",
                      params={"tenant_id": "empresa1"}).json()
    art = item["resultado"]["artifact"]
    assert art["tipo"] == "pdf" and art["sha256"] and art["bytes"] > 0


def test_artefatos_isolados_por_tenant_e_sem_path_traversal(client):
    job_id = _cria_job(client, [DADOS_BB])
    assert client.get(f"/jobs/boletos/{job_id}/artifacts",
                      params={"tenant_id": "OUTRO"}).status_code == 404
    r = client.get(f"/jobs/boletos/{job_id}/artifacts/..%2F..%2Fetc%2Fpasswd",
                   params={"tenant_id": "empresa1"})
    assert r.status_code == 404


def test_artefato_expirado_retorna_410(client, monkeypatch):
    from app.core import artifacts

    job_id = _cria_job(client, [DADOS_BB])
    monkeypatch.setattr(artifacts, "expirado", lambda _m: True)
    r = client.get(f"/jobs/boletos/{job_id}/artifacts", params={"tenant_id": "empresa1"})
    assert r.status_code == 410


# ------------------------------------------------------------------ Fase 4
# Webhook de conclusão (push HMAC ao consumidor do tenant) + métricas por job.
def test_webhook_de_conclusao_com_assinatura(client, monkeypatch):
    enviados = []

    def fake_forward(evento, *, url=None, secret=None):
        enviados.append({"evento": evento, "url": url, "secret": secret})
        return True

    monkeypatch.setattr("app.routers.jobs.forward_event", fake_forward)
    monkeypatch.setenv("SUB__empresa1__URL", "https://consumidor.exemplo/webhook")
    monkeypatch.setenv("SUB__empresa1__SECRET", "s3cr3t")

    job_id = client.post("/jobs/boletos", json={
        "tenant_id": "empresa1",
        "boletos": [DADOS_BB, {"bank": "banco_brasil", "external_id": "RUIM"}],
    }).json()["job_id"]

    assert len(enviados) == 1
    push = enviados[0]
    assert push["url"] == "https://consumidor.exemplo/webhook" and push["secret"] == "s3cr3t"
    ev = push["evento"]
    assert ev["event"] == "job.boletos.partially_completed"
    assert ev["job_id"] == job_id and ev["completed"] == 1 and ev["failed"] == 1
    assert ev["artifacts"]["arquivos"] == 1 and ev["artifacts"]["consolidado"].endswith(".zip")
    assert ev["duracao_ms"] >= 0


def test_sem_callback_do_tenant_nao_ha_push(client, monkeypatch):
    enviados = []
    monkeypatch.setattr("app.routers.jobs.forward_event",
                        lambda e, **kw: enviados.append(e) or True)
    monkeypatch.delenv("SUB__empresa1__URL", raising=False)
    monkeypatch.delenv("EVENT_WEBHOOK_URL", raising=False)
    client.post("/jobs/boletos", json={"tenant_id": "empresa1", "boletos": [DADOS_BB]})
    assert enviados == []


def test_falha_no_push_nao_derruba_o_job(client, monkeypatch):
    def explode(*_a, **_kw):
        raise RuntimeError("consumidor fora do ar")

    monkeypatch.setattr("app.routers.jobs.forward_event", explode)
    monkeypatch.setenv("SUB__empresa1__URL", "https://consumidor.exemplo/webhook")
    job_id = client.post("/jobs/boletos",
                         json={"tenant_id": "empresa1", "boletos": [DADOS_BB]}).json()["job_id"]
    j = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["status"] == js.JOB_COMPLETED


def test_metricas_do_job(client):
    job_id = client.post("/jobs/boletos", json={
        "tenant_id": "empresa1", "boletos": [DADOS_BB, {**DADOS_BB, "nosso_numero": "124"}],
    }).json()["job_id"]
    j = client.get(f"/jobs/boletos/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["metricas"]["duracao_ms"] >= 0
    assert j["metricas"]["ms_por_item"] >= 0
