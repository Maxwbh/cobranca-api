#!/usr/bin/env python3
"""Rota do gateway que não aparece na referência quebra o build.

A referência (`docs/api/gateway-python.md`) é o que o integrador lê antes de
abrir o Swagger. Ela não envelhece com erro — envelhece com **omissão**: a rota
nova entra no código, o Swagger a mostra, e o guia simplesmente não a menciona.
Ninguém percebe, porque nada fica errado; só fica faltando.

Foi o que aconteceu até 08/2026, e em escala: o gateway expunha 67 rotas e o
guia citava 31. Faltavam o Pix Automático inteiro (16), os jobs em lote (11),
os Pix recebidos (4) e a leitura/remoção dos webhooks (4).

Esta guarda faz pela referência o que o `postman/check_coverage.py` faz pela
coleção: compara a lista de rotas da **app em execução** com o que o documento
cita, e falha quando sobra rota sem menção.

    PYTHONPATH=gateway python scripts/check_referencia_rotas.py

Só rota **do gateway** entra na conta. A superfície offline (`/api/*`) tem
documento e spec próprios (`docs/openapi.yaml`) e é conferida por lá.
"""
from __future__ import annotations

import pathlib
import re
import sys

REFERENCIA = pathlib.Path("docs/api/gateway-python.md")
METODOS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Rotas que existem e NÃO precisam estar na referência, com o motivo. Lista
# curta e justificada de propósito: isenção sem motivo vira lugar onde se
# esconde rota nova.
ISENTAS = {
    ("GET", "/docs"): "Swagger da própria app",
    ("GET", "/redoc"): "Redoc da própria app",
    ("GET", "/openapi.json"): "a spec que esta guarda usa como fonte",
}


def normalizar(caminho: str) -> str:
    """`/cobranca/{id}` e `/cobranca/{cobranca_id}` são a mesma rota."""
    return re.sub(r"\{[^}]+\}", "{x}", caminho.rstrip("?"))


def rotas_da_app() -> set[tuple[str, str]]:
    from app.main import app

    spec = app.openapi()
    return {(metodo.upper(), normalizar(caminho))
            for caminho, ops in spec["paths"].items()
            for metodo in ops
            if metodo.upper() in METODOS and not caminho.startswith("/api/")}


def rotas_citadas(texto: str) -> set[tuple[str, str]]:
    """O que o documento menciona, nas duas formas em que ele escreve rota.

    Prosa e título usam `POST /cobranca`; as tabelas separam método e caminho em
    células (`| \\`GET\\` · \\`PATCH\\` | \\`/pix-automatico/recorrencias/{id}\\` |`),
    e uma célula pode trazer mais de um de cada.
    """
    achadas: set[tuple[str, str]] = set()
    for m in re.finditer(rf"({'|'.join(METODOS)})\s+`?(/[A-Za-z0-9_/{{}}\-]+)", texto):
        achadas.add((m.group(1), normalizar(m.group(2))))

    for linha in texto.split("\n"):
        if not linha.startswith("|"):
            continue
        celulas = [c.strip() for c in linha.strip("|").split("|")]
        if len(celulas) < 2:
            continue
        metodos = re.findall(rf"`({'|'.join(METODOS)})`", celulas[0])
        caminhos = re.findall(r"`(/[A-Za-z0-9_/{}\-]+)", celulas[1])
        achadas.update((me, normalizar(ca)) for me in metodos for ca in caminhos)
    return achadas


def main() -> int:
    if not REFERENCIA.exists():
        print(f"não encontrei {REFERENCIA} — rode da raiz do repositório", file=sys.stderr)
        return 2

    reais = rotas_da_app()
    citadas = rotas_citadas(REFERENCIA.read_text())
    faltando = sorted(r for r in reais if r not in citadas and r not in ISENTAS)

    cobertas = len(reais) - len(faltando)
    print(f"{REFERENCIA}: {cobertas}/{len(reais)} rotas do gateway documentadas")

    if faltando:
        print(f"\n{len(faltando)} rota(s) sem menção na referência:", file=sys.stderr)
        for metodo, caminho in faltando:
            print(f"  {metodo:7} {caminho}", file=sys.stderr)
        print("\nAcrescente a rota ao guia (basta uma linha de tabela dizendo o que ela faz)"
              "\nou, se ela não pertence à referência, justifique em ISENTAS.", file=sys.stderr)
        return 1

    print("Referência em dia com as rotas do gateway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
