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
        # o href leva o `tenant_id`: as rotas de download exigem, e o manifesto
        # publicava o caminho sem ele -- segui-lo dava 422.
        assert len(a["sha256"]) == 64 and a["bytes"] > 1000
        assert a["href"].startswith(f"/jobs/boletos/{job_id}/artifacts/items/")
        assert ".pdf?tenant_id=empresa1" in a["href"]
    assert m["expira_em"] and m["retencao_dias"] >= 1
    assert m["consolidado"]["nome"].endswith(".zip") and len(m["consolidado"]["sha256"]) == 64
    # nada de base64 no manifesto
    assert "content_base64" not in json.dumps(m)


def test_download_pdf_do_item_e_hash_confere(client):
    job_id = _cria_job(client, [{**DADOS_BB, "external_id": "ITEM-A"}])
    m = client.get(f"/jobs/boletos/{job_id}/artifacts",
                   params={"tenant_id": "empresa1"}).json()
    art = m["arquivos"][0]
    # SEM `params`: o teste segue o link como o manifesto o publica. Passar o
    # tenant à mão era a compensação que escondia o defeito.
    r = client.get(art["href"])
    assert r.status_code == 200, f'{art["href"]} -> {r.status_code}'
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
    r = client.get(m["consolidado"]["href"])
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
    assert ev["artifacts"]["arquivos"] == 1
    assert ".zip?tenant_id=empresa1" in ev["artifacts"]["consolidado"]
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


# O payload que derrubou a produção: itens distintos (nosso_numero diferente)
# mas com o MESMO numero_documento. O `_item_id` deriva de numero_documento
# quando não há external_id/seu_numero, os dois itens colidem na chave primária
# de job_items e o INSERT estourava IntegrityError -> 500.
#
# O DADOS_BB dos testes acima não tem numero_documento, então cai no índice
# (sempre único) — foi por isso que a suíte não pegou.
DADOS_COM_DOC = {**DADOS_BB, "numero_documento": "CTR-2025-001"}


def test_lote_com_numero_documento_repetido_responde_422_e_nao_500(client):
    body = {"tenant_id": "empresa1", "boletos": [
        DADOS_COM_DOC, {**DADOS_COM_DOC, "nosso_numero": "124"}]}
    r = client.post("/jobs/boletos", json=body)
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["duplicados"] == [{"item_id": "CTR-2025-001", "indices": [0, 1]}]


