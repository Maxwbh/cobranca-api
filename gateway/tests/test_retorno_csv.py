# `POST /api/retorno?formato=csv`: a mesma lista do JSON, numa tabela que a
# contabilidade abre — com o cabeçalho no idioma de quem lê.
#
# Fase 3 do roadmap Mercosul ("exportação de liquidações com cabeçalho em
# espanhol"). Medido antes de escrever: o JSON devolve um item por registro,
# com as chaves do `RetornoItem` e a chave OMITIDA quando o arquivo não trouxe
# o campo. O CSV fixa as dez colunas, vazias nesse caso, para a planilha não
# mudar de forma de um arquivo para outro.
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
import yaml

from app.core.retorno_csv import COLUNAS, ROTULOS, retorno_csv

RAIZ = Path(__file__).resolve().parents[2]
FIXTURE = RAIZ / "postman" / "fixtures" / "retorno_cnab400_bb.ret"
SPEC = yaml.safe_load((RAIZ / "docs" / "openapi.yaml").read_text(encoding="utf-8"))


def _post(client, headers=None, **params):
    return client.post("/api/retorno", headers=headers or {},
                       params={"bank": "banco_brasil", "type": "cnab400", **params},
                       files={"data": ("r.ret", FIXTURE.read_bytes(), "text/plain")})


def _linhas(texto: str) -> list[list[str]]:
    assert texto.startswith("\ufeff"), "sem BOM o Excel abre o UTF-8 com acento quebrado"
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


def test_as_colunas_sao_as_do_retorno_item_da_spec():
    """O CSV promete as colunas do schema; schema que cresce tem de puxar a
    tabela junto — e os rótulos nos dois idiomas."""
    props = list(SPEC["components"]["schemas"]["RetornoItem"]["properties"])
    assert list(COLUNAS) == props, f"COLUNAS {list(COLUNAS)} ≠ RetornoItem {props}"
    for idioma in ("pt", "es"):
        assert set(ROTULOS[idioma]) == set(COLUNAS), f"rótulos {idioma} não cobrem as colunas"


def test_json_continua_sendo_o_padrao(client):
    r = _post(client)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert isinstance(r.json(), list) and r.json()[0]["codigo_ocorrencia"] == "06"


def test_csv_em_portugues_por_padrao(client):
    r = _post(client, formato="csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == "attachment; filename=retorno-banco_brasil.csv"
    assert r.headers["content-language"] == "pt"
    cab, *linhas = _linhas(r.text)
    assert cab == [ROTULOS["pt"][c] for c in COLUNAS]
    assert cab[0] == "Nosso número" and cab[3] == "Data da ocorrência"
    assert len(linhas) == len(_post(client).json())
    linha = dict(zip(COLUNAS, linhas[0]))
    assert linha["nosso_numero"] == "00000012345678901"
    assert linha["valor_pago"] == "1500,00", "valor com vírgula decimal, para a planilha"
    assert linha["codigo_ocorrencia"] == "06"
    assert linha["motivo_ocorrencia"] == "Liquidação normal", "o vocabulário do banco não se traduz"
    assert linha["layout_generico"] == "não"
    assert linha["numero_documento"] == "" and linha["data_credito"] == "", (
        "campo que o arquivo não trouxe sai vazio — no JSON a chave é omitida")


def test_csv_em_espanhol_quando_pedido(client):
    r = _post(client, headers={"Accept-Language": "es-PY"}, formato="csv")
    assert r.status_code == 200
    assert r.headers["content-language"] == "es"
    cab, *linhas = _linhas(r.text)
    assert cab == [ROTULOS["es"][c] for c in COLUNAS]
    assert cab[2] == "Fecha de crédito" and cab[8] == "Ocurrencia"
    linha = dict(zip(COLUNAS, linhas[0]))
    assert linha["layout_generico"] == "no"
    assert linha["motivo_ocorrencia"] == "Liquidação normal", "valor do banco: fica como veio"
    # `?lang=es` vale como o cabeçalho
    assert _linhas(_post(client, formato="csv", lang="es").text)[0] == cab


def test_formato_desconhecido_e_400_nos_dois_idiomas(client):
    r = _post(client, formato="xlsx")
    assert r.status_code == 400
    assert r.json()["validation_errors"] == ["`formato` deve ser 'json' ou 'csv' — recebi 'xlsx'"]
    es = _post(client, headers={"Accept-Language": "es"}, formato="xlsx")
    assert es.json()["validation_errors"] == ["`formato` debe ser 'json' o 'csv' — recibí 'xlsx'"]


@pytest.mark.parametrize("bank", ["bancó", "x\r\nX-Inj: 1", "../../etc", "xpto"])
def test_bank_desconhecido_e_400_e_nunca_chega_ao_header(client, bank):
    """`bank` só era conferido contra o header do arquivo quando o slug era
    conhecido; desconhecido, passava — e no CSV ia para o `Content-Disposition`:
    acento dava 500 (header é latin-1), CRLF entrava no cabeçalho da resposta."""
    for formato in ("csv", "json"):
        r = _post(client, formato=formato, bank=bank)
        assert r.status_code == 400, (bank, formato, r.status_code)
        assert r.json()["validation_errors"] == [f"bank {bank!r} não corresponde a banco suportado"]
        assert "content-disposition" not in r.headers
    es = _post(client, headers={"Accept-Language": "es"}, formato="csv", bank=bank)
    assert es.json()["validation_errors"] == [f"bank {bank!r} no corresponde a un banco soportado"]


def test_retorno_csv_puro():
    itens = [{"nosso_numero": "1", "valor_pago": 10.5, "layout_generico": True},
             {"nosso_numero": "2", "valor_pago": 0.0, "layout_generico": False, "motivo_ocorrencia": "a;b"}]
    linhas = _linhas(retorno_csv(itens, "es"))
    assert linhas[1][0] == "1" and linhas[1][5] == "10,50" and linhas[1][9] == "sí"
    assert linhas[2][8] == "a;b", "ponto e vírgula dentro do valor é escapado pelo csv"
    assert len(linhas) == 3 and all(len(l) == len(COLUNAS) for l in linhas)
    assert retorno_csv([], "xx").startswith("\ufeffNosso número;"), "idioma desconhecido cai em pt"
