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
    # A forma de TABELA entrava pelo lado de fora: `| Testes do gateway | 441 |`
    # não casa com "441 testes", então a linha ficou quatro releases em
    # ARCHITECTURE.md com este guarda verde ao lado dela.
    for doc in ("README.md", "docs/ARCHITECTURE.md"):
        texto = (RAIZ / doc).read_text(encoding="utf-8")
        for m in re.finditer(VITRINE_TESTES, texto):
            linha = texto[:m.start()].count("\n") + 1
            pytest.fail(
                f"{doc}:{linha} voltou a cravar '{m.group(0)}'. Total de suíte não "
                "se mantém à mão: diga que há suíte e que o build verifica cobertura.")


#: O padrão do caso acima, num lugar só, para que o controle teste o mesmo.
VITRINE_TESTES = r"(\d{3,5})\s+testes|[Tt]estes[^|\n]*\|\s*(\d{3,5})\s*\|"


@pytest.mark.parametrize("forma,pega", [
    ("A suíte tem 1238 testes hoje", True),           # já era pego
    ("| Testes do gateway | 441 |", True),            # passava por fora
    ("| Testes de contrato da engine | 1153 |", True),  # rótulo mais longo
    ("| Providers REST | 4 |", False),                # número que não é suíte
    ("os 23 testes afirmam o nosso lado", False),     # argumento, e fica preso à parte
])
def test_o_guarda_da_vitrine_reconhece_as_duas_formas(forma, pega):
    """O caso acima só prova algo se o padrão pegar a forma de TABELA — era
    exatamente ela que ficava de fora, com o guarda verde ao lado."""
    achou = bool(re.search(VITRINE_TESTES, forma))
    assert achou is pega, f"{forma!r}: esperado pega={pega}, deu {achou}"


