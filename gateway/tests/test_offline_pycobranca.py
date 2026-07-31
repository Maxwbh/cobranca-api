# Superfície offline /api/* servida NATIVAMENTE pela engine pyCobranca.
# Substitui a matriz de proxy T1-T10 (conexão com o Ruby descontinuada);
# os contratos verificados são os mesmos (PDF binário, headers X-*, CNAB,
# OFX, erros 400 com validation_errors).
import json

import pytest
from pathlib import Path

from app.core import pycob

# Fixtures resolvidas a partir DESTE arquivo, nao do cwd: o CI roda
# `cd gateway && pytest`, mas rodar da raiz do repo tambem tem de funcionar.
FIXTURES = Path(__file__).resolve().parents[2] / "postman" / "fixtures"

DADOS_BB = {
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


@pytest.fixture
def q():
    return {"bank": "banco_brasil", "data": json.dumps(DADOS_BB)}


def test_health_e_info_da_engine(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "OK"
    info = client.get("/api/info").json()
    assert info["engine"] == "pycobranca"
    assert len(info["supported_banks"]) == 18


def test_metadata_expoe_versao_do_pycobranca(client):
    m = client.get("/api/metadata").json()
    assert m["pycobranca"]["version"]
    assert "pyCobranca" in m["pycobranca"]["repository"]


def test_bancos_offline(client):
    b = client.get("/api/bancos").json()
    assert b["total"] == 18
    assert {"slug", "codigo", "boleto", "cnab"} <= set(b["bancos"][0])


def test_validate_ok_e_erro(client, q):
    assert client.get("/api/boleto/validate", params=q).json()["valid"] is True
    r = client.get("/api/boleto/validate", params={"bank": "banco_brasil", "data": "{}"})
    assert r.status_code == 400
    assert r.json()["valid"] is False and r.json()["validation_errors"]


def test_data_traz_os_tres_campos_de_nosso_numero(client, q):
    d = client.get("/api/boleto/data", params=q).json()
    for campo in ("nosso_numero", "nosso_numero_formatado", "nosso_numero_dv",
                   "codigo_barras", "linha_digitavel"):
        assert campo in d
    assert len(d["codigo_barras"]) == 44


def test_pdf_binario_com_headers_x(client, q):
    r = client.get("/api/boleto", params=q)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    for h in ("X-Nosso-Numero", "X-Nosso-Numero-Formatado", "X-Nosso-Numero-DV",
               "X-Codigo-Barras", "X-Linha-Digitavel"):
        assert h.lower() in {k.lower() for k in r.headers}
    assert "attachment" in r.headers["content-disposition"]


def test_pdf_include_data_devolve_base64(client, q):
    r = client.get("/api/boleto", params={**q, "include_data": "true"})
    assert r.status_code == 200
    body = r.json()
    assert body["content_type"] == "application/pdf"
    assert body["content_base64"].startswith("JVBER")  # %PDF em base64


def test_boleto_invalido_400_com_validation_errors(client):
    r = client.get("/api/boleto", params={"bank": "banco_brasil", "data": "{}"})
    assert r.status_code == 400
    assert "validation_errors" in r.json()


def test_multi_pdf_com_header_de_info(client):
    payload = json.dumps([{**DADOS_BB, "bank": "banco_brasil"},
                           {**DADOS_BB, "bank": "banco_brasil", "nosso_numero": "124"}])
    r = client.post("/api/boleto/multi", files={"data": ("b.json", payload, "application/json")})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert r.headers["x-boletos-count"] == "2"
    assert len(json.loads(r.headers["x-boletos-info"])) == 2


def test_remessa_cnab240(client, tmp_path):
    dados = {
        "empresa_mae": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
        "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
        "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
        "sequencial_remessa": 1,
        "pagamentos": [{"nosso_numero": "123456789", "numero_documento": "DOC-1",
                         "data_vencimento": "2027-12-31", "valor": 1500.0,
                         "sacado": "Joao da Silva", "sacado_documento": "52998224725",
                         "sacado_endereco": "Rua Teste, 100", "sacado_bairro": "Centro",
                         "sacado_cidade": "Sao Paulo", "sacado_uf": "SP",
                         "sacado_cep": "01000000"}],
    }
    r = client.post("/api/remessa?bank=banco_brasil&type=cnab240",
                    files={"data": ("r.json", json.dumps(dados), "application/json")})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    linhas = r.text.splitlines()
    assert linhas and all(len(x) == 240 for x in linhas)


def test_remessa_sem_pagamentos_400(client):
    r = client.post("/api/remessa?bank=banco_brasil&type=cnab240",
                    files={"data": ("r.json", json.dumps({"empresa_mae": "X"}), "application/json")})
    assert r.status_code == 400
    assert "validation_errors" in r.json()


def test_render_boleto_e_carne(client):
    r = client.post("/api/render/boleto", json={"bank": "banco_brasil", "data": DADOS_BB})
    assert r.status_code == 200 and r.json()["pdf_base64"].startswith("JVBER")
    r2 = client.post("/api/render/carne",
                     json={"bank": "banco_brasil", "boletos": [DADOS_BB, DADOS_BB, DADOS_BB]})
    assert r2.status_code == 200 and r2.json()["pdf_base64"].startswith("JVBER")


def test_openapi_offline_e_swagger(client):
    assert client.get("/api/openapi.json").status_code == 200
    r = client.get("/api/docs")
    assert r.status_code == 200 and "pyCobranca" in r.text


def test_rotas_do_gateway_intactas(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "bancos" in client.get("/bancos").json()


def test_openapi_do_gateway_sem_rotas_offline(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(p.startswith("/api/") for p in paths)


# --------------------------------------------------------------- lote resiliente
# Contrato de lote (pyCobrança doc 12): a falha de um item não cancela o lote.
def test_multi_tolera_item_invalido_e_reporta_por_item(client):
    payload = json.dumps([
        {**DADOS_BB, "bank": "banco_brasil", "seu_numero": "OK-1"},
        {"bank": "banco_brasil", "seu_numero": "RUIM"},           # inválido
        {**DADOS_BB, "bank": "banco_brasil", "nosso_numero": "124", "seu_numero": "OK-2"},
    ])
    r = client.post("/api/boleto/multi", files={"data": ("b.json", payload, "application/json")})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert r.headers["x-boletos-count"] == "2"
    assert r.headers["x-boletos-failed"] == "1"
    assert r.headers["x-batch-status"] == "partially_completed"
    erros = json.loads(r.headers["x-boletos-errors"])
    assert erros[0]["item_id"] == "RUIM" and erros[0]["errors"]


def test_multi_include_data_traz_resumo_e_erros(client):
    payload = json.dumps([{**DADOS_BB, "bank": "banco_brasil"}, {"bank": "banco_brasil"}])
    r = client.post("/api/boleto/multi?include_data=true",
                    files={"data": ("b.json", payload, "application/json")})
    body = r.json()
    assert body["status"] == "partially_completed"
    assert body["total"] == 2 and body["completed"] == 1 and body["failed"] == 1
    assert body["erros"][0]["status"] == "failed"


def test_multi_falha_so_quando_nenhum_item_e_valido(client):
    payload = json.dumps([{"bank": "banco_brasil"}, {"bank": "banco_brasil"}])
    r = client.post("/api/boleto/multi", files={"data": ("b.json", payload, "application/json")})
    assert r.status_code == 400
    assert r.json()["validation_errors"]


def test_multi_recusa_lote_acima_do_limite(client, monkeypatch):
    from app.routers import offline

    monkeypatch.setattr(offline, "LOTE_MAX", 2)
    payload = json.dumps([{**DADOS_BB, "bank": "banco_brasil"}] * 3)
    r = client.post("/api/boleto/multi", files={"data": ("b.json", payload, "application/json")})
    assert r.status_code == 413
    assert r.json()["recebidos"] == 3


def test_ofx_extrai_nosso_numero_do_memo(client):
    with open(FIXTURES / "extrato_itau.ofx", "rb") as f:
        r = client.post("/api/ofx/parse", files={"file": ("e.ofx", f.read(), "application/octet-stream")})
    assert r.status_code == 201
    tx = r.json()["transacoes"][0]
    # contrato histórico (v1.5.0) + alias novo
    assert "nosso_numero" in tx
    assert "nosso_numero_extraido" not in tx  # nome da v1 foi removido


def _lote_sicoob(n):
    return [{"bank": "sicoob", "cedente": "Empresa Teste LTDA",
             "documento_cedente": "11222333000181", "agencia": "3073",
             "conta_corrente": "12345678", "convenio": "1234567",
             "carteira": "1", "valor": 10.0 + i, "sacado": f"P{i}",
             "sacado_documento": "52998224725", "nosso_numero": str(i + 1),
             "data_vencimento": "2027-12-30"} for i in range(n)]


def test_header_de_lote_cabe_no_limite_default(client):
    """Com LOTE_MAX=200 o header NUNCA estoura: 200 itens dao ~60 KB, abaixo do
    teto de 63 KB. Ou seja, no default nada e truncado — a guarda e rede de
    seguranca para quem elevar LOTE_MAX_ITENS."""
    r = client.post("/api/boleto/multi",
                    files={"data": ("l.json", json.dumps(_lote_sicoob(5)).encode())})
    assert r.status_code == 200
    assert len(json.loads(r.headers["x-boletos-info"])) == 5
    assert "x-boletos-info-truncado" not in r.headers


def test_header_de_lote_trunca_em_vez_de_estourar(client, monkeypatch):
    """X-Boletos-Info cresce ~300 B por item. Passando de 64 KB, o http.client
    recusa a resposta INTEIRA ("got more than 65536 bytes when reading header
    line") e o cliente perde ate o PDF. Acima do teto, truncar e sinalizar."""
    from app.routers import offline

    monkeypatch.setattr(offline, "HEADER_JSON_MAX", 200)   # força o cenário
    r = client.post("/api/boleto/multi",
                    files={"data": ("l.json", json.dumps(_lote_sicoob(20)).encode())})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"                        # o PDF SAI mesmo assim
    assert r.headers["x-boletos-count"] == "20"            # contadores continuam
    assert r.headers["x-boletos-info"] == "[]"
    assert r.headers["x-boletos-info-truncado"] == "true"
    assert "include_data=true" in r.headers["x-boletos-detalhe"]
    assert len(r.headers["x-boletos-info"].encode("latin-1")) <= 200


def test_include_data_entrega_o_detalhe_que_o_header_truncou(client, monkeypatch):
    """A alternativa apontada pelo header truncado tem de funcionar de fato."""
    from app.routers import offline

    monkeypatch.setattr(offline, "HEADER_JSON_MAX", 200)
    r = client.post("/api/boleto/multi?include_data=true",
                    files={"data": ("l.json", json.dumps(_lote_sicoob(20)).encode())})
    assert r.status_code == 200
    assert len(r.json()["boletos"]) == 20                  # detalhe completo no CORPO


def test_retorno_cnab400_extrai_os_campos(client):
    """A fixture era uma folha em BRANCO e o teste so olhava status 200 — passava
    provando nada. Agora ela tem um titulo liquidado real (ocorrencia 06)."""
    with open(FIXTURES / "retorno_cnab400_bb.ret", "rb") as f:
        r = client.post("/api/retorno?bank=banco_brasil&type=cnab400",
                        files={"data": ("ret.ret", f.read())})
    assert r.status_code == 200, r.text
    itens = r.json()
    assert len(itens) == 1
    it = itens[0]
    assert "12345678901" in it["nosso_numero"]
    assert it["codigo_ocorrencia"] == "06"
    assert it["valor_titulo"] == 1500.0
    assert it["valor_pago"] == 1500.0
    assert it["motivo_ocorrencia"]          # a engine descreve a ocorrência


def _remessa_base(**extra_pag):
    pag = {"nosso_numero": "123456789", "numero_documento": "DOC1",
           "data_vencimento": "2027-12-31", "valor": 1500.0,
           "sacado": "Joao", "sacado_documento": "52998224725",
           "sacado_endereco": "R1", "sacado_bairro": "C", "sacado_cidade": "SP",
           "sacado_uf": "SP", "sacado_cep": "01000000", **extra_pag}
    return {"empresa_mae": "E", "documento_cedente": "11222333000181",
            "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
            "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
            "sequencial_remessa": 1, "pagamentos": [pag]}


def _gera(client, payload):
    return client.post("/api/remessa?bank=banco_brasil&type=cnab400",
                       files={"data": ("r.json", json.dumps(payload).encode())})


def test_encargos_entram_no_arquivo_com_os_nomes_da_engine(client):
    """Encargo é um TRIO código/tipo -> valor -> data (doc 06-cnab.md).
    No CNAB 400 a mora é VALOR/dia (`valor_mora`); no 240 é percentual."""
    sem = _gera(client, _remessa_base())
    com = _gera(client, _remessa_base(percentual_multa=2.0, valor_mora=1.0,
                                       cod_desconto="1", valor_desconto=50.0,
                                       data_desconto="2027-12-20"))
    assert sem.status_code == com.status_code == 200
    assert com.text != sem.text


def test_nome_generico_de_encargo_e_recusado_com_dica(client):
    """`multa`/`juros`/`desconto` NÃO viram alias: no CNAB 400 `percentual_mora`
    sequer entra no arquivo, então um alias 'amigável' recriaria o descarte
    silencioso. O erro ensina o trio correto em vez de adivinhar."""
    for campo, dica in (("multa", "codigo_multa"), ("juros", "tipo_mora"),
                        ("desconto", "cod_desconto")):
        r = _gera(client, _remessa_base(**{campo: 2.0}))
        assert r.status_code == 400, (campo, r.text)
        assert campo in r.text and dica in r.text


def test_mora_do_cnab400_e_valor_nao_percentual(client):
    """No 400 a mora é R$/dia. `percentual_mora` não tem posição no layout:
    antes era aceito e sumia calado; agora é recusado com a alternativa."""
    sem = _gera(client, _remessa_base())
    valor = _gera(client, _remessa_base(valor_mora=1.0))
    assert sem.status_code == valor.status_code == 200
    assert valor.text != sem.text                      # valor_mora entra

    percentual = _gera(client, _remessa_base(percentual_mora=1.0))
    assert percentual.status_code == 400               # recusado, não ignorado
    assert "valor_mora" in percentual.text             # e diz o que usar


def test_numero_documento_chega_ao_arquivo(client):
    """`numero_documento` não é o nome da engine (`numero`) e vinha sendo
    descartado — inclusive na fixture do próprio repositório."""
    # largura maxima 10: valor maior estoura o registro (erro do layout)
    com = _gera(client, _remessa_base(numero_documento="DOC2026999"))
    sem = _gera(client, {**_remessa_base(),
                         "pagamentos": [{k: v for k, v in _remessa_base()["pagamentos"][0].items()
                                          if k != "numero_documento"}]})
    assert com.status_code == 200 and sem.status_code == 200
    assert com.text != sem.text

# ---------------------------------------------------------------- encargos
# Cada encargo é um TRIO código/tipo -> valor -> data, com suporte que varia por
# banco e layout (docs 06-cnab.md da engine). Os testes abaixo conferem o VALOR
# gravado no arquivo, não apenas "mudou/não mudou".

def _gera_remessa(banco, tipo, **encargos):
    from app.core import pycob
    base = {"empresa_mae": "E", "documento_cedente": "11222333000181",
            "agencia": "3073", "conta_corrente": "12345678", "digito_conta": "0",
            "convenio": "1234567", "carteira": "18", "variacao_carteira": "017",
            "sequencial_remessa": 1}
    pag = {"nosso_numero": "123456789", "data_vencimento": "2027-12-31",
           "valor": 1500.0, "sacado": "Joao", "sacado_documento": "52998224725",
           "sacado_endereco": "R1", "sacado_bairro": "C", "sacado_cidade": "SP",
           "sacado_uf": "SP", "sacado_cep": "01000000", **encargos}
    base["pagamentos"] = [pag]
    return pycob.gerar_remessa(banco, tipo, base)


def _fim_do_campo(banco, tipo, campo):
    """Última posição que muda entre dois valores — o campo é alinhado à direita."""
    a = _gera_remessa(banco, tipo, **{campo: 11.11})
    b = _gera_remessa(banco, tipo, **{campo: 22.22})
    difs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return difs[-1] if difs else None


@pytest.mark.parametrize("campo,valor,largura", [
    ("valor_mora", 1.50, 13),
    ("valor_desconto", 50.00, 13),
    ("valor_iof", 3.75, 13),
    ("valor_abatimento", 25.00, 13),
])
def test_encargo_grava_o_valor_correto_no_arquivo(campo, valor, largura):
    """Decodifica o campo de volta: `%.2f` sem ponto, zeros à esquerda."""
    from pycobranca.cnab.formatacao import format_valor
    fim = _fim_do_campo("banco_brasil", "cnab400", campo)
    assert fim is not None, f"{campo} sem posição no layout"
    arquivo = _gera_remessa("banco_brasil", "cnab400", **{campo: valor})
    bruto = arquivo[fim - largura + 1:fim + 1]
    assert bruto == format_valor(valor, largura)
    assert int(bruto) / 100 == valor          # decodifica no valor enviado


def test_percentual_multa_grava_o_valor_correto():
    """No 400 a multa é percentual; o BB não tem essa posição (vai por
    instrução), então o teste usa o Sicoob, que tem."""
    from pycobranca.cnab.formatacao import format_valor
    fim = _fim_do_campo("sicoob", "cnab400", "percentual_multa")
    assert fim is not None
    arquivo = _gera_remessa("sicoob", "cnab400", percentual_multa=2.00)
    largura = 4
    bruto = arquivo[fim - largura + 1:fim + 1]
    assert bruto == format_valor(2.00, largura) == "0200"
    assert int(bruto) / 100 == 2.00


def test_percentual_mora_so_vale_com_tipo_mora_2():
    """Regra do TRIO: o valor sozinho não entra. Sem `tipo_mora='2'` o
    percentual de mora é ignorado — silenciosamente, pelo layout."""
    base = _gera_remessa("banco_brasil", "cnab240")
    assert _gera_remessa("banco_brasil", "cnab240", percentual_mora=1.5) == base
    assert _gera_remessa("banco_brasil", "cnab240",
                         tipo_mora="2", percentual_mora=1.5) != base


def test_multa_no_bb400_nao_tem_posicao():
    """Documentado na engine: BB e Itaú no CNAB 400 mandam multa por INSTRUÇÃO,
    não como percentual posicional. Fixa a expectativa para não interpretarmos
    isso como bug mais tarde."""
    base = _gera_remessa("banco_brasil", "cnab400")
    assert _gera_remessa("banco_brasil", "cnab400", percentual_multa=2.0) == base


def test_segundo_e_terceiro_desconto_so_no_cnab240():
    """400 tem só o 1º desconto; 240 tem os três."""
    base240 = _gera_remessa("banco_brasil", "cnab240")
    assert _gera_remessa("banco_brasil", "cnab240", valor_segundo_desconto=10.0) != base240
    assert _gera_remessa("banco_brasil", "cnab240", valor_terceiro_desconto=5.0) != base240
    base400 = _gera_remessa("banco_brasil", "cnab400")
    assert _gera_remessa("banco_brasil", "cnab400", valor_segundo_desconto=10.0) == base400

# --- unidade do encargo (% ou R$) ------------------------------------------
# No CNAB 240 o codigo/tipo E gravado: o banco sabe a unidade pelo arquivo.
# No CNAB 400 ele NAO e gravado — a unidade e fixa pelo layout (multa sempre %,
# mora sempre R$/dia). Mandar a combinacao errada faria o banco cobrar outra
# coisa do pagador, entao a API recusa.

@pytest.mark.parametrize("campo,v1,v2,fixos", [
    ("codigo_multa", "1", "2", {"percentual_multa": 2.0}),
    ("tipo_mora", "1", "2", {"valor_mora": 1.0, "percentual_mora": 1.0}),
    # 1.0.1: desconto com codigo exige valor E data (validacao mais estrita)
    ("cod_desconto", "1", "2", {"valor_desconto": 50.0, "data_desconto": "2027-12-20"}),
])
def test_cnab240_grava_o_codigo_da_unidade(campo, v1, v2, fixos):
    """É o código que diz ao banco se o número é % ou R$."""
    a = _gera_remessa("banco_brasil", "cnab240", **{campo: v1}, **fixos)
    b = _gera_remessa("banco_brasil", "cnab240", **{campo: v2}, **fixos)
    assert a != b, f"{campo} não entra no arquivo — a unidade ficaria indefinida"


@pytest.mark.parametrize("encargo,esperado", [
    ({"codigo_multa": "1", "percentual_multa": 50.0}, "codigo_multa='1'"),
    ({"tipo_mora": "2", "percentual_mora": 1.0}, "tipo_mora='2'"),
    ({"percentual_mora": 1.0}, "percentual_mora"),
])
def test_cnab400_recusa_unidade_que_o_layout_nao_expressa(client, encargo, esperado):
    """R$ 50 de multa lido como 50% cobraria R$ 750 num título de R$ 1.500."""
    r = _gera(client, _remessa_base(**encargo))
    assert r.status_code == 400, r.text
    assert esperado in r.text


def test_cnab400_aceita_a_combinacao_correta(client):
    r = _gera(client, _remessa_base(codigo_multa="2", percentual_multa=2.0,
                                     tipo_mora="1", valor_mora=1.5))
    assert r.status_code == 200, r.text


def test_iof_e_abatimento_gravam_o_valor(client):
    """IOF e abatimento são valores em R$ — sem código de unidade."""
    from pycobranca.cnab.formatacao import format_valor
    for campo, valor in (("valor_iof", 3.75), ("valor_abatimento", 25.00)):
        fim = _fim_do_campo("banco_brasil", "cnab400", campo)
        assert fim is not None, campo
        arq = _gera_remessa("banco_brasil", "cnab400", **{campo: valor})
        bruto = arq[fim - 12:fim + 1]
        assert bruto == format_valor(valor, 13)
        assert int(bruto) / 100 == valor


# O parametro `template` existia na rota, era aceito sem erro e nunca chegava
# na engine: `pdf_boleto` chamava render_boleto_pdf sem `modelo`. Resultado —
# `classico` saia pixel a pixel igual a `moderno`, e o modelo classico da
# engine era inalcancavel pela API. Detectado comparando os PDFs do servico em
# producao: PNG renderizado com sha256 identico para os dois templates.
#
# O teste compara TAMANHO, nao bytes: o PDF carrega metadados variaveis, entao
# duas chamadas com o mesmo modelo diferem nos bytes. O tamanho e estavel por
# modelo (moderno ~5427, classico ~5013). Comparar pixels seria mais forte,
# mas exigiria um renderizador que nao esta nas dependencias de teste.
def _pdf(client, template=None):
    import json as _json
    q = {"bank": "banco_brasil", "type": "pdf", "data": _json.dumps(DADOS_BB)}
    if template:
        q["template"] = template
    r = client.get("/api/boleto", params=q)
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    return r.content


def test_mesmo_template_gera_pdf_do_mesmo_tamanho(client):
    # Ancora do teste seguinte: sem isto, uma diferenca de tamanho entre
    # modelos poderia ser so ruido de geracao.
    assert len(_pdf(client, "moderno")) == len(_pdf(client, "moderno"))


def test_template_classico_gera_pdf_diferente_do_moderno(client):
    assert len(_pdf(client, "classico")) != len(_pdf(client, "moderno")), \
        "template ignorado: classico saiu igual a moderno"


def test_template_default_continua_moderno(client):
    assert len(_pdf(client)) == len(_pdf(client, "moderno"))


def test_template_invalido_responde_400(client):
    import json as _json
    r = client.get("/api/boleto", params={
        "bank": "banco_brasil", "type": "pdf", "template": "inexistente",
        "data": _json.dumps(DADOS_BB)})
    assert r.status_code == 400, r.text
    assert "template" in r.text


# `instrucoes` chegava crua na engine, que espera LISTA de linhas. Com string,
# ela iterava os CARACTERES: o boleto saia com "A", "p", "o", "s"... um por
# linha, ate estourar a caixa -- sem erro e com o texto perdido.
#
# A asercao e sobre a NORMALIZACAO e sobre os limites, nao sobre o desenho do
# PDF: inspecionar o conteudo renderizado exigiria um leitor de PDF, que nao
# tem por que virar dependencia do produto.
INSTRUCOES_6 = (
    "Apos o vencimento, cobrar multa de 2% e juros de mora de 1% ao mes, pro rata die.\n"
    "Conceder desconto de R$ 50,00 para pagamento efetuado ate 5 dias antes do vencimento.\n"
    "Nao receber apos 30 dias corridos do vencimento; decorrido o prazo, protestar o titulo.\n"
    "Havendo divergencia com o contrato n. CTR-2026-0417, prevalece o instrumento contratual.\n"
    "Duvidas: setor financeiro, telefone (11) 3679-2380, dias uteis das 9h as 18h.\n"
    "Pagavel em qualquer instituicao financeira do pais ate a data de vencimento."
)


def test_instrucoes_string_vira_lista_de_linhas_e_nao_de_caracteres():
    linhas = pycob._linhas(INSTRUCOES_6, "instrucoes")
    assert linhas == INSTRUCOES_6.splitlines()
    assert len(linhas) == 6, "string iterada caractere a caractere"


def test_instrucoes_chegam_sem_reformatacao():
    # Validar, nunca reescrever: cada linha sai igual ao que entrou.
    for original, normalizada in zip(INSTRUCOES_6.splitlines(),
                                     pycob._linhas(INSTRUCOES_6, "instrucoes")):
        assert original == normalizada


def test_instrucoes_string_e_lista_produzem_o_mesmo_pdf():
    a = pycob.pdf_boleto("banco_brasil", {**DADOS_BB, "instrucoes": INSTRUCOES_6})
    b = pycob.pdf_boleto("banco_brasil",
                         {**DADOS_BB, "instrucoes": INSTRUCOES_6.splitlines()})
    assert len(a) == len(b)


def test_linha_longa_e_recusada_e_nao_reformatada():
    # 178 caracteres numa linha so: atravessava a coluna de Desconto/Mora/Valor
    # cobrado, deixando as duas ilegiveis. O gateway NAO quebra a linha por
    # conta propria -- reescrever texto de cobranca e do cliente.
    longa = ("Apos o vencimento, cobrar multa de 2% sobre o valor do titulo e juros de mora"
             " de 1% ao mes, calculados pro rata die a partir do primeiro dia util.")
    assert len(longa) > pycob.LARGURA_INSTRUCAO
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.pdf_boleto("banco_brasil", {**DADOS_BB, "instrucoes": longa})
    assert f"linha 1 com {len(longa)}" in exc.value.erros[0]


def test_instrucoes_que_nao_cabem_sao_recusadas_em_vez_de_sumir():
    # A engine simplesmente NAO desenha a partir da oitava linha. Em documento
    # de cobranca, perder clausula em silencio e pior que recusar.
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.pdf_boleto("banco_brasil",
                         {**DADOS_BB, "instrucoes": "\n".join(["ok"] * 20)})
    assert "máximo 7" in exc.value.erros[0]


def test_instrucoes_no_limite_continuam_aceitas():
    no_limite = "\n".join(f"Linha {i + 1} de instrucao do beneficiario"
                          for i in range(pycob.MAX_LINHAS_INSTRUCAO))
    pdf = pycob.pdf_boleto("banco_brasil", {**DADOS_BB, "instrucoes": no_limite})
    assert pdf[:4] == b"%PDF"


def test_render_boleto_aceita_template(client):
    # O irmao GET /api/boleto aceitava; este nem declarava o parametro, entao
    # quem migrava de um para o outro perdia a escolha do modelo em silencio.
    import base64 as _b64
    def _tam(tpl):
        corpo = {"bank": "banco_brasil", "data": DADOS_BB}
        if tpl:
            corpo["template"] = tpl
        r = client.post("/api/render/boleto", json=corpo)
        assert r.status_code == 200, r.text
        return len(_b64.b64decode(r.json()["pdf_base64"]))
    assert _tam("classico") != _tam("moderno")
    assert _tam(None) == _tam("moderno")
