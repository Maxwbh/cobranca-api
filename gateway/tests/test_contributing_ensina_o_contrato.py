# O guia de contribuição ensina o contrato de hoje, numa língua só.
#
# Revisão externa de 01/11/2026: no meio do exemplo de teste em pytest havia
# um bloco RSpec (`describe … do … end`) da era da engine Ruby, e o exemplo
# Python mandava `"provider": "banconovo"` — o apelido legado que sai na 4.0.0
# — e esperava `200` de um `POST /cobranca` que responde `201`. Quem copia o
# guia copia o contrato errado.
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TEXTO = (RAIZ / "CONTRIBUTING.md").read_text(encoding="utf-8")


def _blocos_python() -> list[str]:
    return re.findall(r"```python\n(.*?)```", TEXTO, re.S)


def test_nenhum_bloco_python_tem_ruby_dentro():
    for bloco in _blocos_python():
        for sinal in ("describe '", "it '", "expect(", "\nend\n", ".to eq("):
            assert sinal not in bloco, f"bloco Python com Ruby dentro: {sinal!r}"


def test_o_exemplo_de_teste_ensina_os_dois_eixos_e_o_201():
    exemplo = next((b for b in _blocos_python() if "/cobranca" in b), None)
    assert exemplo, "o exemplo de teste de `POST /cobranca` sumiu do guia"
    assert re.search(r'"provider":\s*"(on|off)"', exemplo), "o exemplo tem de usar `provider=on|off`"
    assert '"banco":' in exemplo, "o exemplo tem de dizer o `banco` à parte"
    assert "status_code == 201" in exemplo, "`POST /cobranca` responde 201, não 200"
    assert not re.search(r'"provider":\s*"(c6|sicoob|inter|itau|banconovo|pycobranca)"', exemplo), (
        "nome de banco no `provider` é o apelido legado — não é o que o guia ensina")
