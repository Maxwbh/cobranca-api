# Campo fora do contrato e erro, nao sobra.
#
# O descarte silencioso era o mecanismo por tras de quase toda a familia de
# defeitos deste modulo: o campo entrava no payload, nao era nome de nada, e
# sumia -- com `200` e um boleto que nao tem o que o chamador achou que tinha.
# `numero_docmento` produzia um titulo sem numero de documento e nada na
# resposta dizia que faltava. A engine fechou a mesma fronteira em
# `contracts.boleto_de_api`.
from __future__ import annotations

import json

import pytest

from app.core import pycob

BANCO = "banco_brasil"
BASE = {
    "valor": 150.0,
    "cedente": "Empresa Teste LTDA",
    "documento_cedente": "11222333000181",
    "sacado": "Joao da Silva",
    "sacado_documento": "52998224725",
    "agencia": "3073",
    "conta_corrente": "12345678",
    "convenio": "1234567",
    "carteira": "18",
    "nosso_numero": "123",
    "data_vencimento": "2027-12-30",
}


def test_campo_desconhecido_e_recusado():
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "cor_favorita": "azul"})
    assert "'cor_favorita'" in exc.value.erros[0]


def test_erro_de_digitacao_ganha_sugestao():
    """Quase todo caso e typo: apontar o campo certo resolve mais rapido que
    listar os quarenta aceitos."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "numero_docmento": "NF-1"})
    assert "numero_documento" in exc.value.erros[0]


def test_o_erro_lista_o_que_o_banco_aceita():
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "xyz": "1"})
    listagem = exc.value.erros[-1]
    assert "nosso_numero" in listagem and "carteira" in listagem


def test_o_campo_que_sumia_agora_acusa(client):
    """O caso concreto: `numero_docmento` produzia um boleto sem o numero do
    documento, com 200, e nada apontava a falta."""
    r = client.get("/api/boleto/data", params={
        "bank": BANCO, "data": json.dumps({**BASE, "numero_docmento": "NF-1"})})
    assert r.status_code == 400, r.text
    assert any("numero_docmento" in e for e in r.json()["validation_errors"])


def test_nome_nativo_da_engine_continua_valendo():
    """`conta` e `conta_corrente` sao o mesmo campo em vocabularios diferentes;
    recusar o nativo quebraria quem ja o usa."""
    nativo = {k: v for k, v in BASE.items() if k != "conta_corrente"}
    a = pycob.dados_boleto(BANCO, {**nativo, "conta": "12345678"})
    b = pycob.dados_boleto(BANCO, BASE)
    assert a["codigo_barras"] == b["codigo_barras"]


def test_as_duas_grafias_com_valores_diferentes_sao_recusadas():
    """A ordem do dicionario decidia qual sobrevivia: um dos dois valores ia
    para o boleto e o outro sumia, sem erro -- e nos dois casos e o numero da
    conta que se esta errando."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "conta": "99999999"})
    assert "mesmo campo" in exc.value.erros[0]


@pytest.mark.parametrize("campo", ["desconto_abatimento", "outras_deducoes",
                                   "mora_multa", "outros_acrescimos", "valor_cobrado"])
def test_faixa_do_caixa_e_aceita_e_nao_vai_para_o_boleto(campo):
    """Desconto, multa e juros dependem da DATA DO PAGAMENTO.

    A faixa FEBRABAN do boleto e' preenchida pelo CAIXA, no ato: o valor nao se
    sabe na emissao, e numero impresso antes disso induz o pagador a erro — vai
    estar errado em qualquer data que nao a suposta.

    Aceito e ignorado, nao recusado: o mesmo registro de cobranca alimenta o
    boleto E a remessa, e e' natural que o payload traga os encargos. Recusar
    obrigaria quem integra a montar dois objetos para o mesmo titulo.
    """
    import io

    from pypdf import PdfReader
    pdf, info = pycob.emitir_boleto(BANCO, {**BASE, campo: 1234.56})
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "1.234,56" not in texto, f"`{campo}` foi impresso no boleto"
    assert "totalizadores" not in info


def test_o_boleto_sai_identico_com_ou_sem_os_encargos():
    """Ignorar de verdade: nem o codigo de barras nem o papel mudam."""
    com = {**BASE, "desconto_abatimento": 150.0, "mora_multa": 8.0,
           "valor_cobrado": 1137.50}
    assert pycob.dados_boleto(BANCO, com) == pycob.dados_boleto(BANCO, BASE)


def test_zero_tambem_e_ignorado():
    """`0` e valor informado, nao ausencia — e imprimiria `0,00` na faixa."""
    assert pycob.dados_boleto(BANCO, {**BASE, "mora_multa": 0}) == \
        pycob.dados_boleto(BANCO, BASE)


def test_a_regra_impressa_continua_valendo():
    """O lugar certo do desconto/multa no PAPEL e' o texto da instrucao."""
    import io

    from pypdf import PdfReader
    pdf = pycob.pdf_boleto(BANCO, {**BASE, "instrucoes": [
        "Apos o vencimento, multa de 2% e juros de 1% ao mes.",
        "Desconto de R$ 150,00 ate 5 dias antes do vencimento."]})
    texto = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "multa de 2%" in texto and "Desconto de R$ 150,00" in texto


