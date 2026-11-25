# A Cobranca-API fala da M&S do Brasil como o estudo de marca fala.
#
# Estudo de marca da M&S do Brasil, v0.4 (novembro de 2026), aplicado ao
# repositório em 25/11/2026. Antes dele, o crédito à empresa saía de cinco
# jeitos — "M&S do Brasil LTDA", "M&S do Brasil Ltda", com hífen, com
# travessão — em 17 lugares, do README ao `contact` das duas specs. O estudo
# escreve o nome sempre como "M&S do Brasil", com "Desenvolvimento de
# sistemas" como texto de apoio fora do logotipo. A razão social continua
# onde ela é dado, não vitrine: o `legalName` do JSON-LD e o cedente de
# exemplo.
#
# O estudo também diz o que a família compartilha e o que fica de fora, e
# isso já era verdade aqui sem guarda nenhum: o ciano da Cobranca-API é o
# "ciano elo" do estudo, hex por hex, e vermelho não entra na identidade.
# Agora é preso.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

#: Onde o crédito à empresa aparece para quem lê. Lista explícita, de
#: propósito: arquivo novo com crédito entra aqui à mão.
CREDITOS = [
    "README.md", "CONTRIBUTING.md",
    "docs/index.md", "docs/README.md", "docs/deploy.md", "docs/ARCHITECTURE.md",
    "docs/api/ofx-parsing.md", "docs/api/pix.md", "docs/api/troubleshooting.md",
    "docs/fields/nosso-numero.md", "docs/es/index.md", "docs/es/comercial.md",
    "docs/_layouts/default.html", "docs/_includes/head-custom.html",
    "docs/openapi.yaml", "gateway/app/main.py",
]

#: Nome com razão social, em qualquer caixa da sigla. O cedente de exemplo
#: ("M&S DO BRASIL LTDA", em maiúsculas, como sai no boleto) não casa: o
#: padrão exige "do Brasil" em caixa de nome próprio.
COM_RAZAO_SOCIAL = re.compile(r"M(?:&|&amp;)S do Brasil,? (?:LTDA|Ltda)")

#: O par ciano do estudo: "ciano elo" (sobre escuro) e "ciano elo claro"
#: (sobre claro). Vieram das marcas dos produtos — o estudo diz isso na
#: página de cores —, então aqui é o mesmo hex, não uma aproximação.
CIANO_ELO, CIANO_ELO_CLARO = "#06B6D4", "#0891B2"

#: Vermelhos que o estudo exclui da identidade "nem como cor de destaque".
VERMELHO = re.compile(r"#(?:ef4444|dc2626|b91c1c|991b1b|f87171|e11d48|f43f5e|ff0000)\b|"
                      r"(?:fill|stroke|color)\s*[=:]\s*[\"']?red\b", re.I)


@pytest.mark.parametrize("arquivo", CREDITOS)
def test_o_credito_escreve_o_nome_como_o_estudo(arquivo):
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    assert "msbrasil.inf.br" in texto, f"{arquivo} perdeu o link da M&S do Brasil"
    # a razão social só vale no `legalName` do JSON-LD
    sem_legal = re.sub(r'"legalName":\s*"[^"]*"', "", texto)
    achados = COM_RAZAO_SOCIAL.findall(sem_legal)
    assert not achados, (
        f"{arquivo} escreve {achados[0]!r}; o estudo de marca escreve "
        "'M&S do Brasil' — a razão social fica no `legalName` do JSON-LD")


def test_o_json_ld_separa_nome_de_razao_social():
    html = (RAIZ / "docs/_includes/head-custom.html").read_text(encoding="utf-8")
    orgs = re.findall(r'\{\s*"@type":\s*"Organization"[^}]*\}', html)
    assert len(orgs) == 2, "o JSON-LD mudou de forma (worksFor e publisher) — reveja o guarda"
    for org in orgs:
        assert '"name": "M&S do Brasil"' in org, org
        assert '"legalName": "M&S do Brasil LTDA"' in org, org


def test_o_ciano_do_produto_e_o_ciano_elo_do_estudo():
    gerador = (RAIZ / "scripts/gerar-banners.py").read_text(encoding="utf-8")
    m = re.search(r'^CIANO, CIANO_ESC = "(#[0-9A-Fa-f]{6})", "(#[0-9A-Fa-f]{6})"', gerador, re.M)
    assert m, "a paleta do gerador de banners mudou de forma — reveja o guarda"
    assert (m.group(1).upper(), m.group(2).upper()) == (CIANO_ELO, CIANO_ELO_CLARO), (
        f"o ciano da Cobranca-API ({m.group(1)}, {m.group(2)}) deixou de ser o ciano elo "
        f"do estudo de marca ({CIANO_ELO}, {CIANO_ELO_CLARO}) — é ele que amarra o "
        "produto à família da M&S do Brasil")
    marca = (RAIZ / "docs/assets/marca.svg").read_text(encoding="utf-8")
    assert CIANO_ELO_CLARO.lower() in marca.lower(), "marca.svg (fundo claro) sem o ciano elo claro"


IDENTIDADE = sorted((RAIZ / "docs/assets").glob("*.svg")) + [RAIZ / "scripts/gerar-banners.py",
                                                            RAIZ / "docs/_includes/head-custom.html"]


@pytest.mark.parametrize("arquivo", IDENTIDADE, ids=lambda p: p.name)
def test_vermelho_nao_entra_na_identidade(arquivo):
    achados = VERMELHO.findall(arquivo.read_text(encoding="utf-8"))
    assert not achados, (
        f"{arquivo.relative_to(RAIZ)} usa vermelho ({achados[0]}); o estudo de marca "
        "da M&S do Brasil o exclui da identidade, nem como destaque")


def test_o_padrao_de_vermelho_reconhece_o_que_deve():
    assert VERMELHO.search('<rect fill="#EF4444"/>')
    assert VERMELHO.search("color: red;")
    assert not VERMELHO.search('<rect fill="#0891B2"/> shape-rendering="crispEdges"')
