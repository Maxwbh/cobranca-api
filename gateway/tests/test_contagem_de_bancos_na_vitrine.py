# "4 bancos ON · 19 OFF" está escrito à mão em quatro arquivos.
#
# A mesma frase aparece no `pill` de `/docs` e de `/redoc` (`app/main.py`), no
# Swagger publicado (`scripts/gerar-swagger-estatico.py`) e na pílula do banner
# da capa (`scripts/gerar-banners.py`). Quatro cópias, nenhuma derivada do
# serviço — e até hoje o banner dizia outra coisa: "19 bancos", o total de
# instituições distintas. Não estava errado; respondia OUTRA pergunta, e as
# duas telas da mesma marca davam números diferentes sem dizer de quê.
#
# A contagem agora é uma só, na forma que diz o que cada número é. Este guarda
# cobra as duas coisas: que as cópias concordem entre si, e que concordem com
# o que a API publica.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

#: `N bancos ON · M OFF`, nas quatro grafias em que a frase existe hoje.
FRASE = re.compile(r"(\d+)\s*bancos?\s*ON\s*[·.]\s*(\d+)\s*OFF", re.IGNORECASE)

ARQUIVOS = (
    "gateway/app/main.py",
    "scripts/gerar-swagger-estatico.py",
    "scripts/gerar-banners.py",
    "docs/assets/banner.svg",
    "docs/assets/banner-mobile.svg",
)


def _reais() -> tuple[int, int]:
    """(online, offline) medidos no serviço, não digitados."""
    from fastapi.testclient import TestClient

    from app.core import pycob
    from app.main import app
    itens = TestClient(app).get("/bancos").json()["bancos"]
    online = len([b for b in itens if "on" in b["caminhos"]])
    return online, len(pycob.bancos_suportados())


def _ocorrencias(arq: str) -> list[tuple[int, int, int]]:
    """(linha, online, offline) de cada vez que a frase aparece no arquivo."""
    texto = (RAIZ / arq).read_text(encoding="utf-8")
    return [(texto.count("\n", 0, m.start()) + 1, int(m.group(1)), int(m.group(2)))
            for m in FRASE.finditer(texto)]


def test_a_frase_existe_em_todos_os_arquivos_que_a_publicam():
    """Varredura que não acha nada passa por engano — e este guarda só vale se
    souber que o banner, o Swagger servido e o publicado estão todos cobertos."""
    faltam = [a for a in ARQUIVOS if not _ocorrencias(a)]
    assert not faltam, (
        f"a frase 'N bancos ON · M OFF' sumiu de {faltam}. Se foi reescrita, "
        "atualize o padrão aqui — não deixe o guarda verde sobre o que não vê.")


@pytest.mark.parametrize("arq", ARQUIVOS)
def test_a_contagem_publicada_bate_com_o_servico(arq: str):
    online, offline = _reais()
    errados = [f"  linha {n}: diz {o} ON · {f} OFF"
               for n, o, f in _ocorrencias(arq) if (o, f) != (online, offline)]
    assert not errados, (
        f"{arq} contradiz o serviço, que tem {online} online e {offline} "
        "offline:\n" + "\n".join(errados))


def test_as_quatro_copias_dizem_a_mesma_coisa():
    """Entre si, antes mesmo de bater com o serviço: duas cópias concordando
    com o serviço e uma terceira fora do padrão seria pega acima, mas o erro
    que custa caro é o silencioso — duas telas, dois números."""
    vistas = {(o, f) for arq in ARQUIVOS for _, o, f in _ocorrencias(arq)}
    assert len(vistas) == 1, f"as cópias divergem entre si: {sorted(vistas)}"


def test_o_banner_e_derivado_do_script_e_nao_editado_a_mao():
    """O `.svg` é artefato: quem manda é `scripts/gerar-banners.py`. Editar o
    SVG direto funciona até alguém rodar o gerador e a edição sumir."""
    for arte in ("banner.svg", "banner-mobile.svg"):
        texto = (RAIZ / "docs" / "assets" / arte).read_text(encoding="utf-8")
        assert "GERADO por scripts/gerar-banners.py" in texto, (
            f"{arte} perdeu o aviso de que é gerado")


def test_o_guarda_reconhece_a_grafia_que_saiu(tmp_path):
    """Controle: o padrão tem de pegar a forma publicada, e NÃO pegar a frase
    antiga, que contava outra coisa."""
    assert FRASE.search("4 bancos ON · 19 OFF")
    assert FRASE.search('pill="4 bancos ON · 19 OFF",')
    assert not FRASE.search("19 bancos"), "a frase do total não é esta contagem"
    assert not FRASE.search("19 bancos · sem convênio"), (
        "a pílula da superfície offline conta só um lado — não entra aqui")