def test_os_encargos_continuam_indo_no_cnab():
    """O CNAB e' arquivo de processamento do banco: ele PRECISA dos valores.

    E' de la que o banco aprende a calcular na data em que o titulo for pago —
    o que o boleto impresso nao tem como saber.
    """
    dados = {
        "empresa_mae": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
        "agencia": "3073", "conta_corrente": "12345678", "convenio": "1234567",
        "carteira": "18", "sequencial_remessa": 1,
        "pagamentos": [{
            "nosso_numero": "123456789", "numero_documento": "NF-1",
            "data_vencimento": "2027-12-31", "valor": 1279.50,
            "sacado": "Joao", "sacado_documento": "52998224725",
            "sacado_endereco": "Rua Teste, 100", "sacado_bairro": "Centro",
            "sacado_cidade": "Sao Paulo", "sacado_uf": "SP", "sacado_cep": "01000000",
            "codigo_multa": "2", "percentual_multa": 2.00, "data_multa": "2028-01-01",
            "tipo_mora": "2", "percentual_mora": 1.00, "data_mora": "2028-01-01",
            "cod_desconto": "1", "valor_desconto": 150.00, "data_desconto": "2027-12-26",
        }],
    }
    cnab = pycob.gerar_remessa(BANCO, "cnab240", dados)
    linhas = cnab.splitlines()
    # segmento R: e' onde multa, desconto e mora viajam no CNAB 240
    assert [l for l in linhas if len(l) > 13 and l[13] == "R"], "segmento R ausente"


def test_campo_deprecado_vazio_continua_sendo_ausencia():
    """`emv: ""` e ausencia, nao intencao -- e o campo esta documentado."""
    pycob.dados_boleto(BANCO, {**BASE, "emv": ""})


def test_campo_deprecado_preenchido_mantem_a_mensagem_propria():
    """Recusa por 'desconhecido' seria pior que a explicacao que ja existia."""
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.dados_boleto(BANCO, {**BASE, "emv": "0002..."})
    assert "chave_pix" in exc.value.erros[0]


def test_identificador_de_lote_nao_e_campo_desconhecido():
    """`seu_numero` e `external_id` identificam o ITEM dentro do lote -- e de
    onde sai o `item_id` que acusa parcela duplicada."""
    pycob.dados_boleto(BANCO, {**BASE, "seu_numero": "P-01", "external_id": "X1"})


def test_flag_devolve_o_comportamento_antigo(monkeypatch):
    """Escotilha para quem descobrir em producao que mandava um campo a mais.
    Nao e para ficar ligada: sai na 3.0.0."""
    monkeypatch.setenv(pycob.FLAG_CAMPO_DESCONHECIDO, "1")
    d = pycob.dados_boleto(BANCO, {**BASE, "cor_favorita": "azul"})
    assert d["codigo_barras"]


def test_account_config_nao_e_contrato_fechado():
    """O blob e por provider, por decisao de projeto: um tenant guarda no mesmo
    lugar as chaves do caminho online e as do offline. Recusar culparia o
    chamador por uma montagem nossa."""
    import datetime

    from app.providers.offline_engine import _to_engine_payload
    from app.schemas import Cobranca, Pagador

    c = Cobranca(valor="10.00", vencimento=datetime.date(2027, 12, 31), seu_numero="1",
                 pagador=Pagador(nome="Teste", documento="12345678909"))
    d = _to_engine_payload(c, {"bank": BANCO, "cooperativa": "3073",
                               "numeroCliente": "99", "carteira": "18"})
    assert d["carteira"] == "18"
    assert "cooperativa" not in d and "numeroCliente" not in d
    pycob.construir_boleto(BANCO, d)  # nao levanta


def test_carne_filtra_o_blob_mesmo_sem_bank_dentro_dele(client):
    """O /carne resolve o banco pelo `provider`/`banco` e nao o repete no blob.

    Sem o banco, o filtro do `account_config` desligava -- e o blob chegava cru
    na fronteira estrita, entao o chamador levava 400 por uma chave do proprio
    blob. E' exatamente a acusacao que o filtro existe para evitar. Achado
    executando o corpo que o Swagger preenche em POST /carne, onde
    `account_config` vem com o `additionalProp1` de exemplo.
    """
    corpo = {
        "tenant_id": "empresa1", "provider": "off", "banco": BANCO,
        "account_config": {"agencia": "3073", "conta_corrente": "12345678",
                           "convenio": "1234567", "carteira": "18",
                           "cedente": "Empresa Teste LTDA",
                           "documento_cedente": "11222333000181",
                           # chave que nao e do titulo: veio do outro lado do blob
                           "additionalProp1": "string"},
        "parcelas": [
            {"valor": "150.00", "vencimento": "2027-12-30", "nosso_numero": str(700 + i),
             "seu_numero": f"P-{i}",
             "pagador": {"nome": "Joao", "documento": "52998224725"}}
            for i in range(2)],
    }
    r = client.post("/carne", json=corpo)
    assert r.status_code == 201, r.text
    assert len(r.json()["cobrancas"]) == 2


def test_blob_com_as_duas_grafias_prefere_a_do_contrato():
    """O mesmo `account_config` carrega os dois lados: no C6 `conta` e a conta
    do REST, na engine e o que o contrato chama de `conta_corrente`."""
    import datetime

    from app.providers.offline_engine import _to_engine_payload
    from app.schemas import Cobranca, Pagador

    c = Cobranca(valor="10.00", vencimento=datetime.date(2027, 12, 31), seu_numero="1",
                 pagador=Pagador(nome="Teste", documento="12345678909"))
    d = _to_engine_payload(c, {"bank": BANCO, "conta": "123",
                               "conta_corrente": "12345678"})
    assert d["conta_corrente"] == "12345678" and "conta" not in d
