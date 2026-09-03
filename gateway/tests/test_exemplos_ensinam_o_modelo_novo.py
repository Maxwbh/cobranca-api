# Exemplo de cliente ensina os DOIS EIXOS, não o apelido legado.
#
# `provider` é o CAMINHO (`on`/`off`) e `banco` é a INSTITUIÇÃO. O nome do banco
# no `provider` (`c6`, `sicoob`, `inter`, `itau`) e o `pycobranca` seguem
# aceitos como apelido — há integração em produção e roteiro de homologação já
# enviado ao banco com esses payloads —, e saem na 3.0.0.
#
# Aceitar é uma coisa; ENSINAR é outra. As três funções de checkout do pacote
# Oracle traziam `p_provider IN VARCHAR2 DEFAULT 'c6'`: quem nunca passasse o
# parâmetro herdava a grafia que vai sair, sem escolher. O cabeçalho do pacote
# ainda dizia "nada aqui precisa mudar" enquanto os arquivos de exemplo ao lado
# já usavam `'on'` + `p_banco`.
#
# Este guarda vale só para VALOR PADRÃO e para a chamada que o exemplo executa.
# Citar o apelido em prosa é o certo — é assim que se documenta o que ainda
# funciona —, e por isso comentário não é lido aqui.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
EXEMPLOS = RAIZ / "examples"

#: Apelidos legados: o nome do banco no lugar do caminho, e o `pycobranca`.
LEGADO = ("c6", "sicoob", "inter", "itau", "pycobranca")

#: `p_provider ... DEFAULT '<apelido>'` — o default é o que ensina em silêncio.
DEFAULT_LEGADO = re.compile(
    r"p_provider\s+IN\s+VARCHAR2\s+DEFAULT\s+'(" + "|".join(LEGADO) + r")'",
    re.IGNORECASE,
)


def _sql() -> list[Path]:
    return sorted(EXEMPLOS.rglob("*.sql"))


def test_existe_exemplo_sql_para_conferir():
    """Guarda que varre diretório precisa provar que achou alguma coisa."""
    assert _sql(), f"nenhum .sql em {EXEMPLOS}"


@pytest.mark.parametrize("arquivo", _sql(), ids=lambda p: p.name)
def test_nenhum_default_de_provider_usa_apelido_legado(arquivo: Path):
    achados = [f"  {n}: {l.strip()}"
               for n, l in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1)
               if DEFAULT_LEGADO.search(l)]
    assert not achados, (
        f"{arquivo.relative_to(RAIZ)} tem DEFAULT com apelido legado de `provider`. "
        "O padrão ensina quem nunca passa o parâmetro: use `DEFAULT 'on'` (ou "
        "`'off'`) com o `p_banco` ao lado. O apelido continua aceito na "
        "chamada:\n" + "\n".join(achados))


def test_o_padrao_reconhece_o_caso_que_existia():
    """A prova acima só vale se o padrão pegar a linha real que estava lá —
    padrão que não casa com nada aprova todo arquivo em silêncio."""
    assert DEFAULT_LEGADO.search("p_provider IN VARCHAR2 DEFAULT 'c6',")
    assert DEFAULT_LEGADO.search("  p_provider IN VARCHAR2 DEFAULT 'pycobranca')")
    # E não pode barrar o vocabulário que fica.
    assert not DEFAULT_LEGADO.search("p_provider IN VARCHAR2 DEFAULT 'on',")
    assert not DEFAULT_LEGADO.search("p_provider IN VARCHAR2 DEFAULT 'off',")
    # Nem a prosa que documenta o apelido.
    assert not DEFAULT_LEGADO.search("-- `p_provider => 'c6'` continua valendo")
