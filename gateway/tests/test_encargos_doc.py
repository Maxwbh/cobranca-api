"""A matriz de encargos em docs/api/encargos.md tem de bater com o comportamento
real da engine. Sem isto, a doc envelhece calada quando a engine muda.

Cada linha da tabela CNAB 400 do doc diz se o banco tem posição para o encargo;
aqui geramos o arquivo e conferimos que ✅ realmente entra e — implicitamente —
que não afirmamos suporte onde não há.
"""
import re
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[2] / "docs" / "api" / "encargos.md"

# banco no doc (com código) -> slug do provider offline
SLUG = {
    "037": None,  # placeholder
    "Santander (033)": "santander", "Bradesco (237)": "bradesco",
    "Sicoob (756)": "sicoob", "Banrisul (041)": "banrisul",
    "Banco do Nordeste (004)": "banco_nordeste", "C6 (336)": "banco_c6",
    "Unicred (136)": "unicred", "CrediSIS (097)": "credisis",
    "Itaú (341)": "itau", "Banco do Brasil (001)": "banco_brasil",
    "Citibank (745)": "citibank", "BRB / Brasília (070)": "banco_brasilia",
}

# coluna do doc -> (kwargs que EXERCITAM o encargo no 400)
COLUNA = {
    "Mora": {"valor_mora": 1.0},
    "Multa": {"percentual_multa": 2.0},
    "IOF": {"valor_iof": 3.0},
    "Abat.": {"valor_abatimento": 25.0},
}

# contas por banco (alguns exigem campos próprios; os que não sei, pulo)
CONTA = {
    "banco_brasil": {"agencia": "3073", "conta_corrente": "12345678",
                     "convenio": "1234567", "carteira": "18", "variacao_carteira": "017"},
    "banco_c6": {"agencia": "3073", "conta_corrente": "12345678",
                 "convenio": "1234567", "carteira": "1"},
}


def _linhas_400():
    """Extrai a tabela cujo cabeçalho tem 'Banco' e 'Multa' (a matriz do 400)."""
    linhas_md = DOC.read_text().splitlines()
    cabec, corpo, dentro = None, [], False
    for ln in linhas_md:
        if ln.strip().startswith("|") and "Banco" in ln and "Multa" in ln:
            cabec = [c.strip() for c in ln.strip().strip("|").split("|")]
            dentro = True
            continue
        if dentro:
            if not ln.strip().startswith("|"):
                break
            if set(ln.strip()) <= set("|-: "):   # separador
                continue
            cels = [c.strip() for c in ln.strip().strip("|").split("|")]
            corpo.append(dict(zip(cabec, cels)))
    assert cabec, "tabela do CNAB 400 não encontrada no doc"
    return cabec, corpo


def test_doc_de_encargos_existe_e_tem_matriz():
    cabec, linhas = _linhas_400()
    assert "Multa" in cabec and "Mora" in cabec
    assert len(linhas) >= 10          # a doc lista os bancos do 400


@pytest.mark.parametrize("banco,coluna", [
    ("banco_brasil", "Mora"), ("banco_brasil", "IOF"), ("banco_brasil", "Abat."),
    ("banco_c6", "Mora"), ("banco_c6", "Multa"), ("banco_c6", "Abat."),
])
def test_matriz_do_doc_bate_com_o_comportamento(client, banco, coluna):
    """Onde o doc diz ✅, o encargo TEM de entrar no arquivo; onde diz —, não."""
    import json
    from app.core import pycob
    _, linhas = _linhas_400()
    marca = {SLUG.get(l["Banco"]): l for l in linhas}.get(banco)
    assert marca, f"{banco} não está na matriz do doc"
    esperado_suporte = marca[coluna] == "✅"

    base = {"empresa_mae": "E", "documento_cedente": "11222333000181",
            "digito_conta": "0", "sequencial_remessa": 1, **CONTA[banco]}
    pag = {"nosso_numero": "123456789", "data_vencimento": "2027-12-31",
           "valor": 1500.0, "sacado": "Joao", "sacado_documento": "52998224725",
           "sacado_endereco": "R1", "sacado_bairro": "C", "sacado_cidade": "SP",
           "sacado_uf": "SP", "sacado_cep": "01000000"}
    def gera(extra):
        d = dict(base); d["pagamentos"] = [dict(pag, **extra)]
        return pycob.gerar_remessa(banco, "cnab400", d)

    real_suporte = gera({}) != gera(COLUNA[coluna])
    assert real_suporte == esperado_suporte, (
        f"doc diz {'✅' if esperado_suporte else '—'} para {banco}/{coluna}, "
        f"mas o comportamento real é {'entra' if real_suporte else 'não entra'}")
