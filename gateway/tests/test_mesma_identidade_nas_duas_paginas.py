# Site e Swagger são a mesma marca — e nada cobrava isso.
#
# As duas páginas que o leitor vê (a capa em `maxwbh.github.io/cobranca-api` e
# o Swagger, servido em `/docs` e publicado em `swagger/`) são montadas por
# arquivos diferentes: `docs/_includes/head-custom.html` e
# `gateway/app/core/swagger_tema.py`. A paleta estava escrita nos dois, à mão,
# em hexadecimal.
#
# Já tinha divergido em três tokens, todos para papéis que o site resolvia:
# `#A5F3FC` no texto da pill (o site usa `#67E8F9`), `#E8EEF6` no código inline
# (`#F1F5F9`) e `#ECFEFF` no hover do chip (`#F0F9FF`). Ninguém decidiu isso —
# foram escolhas independentes em dois arquivos para o mesmo elemento.
#
# A regra é uma: a paleta do Swagger é um SUBCONJUNTO da do site. O site manda,
# porque é a capa; o Swagger não inventa cor.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SITE = RAIZ / "docs" / "_includes" / "head-custom.html"
SWAGGER = RAIZ / "gateway" / "app" / "core" / "swagger_tema.py"

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")

#: Os cinco que definem a marca. Precisam estar nos DOIS: é o que faz uma
#: página parecer a outra, e não só não se contradizer.
NUCLEO = {
    "#0F172A": "navy do cabeçalho",
    "#152449": "navy claro do gradiente",
    "#06B6D4": "ciano da marca",
    "#22D3EE": "ciano do hover",
    "#F8FAFC": "off-white do texto sobre navy",
}


def _cores(arq: Path) -> set[str]:
    return {m.group(0).upper() for m in HEX.finditer(arq.read_text(encoding="utf-8"))}


def test_os_dois_arquivos_de_identidade_existem():
    for arq in (SITE, SWAGGER):
        assert arq.is_file(), f"{arq.relative_to(RAIZ)} sumiu — reveja este guarda"


def test_o_swagger_nao_inventa_cor_fora_da_paleta_do_site():
    extras = sorted(_cores(SWAGGER) - _cores(SITE))
    assert not extras, (
        f"o tema do Swagger usa {extras}, que não existem em "
        f"{SITE.relative_to(RAIZ)}. Use um token do site, ou acrescente o novo "
        "lá primeiro — a capa é quem define a paleta.")


@pytest.mark.parametrize("cor,papel", sorted(NUCLEO.items()))
def test_a_cor_do_nucleo_da_marca_esta_nas_duas_paginas(cor: str, papel: str):
    faltam = [arq.relative_to(RAIZ) for arq in (SITE, SWAGGER)
              if cor not in _cores(arq)]
    assert not faltam, f"{cor} ({papel}) sumiu de {faltam}"


def test_a_tabela_da_descricao_rola_sozinha():
    """Medido com navegador a 390px: a tabela da descrição tem ~635px de
    largura natural e, com `overflow: hidden`, empurrava a PÁGINA inteira para
    fora — 390 de viewport contra 681 de conteúdo, rolagem horizontal valendo
    para o texto também. Com rolagem própria, quem rola é a tabela.

    Guarda estático porque o CI não roda navegador: o que fica preso é a regra
    que a medição ensinou.
    """
    # Os comentários saem ANTES de procurar regra: o comentário deste bloco
    # explica o defeito citando `overflow: hidden`, e a primeira versão deste
    # guarda acusou a própria explicação de ser a regra que ela descreve.
    css = re.sub(r"/\*.*?\*/", " ", SWAGGER.read_text(encoding="utf-8"), flags=re.S)
    bloco = re.search(r"\.swagger-ui \.info \.description table \{(.*?)\}", css, re.S)
    assert bloco, "o bloco da tabela mudou de forma — reveja este guarda"
    regras = bloco.group(1)
    assert "overflow-x: auto" in regras and "display: block" in regras, (
        "a tabela da descrição voltou a não rolar sozinha; no telefone ela "
        f"arrasta a página inteira. Regras atuais: {regras.strip()[:200]}")
    assert "overflow: hidden" not in regras, (
        "`overflow: hidden` voltou — foi exatamente ele que escondeu o estouro "
        "em vez de contê-lo")


def test_o_guarda_reconhece_uma_cor_de_fora(tmp_path):
    """Controle: um token inventado precisa ser pego.

    Com as duas paletas alinhadas hoje, o caso real tem de ser montado — senão
    este arquivo ficaria verde mesmo com o padrão quebrado.
    """
    falso = SWAGGER.read_text(encoding="utf-8").replace("#06B6D4", "#FF00FF", 1)
    arq = tmp_path / "swagger_tema.py"
    arq.write_text(falso, encoding="utf-8")
    extras = _cores(arq) - _cores(SITE)
    assert "#FF00FF" in extras, "o padrão parou de extrair cor do tema"
