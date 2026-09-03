# Fase 3 — remessa CNAB em lote com SUBLOTES DETERMINÍSTICOS.
# Regra da doc 12: nunca misturar banco/layout/convênio/carteira/conta
# incompatíveis no mesmo arquivo; 1 arquivo por sublote; reprocessar só o
# sublote com erro.
import io
import json
import zipfile

import pytest

from app.core import job_store as js
from app.core import pycob

CAB_BB = {
    "bank": "banco_brasil", "cnab_type": "cnab240",
    "empresa_mae": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
    "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
    "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
    "sequencial_remessa": 1,
}
PAG = {
    "nosso_numero": "123456789", "numero_documento": "DOC-1",
    "data_vencimento": "2027-12-31", "valor": 1500.0,
    "sacado": "Joao da Silva", "sacado_documento": "52998224725",
    "sacado_endereco": "Rua Teste, 100", "sacado_bairro": "Centro",
    "sacado_cidade": "Sao Paulo", "sacado_uf": "SP", "sacado_cep": "01000000",
}


@pytest.fixture(autouse=True)
def _isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


# ---------------------------------------------------------------- função pura
def test_agrupamento_nunca_mistura_incompativeis():
    titulos = [
        {**CAB_BB, "pagamentos": [PAG]},
        {**CAB_BB, "pagamentos": [{**PAG, "nosso_numero": "2"}]},          # mesmo grupo
        {**CAB_BB, "convenio": "7654321", "pagamentos": [PAG]},            # convênio dif.
        {**CAB_BB, "cnab_type": "cnab400", "pagamentos": [PAG]},           # layout dif.
    ]
    sublotes = pycob.agrupar_sublotes(titulos)
    assert len(sublotes) == 3
    primeiro = next(s for s in sublotes if s["quantidade"] == 2)
    assert primeiro["chave"]["convenio"] == "1234567"
    assert {s["chave"]["cnab_type"] for s in sublotes} == {"cnab240", "cnab400"}


def test_agrupamento_e_deterministico():
    titulos = [{**CAB_BB, "pagamentos": [PAG]}, {**CAB_BB, "pagamentos": [PAG]}]
    a = [s["chave"] for s in pycob.agrupar_sublotes(titulos)]
    b = [s["chave"] for s in pycob.agrupar_sublotes(titulos)]
    assert a == b


# ---------------------------------------------------------------- job completo
def _cria(client, titulos, headers=None):
    return client.post("/jobs/cnab/remessas",
                       json={"tenant_id": "empresa1", "titulos": titulos},
                       headers=headers or {})


def test_job_gera_um_arquivo_por_sublote(client):
    titulos = [
        {**CAB_BB, "pagamentos": [PAG]},
        {**CAB_BB, "convenio": "7654321", "pagamentos": [{**PAG, "nosso_numero": "9"}]},
    ]
    r = _cria(client, titulos)
    assert r.status_code == 202
    corpo = r.json()
    assert corpo["titulos"] == 2 and len(corpo["sublotes"]) == 2
    job_id = corpo["job_id"]

    job = client.get(f"/jobs/cnab/remessas/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert job["sublotes"] == 2
    assert job["status"] in (js.JOB_COMPLETED, js.JOB_PARTIAL)

    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    assert files["tipo"] == "cnab_remessas"
    for a in files["arquivos"]:
        assert a["nome"].endswith(".rem") and len(a["sha256"]) == 64 and a["registros"] > 0
        assert a["chave"]["bank"] == "banco_brasil"


def test_download_do_arquivo_cnab_com_240_colunas(client):
    job_id = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}]).json()["job_id"]
    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    arquivo = files["arquivos"][0]
    r = client.get(arquivo["href"], params={"tenant_id": "empresa1"})
    assert r.status_code == 200
    linhas = r.text.splitlines()
    assert linhas and all(len(x) == 240 for x in linhas)
    import hashlib

    assert hashlib.sha256(r.content).hexdigest() == arquivo["sha256"]


