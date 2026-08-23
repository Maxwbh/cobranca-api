# A doc offline conferida contra o servico, nao contra si mesma.
#
# Spec envelhece de tres jeitos, e nenhum deles quebra teste nenhum:
#
#   1. campo que a rota devolve e a spec nao declara — quem le acha que nao
#      existe e nao usa;
#   2. campo que a spec declara e a rota nao devolve — quem le recebe
#      `undefined` e nao tem o que investigar;
#   3. `example` que o proprio schema ao lado dele recusa — e' o corpo que o
#      Swagger UI preenche no "Try it out", entao a doc responde 400 no
#      primeiro clique de quem chega.
#
# O terceiro tem um agravante: o swagger-ui GERA o corpo varrendo todas as
# propriedades do schema, entao um `example` explicito no requestBody nao e'
# enfeite — e' o que impede a doc de ensinar um payload impossivel.
from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from jsonschema import Draft202012Validator

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

DADOS = {
    "valor": 1279.50, "cedente": "Empresa Exemplo Servicos LTDA",
    "documento_cedente": "11222333000181", "sacado": "Maria de Souza",
    "sacado_documento": "52998224725", "agencia": "3073",
    "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
    "nosso_numero": "1042", "numero_documento": "NF-2027-0042",
    "data_vencimento": "2027-09-10", "chave_pix": "11222333000181",
    "logo_empresa": "EXEMPLO", "cor_marca": "1B4F8A",
}
SEM_TEMA = {k: v for k, v in DADOS.items() if k not in ("logo_empresa", "cor_marca")}

#: (id, metodo, caminho, query, corpo)
ROTAS = [
    ("boleto/data", "GET", "/api/boleto/data",
     {"bank": "banco_brasil", "data": json.dumps(DADOS)}, None),
    ("boleto/nosso_numero", "GET", "/api/boleto/nosso_numero",
     {"bank": "banco_brasil", "data": json.dumps(DADOS)}, None),
    ("render/boleto", "POST", "/api/render/boleto", None,
     {"bank": "banco_brasil", "data": DADOS}),
    ("render/carne", "POST", "/api/render/carne", None,
     {"bank": "banco_brasil", "boletos": [
         SEM_TEMA,
         {**SEM_TEMA, "nosso_numero": "1043", "numero_documento": "NF-2027-0043"}]}),
    ("render/fatura", "POST", "/api/render/fatura", None,
     {"bank": "banco_brasil", "data": DADOS,
      "itens": [{"descricao": "Mensalidade", "valor_unitario": 1279.50}]}),
]


def _resolver(no, raiz):
    """Achata `$ref` para o validador enxergar o schema inteiro."""
    if isinstance(no, dict):
        if "$ref" in no:
            alvo = raiz
            for parte in no["$ref"].lstrip("#/").split("/"):
                alvo = alvo[parte]
            return _resolver(alvo, raiz)
        return {k: _resolver(v, raiz) for k, v in no.items()}
    if isinstance(no, list):
        return [_resolver(i, raiz) for i in no]
    return no


def _schema_da_resposta(metodo, caminho):
    conteudo = (SPEC["paths"][caminho][metodo.lower()]["responses"]["200"]
                .get("content", {}).get("application/json"))
    return _resolver(conteudo["schema"], SPEC) if conteudo else None


def _chamar(client, metodo, caminho, query, corpo):
    if metodo == "GET":
        return client.get(caminho, params=query)
    return client.post(caminho, json=corpo, params=query or {})


@pytest.mark.parametrize(("ident", "metodo", "caminho", "query", "corpo"), ROTAS,
                         ids=[r[0] for r in ROTAS])
def test_resposta_bate_com_o_schema_declarado(client, ident, metodo, caminho, query, corpo):
    r = _chamar(client, metodo, caminho, query, corpo)
    assert r.status_code == 200, r.text
    schema = _schema_da_resposta(metodo, caminho)
    erros = [f"{'/'.join(map(str, e.path)) or '<raiz>'}: {e.message}"
             for e in Draft202012Validator(schema).iter_errors(r.json())]
    assert not erros, f"{caminho} não satisfaz o schema da própria spec: {erros}"


