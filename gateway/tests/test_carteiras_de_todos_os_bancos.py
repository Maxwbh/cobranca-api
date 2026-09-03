# Toda carteira de todo banco offline, pela fronteira HTTP.
#
# A engine tem varredura própria, e ela para na engine. Esta passa por
# `GET /api/boleto/data` e `GET /api/boleto?type=pdf` — onde moram o schema
# fechado, `campos_aceitos`, a tradução de nomes e o mapeamento de erros. Um
# banco pode calcular perfeitamente na engine e ser inalcançável pela API.
#
# O resultado é conferido por `febraban.py`, escrito do zero a partir do layout
# da ficha de compensação. Perguntar à engine se a saída dela está certa não
# prova nada; o verificador é a segunda opinião.
from __future__ import annotations

import io
import json
from datetime import date

import pytest
from pypdf import PdfReader

from app.core import pycob

from . import febraban as fb

VALOR = 1279.50
VENCIMENTO = date(2027, 9, 10)

COMUM = {
    "valor": VALOR,
    "data_vencimento": VENCIMENTO.isoformat(),
    "data_documento": "2027-08-01",
    "cedente": "Empresa Exemplo Servicos LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Maria Aparecida de Souza",
    "sacado_documento": "52998224725",
}

#: `regras_campos` usa o nome NATIVO da engine; o contrato REST usa outro em um
#: caso. Traduzir aqui é o que faz a varredura exercitar a fronteira de verdade.
NOME_NO_CONTRATO = {"conta": "conta_corrente"}

#: Campo cujo valor não é um número qualquer do tamanho máximo.
VALOR_FIXO = {
    "byte_idt": "2",        # Sicredi: 1 = cliente, 2 = banco
    "quantidade": "001",    # Sicoob: parcelas do carnê
}

#: Campo OBRIGATÓRIO que não tem regra de tamanho em `regras_campos`.
#:
#: `regras_campos` prende o TAMANHO dos campos que entram no campo livre — não é
#: a lista do que o banco exige. No BB o convênio é obrigatório e o tamanho não é
#: livre (4, 6 ou 7 dígitos, e é ele que decide o formato do nosso número); no
#: Santander o código do cedente é obrigatório e não aparece em regra nenhuma.
OBRIGATORIO_SEM_REGRA = {
    "banco_brasil": {"convenio": "1234567"},
    "santander": {"convenio": "1234567"},
}


def _payload(slug: str, carteira: str) -> dict:
    classe = pycob._classe_banco(slug)
    dados = dict(COMUM, carteira=carteira)
    for campo, (minimo, maximo) in (getattr(classe, "regras_campos", {}) or {}).items():
        tamanho = maximo or minimo
        if campo in VALOR_FIXO:
            bruto = VALOR_FIXO[campo]
        else:
            # Dígitos variados de propósito: valor repetido esconderia troca de
            # posição entre campos vizinhos no campo livre.
            bruto = "".join(str((i + 1) % 10) for i in range(tamanho)) or "1"
        dados[NOME_NO_CONTRATO.get(campo, campo)] = bruto
    dados.update(OBRIGATORIO_SEM_REGRA.get(slug, {}))
    return dados


def _todas_as_carteiras() -> list[tuple[str, str]]:
    pares = []
    for slug in pycob.bancos_suportados():
        classe = pycob._classe_banco(slug)
        for carteira in getattr(classe, "carteiras", ()) or ():
            pares.append((slug, carteira))
    return pares


CARTEIRAS = _todas_as_carteiras()


def test_a_varredura_cobre_todo_banco_e_toda_carteira():
    """A lista sai do registro da engine, então não envelhece — mas um erro de
    montagem que a esvaziasse faria as provas abaixo passarem sem rodar nada."""
    assert len(pycob.bancos_suportados()) == 19
    assert len(CARTEIRAS) >= 55
    assert {slug for slug, _ in CARTEIRAS} == set(pycob.bancos_suportados())


