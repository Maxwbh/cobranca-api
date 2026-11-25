# A Cobranca-API fala da M&S do Brasil como o manual de marca fala.
#
# Primeira aplicação (25/11/2026), com o estudo v0.4: o crédito à empresa
# saía de cinco jeitos — "M&S do Brasil LTDA", "Ltda", com hífen, com
# travessão — em 16 lugares, do README ao `contact` das duas specs. O nome
# passou a "M&S do Brasil"; a razão social ficou onde é dado, o `legalName`
# do JSON-LD.
#
# Segunda aplicação, com o kit v0.7 (conceito visual congelado, ainda sem
# INPI nem prova de impressão). O que ele mudou para este repositório:
#   - arquitetura de marcas ENDOSSADA, aprovada: o produto mantém nome e
#     desenho e assina "um projeto M&S do Brasil"; em repositório e
#     documentação técnica o produto vem primeiro e o endosso fica no
#     rodapé do README;
#   - posicionamento permanente: "Engenharia de software para sistemas que
#     não podem parar". A especialização Oracle virou mensagem COMERCIAL —
#     sai da documentação técnica;
#   - a licença dos projetos de código aberto não autoriza o uso da marca;
#   - nenhum SVG da marca é editado à mão: sai do gerador do kit.
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
README = (RAIZ / "README.md").read_text(encoding="utf-8")
PASTA_MS = RAIZ / "docs" / "assets" / "ms"

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

#: O par ciano do kit v0.7: "ciano" (sobre escuro) e "ciano escuro" (sobre
#: claro). O manual diz que veio das marcas dos produtos, então aqui é o
#: mesmo hex, não uma aproximação.
CIANO, CIANO_ESCURO = "#06B6D4", "#0891B2"

#: Os dois arquivos do kit v0.7 que este repositório publica, com o SHA-256
#: de como saíram do `gerar_kit.py`. Mudou o hash, alguém editou à mão — ou
#: o kit mudou de versão, e aí o hash muda junto com a nota em
#: `docs/assets/ms/README.md`.
KIT = {
    "ms-assinatura-horizontal-fundo-claro.svg":
        "efb7f6e6b80c1539f94884afe03af9e9e43d532e9dd32129229a74acb93bb897",
    "ms-assinatura-horizontal-fundo-escuro.svg":
        "34f70c5252a06630adf5c433d65cc4be46f8230792e91e5291c168b85d2ff182",
}

#: Vermelhos fora da identidade "nem como cor de destaque" — inclusive o
#: `--ms-erro` do próprio kit, que é de interface e "nunca na identidade".
VERMELHO = re.compile(r"#(?:ef4444|dc2626|b91c1c|991b1b|f87171|e11d48|f43f5e|ff0000|b42318)\b|"
                      r"(?:fill|stroke|color)\s*[=:]\s*[\"']?red\b", re.I)

#: Coisas que um SVG publicado não pode carregar: código, handler, recurso de
#: fora. O kit vem de fora do repositório; isto é o que se confere antes.
SVG_INSEGURO = re.compile(r"<script|javascript:|\son[a-z]+\s*=|<foreignObject|@import|"
                          r"(?:xlink:)?href\s*=\s*[\"']https?:|url\(\s*[\"']?https?:", re.I)

POSICIONAMENTO = "Engenharia de software para sistemas que não podem parar"
ORACLE_COMERCIAL = "desenvolve, moderniza e sustenta sistemas Oracle"


def _rodape_do_readme() -> str:
    return README.rsplit("\n---\n", 1)[1]


@pytest.mark.parametrize("arquivo", CREDITOS)
def test_o_credito_escreve_o_nome_como_o_manual(arquivo):
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    assert "msbrasil.inf.br" in texto, f"{arquivo} perdeu o link da M&S do Brasil"
    # a razão social só vale no `legalName` do JSON-LD
    sem_legal = re.sub(r'"legalName":\s*"[^"]*"', "", texto)
    achados = COM_RAZAO_SOCIAL.findall(sem_legal)
    assert not achados, (
        f"{arquivo} escreve {achados[0]!r}; o manual escreve 'M&S do Brasil' — "
        "a razão social fica no `legalName` do JSON-LD")


