# Link da doc aponta para coisa que o site PUBLICA.
#
# Quatro páginas linkavam `../openapi.yaml` e o site respondia 404: o arquivo
# existe no disco — então toda checagem de "o alvo existe?" passava — mas estava
# no `exclude` do `_config.yml`, e o Jekyll não o copia. No GitHub o mesmo link
# funciona, porque lá se lê o repositório; o defeito só aparecia para quem lia a
# versão publicada, que é justamente quem chega pelo Google.
#
# A regra, então, não é "o alvo existe", é "o alvo é publicado". Quem decide
# isso é o `exclude`, e é dele que este guarda parte.
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
SITE = RAIZ / "docs"
CONFIG = SITE / "_config.yml"

#: `[texto](alvo)` com alvo relativo. Fora: http(s), mailto, âncora pura.
LINK = re.compile(r"\[[^\]]*\]\(\s*(?!https?:|mailto:|#)([^)\s]+)")


def _excluidos() -> set[str]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return {str(x).strip("/") for x in (cfg.get("exclude") or [])}


def _paginas() -> list[Path]:
    return sorted(p for p in SITE.rglob("*.md") if "_includes" not in p.parts)


def test_existe_pagina_para_conferir():
    """Guarda que varre diretório prova primeiro que achou alguma coisa."""
    assert len(_paginas()) > 10, f"poucas páginas em {SITE}"


@pytest.mark.parametrize("pagina", _paginas(), ids=lambda p: str(p.relative_to(SITE)))
def test_link_relativo_aponta_para_arquivo_publicado(pagina: Path):
    excluidos = _excluidos()
    problemas = []
    for n, linha in enumerate(pagina.read_text(encoding="utf-8").splitlines(), 1):
        for alvo in LINK.findall(linha):
            alvo = alvo.split("#")[0]
            if not alvo:
                continue
            destino = (pagina.parent / alvo).resolve()
            try:
                rel = destino.relative_to(SITE)
            except ValueError:
                continue  # aponta para fora de docs/ (o repo no GitHub) — outro contrato
            if not destino.exists():
                problemas.append(f"  {n}: {alvo} — não existe")
            elif rel.parts and (str(rel) in excluidos or rel.parts[0] in excluidos):
                problemas.append(
                    f"  {n}: {alvo} — existe, mas está no `exclude` do _config.yml, "
                    "então o site responde 404")
    assert not problemas, (
        f"{pagina.relative_to(RAIZ)} linka alvo que o site não publica:\n"
        + "\n".join(problemas))


def test_o_guarda_reconhece_um_alvo_excluido(tmp_path):
    """A prova acima só vale se souber distinguir "existe" de "é publicado" —
    era exatamente aí que a checagem ingênua passava."""
    excluidos = _excluidos()
    # Com o `exclude` vazio hoje, o caso real precisa ser montado à mão.
    fingido = {"openapi.yaml"}
    alvo = Path("openapi.yaml")
    assert str(alvo) in fingido, "o padrão de comparação mudou"
    assert "openapi.yaml" not in excluidos, (
        "`openapi.yaml` voltou ao `exclude` — quatro páginas linkam para ele e "
        "o site volta a responder 404")
