# A spec offline conta os bancos como a engine conta.
#
# Revisão externa de 03/11/2026, do Swagger: `docs/openapi.yaml` dizia "19
# bancos" num trecho e "Os 18, como a engine responde hoje" em outro; a
# tabela tinha 18 linhas (sem o Inter, 077); o exemplo de `GET /api/bancos`
# trazia `total: 18`; e a spec do gateway dizia "os 18 slugs do catálogo
# offline". O 18→19 do Inter já tinha sido caçado em README, banner, badge e
# site — e o guarda de contagem não lia a spec. Inventário parcial, de novo.
#
# Aqui a spec é lida como a engine é lida: a tabela tem de ter exatamente os
# bancos da engine, com as mesmas colunas de CNAB e PIX; cada "N" por extenso
# tem de ser o total; o exemplo também.
from __future__ import annotations

import re
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SPEC_TEXTO = (RAIZ / "docs" / "openapi.yaml").read_text(encoding="utf-8")
SPEC = yaml.safe_load(SPEC_TEXTO)

LINHA = re.compile(r"^\s*\| (?P<nome>[^|]+?) \| (?P<codigo>\d{3}) \| (?P<boleto>[^|]+?) \| "
                   r"(?P<c240>[^|]+?) \| (?P<c400>[^|]+?) \| (?P<pix>[^|]+?) \|$", re.MULTILINE)


def _engine(client) -> dict[str, dict]:
    return {b["codigo"]: b for b in client.get("/api/bancos").json()["bancos"]}


def test_a_tabela_da_spec_tem_exatamente_os_bancos_da_engine(client):
    engine = _engine(client)
    linhas = {m.group("codigo"): m for m in LINHA.finditer(SPEC["info"]["description"])}
    assert len(linhas) >= 18, "a tabela de bancos da spec mudou de forma — reveja o padrão"
    faltam = sorted(set(engine) - set(linhas))
    sobram = sorted(set(linhas) - set(engine))
    assert not faltam and not sobram, f"tabela da spec: faltam {faltam}, sobram {sobram}"
    for codigo, m in linhas.items():
        b = engine[codigo]
        assert (m.group("c240").strip() == "✅") == ("cnab240" in b["cnab"]), (codigo, "CNAB 240")
        assert (m.group("c400").strip() == "✅") == ("cnab400" in b["cnab"]), (codigo, "CNAB 400")
        assert (m.group("pix").strip() == "✅") == bool(b["pix_remessa"]), (codigo, "PIX")
        assert m.group("boleto").strip() == "✅", (codigo, "todo banco da engine emite boleto")


def test_toda_contagem_por_extenso_na_spec_offline_e_o_total(client):
    total = client.get("/api/bancos").json()["total"]
    desc = SPEC["info"]["description"]
    achados = {
        "Os N, como a engine responde hoje": re.search(r"Os (\d+), como a engine responde hoje", desc),
        "Boleto em PDF vale para os N": re.search(r"Boleto em PDF vale para os (\d+)", desc),
        "N bancos, sem convênio": re.search(r"(\d+) bancos, sem convênio", desc),
    }
    for rotulo, m in achados.items():
        assert m, f"a frase '{rotulo}' sumiu da spec — reveja o guarda"
        assert int(m.group(1)) == total, f"'{rotulo}' diz {m.group(1)}; a engine tem {total}"


def test_o_exemplo_de_total_em_api_bancos_e_o_total(client):
    total = client.get("/api/bancos").json()["total"]
    exemplo = (SPEC["paths"]["/api/bancos"]["get"]["responses"]["200"]["content"]
               ["application/json"]["schema"]["properties"]["total"]["example"])
    assert exemplo == total, f"exemplo de `total` na spec: {exemplo}; a engine responde {total}"
    desc = SPEC["paths"]["/api/bancos"]["get"].get("description", "")
    m = re.search(r"Retorna os (\d+) bancos", desc)
    assert m and int(m.group(1)) == total, f"descrição de /api/bancos: {m and m.group(1)} ≠ {total}"


def test_a_spec_do_gateway_conta_os_slugs_da_engine_como_ela_responde(client):
    """`bancos_cnab` do registro da engine em `GET /bancos` — a descrição dizia
    "os 18 slugs" e a lista tem 19."""
    from app.main import app
    registro = next(b for b in client.get("/bancos").json()["bancos"] if "bancos_cnab" in b)
    real = len(registro["bancos_cnab"])
    # a descrição vive inline na resposta de GET /bancos, não em `components`
    import json
    texto = json.dumps(app.openapi(), ensure_ascii=False)  # sem dobra de linha, ao contrário do YAML
    m = re.search(r"os (\d+) slugs do catálogo offline", texto)
    assert m, "a descrição de `bancos_cnab` mudou — reveja o guarda"
    assert int(m.group(1)) == real, f"spec do gateway diz {m.group(1)} slugs; o registro traz {real}"
