# O Swagger em espanhol é a MESMA spec, e cobre TODO o texto dela.
#
# A tradução vive num dicionário (`docs/i18n/es/swagger.yaml`) com o português
# inteiro como chave. Texto novo ou alterado no código deixa de casar — e é
# isto que este guarda cobra: nenhum texto da spec sem par, nenhuma tradução
# órfã. Sem ele a versão em espanhol envelhece em silêncio, que é o jeito que
# toda doc desta revisão envelheceu.
#
# Cobra também o mecanismo: `?lang=es` e `Accept-Language` nas duas specs
# servidas, a casca de `/docs?lang=es`, e as cópias publicadas em
# `docs/swagger/es/`.
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.i18n_openapi import (DICIONARIO, dicionario, faltam, idioma_pedido,
                                   sobram, textos_da_spec, traduzir_spec)
from app.main import app

RAIZ = Path(__file__).resolve().parents[2]
SPEC_OFFLINE = yaml.safe_load((RAIZ / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
PUBLICADO_ES = RAIZ / "docs" / "swagger" / "es"


def test_o_dicionario_existe_e_nao_e_pequeno():
    assert DICIONARIO.is_file(), f"sem {DICIONARIO}"
    assert len(dicionario("es")) > 500, "o dicionário encolheu — alguém apagou entradas?"


def test_todo_texto_da_spec_do_gateway_tem_traducao():
    pendentes = faltam(app.openapi(), "es")
    assert not pendentes, (
        f"{len(pendentes)} texto(s) da spec do gateway sem tradução — a spec mudou e o "
        f"dicionário não. Primeiros: {[p[:80] for p in pendentes[:5]]}. "
        "Rode: PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py --faltam-es")


def test_todo_texto_da_spec_offline_tem_traducao():
    pendentes = faltam(SPEC_OFFLINE, "es")
    assert not pendentes, (
        f"{len(pendentes)} texto(s) da spec offline sem tradução. "
        f"Primeiros: {[p[:80] for p in pendentes[:5]]}")


def test_nenhuma_traducao_ficou_orfa():
    """Entrada cujo português não existe mais em spec nenhuma: o texto mudou no
    código e a tradução ficou para trás, apontando para uma frase que ninguém
    lê. Ou se atualiza a chave, ou se apaga."""
    orfas = sobram([app.openapi(), SPEC_OFFLINE], "es")
    assert not orfas, f"{len(orfas)} tradução(ões) órfã(s): {[o[:80] for o in orfas[:5]]}"


def test_a_traducao_nao_muda_a_estrutura():
    """Só `summary`/`description` mudam. Rotas, campos, tipos, exemplos e
    `required` são idênticos — é uma spec, não duas."""
    pt, es = app.openapi(), traduzir_spec(app.openapi(), "es")
    assert set(pt["paths"]) == set(es["paths"])
    assert set(pt["components"]["schemas"]) == set(es["components"]["schemas"])
    bd_pt = SPEC_OFFLINE["components"]["schemas"]["BoletoData"]
    bd_es = traduzir_spec(SPEC_OFFLINE, "es")["components"]["schemas"]["BoletoData"]
    assert list(bd_pt["properties"]) == list(bd_es["properties"])
    assert bd_pt["required"] == bd_es["required"]
    assert len(textos_da_spec(pt)) == len(textos_da_spec(es))


@pytest.mark.parametrize("cabecalho,lang,esperado", [
    (None, None, "pt"),
    ("es", None, "es"),
    ("es-PY,es;q=0.9,pt;q=0.5", None, "es"),
    ("es-AR", None, "es"),
    ("pt-BR,es;q=0.8", None, "pt"),
    ("en-US,en;q=0.9", None, "pt"),
    ("*", None, "pt"),
    ("pt-BR", "es", "es"),
    ("es", "pt", "pt"),
    ("es", "fr", "pt"),
])
def test_idioma_pedido(cabecalho, lang, esperado):
    assert idioma_pedido(cabecalho, lang) == esperado


def test_openapi_json_sai_em_espanhol_quando_pedido(client):
    pt = client.get("/openapi.json")
    es_q = client.get("/openapi.json?lang=es")
    es_h = client.get("/openapi.json", headers={"Accept-Language": "es-PY,es;q=0.9"})
    assert pt.status_code == es_q.status_code == es_h.status_code == 200
    assert "Successful Response" in pt.text and "Respuesta exitosa" not in pt.text
    for r in (es_q, es_h):
        assert "Respuesta exitosa" in r.text and "Successful Response" not in r.text
        assert r.headers["content-language"] == "es"
        assert "Accept-Language" in r.headers.get("vary", "")
    assert pt.headers["content-language"] == "pt"
    # ETag distinto por idioma: o 304 de um não pode servir o outro.
    assert pt.headers["etag"] != es_q.headers["etag"]
    assert es_q.headers["etag"] == es_h.headers["etag"]


def test_openapi_offline_sai_em_espanhol_quando_pedido(client):
    pt = client.get("/api/openapi.json")
    es = client.get("/api/openapi.json", headers={"Accept-Language": "es"})
    assert pt.status_code == es.status_code == 200
    assert "Operações com boletos bancários" in pt.text
    assert "Operaciones con boletos bancarios" in es.text
    assert "Operações com boletos bancários" not in es.text
    assert es.headers["content-language"] == "es"


def test_a_casca_do_docs_acompanha_o_lang(client):
    from app.core.swagger_tema import SUBTITULO, SUBTITULO_ES
    pt = client.get("/docs").text
    es = client.get("/docs?lang=es").text
    assert SUBTITULO in pt and SUBTITULO_ES not in pt
    assert SUBTITULO_ES in es and SUBTITULO not in es
    assert "/openapi.json?lang=es" in es, "a casca em espanhol tem de fixar o idioma da spec na URL"
    assert "/openapi.json?lang=es" not in pt
    es_offline = client.get("/api/docs?lang=es").text
    assert SUBTITULO_ES in es_offline and "/api/openapi.json?lang=es" in es_offline


def test_as_copias_publicadas_em_espanhol_existem_e_estao_em_dia():
    """`docs/swagger/es/` é gerado pelo mesmo script que o resto; `--conferir`
    no CI pega defasagem. Aqui: existem, são espanhol, e a spec publicada é a
    que o código gera agora."""
    import importlib.util
    for nome in ("index.html", "offline.html", "openapi.json", "openapi-offline.yaml"):
        assert (PUBLICADO_ES / nome).is_file(), f"docs/swagger/es/{nome} não publicado"
    spec = importlib.util.spec_from_file_location(
        "gerar_swagger", RAIZ / "scripts" / "gerar-swagger-estatico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gerado = mod.gerar()
    for nome in ("openapi.json", "openapi-offline.yaml"):
        assert (PUBLICADO_ES / nome).read_text() == gerado[PUBLICADO_ES / nome], (
            f"docs/swagger/es/{nome} está defasado — rode scripts/gerar-swagger-estatico.py")
    publicado = (PUBLICADO_ES / "openapi.json").read_text()
    assert "Respuesta exitosa" in publicado and "Successful Response" not in publicado


@pytest.mark.parametrize("pagina", ["index.html", "offline.html"])
def test_a_casca_publicada_em_espanhol_nao_repete_o_docker_run(pagina):
    """Mesma regra de `test_cabecalho_do_swagger_nao_repete`, para as cópias ES."""
    html = (PUBLICADO_ES / pagina).read_text()
    topo = re.search(r'<div class="cob-topbar">(.*?)</div>\s*<div id="swagger-ui">', html, re.S)
    assert topo, "o cabeçalho mudou de marcação — reveja o guarda"
    assert topo.group(1).count("docker run -p 8000:8000") == 1
    assert "habla con la suya" in html, "a casca publicada em es/ não está em espanhol"
    assert "../vendor" in html, "a cópia em es/ tem de buscar o renderizador um nível acima"


def test_o_guarda_reconhece_um_texto_sem_traducao():
    """Controle: spec com uma frase nova tem de aparecer em `faltam`."""
    s = {"paths": {"/x": {"get": {"summary": "Frase que não existe no dicionário",
                                  "description": "Successful Response"}}}}
    assert faltam(s, "es") == ["Frase que não existe no dicionário"]
    assert traduzir_spec(s, "es")["paths"]["/x"]["get"]["description"] == "Respuesta exitosa"