def test_o_json_ld_separa_nome_de_razao_social():
    html = (RAIZ / "docs/_includes/head-custom.html").read_text(encoding="utf-8")
    orgs = re.findall(r'\{\s*"@type":\s*"Organization"[^}]*\}', html)
    assert len(orgs) == 2, "o JSON-LD mudou de forma (worksFor e publisher) — reveja o guarda"
    for org in orgs:
        assert '"name": "M&S do Brasil"' in org, org
        assert '"legalName": "M&S do Brasil LTDA"' in org, org


# --- Endosso (kit v0.7, arquitetura de marcas) -------------------------------

def test_o_produto_vem_primeiro_e_o_endosso_fica_no_rodape():
    """Em repositório, o produto abre o README e a M&S assina no rodapé."""
    inicio = README[:README.index("img.shields.io")]
    assert "ms-assinatura" not in inicio, "a assinatura da M&S subiu para o topo — o produto vem primeiro"
    rodape = _rodape_do_readme()
    assert "um projeto" in rodape, "o rodapé do README perdeu a linha de endosso 'um projeto M&S do Brasil'"
    for variante in ("fundo-claro", "fundo-escuro"):
        assert f"docs/assets/ms/ms-assinatura-horizontal-{variante}.svg" in rodape, (
            f"o rodapé não serve a variante {variante} — no tema oposto do GitHub a assinatura some")
    assert 'prefers-color-scheme: dark' in rodape
    assert 'alt="M&S do Brasil"' in rodape


def test_a_assinatura_respeita_a_altura_minima():
    """28 px é o mínimo da assinatura horizontal em tela (kit v0.7); abaixo
    disso o "DO BRASIL" passa de 7 px e some."""
    usos = {"README.md": _rodape_do_readme(),
            "docs/_layouts/default.html": (RAIZ / "docs/_layouts/default.html").read_text(encoding="utf-8")}
    for arquivo, texto in usos.items():
        alturas = [int(h) for h in re.findall(r'<img[^>]*ms-assinatura[^>]*height="(\d+)"', texto)]
        assert alturas, f"{arquivo}: assinatura da M&S sem `height` explícito"
        assert min(alturas) >= 28, f"{arquivo}: assinatura com {min(alturas)} px; o mínimo é 28"


def test_o_site_endossa_no_rodape_nas_duas_linguas():
    html = (RAIZ / "docs/_layouts/default.html").read_text(encoding="utf-8")
    rodape = html[html.index('<footer class="site-footer">'):html.index("</footer>")]
    assert "ms-assinatura-horizontal-fundo-claro.svg" in rodape
    assert re.search(r"\{% if es %\}un proyecto\{% else %\}um projeto\{% endif %\}", rodape), (
        "o rodapé do site não endossa nas duas línguas")


@pytest.mark.parametrize("arquivo,sha", sorted(KIT.items()))
def test_a_marca_e_a_do_kit_sem_edicao(arquivo, sha):
    caminho = PASTA_MS / arquivo
    assert caminho.is_file(), f"docs/assets/ms/{arquivo} não existe"
    assert hashlib.sha256(caminho.read_bytes()).hexdigest() == sha, (
        f"docs/assets/ms/{arquivo} não é o arquivo do kit v0.7 — SVG da marca não se "
        "edita à mão; gere de novo pelo kit e troque o hash aqui")


@pytest.mark.parametrize("arquivo", sorted(KIT))
def test_o_svg_da_marca_nao_carrega_nada_de_fora(arquivo):
    achados = SVG_INSEGURO.findall((PASTA_MS / arquivo).read_text(encoding="utf-8"))
    assert not achados, f"docs/assets/ms/{arquivo} traz {achados[0]!r}"


