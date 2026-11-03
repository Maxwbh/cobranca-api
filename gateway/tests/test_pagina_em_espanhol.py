# A página em espanhol promete cobrir TODO o vocabulário do boleto.
#
# `docs/es/index.md` existe para um público concreto — empresa do Mercosul
# cobrando no Brasil — e o que a separa de uma tradução solta é o glossário:
# "esta tabla cubre todos los campos del boleto". Essa frase é uma promessa
# contra o `BoletoData` da spec, e spec cresce. Campo novo entra na API, o
# glossário fica parado, e a promessa vira mentira em silêncio — o mesmo jeito
# que todo número da vitrine envelheceu nesta revisão.
#
# Então o glossário é derivado, não digitado: todo campo da spec tem de estar
# na página, e a página não pode inventar campo que a spec não tem. O mesmo
# vale para as contagens de banco, que a página escreve por extenso.
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
PAGINA = RAIZ / "docs" / "es" / "index.md"
CAPA = RAIZ / "docs" / "index.md"
SPEC = RAIZ / "docs" / "openapi.yaml"
LAYOUT = RAIZ / "docs" / "_layouts" / "default.html"


def _texto() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _spec_boleto() -> tuple[set[str], set[str]]:
    sch = yaml.safe_load(SPEC.read_text(encoding="utf-8"))["components"]["schemas"]["BoletoData"]
    return set(sch["properties"]), set(sch.get("required") or [])


def _campos_na_pagina() -> set[str]:
    """Todo `nome_de_campo` em crase. `instrucao1 … instrucao6` é escrito
    como intervalo na tabela; o guarda expande, porque a spec os lista um a um."""
    vistos = set(re.findall(r"`([a-z][a-z0-9_]*)`", _texto()))
    if "instrucao1" in vistos and "instrucao6" in vistos:
        vistos |= {f"instrucao{i}" for i in range(1, 7)}
    return vistos


def test_a_pagina_existe_e_se_declara_em_espanhol():
    assert PAGINA.is_file()
    cabecalho = _texto().split("---")[1]
    assert re.search(r"^lang:\s*es\s*$", cabecalho, re.MULTILINE), (
        "sem `lang: es` no front matter o <html> sai em pt-BR, e o Google e o "
        "leitor de tela leem espanhol como português")


def test_o_layout_honra_o_lang_da_pagina():
    """O layout usava só `site.lang`. Uma página declarar `lang: es` não
    adiantava nada enquanto o `<html>` ignorasse."""
    html = LAYOUT.read_text(encoding="utf-8")
    assert re.search(r'<html lang="\{\{\s*page\.lang\s*\|\s*default:\s*site\.lang', html), (
        "o <html lang> do layout não lê `page.lang` antes de `site.lang` — a "
        "página em espanhol sai rotulada como pt-BR")


def test_todo_campo_do_boleto_esta_no_glossario():
    campos, _ = _spec_boleto()
    faltam = sorted(campos - _campos_na_pagina())
    assert not faltam, (
        f"a página em espanhol promete cobrir todos os campos do boleto e não "
        f"cita {faltam}. Acrescente ao glossário — a spec cresceu e a página não.")


def test_o_glossario_nao_inventa_campo():
    """O contrário: campo que a página cita e a API não aceita ensina errado."""
    campos, _ = _spec_boleto()
    #: Palavras em crase que NÃO são campo do boleto: parâmetros de query,
    #: valores e o que a página cita de outro contexto. Lista fechada, de
    #: propósito: palavra nova em crase tem de ser acrescentada aqui à mão, e é
    #: aí que alguém olha.
    nao_sao_campos = {"tenant_id", "moderno"}
    sobram = sorted(c for c in _campos_na_pagina()
                    if c not in campos and c not in nao_sao_campos)
    assert not sobram, (
        f"a página cita {sobram} em crase, e não é campo do boleto nem está na "
        "lista de exceções deste guarda")


