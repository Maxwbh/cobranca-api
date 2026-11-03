"""Retorno CNAB em CSV, com cabeçalho no idioma de quem lê.

`POST /api/retorno?formato=csv` devolve a MESMA lista que o JSON — um item por
registro do arquivo —, numa tabela que a contabilidade abre direto: ponto e
vírgula como separador (o Excel em pt-BR e em es-* lê sem assistente), vírgula
decimal nos valores, e as colunas do `RetornoItem`, sempre as dez, vazias
quando o arquivo não trouxe o campo (no JSON a chave é omitida).

O que NÃO muda com o idioma: os valores. `motivo_ocorrencia` sai como o banco
escreveu, em português — é o vocabulário do arquivo, e traduzi-lo seria dar a
uma ocorrência o sentido que o banco não deu. As datas saem como o banco as
gravou (`DDMMAA`/`DDMMAAAA`), igual ao JSON.
"""
from __future__ import annotations

import csv
import io
from typing import Any

#: Colunas do `RetornoItem` (docs/openapi.yaml), na ordem da spec.
COLUNAS = ("nosso_numero", "numero_documento", "data_credito", "data_ocorrencia",
           "valor_titulo", "valor_pago", "valor_tarifa", "codigo_ocorrencia",
           "motivo_ocorrencia", "layout_generico")

ROTULOS: dict[str, dict[str, str]] = {
    "pt": {
        "nosso_numero": "Nosso número", "numero_documento": "Número do documento",
        "data_credito": "Data do crédito", "data_ocorrencia": "Data da ocorrência",
        "valor_titulo": "Valor do título", "valor_pago": "Valor pago",
        "valor_tarifa": "Tarifa", "codigo_ocorrencia": "Código da ocorrência",
        "motivo_ocorrencia": "Ocorrência", "layout_generico": "Layout genérico",
    },
    "es": {
        "nosso_numero": "Nosso número", "numero_documento": "Número de documento",
        "data_credito": "Fecha de crédito", "data_ocorrencia": "Fecha de ocurrencia",
        "valor_titulo": "Valor del título", "valor_pago": "Valor pagado",
        "valor_tarifa": "Tarifa", "codigo_ocorrencia": "Código de ocurrencia",
        "motivo_ocorrencia": "Ocurrencia", "layout_generico": "Layout genérico",
    },
}

BOOLEANO = {"pt": ("sim", "não"), "es": ("sí", "no")}


def _celula(valor: Any, idioma: str) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return BOOLEANO[idioma][0 if valor else 1]
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor)


def retorno_csv(itens: list[dict[str, Any]], idioma: str = "pt") -> str:
    idioma = idioma if idioma in ROTULOS else "pt"
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    escritor.writerow([ROTULOS[idioma][c] for c in COLUNAS])
    for item in itens:
        escritor.writerow([_celula(item.get(c), idioma) for c in COLUNAS])
    # BOM: é o que faz o Excel abrir UTF-8 com acento certo sem perguntar.
    return "\ufeff" + saida.getvalue()
