#!/usr/bin/env python3
"""Guarda de cobertura (plano §8): endpoint sem request na coleção => exit 1.

Compara:
  1. paths+methods do OpenAPI do gateway (importa o app FastAPI); e
  2. a superfície offline /api/*, derivada do PRÓPRIO ROUTER
contra os requests da coleção Postman. Uso:
  python postman/check_coverage.py            # da raiz do repo
Saída: tabela endpoint x testado (o snapshot de cobertura da evidência).
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION = os.path.join(REPO, "postman", "cobranca-api.postman_collection.json")

#: Métodos que contam como superfície. `HEAD` e `OPTIONS` o Starlette registra
#: sozinho e ninguém integra contra eles.
METODOS = ("GET", "POST", "PUT", "DELETE", "PATCH")


def norm(path: str) -> str:
    """/cobranca/{{cobranca_id}} e /cobranca/{cobranca_id} -> /cobranca/*"""
    path = re.sub(r"\{\{[^}]+\}\}", "*", path)
    path = re.sub(r"\{[^}]+\}", "*", path)
    return path.rstrip("/") or "/"


def collection_requests() -> set[tuple[str, str]]:
    data = json.load(open(COLLECTION, encoding="utf-8"))
    seen: set[tuple[str, str]] = set()

    def walk(items):
        for item in items:
            if "item" in item:
                walk(item["item"])
                continue
            r = item["request"]
            path = "/" + "/".join(r["url"].get("path", []))
            seen.add((r["method"].upper(), norm(path)))

    walk(data["item"])
    return seen


def gateway_endpoints() -> list[tuple[str, str]]:
    sys.path.insert(0, os.path.join(REPO, "gateway"))
    from app.main import app  # noqa: E402

    eps = []
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            eps.append((method.upper(), norm(path)))
    return sorted(set(eps))


def offline_endpoints() -> list[tuple[str, str]]:
    """A superfície offline sai do ROUTER, não de uma lista à mão.

    A lista que havia aqui tinha SETE rotas a menos que o router: `/api/boleto/
    multi`, as quatro `/api/render/*`, `/api/openapi.json` e `/api/openapi.yaml`.
    Elas existiam, estavam publicadas em `docs/openapi.yaml` e não tinham request
    nenhum — e não eram cobradas, porque rota fora do inventário não conta como
    faltante. O relatório dizia "Cobertura: 100%": verdade sobre a lista, falso
    sobre a superfície.

    Um inventário à mão só está certo no dia em que é escrito. Este se corrige
    sozinho quando entra rota nova — que é o único momento em que alguém precisa
    ser avisado.
    """
    sys.path.insert(0, os.path.join(REPO, "gateway"))
    from app.routers import offline  # noqa: E402

    eps = {
        (metodo, norm(rota.path))
        for rota in offline.router.routes
        for metodo in (getattr(rota, "methods", ()) or ())
        if getattr(rota, "path", "").startswith("/api/") and metodo in METODOS
    }
    return sorted(eps)


def main() -> int:
    tested = collection_requests()
    missing = []
    print(f"{'Endpoint':60} Testado")
    for method, path in gateway_endpoints() + offline_endpoints():
        ok = (method, path) in tested
        print(f"{method:7} {path:52} {'✔' if ok else '✘ FALTA'}")
        if not ok:
            missing.append((method, path))
    print(f"\nCobertura: {'100%' if not missing else f'faltam {len(missing)} endpoints'}")
    if missing:
        print("Endpoint novo? Adicione um request com ID BC-xxx à coleção (plano §4/§8).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
