# O README da raiz afirma números e listas que o código sabe responder.
#
# Revisão de 31/10/2026, cada linha medida contra o serviço: "98 requests" na
# coleção que tem 146; a tabela de bancos somava 18 ("10 + 8") num catálogo de
# 19; duas listas de bancos online paravam no Inter, sem o Itaú; a nota do
# herói ainda mandava o leitor a uma "demo no Render" que o PR #35 removeu; e
# um bullet dizia que a faixa FEBRABAN sai "com o valor cobrado somado" quando
# a mesma página, 60 linhas antes, explica que ela sai em branco de propósito.
#
# Nada disso era mentira quando foi escrito. Virou — e é por isso que cada
# número da vitrine tem de vir de onde ele nasce.
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
COLECAO = RAIZ / "postman" / "cobranca-api.postman_collection.json"


def _conta_requests(itens: list) -> int:
    return sum(_conta_requests(i["item"]) if "item" in i else 1 for i in itens)


def test_o_numero_de_requests_da_colecao_postman_e_o_da_colecao():
    real = _conta_requests(json.loads(COLECAO.read_text(encoding="utf-8"))["item"])
    citados = [int(n) for n in re.findall(r"(\d+) requests", README)]
    assert citados, "o README deixou de citar a contagem de requests da coleção"
    assert set(citados) == {real}, f"README cita {citados} requests; a coleção tem {real}"
    # (o postman/README.md fala em "9 requests" do SMOKE — outro recorte, não a coleção)


def test_a_tabela_de_bancos_fecha_no_total_do_catalogo():
    """`+ N bancos` tem de ser o que falta para o total da engine — era "+ 8"
    com dez linhas listadas, somando 18 num catálogo de 19."""
    from app.core import pycob
    total = len(pycob.bancos_suportados())
    m = re.search(r"## Bancos Suportados\n\n(\|.*\n)+", README)
    assert m, "a seção 'Bancos Suportados' mudou — reveja o guarda"
    linhas = [l for l in m.group(0).splitlines() if l.startswith("|")]
    # fora: cabeçalho, separador e a própria linha "+ N bancos"
    nomeados = [l for l in linhas[2:] if not re.match(r"\|\s*\+ \d+ bancos", l)]
    resto = re.search(r"\|\s*\+ (\d+) bancos", m.group(0))
    assert resto, "a linha '+ N bancos' sumiu"
    assert len(nomeados) + int(resto.group(1)) == total, (
        f"{len(nomeados)} bancos nomeados + {resto.group(1)} = "
        f"{len(nomeados) + int(resto.group(1))}, mas a engine tem {total}")


def test_a_tabela_de_bancos_concorda_com_a_engine_em_remessa_e_pix(client):
    """Cada banco nomeado: os layouts de remessa e o PIX na remessa são os que
    `GET /api/bancos` responde — a coluna 'Retorno' a API não publica, e por
    isso não é cobrada aqui."""
    catalogo = {b["slug"]: b for b in client.get("/api/bancos").json()["bancos"]}
    por_nome = {"Banco do Brasil": "banco_brasil", "Santander": "santander", "Caixa": "caixa",
                "Bradesco": "bradesco", "Banco C6": "banco_c6", "Itaú": "itau", "Sicredi": "sicredi",
                "Sicoob": "sicoob", "Banrisul": "banrisul", "Unicred": "unicred", "Inter": "inter"}
    secao = re.search(r"## Bancos Suportados\n\n(\|.*\n)+", README).group(0)
    conferidos = 0
    for linha in secao.splitlines()[2:]:
        celulas = [c.strip(" *") for c in linha.strip("|").split("|")]
        if len(celulas) < 6 or celulas[0] not in por_nome:
            continue
        banco = catalogo[por_nome[celulas[0]]]
        layouts = set(re.findall(r"\d{3}", celulas[3]))
        assert layouts == {c.replace("cnab", "") for c in banco["cnab"]}, (
            f"{celulas[0]}: README diz remessa {layouts}, engine {banco['cnab']}")
        assert (celulas[5] == "✅") == bool(banco["pix_remessa"]), (
            f"{celulas[0]}: README diz PIX {celulas[5]!r}, engine {banco['pix_remessa']}")
        conferidos += 1
    assert conferidos >= 10, f"só {conferidos} linhas conferidas — a tabela mudou de forma?"


def test_os_diferenciais_offline_sao_os_da_engine(client):
    """'19 bancos offline — 17 com remessa, 21 combinações banco×layout, 7 com
    segmento PIX': quatro números numa frase, os quatro medidos."""
    bancos = client.get("/api/bancos").json()["bancos"]
    com_remessa = [b for b in bancos if b["cnab"]]
    m = re.search(r"\*\*(\d+) bancos offline\*\* — boleto \+ CNAB \((\d+) bancos com remessa, "
                  r"(\d+) combinações banco×layout, (\d+) com segmento PIX\)", README)
    assert m, "a frase dos diferenciais offline mudou — reveja o guarda"
    assert tuple(map(int, m.groups())) == (
        len(bancos), len(com_remessa), sum(len(b["cnab"]) for b in com_remessa),
        sum(1 for b in bancos if b["pix_remessa"]))


def test_toda_lista_de_bancos_online_inclui_o_itau():
    """Duas listas paravam em 'C6, Sicoob, Inter'. O Itaú entrou na 2.3 e a
    vitrine seguiu dizendo três."""
    sobras = [l for l in README.splitlines()
              if re.search(r"C6, Sicoob, Inter\b", l) and "Itaú" not in l]
    assert not sobras, f"listas de bancos online sem o Itaú:\n" + "\n".join(f"  {s[:100]}" for s in sobras)


def test_a_contagem_de_endpoints_offline_e_a_do_router():
    from app.routers import offline
    reais = {r.path for r in offline.router.routes if hasattr(r, "methods")}
    m = re.search(r"Ver todos os (\d+) endpoints offline", README)
    assert m and int(m.group(1)) == len(reais), f"README: {m and m.group(1)}; router: {len(reais)}"
    bloco = README.split("Ver todos os")[1].split("</details>")[0]
    listados = set(re.findall(r"`(/api/[^`]+)`", bloco))
    assert listados == reais, f"faltam {sorted(reais - listados)}; sobram {sorted(listados - reais)}"


def test_o_readme_nao_manda_para_demo_nem_promete_faixa_preenchida():
    assert "ambiente de demonstração" not in README and "free tier" not in README, (
        "o README voltou a falar de uma demo pública — o produto é self-hosted")
    assert "render.com/deploy" not in README, (
        "botão 'Deploy to Render' no README: o Render é apêndice do guia, não o deploy de referência")
    assert "valor cobrado somado" not in README, (
        "a faixa FEBRABAN sai em branco de propósito (a própria página explica); não prometer o contrário")
    assert "ghcr.io/maxwbh/cobranca-api:latest" in README


@pytest.mark.parametrize("trecho", ["swagger/es/", "cobranca-api/es/", "?lang=es", "formato=csv"])
def test_o_readme_aponta_o_que_a_api_passou_a_fazer(trecho):
    assert trecho in README, f"o README não menciona {trecho!r}"
