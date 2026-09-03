# O dialeto do Pix Automático confere com a spec do próprio Inter.
#
# O provider herda `BacenPixAutomaticoMixin` porque o dialeto é o do BACEN — e
# herdar não prova que o banco exponha as rotas. Ficou atrás de
# `INTER_PIX_AUTOMATICO_READY` enquanto ninguém confirmou; a confirmação veio da
# spec OpenAPI publicada pelo banco.
#
# A página de referência é SPA (Redocly) e não entrega os endpoints por fetch: a
# URL da spec saiu do bundle `/assets/js/main.*.js`. O inventário extraído dela
# está versionado em `docs/homologacao/evidencia-pix-automatico-inter.json`, e é
# contra ele que estas provas rodam — sem rede, e sem depender de memória de
# quem leu a página.
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.providers import bacen_pix
from app.providers.inter import INTER_SCOPES, InterProvider
from app.routers._capacidades import disponivel

EVIDENCIA = Path(__file__).resolve().parents[2] / "docs" / "homologacao" / \
    "evidencia-pix-automatico-inter.json"


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(EVIDENCIA.read_text(encoding="utf-8"))


def _chamadas_do_mixin() -> set[tuple[str, str]]:
    """(método, path) de cada chamada do mixin, com `{param}` normalizado."""
    fonte = inspect.getsource(bacen_pix)
    trecho = fonte[fonte.index("class BacenPixAutomaticoMixin"):]
    return {(m.upper(), re.sub(r"\{[^}]+\}", "{}", caminho))
            for m, caminho in re.findall(
                r'request\(\s*"(\w+)",\s*f?"\{self\.PIX_BASE\}([^"]*)"', trecho)}


def _operacoes_da_spec(spec: dict) -> set[tuple[str, str]]:
    fora = set()
    for op in spec["operacoes"]:
        metodo, caminho = op.split(" ", 1)
        # `/sandbox/*` simula pagamento e status — é ferramenta de teste do
        # banco, não superfície de produção.
        if caminho.startswith("/sandbox/"):
            continue
        fora.add((metodo, re.sub(r"\{[^}]+\}", "{}", caminho)))
    return fora


# --- o que destravou a capacidade ----------------------------------------------

def test_toda_chamada_do_mixin_existe_na_spec_do_inter(spec):
    """A prova que virou a chave.

    Herdar o dialeto BACEN não garantia nada: bastava o Inter usar outro path
    base ou outro recorte de rotas para toda chamada bater em 404. As 17 do
    mixin existem, uma a uma.
    """
    ausentes = sorted(_chamadas_do_mixin() - _operacoes_da_spec(spec))
    assert not ausentes, f"o Inter não expõe: {ausentes}"


def test_o_path_base_e_o_mesmo(spec):
    """`/pix/v2`, igual ao C6 e ao Sicoob — é o que torna o mixin reaproveitável.
    Base diferente faria TODA chamada 404, e o erro não pareceria de path."""
    assert InterProvider.PIX_BASE == spec["path_base"]
    assert all(s.endswith(spec["path_base"]) for s in spec["servers"]), spec["servers"]


def test_o_token_pede_os_escopos_do_recurso(spec):
    """Paths certos e escopo faltando dá 403 — falha que não se parece com
    "faltou escopo". Era o buraco que restava depois de confirmar as rotas."""
    do_recurso = {e for e in spec["scopes"]
                  if e.split(".")[0] in ("rec", "solicrec", "cobr", "webhookrec",
                                         "webhookcobr", "payloadlocationrec")}
    faltando = sorted(do_recurso - set(INTER_SCOPES))
    assert not faltando, f"o token do Inter não pede: {faltando}"


def test_a_capacidade_esta_liberada():
    assert disponivel(InterProvider, "criar_recorrencia", "inter")


def test_o_catalogo_anuncia_e_nao_ressalva(client):
    bancos = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}
    assert "pix_automatico" in bancos["inter"]["capacidades"]
    assert not bancos["inter"].get("capacidades_nao_confirmadas")


# --- o escopo pedido continua sendo o escopo usado -----------------------------

def test_nao_pedimos_escopo_que_nao_usamos(spec):
    """A regra do arquivo: "pedir escopo que não se usa amplia o estrago de um
    vazamento de credencial sem entregar nada". Vale para os novos também.

    Cada escopo de Pix Automático no token tem de corresponder a rota que o
    mixin chama — `.read` para GET, `.write` para o resto.
    """
    usados = {caminho.strip("/").split("/")[0] for _, caminho in _chamadas_do_mixin()}
    prefixos = {"rec", "solicrec", "cobr", "webhookrec", "webhookcobr",
                "payloadlocationrec"}
    for escopo in INTER_SCOPES:
        base = escopo.split(".")[0]
        if base not in prefixos:
            continue
        # `payloadlocationrec` é o escopo de `/locrec` — nome do recurso no
        # BACEN, não do path.
        recurso = "locrec" if base == "payloadlocationrec" else base
        assert recurso in usados, f"escopo `{escopo}` pedido e nenhuma rota o usa"


def test_pagamentos_continuam_fora_do_token():
    """Saída de dinheiro não entra: o produto é cobrança. Acrescentar escopo de
    Pix Automático não pode ter arrastado escopo de pagamento junto."""
    assert not [e for e in INTER_SCOPES if e.startswith("pagamento")]
    assert not [e for e in INTER_SCOPES if e.startswith("webhook-banking")]


# --- a evidência é do banco, não nossa ----------------------------------------

def test_a_evidencia_aponta_a_fonte(spec):
    """Sem a fonte, o arquivo vira opinião versionada."""
    fonte = spec["fonte"]
    assert fonte["spec"].startswith("https://developers.inter.co/")
    assert fonte["spec"].endswith(".yaml")
    assert fonte["titulo"] == "API Pix Automático"
    assert fonte["obtida_em"]


def test_a_restricao_do_bacen_esta_registrada(spec):
    """A spec não diz, a página de referência diz: a API só é oferecida a CNPJ
    com 6+ meses de atividade. É recusa de cadastro, não erro de integração —
    e sem isso registrado a investigação começaria pelo lugar errado."""
    assert "6 meses" in spec["restricao_bacen"]


def test_as_jornadas_do_bacen_estao_cobertas(spec):
    """As quatro jornadas dependem de `rec`, `solicrec`, `locrec` e `cobr`.
    Faltar um recurso deixaria uma jornada inteira sem caminho."""
    recursos = {caminho.strip("/").split("/")[0] for _, caminho in _chamadas_do_mixin()}
    assert {"rec", "solicrec", "locrec", "cobr"} <= recursos
