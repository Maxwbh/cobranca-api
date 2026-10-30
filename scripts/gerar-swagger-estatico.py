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
    docs/swagger/es/…            as quatro mesmas, em ESPANHOL: a spec é a
                                 mesma com os textos trocados pelo dicionário
                                 `docs/i18n/es/swagger.yaml` (core.i18n_openapi)

O mesmo `pagina_swagger()` que serve `/docs` monta estas páginas: um tema só,
que não diverge entre a demo e o site.

Uso:
    PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py
    PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py --conferir
    PYTHONPATH=gateway python scripts/gerar-swagger-estatico.py --faltam-es

`--conferir` não escreve nada e sai 1 se o que está no git estiver defasado em
relação ao código — é o que impede a spec publicada de envelhecer em silêncio.
`--faltam-es` lista os textos da spec sem tradução (e as traduções órfãs) e
sai 1 se houver algum — o guarda `test_swagger_em_espanhol.py` cobra o mesmo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SAIDA = REPO / "docs" / "swagger"
SPEC_OFFLINE = REPO / "docs" / "openapi.yaml"

sys.path.insert(0, str(REPO / "gateway"))

from app.core.i18n_openapi import faltam, sobram, traduzir_spec  # noqa: E402
from app.core.swagger_tema import (SUBTITULO_ES, TAGLINE_ES,  # noqa: E402
                                   pagina_swagger)
from app.main import app                        # noqa: E402

GITHUB = "https://github.com/Maxwbh/cobranca-api"
SITE = "https://maxwbh.github.io/cobranca-api"


# O "onde executar" NÃO vive mais aqui. Ele existia porque a página publicada
# não tem servidor atrás e o "Try it out" não teria para onde mandar a chamada
# — razão que continua valendo. O que mudou é o lugar: a frase e o comando
# passaram para o herói do `swagger_tema`, que serve as DUAS superfícies, a
# servida e a publicada. Mantê-lo aqui também punha o mesmo `docker run` duas
# vezes na mesma tela, com dez pixels de distância — defeito que só aparecia no
# site, porque ao vivo o `detalhe` nunca teve este sufixo.


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


def _spec_do_gateway(idioma: str = "pt") -> str:
    return _para_o_site(json.dumps(traduzir_spec(app.openapi(), idioma),
                                   ensure_ascii=False, indent=2)) + "\n"


def _spec_offline(idioma: str = "pt") -> str:
    """Em português, o YAML byte a byte (com comentários). Em espanhol é
    reserializado: os comentários do fonte são do mantenedor, não do leitor."""
    cru = SPEC_OFFLINE.read_text()
    if idioma == "pt":
        return _para_o_site(cru)
    arvore = traduzir_spec(yaml.safe_load(cru), idioma)
    return _para_o_site(yaml.safe_dump(arvore, allow_unicode=True, sort_keys=False, width=100))


def _paginas_es() -> dict[Path, str]:
    es = SAIDA / "es"
    return {
        es / "openapi.json": _spec_do_gateway("es"),
        es / "index.html": pagina_swagger(
            titulo="Cobranca-API — Gateway (Swagger, español)",
            superficie="Gateway REST · multibanco",
            pill="4 bancos ON · 19 OFF",
            detalhe=f"v{app.version} · C6 · Sicoob · Inter · Itaú · Pix BACEN",
            tagline=TAGLINE_ES, subtitulo=SUBTITULO_ES,
            links=[("GitHub", GITHUB, False),
                   ("Português →", "../index.html", False),
                   ("Offline / pyCobrança →", "./offline.html", True)],
            spec_url="./openapi.json",
            assets="../vendor",
        ),
        es / "offline.html": pagina_swagger(
            titulo="Cobranca-API — Offline (Swagger, español)",
            superficie="Offline · pyCobrança",
            pill="19 bancos · sin convenio",
            detalhe=f"v{app.version} · boleto, CNAB y OFX sin convenio",
            tagline=TAGLINE_ES, subtitulo=SUBTITULO_ES,
            links=[("pyCobranca", "https://github.com/Maxwbh/pyCobranca", False),
                   ("Português →", "../offline.html", False),
                   ("Gateway REST →", "./index.html", True)],
            spec_url="./openapi-offline.yaml",
            assets="../vendor",
        ),
        es / "openapi-offline.yaml": _spec_offline("es"),
    }


def gerar() -> dict[Path, str]:
    return {**_paginas_es(),
        SAIDA / "openapi.json": _spec_do_gateway(),
        SAIDA / "index.html": pagina_swagger(
            titulo="Cobranca-API — Gateway (Swagger)",
            superficie="Gateway REST · multi-banco",
            pill="4 bancos ON · 19 OFF",
            detalhe=f"v{app.version} · C6 · Sicoob · Inter · Itaú · Pix BACEN",
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
            detalhe=f"v{app.version} · boleto, CNAB e OFX sem convênio",
            links=[("pyCobranca", "https://github.com/Maxwbh/pyCobranca", False),
                   ("Gateway REST →", "./index.html", True)],
            spec_url="./openapi-offline.yaml",
            assets="./vendor",
        ),
        SAIDA / "openapi-offline.yaml": _spec_offline("pt"),
    }


def _faltam_es() -> int:
    offline = yaml.safe_load(SPEC_OFFLINE.read_text())
    pendentes = faltam(app.openapi()) + [t for t in faltam(offline) if t not in faltam(app.openapi())]
    orfas = sobram([app.openapi(), offline])
    for t in pendentes:
        print(f"SEM TRADUÇÃO: {t[:110]!r}")
    for t in orfas:
        print(f"ÓRFÃ (o português mudou ou saiu): {t[:110]!r}")
    if pendentes or orfas:
        print(f"\n{len(pendentes)} sem tradução, {len(orfas)} órfã(s) — docs/i18n/es/swagger.yaml")
        return 1
    print("Dicionário PT→ES cobre as duas specs, sem entrada órfã.")
    return 0


def main() -> int:
    if "--faltam-es" in sys.argv:
        return _faltam_es()
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
