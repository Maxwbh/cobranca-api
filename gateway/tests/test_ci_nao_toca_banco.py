# Teste contra banco não roda no GitHub Actions.
#
# O que a regressão contra banco exige para valer alguma coisa é `client_secret`,
# certificado `.pfx` e a senha dele, dos dois bancos — material que abre conta de
# produção da empresa. Em secret de repositório isso se espalha por runner
# compartilhado, log de job e artefato, por um teste que, fora da janela do
# sandbox, nem conclusivo é.
#
# Havia um workflow agendado (`regressao-hml.yml`). Enquanto existiu sem os
# secrets cadastrados, reprovou toda semana por credencial ausente e não por
# defeito — três execuções seguidas em vermelho que não significavam nada, que é
# o jeito mais rápido de ensinar a ignorar o vermelho.
#
# A regra fica aqui porque regra escrita e não cobrada é como ela volta: basta
# alguém acrescentar um workflow "só para conferir o sandbox".
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

#: Secret cujo nome denuncia credencial de banco. Não é lista de nomes exatos:
#: o que se quer barrar é a PRÓXIMA variação, não as que já existiram.
CREDENCIAL_DE_BANCO = re.compile(
    r"secrets\.\w*(C6|SICOOB|INTER|ITAU|CLIENT_SECRET|PFX|CERT|CHAVE_PIX)\w*",
    re.IGNORECASE,
)


def _arquivos() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


def test_existe_workflow_para_conferir():
    """Sem isto, um diretório vazio (ou renomeado) faria a prova abaixo passar
    sem olhar nada — que é o modo de falhar deste tipo de guarda."""
    assert _arquivos(), f"nenhum workflow encontrado em {WORKFLOWS}"


@pytest.mark.parametrize("arquivo", _arquivos(), ids=lambda p: p.name)
def test_workflow_nao_usa_credencial_de_banco(arquivo: Path):
    texto = arquivo.read_text(encoding="utf-8")
    achados = sorted(set(CREDENCIAL_DE_BANCO.findall(texto)))
    linhas = [f"  {n}: {l.strip()}"
              for n, l in enumerate(texto.splitlines(), 1)
              if CREDENCIAL_DE_BANCO.search(l)]
    assert not achados, (
        f"{arquivo.name} usa secret de credencial de banco — teste contra banco "
        "não roda no Actions. Rode `postman/run-regressao.sh` na máquina de quem "
        "tem a credencial (ver postman/README.md):\n" + "\n".join(linhas))


def test_o_padrao_reconhece_uma_credencial_de_banco():
    """A prova acima só vale se o padrão pegar o caso real — um padrão que não
    casa com nada aprova todo workflow em silêncio."""
    assert CREDENCIAL_DE_BANCO.search("${{ secrets.COB_C6_CLIENT_SECRET }}")
    assert CREDENCIAL_DE_BANCO.search("${{ secrets.COB_SICOOB_PFX_BASE64 }}")
    assert CREDENCIAL_DE_BANCO.search("${{ secrets.COB_CHAVE_PIX }}")
    # E não pode barrar o que é legítimo no CI.
    assert not CREDENCIAL_DE_BANCO.search("${{ secrets.GITHUB_TOKEN }}")
    assert not CREDENCIAL_DE_BANCO.search("${{ vars.KEEPALIVE_URLS }}")
