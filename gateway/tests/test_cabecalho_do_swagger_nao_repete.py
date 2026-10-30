# O cabeçalho não diz a mesma coisa duas vezes.
#
# O `docker run` aparecia DUAS vezes no Swagger publicado, com dez pixels de
# distância: uma na linha de detalhe e outra no chip do herói. Não era cópia e
# cola — eram duas decisões certas em momentos diferentes. O
# `gerar-swagger-estatico.py` trazia um "para executar:" desde que a página
# publicada passou a existir sem servidor atrás; depois o comando entrou no
# herói do `swagger_tema`, que serve as duas superfícies. Nenhuma das duas
# sabia da outra.
#
# E o defeito só aparecia no SITE: ao vivo o `detalhe` nunca teve o sufixo,
# então screenshot local não mostrava nada. Quem viu foi a página publicada.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

PAGINAS = ("docs/swagger/index.html", "docs/swagger/offline.html")

#: O que não pode se repetir no cabeçalho. São as afirmações da casca — o
#: corpo da spec pode citar o comando à vontade, e cita.
UMA_VEZ_SO = (
    "docker run -p 8000:8000",
    "ghcr.io/maxwbh/cobranca-api:latest",
)


def _cabecalho(arq: str) -> str:
    """Só o `<div class="cob-topbar">…</div>`, não a página inteira."""
    texto = (RAIZ / arq).read_text(encoding="utf-8")
    m = re.search(r'<div class="cob-topbar">.*?\n  </div>', texto, re.S)
    assert m, f"{arq}: o herói mudou de forma — reveja este guarda"
    return m.group(0)


@pytest.mark.parametrize("arq", PAGINAS)
@pytest.mark.parametrize("frase", UMA_VEZ_SO)
def test_o_cabecalho_nao_repete_a_mesma_frase(arq: str, frase: str):
    n = _cabecalho(arq).count(frase)
    assert n <= 1, (
        f"{arq}: o cabeçalho diz {frase!r} {n} vezes. O comando vive no herói "
        "(`swagger_tema.TAGLINE`), que vale para a página servida e para a "
        "publicada — quem o repetir aqui está duplicando o que já está lá.")


@pytest.mark.parametrize("arq", PAGINAS)
def test_o_cabecalho_ainda_ensina_a_executar(arq: str):
    """O oposto do caso acima, e igualmente necessário.

    Tirar a repetição não pode virar tirar a informação: a página publicada
    não tem servidor atrás, e sem o comando o leitor clica em `Try it out`,
    não acontece nada, e ele conclui que a API está quebrada.
    """
    cab = _cabecalho(arq)
    assert "docker run -p 8000:8000" in cab, (
        f"{arq}: o cabeçalho deixou de dizer como executar")


def test_o_gerador_nao_tem_mais_sufixo_proprio():
    """A fonte do defeito: um "onde executar" só do site, fora do tema."""
    gerador = (RAIZ / "scripts" / "gerar-swagger-estatico.py").read_text(encoding="utf-8")
    assert "_ONDE_EXECUTAR" not in gerador, (
        "voltou um texto de 'como executar' só para o site. Ele vive no herói "
        "do `swagger_tema`, que serve as duas superfícies.")
