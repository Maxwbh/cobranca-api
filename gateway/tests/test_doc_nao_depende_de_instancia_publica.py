# A documentação não manda ninguém para uma instância que não é dele.
#
# O site e o README apontavam, em nove lugares, para uma demo pública no plano
# gratuito do Render: o botão do herói, o `curl` da primeira página, a tabela
# "testar a API agora", o cabeçalho do Swagger estático e o `servers.default`
# da spec — que é o endereço que o "Try it out" usa quando ninguém mexe nele.
#
# O produto é self-hosted. Uma demo compartilhada que hiberna em 15 minutos
# ensina o endereço errado (o leitor copia o host da demo para o código dele),
# dá a impressão de API quebrada na primeira chamada fria, e põe uma rota de
# geração de PDF aberta para qualquer um, num container de 512 MB.
#
# O endereço certo é o do próprio leitor: `docker run -p 8000:8000
# ghcr.io/maxwbh/cobranca-api:latest` e `localhost:8000`.
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]

#: Qualquer host de PaaS gratuito serve de demo compartilhada — o defeito não é
#: do Render, é de a doc depender de um servidor que não é de quem lê.
DEMO = re.compile(
    r"https?://[\w.-]+\.(onrender\.com|herokuapp\.com|fly\.dev|railway\.app|vercel\.app)")

#: Onde procurar: o que o leitor lê. `docs/swagger/` é gerado — entra pela
#: fonte (`scripts/gerar-swagger-estatico.py`), não por cópia.
ALVOS = ("README.md", "docs/**/*.md", "docs/openapi.yaml", "scripts/*.py",
         "examples/**/*.md", "postman/*.md")

#: Dois arquivos ENSINAM sobre hospedagem, e aí o nome do provedor é a lição,
#: não uma dependência: `deploy.md` mostra como subir (Render incluído) e
#: `troubleshooting.md` explica o `429` do cold start de quem escolheu o plano
#: gratuito. O que o guarda proíbe é a doc *depender* de uma instância
#: concreta para o leitor conseguir usar o produto.
EXCECOES = {"docs/deploy.md", "docs/api/troubleshooting.md"}


def _arquivos() -> list[Path]:
    achados: list[Path] = []
    for padrao in ALVOS:
        achados += [p for p in RAIZ.glob(padrao)
                    if p.is_file()
                    and ".jekyll-cache" not in p.parts
                    and str(p.relative_to(RAIZ)) not in EXCECOES
                    and "swagger" not in p.relative_to(RAIZ).parts[:2]]
    return sorted(set(achados))


def test_existe_o_que_conferir():
    """Varredura que não acha arquivo nenhum passa por engano."""
    achados = _arquivos()
    assert len(achados) > 20, f"só {len(achados)} arquivos varridos — o padrão quebrou"


@pytest.mark.parametrize("arq", _arquivos(), ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhuma_pagina_aponta_para_instancia_publica(arq: Path):
    texto = arq.read_text(encoding="utf-8")
    achados = [f"  linha {texto.count(chr(10), 0, m.start()) + 1}: {m.group(0)}"
               for m in DEMO.finditer(texto)]
    assert not achados, (
        f"{arq.relative_to(RAIZ)} manda o leitor para uma instância que não é "
        "dele:\n" + "\n".join(achados)
        + "\n\nUse `docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest`"
          " e `localhost:8000`.")


def test_o_server_default_da_spec_e_o_container_local():
    """O `servers[0]` é o que o "Try it out" usa sem ninguém configurar nada.

    Apontava para a demo: quem clicasse mandaria a chamada para um servidor
    compartilhado, e quem copiasse o host levaria o endereço da demo para
    dentro do próprio código.
    """
    spec = yaml.safe_load((RAIZ / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    servidores = spec.get("servers") or []
    assert servidores, "a spec offline ficou sem `servers`"
    primeiro = servidores[0]["url"]
    assert primeiro == "http://localhost:8000", (
        f"`servers[0]` é {primeiro!r}; tem de ser o container local")
    for s in servidores:
        for nome, var in (s.get("variables") or {}).items():
            assert not DEMO.search(var.get("default", "")), (
                f"a variável de servidor `{nome}` tem default {var['default']!r}")


def test_o_merge_na_main_nao_publica_em_provedor_nenhum():
    """`autoDeploy: true` fazia todo merge na `main` publicar numa instância do
    Render — o repositório tinha dono de infraestrutura sem ninguém decidir
    isso a cada release, e a instância pública da doc saía junto.

    O blueprint continua no repo, válido para quem quiser repetir; o que não
    pode voltar é o gatilho automático.
    """
    bp = RAIZ / "render.yaml"
    if not bp.is_file():
        pytest.skip("sem render.yaml — nada a cobrar")
    cfg = yaml.safe_load(bp.read_text(encoding="utf-8"))
    for servico in cfg.get("services") or []:
        assert servico.get("autoDeploy") is False, (
            f"`autoDeploy` do serviço {servico.get('name')!r} é "
            f"{servico.get('autoDeploy')!r}; tem de ser False")


def test_o_guia_de_deploy_nao_e_de_um_provedor_so():
    """O guia era um passo a passo do Render: "Criar Serviço no Render",
    "Regiões Disponíveis", "Já Configuradas no render.yaml". Um produto que é
    um container não tem provedor de referência — o guia descreve o que o
    serviço pede do host, e cada provedor é apêndice.
    """
    texto = (RAIZ / "docs" / "deploy.md").read_text(encoding="utf-8")
    titulos = re.findall(r"^#{2,3} (.+)$", texto, re.MULTILINE)
    assert titulos, "o guia ficou sem seções — reveja este guarda"
    com_provedor = [t for t in titulos
                    if re.search(r"render|heroku|fly\.io|vercel|railway", t, re.I)
                    and "apêndice" not in t.lower()]
    assert not com_provedor, (
        f"seções do guia nomeiam provedor fora de um apêndice: {com_provedor}")
    assert "docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api" in texto, (
        "o guia deixou de abrir pela imagem pronta, que é o caminho que serve "
        "em qualquer host")


def test_o_guarda_reconhece_o_endereco_que_saiu(tmp_path):
    """Controle: o padrão precisa pegar a forma exata que estava publicada."""
    for url in ("https://cobranca-api-sq67.onrender.com/docs",
                "https://cobranca-api-sq67.onrender.com/api/openapi.json",
                "http://qualquer-coisa.fly.dev"):
        assert DEMO.search(url), f"não reconheceu {url}"
    for url in ("http://localhost:8000/docs",
                "https://maxwbh.github.io/cobranca-api/swagger/",
                "https://github.com/Maxwbh/cobranca-api"):
        assert not DEMO.search(url), f"acusou indevidamente {url}"