def test_a_tabela_de_numeros_da_arquitetura_bate_com_o_servico():
    """`docs/ARCHITECTURE.md` afirma números — aqui eles são medidos.

    Toda linha da tabela estava errada na revisão que escreveu este caso: 3
    providers REST onde há 4 (o Itaú entrou), 18 bancos offline onde há 19, 67
    rotas onde há 70. O cabeçalho dizia `v2.2.0`, o que dava à tabela a
    aparência de um retrato datado — mas os números não eram da 2.2.0 nem de
    versão nenhuma: eram do dia em que alguém digitou.
    """
    from app.core import pycob
    from app.main import app

    texto = (RAIZ / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    spec = app.openapi()
    rotas = sum(1 for item in spec["paths"].values() for metodo in item
                if metodo in ("get", "post", "put", "delete", "patch"))

    esperado = {
        r"\| Providers REST \| (\d+)": _providers_rest(),
        r"\| Bancos no caminho offline \| (\d+)": len(pycob.bancos_suportados()),
        r"\| Rotas online \(`/docs`\) \| (\d+)": rotas,
    }
    for padrao, real in esperado.items():
        achado = re.search(padrao, texto)
        assert achado, f"a linha `{padrao}` saiu da tabela — reveja este guarda"
        assert int(achado.group(1)) == real, (
            f"ARCHITECTURE.md diz {achado.group(1)} em `{padrao}` e o serviço "
            f"tem {real}")


def _providers_rest() -> int:
    """Providers REST de verdade: módulo de banco em `app/providers`.

    `base`, `offline_engine` e `bacen_pix` não são banco — o primeiro é a
    classe-mãe, o segundo é o caminho `off` e o terceiro é a API do Banco
    Central, que não emite cobrança.
    """
    nao_sao_banco = {"__init__", "base", "offline_engine", "bacen_pix"}
    return len([p for p in (RAIZ / "gateway" / "app" / "providers").glob("*.py")
                if p.stem not in nao_sao_banco])


@pytest.mark.parametrize("doc,padrao", [
    ("docs/ARCHITECTURE.md", r"^\| \| v(\d+\.\d+\.\d+) \|$"),
    ("docs/index.md", r"ghcr\.io/maxwbh/cobranca-api:(\d+\.\d+\.\d+)"),
])
def test_a_versao_citada_na_doc_e_a_do_VERSION(doc, padrao):
    """Versão escrita na doc × `VERSION`.

    O `bump-version.sh` cobria três arquivos e conferia cada `sed`; estes dois
    não estavam na lista, então o cabeçalho da tabela e o exemplo de pin em
    produção ficaram em `2.2.0` — o exemplo mandando fixar uma imagem antiga é
    o pior dos dois, porque é instrução, não enfeite.
    """
    versao = (RAIZ / "VERSION").read_text().strip()
    texto = (RAIZ / doc).read_text(encoding="utf-8")
    achado = re.search(padrao, texto, re.MULTILINE)
    assert achado, f"{doc}: a frase com a versão mudou — reveja o padrão aqui"
    assert achado.group(1) == versao, (
        f"{doc} diz {achado.group(1)} e VERSION diz {versao}. "
        "O `scripts/bump-version.sh` atualiza os dois — rode-o.")


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


def _bancos_online() -> list[str]:
    """Os bancos do caminho `on`, lidos do catálogo que a API publica."""
    from fastapi.testclient import TestClient

    from app.main import app
    itens = TestClient(app).get("/bancos").json()["bancos"]
    return [b["id"] for b in itens if "on" in b["caminhos"]]


#: Nome de vitrine de cada banco online — é como o texto se refere a ele.
NOME_DE_VITRINE = {"c6": "C6", "sicoob": "Sicoob", "inter": "Inter", "itau": "Itaú"}


def test_a_label_do_dockerfile_cita_todos_os_bancos_online():
    """A `image.description` da imagem publicada × o catálogo do serviço.

    Ficou em "Cobrança multi-banco (C6/Sicoob)" por dois bancos online e uma
    major — e não é texto de arquivo: vai DENTRO da imagem, como
    `org.opencontainers.image.description`, e aparece em quem inspeciona o
    pacote no GHCR. Foi encontrada lendo o config blob da `:3.0.0`, não o
    repositório.
    """
    texto = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    achado = re.search(r'image\.description="([^"]*)"', texto)
    assert achado, "a LABEL image.description saiu do Dockerfile — reveja este guarda"
    label = achado.group(1)
    faltam = [NOME_DE_VITRINE[b] for b in _bancos_online()
              if NOME_DE_VITRINE[b] not in label]
    assert not faltam, (
        f"a label da imagem não cita {faltam}: {label!r}. "
        "Ela é publicada dentro da imagem — quem inspeciona o pacote lê isto.")


def test_a_lista_de_providers_no_readme_do_gateway_esta_completa():
    """`gateway/README.md` descreve o serviço numa tabela de três produtos, e a
    célula de papel lista os providers. Dizia `C6/Sicoob/Inter` com o Itaú já
    no catálogo."""
    texto = (RAIZ / "gateway" / "README.md").read_text(encoding="utf-8")
    achado = re.search(r"\| \*\*Este\*\* \|.*?\| providers ([^,]+),", texto)
    assert achado, "a linha da tabela mudou de forma — reveja este guarda"
    lista = achado.group(1)
    faltam = [NOME_DE_VITRINE[b] for b in _bancos_online()
              if NOME_DE_VITRINE[b] not in lista]
    assert not faltam, f"a lista de providers não cita {faltam}: {lista!r}"


def test_a_secao_de_fallback_cobre_a_flag_de_todo_banco_online():
    """Toda a razão desta seção é dizer quando o caminho `on` é rebaixado.

    Ela nomeava só `C6_REGISTERED_READY` e `SICOOB_REGISTERED_READY`, e dizia
    que o Inter estava FORA do mecanismo — o oposto do medido: com a flag
    ausente, `build_provider` devolve `PyCobrancaProvider` para os quatro.
    Omitir uma flag aqui faz o leitor subir sem ligar a dele.
    """
    texto = (RAIZ / "gateway" / "README.md").read_text(encoding="utf-8")
    faltam = [f"{b.upper()}_REGISTERED_READY" for b in _bancos_online()
              if f"{b.upper()}_REGISTERED_READY" not in texto]
    assert not faltam, f"o README do gateway não documenta as flags {faltam}"


def test_todo_banco_online_e_rebaixado_para_a_engine_sem_a_flag():
    """A afirmação que a seção de fallback faz, cobrada no serviço.

    Sem isto, o README poderia voltar a prometer um `424` que não vem: era
    exatamente o caso do Inter, e o custo de acreditar nele é boleto registrado
    no banco errado.
    """
    import os

    from app.core.vault import Vault
    from app.registry import Banco, Provider, build_provider

    class _Cofre(Vault):
        def get_credentials(self, *a, **k):
            return {}

    for banco in _bancos_online():
        flag = f"{banco.upper()}_REGISTERED_READY"
        guardado = os.environ.pop(flag, None)
        try:
            p = build_provider(provider=Provider("on"), tenant_id="t",
                               account_config={}, vault=_Cofre(), banco=Banco(banco))
            assert type(p).__name__ == "PyCobrancaProvider", (
                f"{banco} com {flag} ausente devolveu {type(p).__name__}, não a "
                "engine — o README promete rebaixamento")
        finally:
            if guardado is not None:
                os.environ[flag] = guardado


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
