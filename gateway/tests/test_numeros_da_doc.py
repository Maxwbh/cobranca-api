# Número afirmado na documentação × número medido agora.
#
# Doc não envelhece com erro — envelhece com número parado. A revisão que criou
# este arquivo achou "864 testes" onde havia 1153, "441 testes" onde havia a
# mesma suíte, "67/67 rotas" onde eram 70, "20 testes" onde eram 23, "30 testes"
# onde eram 62 e "14 pastas" onde eram 20. Nenhum estava errado quando foi
# escrito; todos passaram a estar, e nada acusava.
#
# Onde o número exato é VITRINE (README, ARCHITECTURE) ele saiu: um total de
# testes não ajuda quem lê e mente sozinho a cada commit. O que fica preso aqui
# é o número que serve de ARGUMENTO — "os 23 testes afirmam o nosso lado" só
# vale se forem 23.
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _casos_de(arquivo: str) -> int:
    """Casos coletáveis do arquivo, contando o que `parametrize` multiplica.

    Contar `def test_` daria outro número — e seria o número errado, porque é o
    caso COLETADO que a doc cita.
    """
    import subprocess
    import sys

    saida = subprocess.run(
        [sys.executable, "-m", "pytest", f"gateway/tests/{arquivo}", "-q", "--collect-only"],
        cwd=RAIZ, capture_output=True, text=True,
        env={"PYTHONPATH": "gateway", "PATH": "/usr/bin:/bin"},
    ).stdout
    achado = re.search(r"(\d+) tests? collected", saida)
    assert achado, f"não deu para coletar {arquivo}: {saida[-300:]}"
    return int(achado.group(1))


@pytest.mark.parametrize("doc,padrao,arquivo", [
    ("docs/development/itau-rest.md", r"Os (\d+) testes afirmam", "test_cobranca_itau.py"),
    ("postman/README.md", r"test_c6_checkout\.py` \((\d+) testes\)", "test_c6_checkout.py"),
])
def test_o_numero_de_testes_citado_e_o_que_existe(doc, padrao, arquivo):
    texto = (RAIZ / doc).read_text(encoding="utf-8")
    achado = re.search(padrao, texto)
    assert achado, f"{doc}: a frase com o número mudou — reveja o padrão aqui"
    afirmado, real = int(achado.group(1)), _casos_de(arquivo)
    assert afirmado == real, (
        f"{doc} diz {afirmado} testes e {arquivo} tem {real}. "
        "Atualize a doc — ou tire o número, se ele não estiver a serviço de nada.")


def test_a_vitrine_nao_volta_a_carregar_total_de_testes():
    """README e ARCHITECTURE não devem cravar o total da suíte.

    É o número que mais envelhece e o que menos informa: quem lê quer saber que
    existe suíte e que a cobertura é verificada no build, não o placar do dia.
    """
    for doc in ("README.md", "docs/ARCHITECTURE.md"):
        texto = (RAIZ / doc).read_text(encoding="utf-8")
        for m in re.finditer(r"(\d{3,5})\s+testes", texto):
            linha = texto[:m.start()].count("\n") + 1
            pytest.fail(
                f"{doc}:{linha} voltou a cravar '{m.group(0)}'. Total de suíte não "
                "se mantém à mão: diga que há suíte e que o build verifica cobertura.")


def test_a_contagem_de_bancos_na_doc_bate_com_a_engine():
    """19 é derivado do registro da engine, não digitado.

    O 18→19 do Inter já custou uma varredura por README, banner, badge, Swagger
    e assets. Aqui ele fica preso.
    """
    from app.core import pycob
    reais = len(pycob.bancos_suportados())
    encontrados = []
    for doc in ("README.md", "postman/README.md", "docs/development/roadmap-providers.md"):
        texto = (RAIZ / doc).read_text(encoding="utf-8")
        for m in re.finditer(r"(\d+)\s+bancos?\s+(?:CNAB|offline)", texto):
            encontrados.append((doc, int(m.group(1))))
    assert encontrados, "nenhum documento cita a contagem de bancos — o padrão mudou?"
    errados = [(d, n) for d, n in encontrados if n != reais]
    assert not errados, f"a engine tem {reais} bancos; a doc diz {errados}"


def test_toda_rota_offline_tem_request_na_colecao():
    """O guarda de cobertura tinha uma lista à mão com sete rotas a menos.

    `/api/boleto/multi` e as quatro `/api/render/*` estavam publicadas em
    `docs/openapi.yaml`, existiam no router e não tinham request nenhum — e não
    eram cobradas, porque rota fora do inventário não conta como faltante. O
    relatório dizia "Cobertura: 100%": verdade sobre a lista, falso sobre a
    superfície. Este caso prende o inventário no ROUTER.
    """
    from app.routers import offline

    reais = {
        (metodo, rota.path)
        for rota in offline.router.routes
        for metodo in (getattr(rota, "methods", ()) or ())
        if getattr(rota, "path", "").startswith("/api/")
        and metodo in ("GET", "POST", "PUT", "DELETE", "PATCH")
    }
    colecao = json.loads(
        (RAIZ / "postman" / "cobranca-api.postman_collection.json").read_text(encoding="utf-8"))

    def caminhos(itens):
        for item in itens:
            if "item" in item:
                yield from caminhos(item["item"])
                continue
            pedido = item["request"]
            yield (pedido["method"].upper(), "/" + "/".join(pedido["url"].get("path", [])))

    testadas = set(caminhos(colecao["item"]))
    sem_request = sorted(reais - testadas)
    assert not sem_request, (
        f"rotas /api/* sem request na coleção: {sem_request}. "
        "Acrescente um BC-xxx — o guarda de cobertura também vai reprovar.")
