"""Swagger bilíngue: a spec continua sendo gerada do código, em português; a
versão em espanhol é a MESMA spec com os textos trocados por um dicionário.

Por que dicionário, e não uma segunda spec: duas specs divergem na primeira
edição. Aqui a estrutura (rotas, campos, tipos, exemplos) é uma só, e só o que
é texto para humano — `summary`, `description` — passa pelo mapa. Texto que a
spec em português ganha ou muda deixa de ter par em espanhol, e o guarda
(`tests/test_swagger_em_espanhol.py`) acusa: a tradução não envelhece em
silêncio, envelhece em vermelho.

O dicionário é `docs/i18n/es/swagger.yaml`: uma lista de pares `pt`/`es`, com
o português INTEIRO como chave. Chave longa de propósito — mudou uma palavra
no código, a entrada deixa de casar, e é isso que se quer.

Textos iguais em várias rotas (`tenant_id` em 49 delas, "Successful Response"
em todas) são UMA entrada. Era isso que fazia "traduzir a spec" parecer 16 mil
palavras: distintas, são bem menos.
"""
from __future__ import annotations

import copy
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[3]
DICIONARIO = REPO / "docs" / "i18n" / "es" / "swagger.yaml"

#: Chaves cujo valor é texto para humano. `title` fica de fora: na spec do
#: gateway é o nome do campo em Title Case ("Tenant Id"), não descrição.
CHAVES_DE_TEXTO = ("summary", "description")

IDIOMAS = ("pt", "es")


def _e_texto(chave: str, valor: Any) -> bool:
    return chave in CHAVES_DE_TEXTO and isinstance(valor, str) and valor.strip() != ""


def textos_da_spec(spec: dict) -> list[str]:
    """Todo texto traduzível da spec, distinto, na ordem em que aparece."""
    vistos: dict[str, None] = {}

    def anda(no: Any) -> None:
        if isinstance(no, dict):
            for k, v in no.items():
                if _e_texto(k, v):
                    vistos.setdefault(v, None)
                else:
                    anda(v)
        elif isinstance(no, list):
            for item in no:
                anda(item)

    anda(spec)
    return list(vistos)


@lru_cache(maxsize=1)
def dicionario(idioma: str = "es") -> dict[str, str]:
    """`{texto_pt: texto_es}`. Entrada com `es` vazio não conta como traduzida."""
    arq = DICIONARIO if idioma == "es" else DICIONARIO.with_name(f"swagger.{idioma}.yaml")
    if not arq.is_file():
        return {}
    dados = yaml.safe_load(arq.read_text(encoding="utf-8")) or {}
    return {e["pt"]: e["es"] for e in dados.get("textos", [])
            if isinstance(e, dict) and e.get("pt") and (e.get("es") or "").strip()}


def faltam(spec: dict, idioma: str = "es") -> list[str]:
    """Textos da spec sem tradução no dicionário. Vazio = cobertura total."""
    mapa = dicionario(idioma)
    return [t for t in textos_da_spec(spec) if t not in mapa]


def sobram(specs: list[dict], idioma: str = "es") -> list[str]:
    """Entradas do dicionário que nenhuma spec usa mais — texto em português
    que mudou ou saiu, e cuja tradução ficou órfã."""
    usados = {t for s in specs for t in textos_da_spec(s)}
    return [pt for pt in dicionario(idioma) if pt not in usados]


def traduzir_spec(spec: dict, idioma: str = "es") -> dict:
    """Cópia da spec com os textos trocados. O que não tem par fica em português
    — melhor do que sumir —, e o guarda é quem cobra que isso não aconteça."""
    if idioma == "pt":
        return spec
    mapa = dicionario(idioma)
    novo = copy.deepcopy(spec)

    def anda(no: Any) -> None:
        if isinstance(no, dict):
            for k, v in list(no.items()):
                if _e_texto(k, v):
                    no[k] = mapa.get(v, v)
                else:
                    anda(v)
        elif isinstance(no, list):
            for item in no:
                anda(item)

    anda(novo)
    return novo


_Q = re.compile(r"^\s*([A-Za-z]{1,8})(?:-[A-Za-z0-9]{1,8})*\s*(?:;\s*q\s*=\s*([0-9.]+))?\s*$")


def idioma_pedido(accept_language: str | None, query_lang: str | None = None) -> str:
    """`?lang=es` manda; senão o `Accept-Language` decide entre `pt` e `es`.

    Só o idioma primário conta (`es-PY`, `es-AR`, `es-419` são `es`). Em
    empate ou ausência, português — a língua do código e da API.
    """
    if query_lang:
        q = query_lang.strip().lower()[:2]
        return q if q in IDIOMAS else "pt"
    if not accept_language:
        return "pt"
    melhor, peso = "pt", 0.0
    for parte in accept_language.split(","):
        m = _Q.match(parte)
        if not m:
            continue
        lingua = m.group(1).lower()
        q = float(m.group(2)) if m.group(2) else 1.0
        if lingua in IDIOMAS and q > peso:
            melhor, peso = lingua, q
        elif lingua in IDIOMAS and q == peso and lingua == "pt":
            melhor = "pt"
    return melhor
