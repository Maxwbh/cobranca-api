#!/usr/bin/env python3
"""Guarda de cobertura (plano §8): endpoint sem request na coleção => exit 1.

Compara:
  1. paths+methods do OpenAPI do gateway (importa o app FastAPI); e
  2. o inventário offline /api/* (lista OFFLINE abaixo)
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

# A superfície offline /api/* agora é NATIVA (engine pyCobranca) e aparece no
# OpenAPI interno do app — mas com include_in_schema=False (o Swagger do
# offline é o /api/docs). Por isso o inventário permanece explícito aqui.
OFFLINE = [
    ("GET", "/api/health"), ("GET", "/api/info"), ("GET", "/api/metadata"),
    ("GET", "/api/bancos"), ("GET", "/api/boleto/validate"), ("GET", "/api/boleto/data"),
    ("GET", "/api/boleto/nosso_numero"), ("GET", "/api/boleto"),
    ("POST", "/api/remessa"), ("POST", "/api/retorno"), ("POST", "/api/ofx/parse"),
    ("GET", "/api/docs"),
]


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


def main() -> int:
    tested = collection_requests()
    missing = []
    print(f"{'Endpoint':60} Testado")
    for method, path in gateway_endpoints() + [(m, norm(p)) for m, p in OFFLINE]:
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