@pytest.mark.parametrize(("ident", "metodo", "caminho", "query", "corpo"), ROTAS,
                         ids=[r[0] for r in ROTAS])
def test_nem_campo_a_mais_nem_a_menos(client, ident, metodo, caminho, query, corpo):
    """As duas omissões que o validador de schema não pega sozinho."""
    r = _chamar(client, metodo, caminho, query, corpo)
    declarados = set((_schema_da_resposta(metodo, caminho) or {}).get("properties") or {})
    devolvidos = set(r.json())
    assert not (devolvidos - declarados), \
        f"{caminho} devolve e a spec não declara: {sorted(devolvidos - declarados)}"
    assert not (declarados - devolvidos), \
        f"{caminho}: a spec declara e a rota não devolve: {sorted(declarados - devolvidos)}"


# ---------------------------------------------------------------- exemplos
_RESTRICOES = ("type", "pattern", "enum", "minimum", "maximum", "exclusiveMinimum",
               "exclusiveMaximum", "minLength", "maxLength", "items", "required",
               "properties", "additionalProperties", "oneOf", "anyOf")


def _com_exemplo(no, trilha=""):
    if isinstance(no, dict):
        if no.get("example") is not None:
            yield trilha, no, no["example"]
        for k, v in no.items():
            if k in ("example", "examples"):
                continue
            yield from _com_exemplo(v, f"{trilha}/{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from _com_exemplo(v, f"{trilha}[{i}]")


def test_todo_exemplo_passa_na_restricao_do_proprio_campo():
    ruins = []
    for trilha, no, exemplo in _com_exemplo(SPEC):
        r = {k: v for k, v in no.items() if k in _RESTRICOES}
        if no.get("nullable") and "type" in r:
            r["type"] = [r["type"], "null"]
        if not r:
            continue
        try:
            erros = list(Draft202012Validator({**r, "components": SPEC["components"]})
                         .iter_errors(exemplo))
        except Exception:  # noqa: BLE001 — schema que o validador não monta
            continue
        ruins += [f"{trilha}: example={exemplo!r} — {e.message[:120]}" for e in erros]
    assert not ruins, "exemplos recusados pelo schema ao lado deles: " + "; ".join(ruins)


def test_pattern_ancorado_nas_duas_pontas():
    """`^…$` — sem as duas âncoras o padrão casa substring e não restringe nada."""
    frouxos = [f"{t}: {no['pattern']}" for t, no, _ in _com_exemplo(SPEC)
               if no.get("pattern") and not (no["pattern"].startswith("^")
                                             and no["pattern"].endswith("$"))]
    assert not frouxos, frouxos


def test_corpo_de_requisicao_traz_exemplo_proprio():
    """Sem `example` no requestBody, o swagger-ui inventa um com TODOS os campos.

    E os campos do `BoletoData` não são todos combináveis: `instrucoes` e
    `instrucao1..6` escrevem o mesmo bloco e juntos respondem 400. O corpo
    gerado ficava impossível por construção.
    """
    faltando = []
    for caminho, ops in SPEC["paths"].items():
        for metodo, op in ops.items():
            corpo = (op.get("requestBody") or {}).get("content", {}).get("application/json")
            if corpo is not None and "example" not in corpo:
                faltando.append(f"{metodo.upper()} {caminho}")
    assert not faltando, f"requestBody JSON sem `example`: {faltando}"


def test_o_exemplo_do_request_body_e_aceito_pela_rota(client):
    """A prova final: o corpo que a doc mostra é executado contra o serviço."""
    recusados = []
    for caminho, ops in SPEC["paths"].items():
        corpo = ((ops.get("post") or {}).get("requestBody") or {}) \
            .get("content", {}).get("application/json", {}).get("example")
        if corpo is None:
            continue
        r = client.post(caminho, json=corpo)
        if r.status_code >= 400:
            recusados.append(f"POST {caminho} -> {r.status_code} {r.text[:160]}")
    assert not recusados, recusados