def test_os_obrigatorios_estao_marcados_como_obrigatorios():
    """Os seis que a spec exige têm de estar na seção de obrigatórios — é a
    primeira coisa que o integrador precisa saber."""
    _, obrigatorios = _spec_boleto()
    m = re.search(r"### Los seis obligatorios(.*?)###", _texto(), re.S)
    assert m, "a seção 'Los seis obligatorios' mudou de nome — reveja este guarda"
    secao = set(re.findall(r"`([a-z_]+)`", m.group(1)))
    assert obrigatorios <= secao, (
        f"obrigatórios fora da seção: {sorted(obrigatorios - secao)}")
    assert len(obrigatorios) == 6, (
        f"a spec passou a exigir {len(obrigatorios)} campos e o título ainda diz seis")


def test_a_mensagem_de_erro_citada_e_a_que_a_api_emite(client):
    """A página mostra o erro que um RUC provoca. Mostra o texto REAL, medido
    agora — não o que alguém lembrava."""
    import json
    campos = {"valor": 10.0, "cedente": "X", "documento_cedente": "11222333000181",
              "sacado": "Y", "sacado_documento": "80012345-6", "agencia": "3073",
              "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
              "nosso_numero": "1", "data_vencimento": "2027-12-31"}
    r = client.get("/api/boleto/validate", params={"bank": "banco_brasil", "data": json.dumps(campos)})
    assert r.status_code == 400
    citada = re.search(r"`(sacado_documento: [^`]+)`", _texto())
    assert citada, "a página deixou de citar a mensagem de erro do documento"
    assert citada.group(1) in r.json()["validation_errors"], (
        f"a página cita {citada.group(1)!r}; a API responde {r.json()['validation_errors']}")


def test_as_contagens_de_banco_sao_as_do_servico():
    """'19 bancos offline' e '4 bancos online' estão por extenso na página. São
    o mesmo número que a vitrine, e envelhecem do mesmo jeito."""
    from fastapi.testclient import TestClient

    from app.core import pycob
    from app.main import app
    itens = TestClient(app).get("/bancos").json()["bancos"]
    online = len([b for b in itens if "on" in b["caminhos"]])
    offline = len(pycob.bancos_suportados())
    texto = _texto()
    m_off = re.search(r"\*\*(\d+) bancos offline\*\*", texto)
    m_on = re.search(r"\*\*(\d+) bancos\s+online\*\*", texto)
    assert m_off and m_on, "a página deixou de escrever '**N bancos offline**' / '**M bancos online**'"
    assert int(m_off.group(1)) == offline, f"página diz {m_off.group(1)} offline; engine tem {offline}"
    assert int(m_on.group(1)) == online, f"página diz {m_on.group(1)} online; serviço tem {online}"


def test_a_pagina_nao_aponta_para_instancia_publica():
    """Mesma regra do resto do site — e aqui vale dobrado: o leitor está em
    outro país, e um host de demo é o primeiro que ele copiaria."""
    assert "onrender.com" not in _texto()
    assert "localhost:8000" in _texto(), "a página perdeu o endereço local"


@pytest.mark.parametrize("alvo", ["../swagger/", "../swagger/offline.html", "../deploy.md", "../"])
def test_os_links_relativos_resolvem(alvo: str):
    """De `docs/es/` para cima: cada alvo tem de existir como arquivo ou como
    diretório com índice."""
    assert f"]({alvo})" in _texto(), f"a página deixou de linkar {alvo}"
    destino = (PAGINA.parent / alvo).resolve()
    candidatos = [destino, destino / "index.html", destino / "index.md"]
    assert any(c.exists() for c in candidatos), f"{alvo} não resolve a partir de docs/es/"


def test_a_capa_leva_ate_a_pagina():
    """Página que ninguém acha não existe. A capa em português linka `/es/`."""
    assert re.search(r"\]\(es/\)", CAPA.read_text(encoding="utf-8")), (
        "a capa (docs/index.md) não linka `es/`")


def test_a_pagina_aponta_para_os_exemplos_que_existem():
    """A página manda o leitor aos exemplos em PHP e Python. Os dois diretórios
    têm de existir — link para pasta que não existe é 404 no GitHub."""
    for lang in ("php", "python"):
        assert f"examples/{lang})" in _texto(), f"a página deixou de linkar examples/{lang}"
        assert (RAIZ / "examples" / lang / "README.md").is_file(), f"examples/{lang} sem README"