@pytest.mark.parametrize(("slug", "carteira"), CARTEIRAS,
                         ids=[f"{s}-{c}" for s, c in CARTEIRAS])
def test_boleto_da_carteira_bate_com_a_regra_febraban(client, slug, carteira):
    classe = pycob._classe_banco(slug)
    r = client.get("/api/boleto/data", params={
        "bank": slug, "data": json.dumps(_payload(slug, carteira))})
    assert r.status_code == 200, r.text
    corpo = r.json()

    erros = fb.confere_barras(corpo["codigo_barras"], codigo_banco=classe.codigo,
                              valor=VALOR, vencimento=VENCIMENTO)
    erros += fb.confere_linha(corpo["linha_digitavel"], corpo["codigo_barras"])
    assert not erros, f"{slug}/{carteira}: " + "; ".join(erros)


@pytest.mark.parametrize(("slug", "carteira"), CARTEIRAS,
                         ids=[f"{s}-{c}" for s, c in CARTEIRAS])
def test_o_pdf_sai_e_imprime_a_mesma_linha_do_json(client, slug, carteira):
    """Um banco pode calcular certo e falhar ao DESENHAR — e é o papel que vai
    para o pagador. Conferir a linha dentro do PDF fecha a brecha que a
    conferência do JSON deixa: papel e JSON saindo de objetos diferentes."""
    dados = _payload(slug, carteira)
    esperada = client.get("/api/boleto/data", params={
        "bank": slug, "data": json.dumps(dados)}).json()["linha_digitavel"]
    r = client.get("/api/boleto", params={
        "bank": slug, "type": "pdf", "data": json.dumps(dados)})
    assert r.status_code == 200, r.text[:200]
    assert r.content.startswith(b"%PDF")
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert esperada in texto, f"{slug}/{carteira}: linha do JSON não impressa no PDF"


def test_duas_grafias_da_mesma_carteira_dao_o_mesmo_boleto():
    """`09` no Sicoob virava `0` na primeira posição do campo livre.

    A engine declarava `("1", "3", "9", "09")` e tratava `9` e `09` como a mesma
    carteira ao escolher o identificador — mas o campo livre fazia
    `so_digitos(carteira)[:1]`, que trunca em vez de normalizar. Não existe
    carteira 0 no Sicoob, e o boleto saía estruturalmente válido: o DV é
    recalculado sobre os dígitos errados, então nenhum verificador de estrutura
    pega. Só comparando as duas grafias da MESMA carteira.

    Corrigido na pyCobrança 1.1.1 (`_carteira_no_campo_livre` normaliza). O
    gateway teve um remendo enquanto a correção não chegava à versão do pin;
    ele saiu quando esta varredura passou a dar o mesmo resultado sem ele — e
    este caso é o que autoriza a remoção, porque re-mede em vez de reler.

    Varre todos os bancos porque a próxima ocorrência não vai avisar. O Bradesco
    é o contra-exemplo que impede a regra ingênua: lá `03`, `06` e `09` são
    carteiras de dois dígitos de verdade, e nenhuma delas tem irmã de um dígito.
    """
    divergentes = []
    for slug in pycob.bancos_suportados():
        classe = pycob._classe_banco(slug)
        por_valor: dict[int, list[str]] = {}
        for carteira in getattr(classe, "carteiras", ()) or ():
            if carteira.isdigit():
                por_valor.setdefault(int(carteira), []).append(carteira)
        for grafias in por_valor.values():
            if len(grafias) < 2:
                continue
            barras = {pycob.dados_boleto(slug, _payload(slug, g))["codigo_barras"]
                      for g in grafias}
            if len(barras) > 1:
                divergentes.append((slug, grafias))
    assert not divergentes, (
        "a mesma carteira em grafias diferentes produz boletos diferentes: "
        f"{divergentes}")


