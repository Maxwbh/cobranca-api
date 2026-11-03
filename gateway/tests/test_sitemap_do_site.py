# O sitemap publicado lista páginas de conteúdo, e só elas.
#
# Revisão externa de 03/11/2026 do sitemap.xml, medida contra o site: o
# `jekyll-sitemap` listava o arquivo de verificação do Search Console
# (`googlec2394c0afd3e8857.html` — existe para o Google ler, não para o
# Google indexar) e `/assets/`, que é o README da identidade visual virando
# índice de pasta pelo `jekyll-readme-index` — notas de manutenção, não
# documentação. O plugin só deixa um arquivo de fora com `sitemap: false`, e
# para arquivo estático e README isso se declara em `defaults` do
# `_config.yml`, porque front matter num README aparece como tabela no GitHub.
#
# Este guarda lê o `_config.yml` como o plugin lê: todo caminho de
# `FORA_DO_SITEMAP` tem de ter um `defaults` com `sitemap: false`, e nenhuma
# página de conteúdo pode ter sido posta de fora por engano.
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
SITE = RAIZ / "docs"
CONFIG = yaml.safe_load((SITE / "_config.yml").read_text(encoding="utf-8"))

#: O que existe em `docs/` mas não é página para o Google achar.
FORA_DO_SITEMAP = {
    "googlec2394c0afd3e8857.html",  # verificação do Search Console
    "assets/README.md",             # notas de manutenção da identidade visual → /assets/
}

#: O que TEM de continuar no sitemap — a porta de entrada de cada público.
DENTRO_DO_SITEMAP = {"index.md", "es/index.md", "es/comercial.md", "deploy.md",
                     "development/index.md", "fields/README.md", "homologacao/README.md"}


def _fora_pelo_defaults() -> set[str]:
    fora = set()
    for regra in CONFIG.get("defaults") or []:
        if (regra.get("values") or {}).get("sitemap") is False:
            fora.add(str((regra.get("scope") or {}).get("path", "")).strip("/"))
    return fora


def test_o_plugin_de_sitemap_esta_ligado():
    assert "jekyll-sitemap" in (CONFIG.get("plugins") or []), "sem jekyll-sitemap não há sitemap.xml"


def test_o_que_nao_e_conteudo_fica_fora_do_sitemap():
    fora = _fora_pelo_defaults()
    for caminho in sorted(FORA_DO_SITEMAP):
        assert (SITE / caminho).exists(), f"{caminho} sumiu de docs/ — reveja a lista deste guarda"
        assert caminho in fora, (
            f"{caminho} entra no sitemap.xml: falta um `defaults` com `scope.path: {caminho}` "
            "e `values.sitemap: false` no docs/_config.yml")


def test_nenhuma_pagina_de_conteudo_foi_posta_de_fora():
    fora = _fora_pelo_defaults()
    for caminho in sorted(DENTRO_DO_SITEMAP):
        assert (SITE / caminho).exists(), f"{caminho} sumiu de docs/"
        assert caminho not in fora and not any(caminho.startswith(f + "/") for f in fora if f), (
            f"{caminho} está fora do sitemap por `defaults` — é página de conteúdo")
    # `sitemap: false` no front matter de uma página de conteúdo é o mesmo erro
    for caminho in sorted(DENTRO_DO_SITEMAP):
        texto = (SITE / caminho).read_text(encoding="utf-8")
        if texto.startswith("---"):
            fm = yaml.safe_load(texto.split("---")[1]) or {}
            assert fm.get("sitemap") is not False, f"{caminho} tem `sitemap: false` no front matter"
