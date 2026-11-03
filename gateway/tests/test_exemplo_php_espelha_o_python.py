# O exemplo em PHP espelha o de Python — rota a rota.
#
# `examples/php/` existe porque PHP é a linguagem mais difundida no público que
# o roadmap Mercosul mira, e nasceu como ESPELHO de `examples/python/`: mesmos
# três scripts, mesmas rotas, mesma saída. Espelho que não é cobrado deixa de
# ser espelho na primeira mudança — um dos lados troca a rota, o outro fica
# ensinando a antiga, e ninguém percebe porque "o exemplo roda" (o que roda é
# o outro).
#
# Este guarda cobra o que dá para cobrar sem a API no ar: os pares existem, cada
# par chama as mesmas rotas, os dois leem a mesma variável `API`, e o PHP sai
# com código ≠ 0 quando falha. Rodar os dois contra o container é da revisão —
# e foi feito antes de este arquivo existir.
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PY = RAIZ / "examples" / "python"
PHP = RAIZ / "examples" / "php"

#: Rota dentro de uma string: `"/cobranca"`, `'{API}/api/remessa'`,
#: `"$API/api/boleto"`. Só literal entre aspas — prosa e comentário citam rota
#: em crase ou sem aspas, e não é o que o script CHAMA.
ROTA = re.compile(r"""["'][^"'\n]*?(/api/[a-z_/]+|/cobranca)["']""")


def _pares() -> list[tuple[Path, Path]]:
    return [(p, PHP / (p.stem + ".php")) for p in sorted(PY.glob("generate_*.py"))]


def _rotas(arq: Path) -> set[str]:
    return set(ROTA.findall(arq.read_text(encoding="utf-8")))


def test_existe_par_para_conferir():
    assert len(_pares()) >= 3, f"poucos scripts Python em {PY}"


@pytest.mark.parametrize("py,php", _pares(), ids=lambda p: p.name)
def test_todo_script_python_tem_o_gemeo_em_php(py: Path, php: Path):
    assert php.is_file(), f"{py.name} não tem o par {php.relative_to(RAIZ)}"


@pytest.mark.parametrize("py,php", _pares(), ids=lambda p: p.name)
def test_o_par_chama_as_mesmas_rotas(py: Path, php: Path):
    if not php.is_file():
        pytest.skip("sem par — o teste anterior acusa")
    rotas_py, rotas_php = _rotas(py), _rotas(php)
    assert rotas_py, f"{py.name}: o padrão não achou rota nenhuma — reveja o guarda"
    assert rotas_py == rotas_php, (
        f"{py.name} chama {sorted(rotas_py)}; {php.name} chama {sorted(rotas_php)}. "
        "Os dois têm de ensinar as mesmas rotas.")


@pytest.mark.parametrize("php", sorted(PHP.glob("*.php")), ids=lambda p: p.name)
def test_o_php_le_a_variavel_api_e_falha_alto(php: Path):
    texto = php.read_text(encoding="utf-8")
    assert "getenv('API')" in texto and "http://localhost:8000" in texto, (
        f"{php.name} não lê `API` com fallback em localhost:8000 — o README promete")
    assert "exit(1)" in texto, (
        f"{php.name} nunca sai com código ≠ 0 — falha em CI ficaria verde")
    assert "onrender.com" not in texto


@pytest.mark.parametrize("php", sorted(PHP.glob("*.php")), ids=lambda p: p.name)
def test_o_php_compila(php: Path):
    """`php -l` é o mínimo: exemplo com erro de sintaxe ensina a não rodar."""
    if not shutil.which("php"):
        pytest.skip("sem interpretador php neste ambiente")
    r = subprocess.run(["php", "-l", str(php)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_o_readme_lista_todos_os_scripts():
    readme = (PHP / "README.md").read_text(encoding="utf-8")
    faltam = [p.name for p in PHP.glob("*.php") if f"`{p.name}`" not in readme]
    assert not faltam, f"examples/php/README.md não lista {faltam}"


def test_o_padrao_reconhece_as_linhas_reais():
    """Controle: o regex tem de pegar as três grafias que existem nos scripts —
    padrão que não casa com nada aprova todo par em silêncio."""
    assert ROTA.findall('registro = post("/cobranca", COBRANCA)') == ["/cobranca"]
    assert ROTA.findall("REMESSA_URL = f'{API}/api/remessa'") == ["/api/remessa"]
    assert ROTA.findall('$API_URL = "$API/api/boleto";') == ["/api/boleto"]
    assert ROTA.findall("post('/api/render/boleto', ['bank' => 'itau'") == ["/api/render/boleto"]
    # prosa e comentário ficam de fora
    assert ROTA.findall("# e aí `GET /cobranca/{id}/pdf` responde 422") == []
    assert ROTA.findall("// Carnê é o endpoint POST /api/render/carne") == []
