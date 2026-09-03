#!/usr/bin/env python3
"""Publica o Swagger no site (GitHub Pages), independente do serviço no ar.

A demo do Render hiberna no plano free e a URL muda se o serviço for recriado —
quem chega pelo link do Swagger encontra a página fora do ar e conclui que o
produto não existe. O site é estático e não hiberna.

Gera, a partir do CÓDIGO (nada é escrito à mão):

    docs/swagger/index.html      gateway REST  -> openapi.json
    docs/swagger/openapi.json    spec do gateway, extraída do app FastAPI
    docs/swagger/offline.html    superfície /api/* -> openapi-offline.yaml
    docs/swagger/openapi-offline.yaml   cópia de docs/openapi.yaml

O mesmo `pagina_swagger()` que serve `/docs` monta estas páginas: um tema só,
que não diverge entre a demo e o site.

Uso:
    PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py
    PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py --conferir

`--conferir` não escreve nada e sai 1 se o que está no git estiver defasado em
relação ao código — é o que impede a spec publicada de envelhecer em silêncio.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAIDA = REPO / "docs" / "swagger"
SPEC_OFFLINE = REPO / "docs" / "openapi.yaml"

sys.path.insert(0, str(REPO / "gateway"))

from app.core.swagger_tema import pagina_swagger  # noqa: E402
from app.main import app                        # noqa: E402

GITHUB = "https://github.com/Maxwbh/cobranca-api"
SITE = "https://maxwbh.github.io/cobranca-api"


# A página publicada não tem servidor atrás: o "Try it out" do swagger-ui não
# teria para onde mandar a chamada. Dizer isso no cabeçalho evita que o leitor
# conclua que a API está quebrada — e entrega as duas formas de executar.
_ONDE_EXECUTAR = ('para executar: <a href="https://cobranca-api-sq67.onrender.com/docs">demo</a>'
                  " · <code>docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest</code>")


# As descrições linkam a outra superfície por caminho de SERVIDOR (`/api/docs`).
# No site não há servidor: o link cairia na raiz do github.io. Reescrever aqui
# mantém o texto único no código — a alternativa seria uma segunda redação da
# descrição só para o site, que divergiria na primeira edição.
_LINKS_DO_SITE = {
    "/api/docs": "./offline.html",
    "/api/openapi.yaml": "./openapi-offline.yaml",
    "/docs": "./index.html",          # a spec offline linka o gateway assim
}


def _para_o_site(texto: str) -> str:
    """Troca os links de servidor pelos vizinhos no site."""
    for servidor, site in _LINKS_DO_SITE.items():
        texto = texto.replace(f"]({servidor})", f"]({site})")
    return texto


def _spec_do_gateway() -> str:
    return _para_o_site(json.dumps(app.openapi(), ensure_ascii=False, indent=2)) + "\n"


def gerar() -> dict[Path, str]:
    return {
        SAIDA / "openapi.json": _spec_do_gateway(),
        SAIDA / "index.html": pagina_swagger(
            titulo="Cobranca-API — Gateway (Swagger)",
            superficie="Gateway REST · multi-banco",
            pill="4 bancos ON · 19 OFF",
            detalhe=f"v{app.version} · C6 · Sicoob · Inter · Itaú · Pix BACEN — {_ONDE_EXECUTAR}",
            links=[("GitHub", GITHUB, False),
                   ("Offline / pyCobrança →", "./offline.html", True)],
            spec_url="./openapi.json",
            assets="./vendor",
        ),
        SAIDA / "offline.html": pagina_swagger(
            titulo="Cobranca-API — Offline (Swagger)",
            superficie="Offline · pyCobrança",
            pill="19 bancos · sem convênio",
            # Sem a versão da engine, de propósito. `pycobranca` entra por faixa
            # (>=1.0.2,<2), então ela varia com o ambiente que instalou — e o
            # CI, que roda `pip install` limpo, reprovava o arquivo commitado
            # por uma diferença que não é do código. Página publicada descreve
            # o CONTRATO; a versão do que está rodando é do serviço, e sai em
            # `/api/docs` e em `GET /api/metadata`, que sabem responder por ela.
            detalhe=f"v{app.version} — {_ONDE_EXECUTAR}",
            links=[("pyCobranca", "https://github.com/Maxwbh/pyCobranca", False),
                   ("Gateway REST →", "./index.html", True)],
            spec_url="./openapi-offline.yaml",
            assets="./vendor",
        ),
        SAIDA / "openapi-offline.yaml": _para_o_site(SPEC_OFFLINE.read_text()),
    }


def main() -> int:
    conferir = "--conferir" in sys.argv
    arquivos = gerar()
    divergentes = []
    for caminho, conteudo in arquivos.items():
        atual = caminho.read_text() if caminho.exists() else None
        if atual == conteudo:
            continue
        divergentes.append(caminho.relative_to(REPO))
        if not conferir:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(conteudo)

    if conferir:
        if divergentes:
            print("Swagger publicado está DEFASADO em relação ao código:")
            for d in divergentes:
                print(f"  - {d}")
            print("\nRode: PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py")
            return 1
        print("Swagger publicado em dia com o código.")
        return 0

    if divergentes:
        for d in divergentes:
            print(f"atualizado: {d}")
    else:
        print("nada a fazer — já estava em dia.")
    print(f"\n{SITE}/swagger/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
