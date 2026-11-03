# Link absoluto para o repositório aponta para um caminho que EXISTE.
#
# O site é publicado a partir de `main`, então uma página só aparece lá quando
# `main` também tem o que ela linka — e por isso os links para código usam
# `tree/main`/`blob/main`, não a branch de trabalho. O que isso não garante é
# que o caminho exista: `examples/php` nasceu numa branch e a página em
# espanhol o linkou antes do merge; uma revisão externa leu a branch no GitHub
# e achou o link quebrado. Aqui o caminho é conferido contra a árvore atual —
# se existe aqui, existe em `main` quando a página for publicada.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
LINK = re.compile(r"https://github\.com/Maxwbh/cobranca-api/(?:tree|blob)/main/([^)\s#\"'>]+)")


def _arquivos() -> list[Path]:
    achados = [RAIZ / "README.md", RAIZ / "CONTRIBUTING.md"]
    achados += [p for p in (RAIZ / "docs").rglob("*.md") if "swagger" not in p.parts]
    achados += list((RAIZ / "examples").rglob("*.md")) + list((RAIZ / "postman").glob("*.md"))
    return sorted(p for p in achados if p.is_file())


def _links() -> list[tuple[str, str]]:
    pares = []
    for arq in _arquivos():
        for m in LINK.finditer(arq.read_text(encoding="utf-8")):
            pares.append((str(arq.relative_to(RAIZ)), m.group(1).rstrip("/")))
    return pares


def test_existe_link_para_conferir():
    # Eram 20 em 03/11/2026 (medidos); o piso prova que a varredura achou algo.
    assert len(_links()) >= 15, "a varredura não achou links para o repositório — o padrão quebrou"


@pytest.mark.parametrize("arquivo,caminho", sorted(set(_links())), ids=lambda x: x[:60])
def test_o_caminho_linkado_existe_na_arvore(arquivo: str, caminho: str):
    assert (RAIZ / caminho).exists(), (
        f"{arquivo} linka github.com/.../main/{caminho}, que não existe na árvore — "
        "em `main` o link vai quebrar")


def test_o_padrao_reconhece_o_caso_que_motivou():
    assert LINK.findall("[PHP](https://github.com/Maxwbh/cobranca-api/tree/main/examples/php) y") == ["examples/php"]
    assert LINK.findall("ver [guia](https://github.com/Maxwbh/cobranca-api/blob/main/docs/api/encargos.md)") == ["docs/api/encargos.md"]
    assert LINK.findall("https://github.com/Maxwbh/cobranca-api/releases") == []
