"""Verificador FEBRABAN independente — NÃO usa a pyCobrança.

Escrito do zero a partir do layout da ficha de compensação. Perguntar à engine
se a saída dela está certa não prova nada; este módulo confere o que ela
produziu contra a regra publicada.

Layout do código de barras (44 posições):
    01-03  código do banco
    04     moeda (9 = real)
    05     DV geral do código de barras (módulo 11)
    06-09  fator de vencimento
    10-19  valor em centavos
    20-44  campo livre (25 posições, regra de cada banco)

Linha digitável (47 dígitos, cinco campos):
    campo 1  banco(3) + moeda(1) + livre[1:5]  + DV módulo 10
    campo 2  livre[6:15]                       + DV módulo 10
    campo 3  livre[16:25]                      + DV módulo 10
    campo 4  DV geral do código de barras
    campo 5  fator(4) + valor(10)
"""
from __future__ import annotations

import re
from datetime import date

#: Data-base do fator de vencimento (FEBRABAN).
BASE_FATOR = date(1997, 10, 7)


def dv_modulo11_barras(barras43: str) -> str:
    """DV geral (posição 5), módulo 11 com pesos 2..9 cíclicos da direita.

    Resto 0, 1 ou 10 -> DV = 1. É a regra da ficha de compensação, e difere do
    módulo 11 usado no nosso número de vários bancos.
    """
    pesos, soma = [2, 3, 4, 5, 6, 7, 8, 9], 0
    for i, ch in enumerate(reversed(barras43)):
        soma += int(ch) * pesos[i % 8]
    resto = soma % 11
    dv = 11 - resto
    return "1" if dv in (0, 1, 10, 11) else str(dv)


def dv_modulo10(campo: str) -> str:
    """DV dos campos da linha digitável: módulo 10, pesos 2 e 1 alternados."""
    soma, peso = 0, 2
    for ch in reversed(campo):
        p = int(ch) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    return str((10 - soma % 10) % 10)


def fatores_possiveis(vencimento: date) -> set[str]:
    """Fatores aceitáveis para a data.

    O contador de 4 dígitos estourou: pela nota FEBRABAN, ao passar de 9999 ele
    volta a 1000. Implementações divergem em QUANDO aplicar o retorno, então o
    verificador aceita as duas leituras em vez de reprovar por uma escolha que
    não é erro.
    """
    dias = (vencimento - BASE_FATOR).days
    opcoes = {dias}
    while dias > 9999:
        dias -= 9000
        opcoes.add(dias)
    return {f"{d:04d}" for d in opcoes if 0 < d <= 9999}


def confere_barras(barras: str, *, codigo_banco: str, valor: float,
                   vencimento: date) -> list[str]:
    """Erros encontrados no código de barras. Lista vazia = está certo."""
    erros: list[str] = []
    if len(barras) != 44:
        return [f"código de barras com {len(barras)} posições (esperado 44)"]
    if not barras.isdigit():
        return ["código de barras com caractere não numérico"]

    if barras[0:3] != codigo_banco:
        erros.append(f"banco {barras[0:3]} no código de barras, esperado {codigo_banco}")
    if barras[3] != "9":
        erros.append(f"moeda {barras[3]}, esperado 9 (real)")

    esperado = dv_modulo11_barras(barras[0:4] + barras[5:])
    if barras[4] != esperado:
        erros.append(f"DV geral {barras[4]}, calculado {esperado}")

    aceitos = fatores_possiveis(vencimento)
    if barras[5:9] not in aceitos:
        erros.append(f"fator de vencimento {barras[5:9]}, esperado um de {sorted(aceitos)}")

    centavos = int(round(valor * 100))
    if barras[9:19] != f"{centavos:010d}":
        erros.append(f"valor {barras[9:19]}, esperado {centavos:010d}")

    if barras[19:] == "0" * 25:
        erros.append("campo livre todo zerado")
    return erros


def confere_linha(linha: str, barras: str) -> list[str]:
    """Erros na linha digitável, conferida contra o código de barras."""
    erros: list[str] = []
    so_digitos = re.sub(r"\D", "", linha)
    if len(so_digitos) != 47:
        return [f"linha digitável com {len(so_digitos)} dígitos (esperado 47)"]

    livre = barras[19:]
    c1, c2, c3 = so_digitos[0:10], so_digitos[10:21], so_digitos[21:32]
    dv_geral, campo5 = so_digitos[32], so_digitos[33:47]

    if c1[0:4] != barras[0:4]:
        erros.append(f"campo 1 começa {c1[0:4]}, o barras diz {barras[0:4]}")
    if c1[4:9] != livre[0:5]:
        erros.append(f"campo 1 traz livre[1:5]={c1[4:9]}, o barras diz {livre[0:5]}")
    if c1[9] != dv_modulo10(c1[0:9]):
        erros.append(f"DV do campo 1 é {c1[9]}, calculado {dv_modulo10(c1[0:9])}")

    if c2[0:10] != livre[5:15]:
        erros.append(f"campo 2 traz {c2[0:10]}, o barras diz {livre[5:15]}")
    if c2[10] != dv_modulo10(c2[0:10]):
        erros.append(f"DV do campo 2 é {c2[10]}, calculado {dv_modulo10(c2[0:10])}")

    if c3[0:10] != livre[15:25]:
        erros.append(f"campo 3 traz {c3[0:10]}, o barras diz {livre[15:25]}")
    if c3[10] != dv_modulo10(c3[0:10]):
        erros.append(f"DV do campo 3 é {c3[10]}, calculado {dv_modulo10(c3[0:10])}")

    if dv_geral != barras[4]:
        erros.append(f"DV geral {dv_geral} na linha, {barras[4]} no barras")
    if campo5 != barras[5:19]:
        erros.append(f"campo 5 {campo5}, o barras diz {barras[5:19]}")
    return erros