def test_sublote_invalido_nao_derruba_o_job(client):
    titulos = [
        {**CAB_BB, "pagamentos": [PAG]},
        {**CAB_BB, "convenio": "999", "carteira": "ZZ", "pagamentos": [PAG]},  # inválido
    ]
    job_id = _cria(client, titulos).json()["job_id"]
    job = client.get(f"/jobs/cnab/remessas/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert job["status"] == js.JOB_PARTIAL
    assert job["completed"] == 1 and job["failed"] == 1

    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    assert files["failed"] == 1 and len(files["arquivos"]) == 1


def test_zip_consolidado_de_remessas(client):
    job_id = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}]).json()["job_id"]
    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    r = client.get(files["consolidado"]["href"], params={"tenant_id": "empresa1"})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nomes = z.namelist()
        assert "manifest.json" in nomes and "errors.json" in nomes
        assert any(n.startswith("cnab/") and n.endswith(".rem") for n in nomes)


def test_idempotencia_e_isolamento_por_tenant(client):
    h = {"Idempotency-Key": "remessa-2026-07-25"}
    r1 = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}], headers=h)
    r2 = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}], headers=h)
    assert r1.status_code == 202 and r2.status_code == 200
    assert r2.json()["job_id"] == r1.json()["job_id"]

    job_id = r1.json()["job_id"]
    assert client.get(f"/jobs/cnab/remessas/{job_id}",
                      params={"tenant_id": "OUTRO"}).status_code == 404


def test_validacoes_e_limite(client, monkeypatch):
    from app.routers import jobs

    assert client.post("/jobs/cnab/remessas", json={"titulos": []}).status_code == 422
    monkeypatch.setattr(jobs, "JOB_MAX_ITENS", 1)
    r = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}] * 2)
    assert r.status_code == 413


def test_webhook_e_metricas_do_job_cnab(client, monkeypatch):
    enviados = []
    monkeypatch.setattr("app.routers.jobs.forward_event",
                        lambda e, **kw: enviados.append(e) or True)
    monkeypatch.setenv("SUB__empresa1__URL", "https://consumidor.exemplo/webhook")

    job_id = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}]).json()["job_id"]
    assert enviados and enviados[0]["event"].startswith("job.cnab_remessas.")
    assert enviados[0]["tipo"] == "cnab_remessas"

    j = client.get(f"/jobs/cnab/remessas/{job_id}", params={"tenant_id": "empresa1"}).json()
    assert j["metricas"]["duracao_ms"] >= 0


# --- o nome que o BANCO exige, também no lote ------------------------------------
#
# O arquivo em disco é nomeado pelo sublote, e continua sendo: o nome é único
# dentro do job, e é dele que dependem o href e o zip. Mas quem baixa precisa
# saber com que nome SUBIR — o Inter recusa o upload se o arquivo não se chamar
# `CI400_001_<sequencial>.REM`, com o mesmo sequencial do header.

CAB_INTER = {
    "bank": "inter", "cnab_type": "cnab400",
    "empresa_mae": "M&S DO BRASIL LTDA", "documento_cedente": "05230380000174",
    "agencia": "0001", "conta_corrente": "123456", "digito_conta": "7",
    "convenio": "123456", "carteira": "110", "sequencial_remessa": 42,
}
PAG_INTER = {**PAG, "nosso_numero": "1234567890"}


def test_o_lote_registra_o_nome_de_upload_de_quem_tem_regra(client):
    job_id = _cria(client, [{**CAB_INTER, "pagamentos": [PAG_INTER]}]).json()["job_id"]
    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    arquivo = files["arquivos"][0]
    assert arquivo["nome"].endswith(".rem")          # em disco, pelo sublote
    assert arquivo["nome_para_upload"] == "CI400_001_0000042.REM"


def test_banco_sem_regra_nao_ganha_campo_de_upload(client):
    """Só aparece onde há regra de banco. Presente em todo artefato, o campo
    viraria ruído e quem lê passaria a ignorá-lo justamente onde importa."""
    job_id = _cria(client, [{**CAB_BB, "pagamentos": [PAG]}]).json()["job_id"]
    files = client.get(f"/jobs/cnab/remessas/{job_id}/files",
                       params={"tenant_id": "empresa1"}).json()
    assert "nome_para_upload" not in files["arquivos"][0]