def test_a_pasta_da_marca_so_tem_o_que_foi_conferido():
    presentes = {p.name for p in PASTA_MS.iterdir()}
    assert presentes == set(KIT) | {"README.md"}, (
        f"docs/assets/ms/ tem {sorted(presentes - set(KIT) - {'README.md'})} além do "
        "conferido — arquivo novo do kit entra com hash neste guarda")


def test_a_licenca_do_codigo_nao_cobre_a_marca():
    """Termos de uso do kit: a licença do código aberto não autoriza o uso
    da marca da empresa. Com os arquivos da marca no repositório, isso tem de
    estar escrito onde quem copia lê."""
    licenca = README[README.index("## Licença"):]
    assert "docs/assets/ms" in licenca and "não cobre" in licenca, (
        "a seção Licença do README não diz que a MIT não cobre a marca da M&S do Brasil")
    nota = (PASTA_MS / "README.md").read_text(encoding="utf-8")
    assert "MIT" in nota and "não se aplica" in nota, nota[:200]
    assert "v0.7" in nota, "a nota da pasta não diz de que versão do kit são os arquivos"


# --- Posicionamento (kit v0.7) ------------------------------------------------

@pytest.mark.parametrize("arquivo", ["README.md", "docs/index.md"])
def test_a_documentacao_tecnica_usa_o_posicionamento_permanente(arquivo):
    texto = (RAIZ / arquivo).read_text(encoding="utf-8")
    assert POSICIONAMENTO in texto, f"{arquivo} sem o posicionamento permanente da M&S"
    assert ORACLE_COMERCIAL not in texto, (
        f"{arquivo} usa a mensagem Oracle do estudo v0.4; no v0.7 ela é comercial e "
        "não entra na documentação técnica")


# --- Cores --------------------------------------------------------------------

def test_o_ciano_do_produto_e_o_ciano_do_kit():
    gerador = (RAIZ / "scripts/gerar-banners.py").read_text(encoding="utf-8")
    m = re.search(r'^CIANO, CIANO_ESC = "(#[0-9A-Fa-f]{6})", "(#[0-9A-Fa-f]{6})"', gerador, re.M)
    assert m, "a paleta do gerador de banners mudou de forma — reveja o guarda"
    assert (m.group(1).upper(), m.group(2).upper()) == (CIANO, CIANO_ESCURO), (
        f"o ciano da Cobranca-API ({m.group(1)}, {m.group(2)}) deixou de ser o ciano do "
        f"kit da M&S ({CIANO}, {CIANO_ESCURO}) — é ele que amarra o produto à família")
    marca = (RAIZ / "docs/assets/marca.svg").read_text(encoding="utf-8")
    assert CIANO_ESCURO.lower() in marca.lower(), "marca.svg (fundo claro) sem o ciano escuro"


IDENTIDADE = (sorted((RAIZ / "docs/assets").glob("*.svg")) + sorted(PASTA_MS.glob("*.svg"))
              + [RAIZ / "scripts/gerar-banners.py", RAIZ / "docs/_includes/head-custom.html"])


@pytest.mark.parametrize("arquivo", IDENTIDADE, ids=lambda p: str(p.relative_to(RAIZ)))
def test_vermelho_nao_entra_na_identidade(arquivo):
    achados = VERMELHO.findall(arquivo.read_text(encoding="utf-8"))
    assert not achados, (
        f"{arquivo.relative_to(RAIZ)} usa vermelho ({achados[0]}); o manual da M&S do "
        "Brasil o exclui da identidade, nem como destaque")


def test_os_padroes_reconhecem_o_que_devem():
    assert VERMELHO.search('<rect fill="#EF4444"/>')
    assert VERMELHO.search("--ms-erro: #B42318;")
    assert VERMELHO.search("color: red;")
    assert not VERMELHO.search('<rect fill="#0891B2"/> shape-rendering="crispEdges"')
    assert SVG_INSEGURO.search('<svg onload="x()">')
    assert SVG_INSEGURO.search('<image href="https://exemplo.com/a.png"/>')
    assert not SVG_INSEGURO.search('<svg xmlns="http://www.w3.org/2000/svg" role="img">')
