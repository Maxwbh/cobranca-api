#!/usr/bin/env python3
"""Gera as imagens de boleto do README e da doc, pela API.

    PYTHONPATH=gateway python scripts/gerar-boletos-exemplo.py

As oito imagens da galeria eram feitas **à mão**, uma vez, em tamanhos
diferentes (762px umas, 1166px outras). Por isso envelheceram: a engine
redesenhou o modelo `moderno` e o README seguiu mostrando o desenho antigo,
dizendo "exemplos reais gerados pela API". Com um gerador, refazer é um comando.

Tudo passa por `app.core.pycob` — o mesmo caminho que a API usa. O que aparece
na imagem é o que um cliente recebe; não há atalho para a engine.

Requer `pdftoppm` (poppler-utils) para rasterizar.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "gateway"))

from app.core import pycob  # noqa: E402

SAIDA = REPO / "docs" / "assets" / "boletos"
SAIDA_DOCS = REPO / "docs" / "assets"
LARGURA = 900  # px — uma medida só para a galeria inteira

#: Dados de exemplo. Documento de teste e nomes fictícios: a imagem vai para um
#: README público e boleto é instrumento de pagamento.
BASE = {
    "cedente": "Empresa Exemplo Servicos LTDA",
    "documento_cedente": "11222333000181",
    "cedente_endereco": "Av. Afonso Pena, 1500, Centro, Belo Horizonte, MG",
    "sacado": "Maria Aparecida de Souza",
    "sacado_documento": "52998224725",
    "sacado_endereco": "Rua Presidente Kennedy, 126A, Canaa, Sete Lagoas, MG, CEP 35701206",
    "numero_documento": "NF-2027-0042",
    "valor": 1279.50,
    "data_vencimento": "2027-09-10",
    "especie_documento": "DM",
    "aceite": "N",
    "local_pagamento": "Pagavel em qualquer banco ate o vencimento",
    "instrucoes": [
        "Apos o vencimento, multa de 2% e juros de 1% ao mes.",
        "Desconto de R$ 150,00 ate 5 dias antes do vencimento.",
        "Nao receber apos 30 dias; decorrido o prazo, protestar.",
    ],
}

#: Cada banco tem a sua conta — carteira, convênio e o tamanho do nosso número
#: mudam por regra do banco, e `validar()` recusa o que não bate.
CONTAS = {
    "banco_brasil": {"agencia": "3073", "conta_corrente": "12345678",
                     "convenio": "1234567", "carteira": "18", "nosso_numero": "1042"},
    "itau": {"agencia": "0057", "conta_corrente": "12345", "carteira": "109",
             "nosso_numero": "12345678"},
    "santander": {"agencia": "1234", "conta_corrente": "123456", "carteira": "101",
                  "convenio": "1234567", "nosso_numero": "123456789012"},
    "caixa": {"agencia": "1234", "conta_corrente": "123456", "carteira": "14",
              "convenio": "123456", "nosso_numero": "123456789012345"},
    "banco_c6": {"agencia": "0001", "conta_corrente": "1234567", "carteira": "10",
                 "convenio": "123456789012", "nosso_numero": "1234567890"},
    "sicoob": {"agencia": "3069", "conta_corrente": "12345", "carteira": "1",
               "convenio": "1234567", "variacao": "01", "nosso_numero": "1234567"},
    # 19º banco offline, a partir da pyCobrança 1.1.1. Só a carteira 110: na 112
    # quem numera é o Inter, e o nosso número só existe no retorno.
    "inter": {"agencia": "0001", "conta_corrente": "123456", "carteira": "110",
              "convenio": "123456", "nosso_numero": "1234567890"},
}

FAIXA = {"logo_empresa": "EXEMPLO", "cor_marca": "1B4F8A",
         "rodape_contato": "financeiro@exemplo.com.br  -  (31) 3333-0000"}
#: Desconto, multa e juros NAO vao no boleto — dependem da data do pagamento e
#: a faixa FEBRABAN e' preenchida pelo caixa. A regra vai impressa, como texto,
#: nas `instrucoes` acima; os valores vao na remessa CNAB.
#: Bolepix de verdade: o EMV **do banco**, devolvido ao registrar a cobrança.
#: A imagem saía de `chave_pix`, que monta um BR Code ESTÁTICO — credita a chave
#: e deixa o título em aberto. Chamar aquilo de Bolepix numa imagem pública era
#: ensinar o oposto do produto; o gerador confere `pix_vinculado` antes de
#: escrever o arquivo.
BOLEPIX = {"pix_copia_cola": (
    "00020101021226870014br.gov.bcb.pix2565qrcode.exemplo.com.br/pix/v2/cobv/"
    "9d36b84f-c70b-478f-b95c-12729bd97542520400005303986540515.005802BR"
    "5924EMPRESA EXEMPLO SERVICOS6014BELO HORIZONTE62070503***6304A1B2")}


def _dados(banco: str, **extra) -> dict:
    return {**BASE, **CONTAS[banco], **extra}


def _png(nome: str, pdf: bytes, pasta: Path | None = None) -> None:
    """PDF -> PNG da primeira página, na largura da galeria."""
    with tempfile.TemporaryDirectory() as tmp:
        origem = Path(tmp) / "b.pdf"
        origem.write_bytes(pdf)
        subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", "-scale-to-x", str(LARGURA),
             "-scale-to-y", "-1", str(origem), str(Path(tmp) / "saida")],
            check=True, capture_output=True)
        gerado = next(Path(tmp).glob("saida*.png"))
        destino = (pasta or SAIDA) / f"{nome}.png"
        shutil.copyfile(gerado, destino)
        print(f"  {destino.relative_to(REPO)}  ({destino.stat().st_size // 1024} KB)")


def main() -> int:
    if shutil.which("pdftoppm") is None:
        print("pdftoppm não encontrado — instale poppler-utils", file=sys.stderr)
        return 1
    SAIDA.mkdir(parents=True, exist_ok=True)

    # Galeria por banco: o desenho padrão, que é o que a API entrega sem pedir nada.
    for banco in ("banco_brasil", "itau", "santander", "caixa", "banco_c6",
                  "sicoob", "inter"):
        pdf, _ = pycob.emitir_boleto(banco, _dados(banco))
        _png(banco, pdf)

    # Bolepix: o QR do BANCO, que dá baixa no título. `pix_vinculado` é o que
    # separa este boleto de um com QR avulso — sem a asserção, a imagem voltaria
    # a mostrar um QR que não liquida nada com o nome de Bolepix.
    pdf, info = pycob.emitir_boleto("banco_brasil", _dados("banco_brasil", **BOLEPIX))
    assert info["pix_copia_cola"], "Bolepix sem copia-e-cola"
    assert info["pix_vinculado"] is True, "o QR desta imagem não liquida o título"
    _png("bolepix", pdf)

    # Carnê: 3 vias por A4.
    parcelas = [
        {**_dados("banco_brasil"), "bank": "banco_brasil",
         "nosso_numero": str(1050 + i), "numero_documento": f"NF-2027-0042/{i + 1}",
         "data_vencimento": f"2027-{9 + i:02d}-10",
         "instrucoes": [f"Parcela {i + 1} de 3 do contrato CTR-2027-0042."]}
        for i in range(3)
    ]
    pdf, _ = pycob.pdf_multi(parcelas, template="carne")
    _png("carne", pdf)

    # Os dois modelos, lado a lado, com os mesmos dados — é a comparação que a
    # galeria por banco não mostra, porque todos saem no padrão.
    for modelo in ("moderno", "classico"):
        pdf, _ = pycob.emitir_boleto(
            "banco_brasil", _dados("banco_brasil", **BOLEPIX), modelo)
        _png(f"modelo-{modelo}", pdf)

    # Faixa de marca: só no `moderno`, e é o que o `classico` não tem.
    pdf, _ = pycob.emitir_boleto(
        "banco_brasil", _dados("banco_brasil", **FAIXA, **BOLEPIX))
    _png("faixa-de-marca", pdf)

    _comparativo()
    print(f"\n{len(list(SAIDA.glob('*.png')))} imagens em {SAIDA.relative_to(REPO)}")
    return 0


#: Os dois boletos de `docs/api/online-vs-offline.md`. Ali o texto imprime a
#: linha digitável e o código de barras REAIS da captura, então a imagem não
#: pode sair de um payload qualquer — ela contradiria o número logo acima dela.
#: O payload abaixo foi reconstruído a partir do campo livre publicado no
#: documento, e a asserção confere: se a engine mudar o cálculo, o gerador para
#: aqui em vez de publicar uma imagem que discorda do texto.
COMPARATIVO = {
    "boleto-c6-offline": (
        "banco_c6",
        {"agencia": "0001", "conta_corrente": "1", "convenio": "100",
         "carteira": "10", "nosso_numero": "12345678"},
        "33690.00009 00001.000017 23456.781030 9 15700000125000"),
    "boleto-sicoob-offline": (
        "sicoob",
        {"agencia": "4327", "conta_corrente": "0229385", "convenio": "0229385",
         "carteira": "1", "variacao": "01", "nosso_numero": "7890"},
        "75691.43279 01022.938508 00789.000015 6 15700000125000"),
}

CEDENTE_COMPARATIVO = {
    "valor": 1250.00, "data_vencimento": "2026-09-15",
    "cedente": "Aurora Servicos Empresariais LTDA",
    "documento_cedente": "47816329000199",
    "sacado": "Vitoria Gabriela Emanuelly Ramos",
    "sacado_documento": "77044362109",
}


def _comparativo() -> None:
    for nome, (banco, conta, linha) in COMPARATIVO.items():
        dados = {**CEDENTE_COMPARATIVO, **conta}
        pdf, info = pycob.emitir_boleto(banco, dados)
        if info["linha_digitavel"] != linha:
            raise SystemExit(
                f"{nome}: a linha digitável mudou e o texto de "
                f"online-vs-offline.md ficaria errado.\n"
                f"  documento: {linha}\n  agora:     {info['linha_digitavel']}")
        _png(nome, pdf, SAIDA_DOCS)


if __name__ == "__main__":
    sys.exit(main())