def test_lote_com_external_id_repetido_responde_422(client):
    # external_id tem precedência sobre numero_documento na derivação do id.
    body = {"tenant_id": "empresa1", "boletos": [
        {**DADOS_BB, "external_id": "x"}, {**DADOS_BB, "external_id": "x"}]}
    r = client.post("/jobs/boletos", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["duplicados"] == [{"item_id": "x", "indices": [0, 1]}]


def test_lote_com_numero_documento_distinto_segue_aceito(client):
    body = {"tenant_id": "empresa1", "boletos": [
        DADOS_COM_DOC, {**DADOS_COM_DOC, "numero_documento": "CTR-2025-002"}]}
    r = client.post("/jobs/boletos", json=body)
    assert r.status_code == 202, r.text
    assert r.json()["recebidos"] == 2


def test_item_sem_identificador_continua_caindo_no_indice(client):
    # Dois itens idênticos e sem external_id/seu_numero/numero_documento não
    # colidem: o id vira o índice. Comportamento anterior, preservado.
    body = {"tenant_id": "empresa1", "boletos": [DADOS_BB, DADOS_BB]}
    r = client.post("/jobs/boletos", json=body)
    assert r.status_code == 202, r.text


# O template era aceito, gravado em `meta` e DESCARTADO pelo worker: _processar
# recebia o parametro e chamava pdf_boleto(bank, dados) sem repassar. O job
# registrava um modelo que nunca foi aplicado -- metadado que mente e pior que
# metadado ausente. Conferido contra a producao: moderno, classico e carne
# produziam artefato do MESMO tamanho (o do moderno).
def _um_job(client, template=None, tenant="tpl"):
    corpo = {"tenant_id": tenant, "boletos": [DADOS_BB]}
    if template:
        corpo["template"] = template
    return client.post("/jobs/boletos", json=corpo)


def _bytes_do_artefato(client, r, tenant):
    jid = r.json()["job_id"]
    itens = client.get(f"/jobs/boletos/{jid}/items", params={"tenant_id": tenant}).json()
    return itens["items"][0]["resultado"]["artifact"]["bytes"]


def test_job_respeita_o_template_no_artefato(client):
    a = _bytes_do_artefato(client, _um_job(client, "moderno", "t1"), "t1")
    b = _bytes_do_artefato(client, _um_job(client, "classico", "t2"), "t2")
    assert a != b, "template ignorado: classico saiu do tamanho do moderno"


def test_job_grava_no_meta_o_template_que_aplicou(client):
    r = _um_job(client, "classico", "t3")
    jid = r.json()["job_id"]
    job = client.get(f"/jobs/boletos/{jid}", params={"tenant_id": "t3"}).json()
    assert job["meta"]["template"] == "classico"


def test_job_recusa_template_invalido(client):
    r = _um_job(client, "xpto", "t4")
    assert r.status_code == 422, r.text
    assert "xpto" in r.json()["error"]


def test_job_recusa_carne_apontando_o_endpoint_certo(client):
    # Carne e 3 boletos por pagina; o job gera um PDF por item. Era opcao
    # impossivel por construcao, oferecida no enum do contrato.
    r = _um_job(client, "carne", "t5")
    assert r.status_code == 422, r.text
    assert "/api/render/carne" in r.json()["validation_errors"][0]


def test_job_sem_template_continua_moderno(client):
    a = _bytes_do_artefato(client, _um_job(client, None, "t6"), "t6")
    b = _bytes_do_artefato(client, _um_job(client, "moderno", "t7"), "t7")
    assert a == b


# --- revisao de /jobs -------------------------------------------------------------
#
# A rota entrega LINKS (self, items, files, href do manifesto) em vez de base64,
# que e o contrato da doc 12. O que se mede aqui e se esses links funcionam --
# um link que responde 422 nao e um link, e nada acusava porque os testes
# passavam o tenant_id a mao.

def test_todo_link_do_corpo_e_seguivel_sem_remendo(client):
    """`self`, `items` e `artifacts` sairam sem `tenant_id`, que as rotas de
    consulta exigem: seguir o que a resposta oferecia dava 422. Mesmo defeito do
    `Location` das rotas de criacao, aqui dentro do payload."""
    criado = client.post("/jobs/boletos", json={
        "tenant_id": "empresa1", "boletos": [{**DADOS_BB, "external_id": "LINK-1"}]}).json()

    for campo in ("self", "items"):
        r = client.get(criado[campo])
        assert r.status_code == 200, f'{campo}={criado[campo]} -> {r.status_code} {r.text}'

    job = client.get(criado["self"]).json()
    for campo in ("items", "artifacts"):
        r = client.get(job[campo])
        assert r.status_code == 200, f'{campo}={job[campo]} -> {r.status_code} {r.text}'


_TITULO_CNAB = {
    "bank": "banco_brasil", "cnab_type": "cnab240",
    "empresa_mae": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
    "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
    "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
    "sequencial_remessa": 1,
    "pagamentos": [{
        "nosso_numero": "123456789", "numero_documento": "DOC-1",
        "data_vencimento": "2027-12-31", "valor": 1500.0,
        "sacado": "Joao da Silva", "sacado_documento": "52998224725",
        "sacado_endereco": "Rua Teste, 100", "sacado_bairro": "Centro",
        "sacado_cidade": "Sao Paulo", "sacado_uf": "SP", "sacado_cep": "01000000",
    }],
}


def test_links_do_job_de_remessa_tambem_sao_seguiveis(client):
    criado = client.post("/jobs/cnab/remessas", json={
        "tenant_id": "empresa1", "titulos": [_TITULO_CNAB]}).json()
    assert client.get(criado["self"]).status_code == 200
    assert client.get(criado["files"]).status_code == 200
    job = client.get(criado["self"]).json()
    assert client.get(job["files"]).status_code == 200


@pytest.mark.parametrize("params", [
    {"limite": 0}, {"limite": -1}, {"limite": 501}, {"offset": -5}])
def test_paginacao_fora_da_faixa_e_recusada(client, params):
    """`limite` tinha teto e nao tinha piso: `limite=-1` devolvia o lote INTEIRO
    (paginacao desligada por acidente) e `limite=0`, nada."""
    job_id = _cria_job(client, [DADOS_BB])
    r = client.get(f"/jobs/boletos/{job_id}/items",
                   params={"tenant_id": "empresa1", **params})
    assert r.status_code == 422, r.text


def test_filtro_de_status_inexistente_nao_finge_lista_vazia(client):
    """`status=INVENTADO` respondia 200 com zero itens -- que se le como "nenhum
    item nesse estado", e nao como "esse estado nao existe"."""
    job_id = _cria_job(client, [DADOS_BB])
    r = client.get(f"/jobs/boletos/{job_id}/items",
                   params={"tenant_id": "empresa1", "status": "INVENTADO"})
    assert r.status_code == 422, r.text
    ok = client.get(f"/jobs/boletos/{job_id}/items",
                    params={"tenant_id": "empresa1", "status": "completed"})
    assert ok.status_code == 200 and ok.json()["total_retornado"] == 1


def test_item_alem_do_teto_antigo_de_500_e_encontrado(client, monkeypatch):
    """A busca por item varria `limite=500`. `JOB_MAX_ITENS` e env: com teto
    maior, o item 600 EXISTIA e respondia 404 -- o pior tipo de 404, porque
    afirma ausencia. O limite passa a ser o total do job."""
    from app.core import job_store as js

    job_id = _cria_job(client, [DADOS_BB])
    chamadas = {}
    original = js.SqliteJobStore.itens

    def espiao(self, jid, status=None, limite=100, offset=0):
        chamadas.setdefault("limite", limite)
        return original(self, jid, status=status, limite=limite, offset=offset)

    monkeypatch.setattr(js.SqliteJobStore, "itens", espiao)
    item_id = client.get(f"/jobs/boletos/{job_id}/items",
                         params={"tenant_id": "empresa1"}).json()["items"][0]["item_id"]
    chamadas.clear()
    r = client.get(f"/jobs/boletos/{job_id}/items/{item_id}", params={"tenant_id": "empresa1"})
    assert r.status_code == 200, r.text
    assert chamadas["limite"] != 500, "voltou a varrer com teto fixo"


def test_410_de_artefato_expirado_esta_no_contrato(client):
    """A rota levantava 410 e a spec nao declarava: o consumidor nao tinha como
    distinguir "expirou" de "nunca existiu" sem tentar."""
    spec = client.get("/openapi.json").json()["paths"]
    for rota in ("/jobs/boletos/{job_id}/artifacts",
                 "/jobs/boletos/{job_id}/artifacts/{nome}",
                 "/jobs/boletos/{job_id}/artifacts/items/{nome}",
                 "/jobs/cnab/remessas/{job_id}/files",
                 "/jobs/cnab/remessas/{job_id}/files/{nome}"):
        assert "410" in spec[rota]["get"]["responses"], rota


def test_isolamento_por_tenant_continua_valendo(client):
    """O `tenant_id` na query nao e enfeite: e o que separa os clientes."""
    job_id = _cria_job(client, [DADOS_BB])
    for rota in (f"/jobs/boletos/{job_id}", f"/jobs/boletos/{job_id}/items",
                 f"/jobs/boletos/{job_id}/artifacts"):
        assert client.get(rota, params={"tenant_id": "OUTRO"}).status_code == 404, rota