def test_carteira_fora_do_conjunto_do_banco_e_recusada():
    """O conjunto é validação de verdade, não decoração: emitir numa carteira
    que o beneficiário não tem produz título que o banco recusa ou roteia
    errado — e o erro diz quais existem."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto("sicoob", _payload("sicoob", "7"))
    assert "não suportada" in exc.value.erros[0]
    assert "1" in exc.value.erros[0] and "9" in exc.value.erros[0]


def test_o_verificador_febraban_reprova_boleto_corrompido():
    """Sem esta prova, um verificador quebrado aprovaria as 55 varreduras acima
    em silêncio — e o teste inteiro viraria decoração."""
    corpo = pycob.dados_boleto("banco_brasil", _payload("banco_brasil", "18"))
    barras = corpo["codigo_barras"]
    assert not fb.confere_barras(barras, codigo_banco="001", valor=VALOR,
                                 vencimento=VENCIMENTO)

    trocado = barras[:4] + ("1" if barras[4] != "1" else "2") + barras[5:]
    assert fb.confere_barras(trocado, codigo_banco="001", valor=VALOR,
                             vencimento=VENCIMENTO), "DV geral errado passou"

    outro_valor = barras[:9] + "0000000001" + barras[19:]
    assert fb.confere_barras(outro_valor, codigo_banco="001", valor=VALOR,
                             vencimento=VENCIMENTO), "valor errado passou"

    linha_ruim = corpo["linha_digitavel"].replace(" ", "")[:-1] + "0"
    assert fb.confere_linha(linha_ruim, barras) or linha_ruim.endswith(
        corpo["linha_digitavel"].replace(" ", "")[-1]), "linha corrompida passou"


# --- a doc acompanha o registro ----------------------------------------------
#
# Foi a omissão que deixou o Inter de fora: ele entrou como 19º banco e as duas
# tabelas de campos seguiram com 18 linhas. Nada quebrou — só ficou faltando, que
# é como a doc envelhece de verdade.

DOCS = [
    ("docs/fields/all-banks.md", "Carteiras aceitas"),
    ("docs/api/validacao-campos.md", "Validação de campos"),
]


def _texto(caminho: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[2] / caminho).read_text(encoding="utf-8")


@pytest.mark.parametrize(("caminho", "assunto"), DOCS, ids=[d[0] for d in DOCS])
def test_a_tabela_de_campos_cita_todo_banco_do_registro(caminho, assunto):
    texto = _texto(caminho)
    faltando = [slug for slug in pycob.bancos_suportados()
                if pycob.CODIGO_POR_SLUG[slug] not in texto]
    assert not faltando, (
        f"{caminho} ({assunto}) não cita o código FEBRABAN de: {faltando}")


@pytest.mark.parametrize(("caminho", "assunto"), DOCS, ids=[d[0] for d in DOCS])
def test_a_doc_nao_oferece_carteira_que_o_banco_nao_tem(caminho, assunto):
    """Carteira retirada do código não pode continuar anunciada.

    A `CSB` do HSBC saiu na 1.1.1 — o campo livre dela montava 27 posições onde
    cabem 25, então nunca produziu boleto válido — e as duas tabelas seguiam
    oferecendo. Anunciar carteira que não emite é promessa que sempre falha.

    Olha só as LINHAS DE TABELA do HSBC: o texto corrido explica que a carteira
    saiu, e citá-la ali é o certo. Uma busca solta pelo nome reprovaria a própria
    explicação — foi o que aconteceu na primeira versão desta prova.
    """
    codigo_hsbc = pycob.CODIGO_POR_SLUG["hsbc"]
    do_hsbc = [linha for linha in _texto(caminho).splitlines()
               if linha.lstrip().startswith("|") and codigo_hsbc in linha]
    assert do_hsbc, f"{caminho} não tem linha de tabela para o HSBC ({codigo_hsbc})"
    aceitas = pycob._classe_banco("hsbc").carteiras
    assert "CSB" not in aceitas, "a CSB voltou ao código — reveja esta prova"
    oferecendo = [linha for linha in do_hsbc if "CSB" in linha]
    assert not oferecendo, (
        f"{caminho} oferece a carteira CSB, que saiu do código: {oferecendo}")
