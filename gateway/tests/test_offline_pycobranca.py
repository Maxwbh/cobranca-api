# Superfície offline /api/* servida NATIVAMENTE pela engine pyCobranca.
# Substitui a matriz de proxy T1-T10 (conexão com o Ruby descontinuada);
# os contratos verificados são os mesmos (PDF binário, headers X-*, CNAB,
# OFX, erros 400 com validation_errors).
import inspect
import json

import pytest
from pathlib import Path

from app.core import pycob

# Fixtures resolvidas a partir DESTE arquivo, nao do cwd: o CI roda
# `cd gateway && pytest`, mas rodar da raiz do repo tambem tem de funcionar.
FIXTURES = Path(__file__).resolve().parents[2] / "postman" / "fixtures"


def test_nenhum_teste_abre_arquivo_pelo_cwd():
    """A regra acima estava escrita e nao era cobrada por nada.

    Um caso abria `postman/fixtures/...` cru. Da raiz do repo ele passava; no
    CI, que roda `cd gateway && pytest`, o mesmo caminho aponta para
    `gateway/postman/` e o teste morria com FileNotFoundError. Verde na maquina
    de quem escreveu, vermelho no build — e o diagnostico custa mais caro que o
    defeito, porque a suite inteira parece boa.

    O guarda le o TEXTO dos arquivos de teste: e a unica forma de pegar o caso
    que ainda nao foi escrito. Caminho absoluto, `tmp_path` e o que sai de
    `__file__` continuam livres.
    """
    import re

    suspeitos = []
    for arquivo in sorted(Path(__file__).parent.glob("test_*.py")):
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if "__file__" in linha or "tmp_path" in linha:
                continue
            for m in re.finditer(r"""(?:open|Path)\(\s*['"]([^'"/][^'"]*)['"]""", linha):
                alvo = m.group(1)
                # So interessa o que parece caminho de arquivo do repo.
                if "/" in alvo and not alvo.startswith(("http", "{")):
                    suspeitos.append(f"{arquivo.name}:{n}: {alvo!r}")
    assert not suspeitos, (
        "caminho relativo ao cwd em teste — passa da raiz e quebra no CI, que "
        "roda de `gateway/`. Ancore em `__file__` (veja FIXTURES aqui):\n  "
        + "\n  ".join(suspeitos))

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
    # Contra o registro da engine, não contra um número escrito à mão: o total
    # mudou de 18 para 19 quando o Inter entrou, e um literal aqui só teria
    # atrasado a descoberta.
    assert sorted(info["supported_banks"]) == pycob.bancos_suportados()
    assert "inter" in info["supported_banks"]


def test_metadata_expoe_versao_do_pycobranca(client):
    m = client.get("/api/metadata").json()
    assert m["pycobranca"]["version"]
    assert "pyCobranca" in m["pycobranca"]["repository"]


def test_bancos_offline(client):
    b = client.get("/api/bancos").json()
    assert b["total"] == len(pycob.bancos_suportados())
    assert {"slug", "codigo", "boleto", "cnab"} <= set(b["bancos"][0])


def test_o_inter_e_o_19o_banco_offline(client):
    """A engine não tinha o layout 077 e o caminho `off` do Inter era recusado.

    A 1.1.1 implementou boleto, remessa e retorno CNAB 400 do Inter — só a
    carteira 110, porque na 112 quem numera é o banco e o nosso número só existe
    no retorno.
    """
    b = client.get("/api/bancos").json()
    inter = [x for x in b["bancos"] if x["slug"] == "inter"]
    assert inter, "Inter ausente do catálogo offline"
    assert inter[0]["codigo"] == "077"


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
    # `codigo_multa='1'` (valor fixo) saiu daqui: a 1.1.1 passou a exigir
    # `valor_multa` junto, e esse campo não tem posição em layout 240 nenhum
    # (medido A/B) — a combinação virou irrepresentável, não só inconveniente.
    # `0` (isento) contra `2` (percentual) prova a mesma coisa: o código É
    # gravado, e é dele que o banco tira a unidade.
    ("codigo_multa", "0", "2", {"percentual_multa": 2.0}),
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
    "Apos o vencimento, multa de 2% e juros de 1% ao mes.\n"
    "Desconto de R$ 50,00 ate 5 dias antes do vencimento.\n"
    "Nao receber apos 30 dias; decorrido o prazo, protestar.\n"
    "Prevalece o contrato n. CTR-2026-0417 em caso de duvida.\n"
    "Duvidas: financeiro, (11) 3679-2380, dias uteis 9h-18h.\n"
    "Pagavel em qualquer banco ate a data de vencimento."
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
    # A engine simplesmente NAO desenha da ultima linha em diante. Em documento
    # de cobranca, perder clausula em silencio e pior que recusar.
    cabem = pycob.linhas_de_instrucao("moderno", False)
    with pytest.raises(pycob.DadosInvalidos) as exc:
        pycob.pdf_boleto("banco_brasil",
                         {**DADOS_BB, "instrucoes": "\n".join(["ok"] * 20)})
    assert f"máximo {cabem} em o modelo 'moderno'" in exc.value.erros[0]


def test_instrucoes_no_limite_continuam_aceitas():
    no_limite = "\n".join(f"Linha {i + 1} de instrucao"
                          for i in range(pycob.linhas_de_instrucao("moderno", False)))
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


def test_multi_recusa_boleto_duplicado(client):
    # Mesmo defeito do carne: o `pdf_multi` calculava o item_id e o handler
    # descartava, entao o lote saia com a duplicata impressa.
    import io as _io
    import json as _json
    lote = [{**DADOS_BB, "bank": "banco_brasil", "nosso_numero": str(500 + i),
             "numero_documento": f"L-{i:02d}"} for i in range(4)]
    lote[3] = dict(lote[1])
    r = client.post("/api/boleto/multi",
                    files={"data": ("lote.json", _io.BytesIO(_json.dumps(lote).encode()),
                                    "application/json")})
    assert r.status_code == 422, r.text
    assert r.json()["duplicados"] == [{"item_id": "L-01", "indices": [1, 3]}]


def test_multi_sem_duplicata_continua_aceito(client):
    import io as _io
    import json as _json
    lote = [{**DADOS_BB, "bank": "banco_brasil", "nosso_numero": str(600 + i),
             "numero_documento": f"M-{i:02d}"} for i in range(4)]
    r = client.post("/api/boleto/multi",
                    files={"data": ("lote.json", _io.BytesIO(_json.dumps(lote).encode()),
                                    "application/json")})
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


# Campo que só falta na FORMATAÇÃO: 400 com a mensagem do banco, nunca 500.
#
# `boleto.validar()` aprovava o Sicredi e a exceção estourava depois, ao montar
# o nosso número formatado — fora do handler. O consumidor recebia
# `500 Internal Server Error` por um campo que faltava no payload DELE, e a
# mensagem da engine, que dizia qual era, ficava só no log do servidor.
DADOS_SICREDI = {
    "cedente": "Empresa Exemplo", "documento_cedente": "11222333000181",
    "sacado": "Fulano", "sacado_documento": "11144477735",
    "valor": 1500.0, "data_vencimento": "2026/12/31",
    "agencia": "1234", "conta_corrente": "1234", "nosso_numero": "123",
    "carteira": "1", "convenio": "1234",
}


@pytest.mark.parametrize("rota,params", [
    ("/api/boleto/data", {}),
    ("/api/boleto", {"type": "pdf"}),
    ("/api/boleto/nosso_numero", {}),
])
def test_boleto_invalido_na_formatacao_vira_400(client, rota, params):
    """O que esta prova protege é o CÓDIGO, não a frase: falha de FORMATAÇÃO —
    descoberta depois de `validar()` dizer que estava tudo certo — não pode
    escapar como 500. O Sicredi é o caso limite porque o ano do nosso número sai
    de `data_documento`.
    """
    import json as _json
    dados = {**DADOS_SICREDI, "byte_idt": "2"}   # senão para antes, em `validar()`
    r = client.get(rota, params={"bank": "sicredi",
                                 "data": _json.dumps(dados), **params})
    assert r.status_code == 400, f"{rota} devolveu {r.status_code}: {r.text[:200]}"
    erros = r.json()["validation_errors"]
    assert any("data_documento" in e for e in erros), erros


def test_mensagem_do_banco_chega_ate_o_consumidor(client):
    """A mensagem da engine chega inteira ao chamador, em vez de virar 500 com o
    motivo no log do servidor.

    A 1.1.1 passou a pegar `byte_idt` já em `validar()` (o campo ganhou regra de
    tamanho) e a nomeá-lo pelo rótulo amigável — *"byte de identificação"* — e
    não mais pelo atributo. Para quem lê um traceback é melhor; para quem manda
    JSON é um passo a mais, porque a chave do payload é `byte_idt`. O Swagger
    faz a ponte, e a lista de campos aceitos vai no erro de campo desconhecido.
    """
    import json as _json
    r = client.get("/api/boleto/data", params={
        "bank": "sicredi", "data": _json.dumps(DADOS_SICREDI)})
    assert r.status_code == 400, r.text
    erros = r.json()["validation_errors"]
    assert any("byte de identificação" in e for e in erros), erros


# Débito não pode ser contado como crédito.
#
# A engine normaliza `valor` para POSITIVO e guarda a direção em `tipo`
# (o TRNTYPE do OFX). O roteador deduzia do sinal — que nunca é negativo depois
# da normalização —, então TODA transação saía como `credito` e `total_debitos`
# era eternamente 0. Num extrato de conciliação, o dinheiro que saiu entrava na
# soma do que entrou.
def test_ofx_separa_credito_de_debito(client):
    with open(FIXTURES / "extrato_sicoob.ofx", "rb") as f:
        r = client.post("/api/ofx/parse", files={"file": ("e.ofx", f.read(), "application/octet-stream")})
    assert r.status_code == 201, r.text
    corpo = r.json()
    tipos = [t["tipo"] for t in corpo["transacoes"]]
    # o arquivo tem 2 CREDIT e 2 DEBIT
    assert tipos.count("credito") == 2 and tipos.count("debito") == 2, tipos
    assert corpo["resumo"]["total_creditos"] == 3750.0
    assert corpo["resumo"]["total_debitos"] == 530.5
    # valor sempre positivo: a direção está em `tipo`, não no sinal
    assert all(t["valor"] > 0 for t in corpo["transacoes"])


def test_ofx_somente_creditos_filtra_de_verdade(client):
    with open(FIXTURES / "extrato_sicoob.ofx", "rb") as f:
        bruto = f.read()
    r = client.post("/api/ofx/parse", files={"file": ("e.ofx", bruto, "application/octet-stream")},
                    data={"somente_creditos": "true"})
    corpo = r.json()
    assert corpo["resumo"]["quantidade"] == 2
    assert {t["tipo"] for t in corpo["transacoes"]} == {"credito"}
    assert corpo["resumo"]["total_debitos"] == 0


# JSON válido de forma errada era 500.
#
# `"texto"`, `123` e `{"boletos": [...]}` passam pelo `json.loads` — só quebram
# lá dentro, quando a engine chama `.get()` no que achava ser um objeto. O
# consumidor levava "Internal Server Error" por ter errado a FORMA do corpo,
# que é exatamente o tipo de erro que a API tem de saber nomear. O parse já
# respondia 400; a forma não era conferida em lugar nenhum.
@pytest.mark.parametrize("rota", [
    "/api/boleto/validate", "/api/boleto/data", "/api/boleto/nosso_numero", "/api/boleto",
])
@pytest.mark.parametrize("data,tipo", [('"x"', "texto"), ("123", "número"), ("[]", "lista")])
def test_data_que_nao_e_objeto_vira_400(client, rota, data, tipo):
    r = client.get(rota, params={"bank": "banco_brasil", "type": "pdf", "data": data})
    assert r.status_code == 400, f"{rota} devolveu {r.status_code}: {r.text[:200]}"
    erros = r.json()["validation_errors"]
    assert any(f"`data` deve ser um objeto JSON — recebi {tipo}" in e for e in erros), erros


@pytest.mark.parametrize("corpo,esperado", [
    (b'{"bank": "banco_brasil", "boletos": []}', "`data` deve ser uma lista JSON — recebi objeto"),
    (b'"texto"', "`data` deve ser uma lista JSON — recebi texto"),
    (b'123', "`data` deve ser uma lista JSON — recebi número"),
    (b'["a"]', "`data[0]` deve ser um objeto JSON — recebi texto"),
])
def test_multi_com_lote_de_forma_errada_vira_400(client, corpo, esperado):
    r = client.post("/api/boleto/multi",
                    files={"data": ("lote.json", corpo, "application/json")})
    assert r.status_code == 400, r.text
    assert esperado in r.json()["validation_errors"], r.json()


def test_remessa_com_data_que_nao_e_objeto_vira_400(client):
    r = client.post("/api/remessa", params={"bank": "banco_brasil", "type": "cnab400"},
                    files={"data": ("r.json", b"[]", "application/json")})
    assert r.status_code == 400, r.text
    assert "`data` deve ser um objeto JSON — recebi lista" in r.json()["validation_errors"]


@pytest.mark.parametrize("rota,corpo,esperado", [
    ("/api/render/boleto", {"bank": "banco_brasil", "data": "x"},
     "`data` deve ser um objeto JSON — recebi texto"),
    ("/api/render/carne", {"bank": "banco_brasil", "boletos": "x"},
     "`boletos` deve ser uma lista JSON — recebi texto"),
    ("/api/render/carne", {"bank": "banco_brasil", "boletos": ["a"]},
     "`boletos[0]` deve ser um objeto JSON — recebi texto"),
    ("/api/render/fatura", {"bank": "banco_brasil", "data": DADOS_BB, "itens": "x"},
     "`itens` deve ser uma lista JSON — recebi texto"),
    ("/api/render/fatura", {"bank": "banco_brasil", "data": DADOS_BB, "fatura": "x"},
     "`fatura` deve ser um objeto JSON — recebi texto"),
    ("/api/render/remessa", {"bank": "banco_brasil", "type": "cnab400", "data": "x"},
     "`data` deve ser um objeto JSON — recebi texto"),
])
def test_render_com_campo_de_forma_errada_vira_400(client, rota, corpo, esperado):
    r = client.post(rota, json=corpo)
    assert r.status_code == 400, f"{rota} devolveu {r.status_code}: {r.text[:200]}"
    assert esperado in r.json()["validation_errors"], r.json()


# Template inválido no lote saía 200 com o modelo errado.
#
# `pdf_multi` cai em `moderno` quando não reconhece o modelo — silêncio pior
# que erro, porque o irmão `GET /api/boleto` responde 400 para o mesmo valor.
# `template=modrno` gerava o lote inteiro no modelo default sem avisar ninguém.
def test_multi_recusa_template_invalido(client):
    lote = json.dumps([{**DADOS_BB, "bank": "banco_brasil"}]).encode()
    r = client.post("/api/boleto/multi", params={"template": "modrno"},
                    files={"data": ("lote.json", lote, "application/json")})
    assert r.status_code == 400, r.text
    assert any("template 'modrno' inválido" in e for e in r.json()["validation_errors"])


@pytest.mark.parametrize("template", ["moderno", "classico", "carne"])
def test_multi_aceita_os_tres_modelos(client, template):
    lote = json.dumps([{**DADOS_BB, "bank": "banco_brasil"}]).encode()
    r = client.post("/api/boleto/multi", params={"template": template},
                    files={"data": ("lote.json", lote, "application/json")})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"


# `validation_errors` é lista plana em TODA a superfície — este era o único
# ponto que devolvia objeto-por-campo (`{"type": ["use 'pdf'"]}`), então quem
# iterava a lista esperando mensagens recebia a string "type".
@pytest.mark.parametrize("chamada", [
    lambda c: c.get("/api/boleto", params={"bank": "banco_brasil", "type": "png",
                                           "data": json.dumps(DADOS_BB)}),
    lambda c: c.post("/api/boleto/multi", params={"type": "png"},
                     files={"data": ("lote.json", b"[]", "application/json")}),
])
def test_formato_descontinuado_devolve_lista_plana(client, chamada):
    r = chamada(client)
    assert r.status_code == 400, r.text
    erros = r.json()["validation_errors"]
    assert isinstance(erros, list) and all(isinstance(e, str) for e in erros), erros
    assert any("pdf" in e for e in erros), erros


# `emv` e `pix_label` eram aceitos e DESCARTADOS em silêncio.
#
# Vinham da era Ruby, onde o QR chegava pronto no payload. Hoje quem desenha o
# Bolepix é `chave_pix`: a engine monta o EMV e o QR. Mandar `emv` devolvia 200
# com um boleto SEM QR — e nada na resposta indicava a falta, então o boleto
# chegava ao pagador sem como pagar por Pix. O exemplo `generate_test_boletos.py`
# gerava seis boletos "pix" assim.
@pytest.mark.parametrize("campo", ["emv", "pix_label"])
def test_campo_de_pix_sem_consumidor_vira_400(client, campo):
    dados = {**DADOS_BB, campo: "valor qualquer"}
    r = client.get("/api/boleto", params={"bank": "banco_brasil", "type": "pdf",
                                          "data": json.dumps(dados)})
    assert r.status_code == 400, r.text
    erros = r.json()["validation_errors"]
    assert any(f"`{campo}` não gera QR Pix" in e for e in erros), erros
    assert any("chave_pix" in e for e in erros), erros


def test_campo_vazio_nao_e_recusado(client):
    """Só o valor preenchido acusa: `emv: ""` é ausência, não intenção."""
    r = client.get("/api/boleto", params={"bank": "banco_brasil", "type": "pdf",
                                          "data": json.dumps({**DADOS_BB, "emv": ""})})
    assert r.status_code == 200, r.text


def test_chave_pix_desenha_o_qr(client):
    """O caminho que funciona, medido pelo PDF — não pelo status."""
    sem = client.get("/api/boleto", params={"bank": "banco_brasil", "type": "pdf",
                                            "data": json.dumps(DADOS_BB)})
    com = client.get("/api/boleto", params={
        "bank": "banco_brasil", "type": "pdf",
        "data": json.dumps({**DADOS_BB, "chave_pix": "11222333000181",
                            "tipo_chave_pix": "cnpj"})})
    assert sem.status_code == com.status_code == 200
    assert len(com.content) > len(sem.content), "PDF com Pix não ficou maior — cadê o QR?"


def test_banco_sem_pix_recusa_a_chave(client):
    """Silêncio seria pior: o boleto sairia sem o QR que o emissor pediu."""
    r = client.get("/api/boleto", params={
        "bank": "banrisul", "type": "pdf",
        "data": json.dumps({**DADOS_BB, "agencia": "1234", "conta_corrente": "12345",
                            "carteira": "1", "chave_pix": "11222333000181",
                            "tipo_chave_pix": "cnpj"})})
    assert r.status_code == 400, r.text
    assert any("não suporta PIX" in e for e in r.json()["validation_errors"])


# ---------------------------------------------------------------- spec offline
#
# `/api/openapi.json`, `/api/openapi.yaml` e `/api/docs` servem o mesmo arquivo.
# Ele era lido e parseado A CADA chamada: ~150 ms por request de 75 KB de YAML,
# trinta vezes o resto da superfície — e é o que o Swagger da própria API busca
# ao abrir.
def test_json_e_yaml_descrevem_a_mesma_spec(client):
    import yaml as _yaml
    from app.routers import offline as _off
    do_json = client.get("/api/openapi.json").json()
    do_yaml = _yaml.safe_load(client.get("/api/openapi.yaml").content)
    assert do_json == do_yaml
    assert do_json == _yaml.safe_load(_off._SPEC.read_text(encoding="utf-8"))


def test_yaml_sai_byte_a_byte(client):
    """Reserializar traria outra ordem e perderia os comentários."""
    from app.routers import offline as _off
    r = client.get("/api/openapi.yaml")
    assert r.content == _off._SPEC.read_bytes()


def test_etag_igual_nas_duas_formas_e_304_no_recarregamento(client):
    j = client.get("/api/openapi.json")
    y = client.get("/api/openapi.yaml")
    assert j.headers["etag"] == y.headers["etag"]
    r = client.get("/api/openapi.json", headers={"If-None-Match": j.headers["etag"]})
    assert r.status_code == 304 and not r.content


def test_edicao_do_arquivo_aparece_sem_reiniciar(client):
    """O cache é por mtime — em dev, editar o YAML tem de refletir na hora."""
    from app.routers import offline as _off
    original = _off._SPEC.read_text(encoding="utf-8")
    try:
        _off._SPEC.write_text(original.replace("  version: 2.2.0", "  version: 9.9.9"),
                              encoding="utf-8")
        assert client.get("/api/openapi.json").json()["info"]["version"] == "9.9.9"
    finally:
        _off._SPEC.write_text(original, encoding="utf-8")
    assert client.get("/api/openapi.json").json()["info"]["version"] == "2.2.0"


# Sem o arquivo, as três rotas respondiam "Internal Server Error" — já
# aconteceu em produção, com o `.dockerignore` excluindo o YAML da imagem. O 500
# anônimo manda procurar na aplicação; o defeito está no empacotamento.
@pytest.mark.parametrize("rota", ["/api/openapi.json", "/api/openapi.yaml", "/api/docs"])
def test_spec_ausente_responde_503_com_o_caminho(client, rota):
    import pathlib
    from app.routers import offline as _off
    guardado, _off._SPEC, _off._cache_spec = _off._SPEC, pathlib.Path("/nao/existe.yaml"), None
    try:
        r = client.get(rota)
        assert r.status_code == 503, r.text
        assert "/nao/existe.yaml" in r.json()["detail"]
    finally:
        _off._SPEC, _off._cache_spec = guardado, None
    assert client.get(rota).status_code == 200


def test_503_sobrevive_a_reload_do_modulo(client):
    """`SpecAusente` herda de HTTPException por causa deste caso.

    `tests/test_carne.py` recarrega este módulo para reler `LOTE_MAX_ITENS`. Com
    um handler casando por classe no `main`, a classe recriada pelo reload não
    era reconhecida e o 503 virava 500 — só na suíte inteira, nunca no arquivo
    isolado.
    """
    import importlib
    import pathlib

    from app import routers
    importlib.reload(routers.offline)
    off = routers.offline
    guardado, off._SPEC, off._cache_spec = off._SPEC, pathlib.Path("/nao/existe.yaml"), None
    try:
        r = client.get("/api/openapi.json")
        assert r.status_code == 503, r.text
    finally:
        off._SPEC, off._cache_spec = guardado, None


# ------------------------------------------------------- páginas de documentação
#
# `/docs` e `/api/docs` buscavam CSS e JS na unpkg.com. Este produto é
# self-hosted, em rede que libera saída HOST A HOST (é o que o
# `examples/oracle/acl_setup.sql` configura): alcançar a API não implica
# alcançar a unpkg. Onde não alcança, a página abre com o cabeçalho da
# plataforma e o Swagger não renderiza — em branco, sem erro nenhum.
@pytest.mark.parametrize("rota", ["/docs", "/api/docs", "/redoc"])
def test_pagina_nao_carrega_recurso_de_terceiro(client, rota):
    import re

    html = client.get(rota).text
    # Só o que o NAVEGADOR BUSCA para renderizar — `<link>`, `<script>`, `<img>`.
    # `<a href>` externo é link de navegação: o usuário clica se quiser, e a
    # página não depende dele para aparecer.
    recursos = re.findall(r'<(?:link|script|img)\b[^>]*?(?:href|src)="([^"]+)"', html)
    externos = sorted(u for u in recursos if u.startswith(("http://", "https://")))
    assert externos == [], f"{rota} busca recurso externo: {externos}"


@pytest.mark.parametrize("arquivo", ["swagger-ui.css", "swagger-ui-bundle.js"])
def test_renderizador_sai_da_propria_aplicacao(client, arquivo):
    r = client.get(f"/swagger-ui/{arquivo}")
    assert r.status_code == 200, r.text
    assert len(r.content) > 10_000, "arquivo do swagger-ui truncado?"


@pytest.mark.parametrize("rota", ["/docs", "/api/docs"])
def test_pagina_aponta_para_o_renderizador_servido(client, rota):
    html = client.get(rota).text
    assert '"/swagger-ui/swagger-ui.css"' in html
    assert '"/swagger-ui/swagger-ui-bundle.js"' in html


def test_cdn_de_reserva_tem_versao_pinada():
    """`@5` flutuante deixaria a página mudar sozinha a cada release do upstream."""
    import re

    from app.core.swagger_tema import CDN_SWAGGER
    assert re.search(r"@\d+\.\d+\.\d+$", CDN_SWAGGER), CDN_SWAGGER


# A spec do gateway declarava os erros vindos DO BANCO (409, 424, 429, 502, 504)
# e esquecia os do TOKEN, que vêm antes e valem nas mesmas rotas: `401` só
# aparecia em `credenciais`/`webhooks` e `403` em NENHUMA das 67 operações,
# enquanto a API responde os dois em todas as que aceitam `bapi_`.
def test_spec_declara_os_erros_de_token_onde_eles_acontecem(client):
    from app.main import app

    spec = app.openapi()
    operacoes = [(m.upper(), p, o) for p, d in spec["paths"].items() for m, o in d.items()
                 if m in ("get", "post", "put", "patch", "delete")]
    com_token = [(m, p) for m, p, o in operacoes if o.get("security")]
    assert len(com_token) >= 60, "cadê as rotas que aceitam token?"
    for m, p, o in operacoes:
        if not o.get("security"):
            continue
        faltando = {"401", "403"} - set(o.get("responses") or {})
        assert not faltando, f"{m} {p} aceita token e não declara {sorted(faltando)}"


def test_401_e_403_do_token_acontecem_de_verdade(client):
    """A declaração vale pelo que a API faz — não pelo que a spec afirma."""
    token = client.post("/credenciais", json={
        "tenant_id": "e1", "provider": "on", "banco": "c6",
        "credentials": {"client_id": "x", "client_secret": "y"}}).json()["token"]

    r = client.get("/cobranca/1", params={"tenant_id": "e1", "provider": "on", "banco": "c6"},
                   headers={"Authorization": "Bearer bapi_naoexiste"})
    assert r.status_code == 401, r.text

    # o bapi_ amarra tenant E banco: trocar qualquer um dos dois é 403
    r = client.get("/cobranca/1", params={"tenant_id": "e1", "provider": "on", "banco": "sicoob"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text
    r = client.get("/cobranca/1", params={"tenant_id": "outro", "provider": "on", "banco": "c6"},
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


def test_rota_sem_token_nao_ganha_401(client):
    """`/bancos` é introspecção e `/health` é sonda — declarar ali seria ruído."""
    from app.main import app

    spec = app.openapi()
    for rota in ("/bancos", "/health"):
        assert "401" not in spec["paths"][rota]["get"]["responses"], rota


# `/redoc` vinha pronto do FastAPI: sem o tema da plataforma, com o favicon do
# `fastapi.tiangolo.com` e buscando renderizador, fonte e ícone em três
# terceiros. Era a única das três páginas de documentação fora do padrão — e a
# única que continuava quebrada num deploy sem saída para a internet.
def test_redoc_usa_a_casca_da_plataforma(client):
    html = client.get("/redoc").text
    assert "cob-topbar" in html and "Cobranca<span>-API</span>" in html
    assert "fastapi.tiangolo.com" not in html
    assert "fonts.googleapis.com" not in html
    assert '<redoc spec-url="/openapi.json">' in html
    assert '"/swagger-ui/redoc.standalone.js"' in html


def test_renderizador_do_redoc_sai_da_propria_aplicacao(client):
    r = client.get("/swagger-ui/redoc.standalone.js")
    assert r.status_code == 200 and len(r.content) > 100_000


# A spec do gateway tem ~324 KB e o `/docs` a busca inteira a cada abertura. O
# irmão offline já devolvia 304 desde a revisão anterior; as duas superfícies
# respondiam diferente para a mesma pergunta.
def test_openapi_do_gateway_tem_etag_e_304(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200 and r.headers.get("etag")
    assert r.json()["openapi"].startswith("3.")
    r304 = client.get("/openapi.json", headers={"If-None-Match": r.headers["etag"]})
    assert r304.status_code == 304 and not r304.content


def test_as_duas_specs_respondem_igual_ao_condicional(client):
    """Consistência entre as superfícies: mesma pergunta, mesma resposta."""
    for rota in ("/openapi.json", "/api/openapi.json"):
        etag = client.get(rota).headers["etag"]
        assert client.get(rota, headers={"If-None-Match": etag}).status_code == 304, rota


# ------------------------------------------------------------------ sondas
#
# As duas respondem `status`, com CAIXA DIFERENTE, e é deliberado: o `"OK"` do
# `/api/health` é contrato herdado da v1.x e o `"ok"` do `/health` é o que o
# `examples/oracle/cobranca_api_pkg.sql` e a coleção Postman comparam por
# igualdade. Trocar qualquer um dos dois quebra um consumidor real — o teste
# fixa os dois para que a mudança seja uma decisão, não um deslize.
def test_sondas_respondem_status_com_a_caixa_de_cada_superficie(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json()["status"] == "OK"


def test_health_do_gateway_nao_toca_em_nada(client):
    """É o que mata o container quando falha (Dockerfile, compose, Render)."""
    assert client.get("/health").json() == {"status": "ok"}
    # sem credencial, sem banco ligado, sem cofre: continua ok
    assert client.get("/health").status_code == 200


def test_timestamp_do_api_health_e_iso_com_offset(client):
    """A página prometia sufixo `Z`; a API devolve `+00:00` com microssegundos."""
    from datetime import datetime

    ts = client.get("/api/health").json()["timestamp"]
    assert not ts.endswith("Z"), ts
    assert datetime.fromisoformat(ts).utcoffset().total_seconds() == 0, ts


def test_health_do_gateway_tem_schema_proprio_na_spec(client):
    """Era `additionalProperties: string` sem exemplo — a rota mais consumida
    por automação era a menos especificada da API."""
    from app.main import app

    op = app.openapi()["paths"]["/health"]["get"]
    corpo = op["responses"]["200"]["content"]["application/json"]
    assert corpo["schema"] == {"$ref": "#/components/schemas/Saude"}
    assert corpo["example"] == {"status": "ok"}
    assert app.openapi()["components"]["schemas"]["Saude"]["properties"]["status"]["const"] == "ok"


def test_exemplo_do_api_health_na_spec_bate_com_a_resposta(client):
    """O exemplo tem de ser algo que a API realmente devolveria."""
    from datetime import datetime

    import yaml

    from app.routers import offline as _off
    spec = yaml.safe_load(_off._SPEC.read_text(encoding="utf-8"))
    exemplo = spec["paths"]["/api/health"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    real = client.get("/api/health").json()
    assert set(exemplo) == set(real)
    assert exemplo["status"] == real["status"]
    # mesmo formato de instante, não só mesmo campo
    datetime.fromisoformat(exemplo["timestamp"])
    assert not exemplo["timestamp"].endswith("Z")


# ------------------------------------------------------------------- catálogo
#
# `GET /bancos` é a rota para onde o resto da documentação manda quem precisa da
# matriz exata ("`GET /bancos` responde a matriz exata, por introspecção"). Se
# ela mentir, mente tudo que aponta para ela.
def test_caminho_efetivo_e_o_que_a_cobranca_faz_de_verdade(client, monkeypatch):
    """A promessa central do catálogo, medida nos dois estados da flag."""
    conta = {"agencia": "1234", "conta_corrente": "12345", "carteira": "109",
             "convenio": "12345", "cedente": "E", "documento_cedente": "11222333000181",
             "nosso_numero": "123"}
    corpo = {"tenant_id": "t", "provider": "on", "banco": "itau", "account_config": conta,
             "cobranca": {"valor": 150.0, "vencimento": "2027-12-30", "seu_numero": "P1",
                          "pagador": {"nome": "J", "documento": "52998224725"}}}

    def catalogo():
        return next(b for b in client.get("/bancos").json()["bancos"] if b["id"] == "itau")

    monkeypatch.delenv("ITAU_REGISTERED_READY", raising=False)
    assert catalogo()["caminho_efetivo"] == "off"
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 201 and r.json()["linha_digitavel"], "devia sair pela engine"

    monkeypatch.setenv("ITAU_REGISTERED_READY", "true")
    assert catalogo()["caminho_efetivo"] == "on"
    # foi ao banco: sem credencial no cofre, 424 — e não um 201 da engine
    assert client.post("/cobranca", json=corpo).status_code == 424


def test_capacidades_novas_discriminam_os_bancos(client):
    """`GET /pix/{txid}` não existe no Itaú; `/conciliacao/transacoes` só no C6;
    sem `normalizar_webhook` o `POST /webhooks/{banco}` não entende a notificação."""
    caps = {b["id"]: set(b["capacidades"]) for b in client.get("/bancos").json()["bancos"]}
    assert "conciliacao_transacoes" in caps["c6"]
    assert "conciliacao_transacoes" not in caps["sicoob"]
    for banco in ("c6", "sicoob", "inter"):
        assert {"pix_consulta", "webhook_entrada"} <= caps[banco], banco
    assert not ({"pix_consulta", "webhook_entrada"} & caps["itau"])


def test_consultar_fica_fora_das_capacidades(client):
    """O provider offline sobrescreve `consultar` para devolver `pendente` com
    uma dica — sobrescrever ali é honestidade, não capacidade. Anunciar faria o
    consumidor esperar consulta de status onde não há estado."""
    from app.routers.bancos import _CAPACIDADES

    assert "consultar" not in _CAPACIDADES
    caps = {b["id"]: set(b["capacidades"]) for b in client.get("/bancos").json()["bancos"]}
    assert not any("consulta" in c for c in caps["pycobranca"])


def test_schema_do_catalogo_descreve_os_campos_que_a_rota_devolve(client):
    """O schema era `additionalProperties: true` — "um objeto qualquer" — na rota
    que a documentação inteira usa como fonte. Descrito à mão, precisa de guarda
    contra envelhecer."""
    from app.main import app

    op = app.openapi()["paths"]["/bancos"]["get"]
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    corpo = client.get("/bancos").json()
    assert set(schema["properties"]) == set(corpo)
    declarados = set(schema["properties"]["bancos"]["items"]["properties"])
    reais = {k for b in corpo["bancos"] for k in b}
    assert declarados == reais, f"só no schema {declarados - reais} | só na resposta {reais - declarados}"


def test_documentacao_de_cada_banco_existe(client):
    import pathlib

    from app.routers import offline as _off
    raiz = _off._SPEC.parent.parent
    for b in client.get("/bancos").json()["bancos"]:
        caminho = b.get("documentacao")
        if caminho:
            assert (raiz / caminho).exists(), f"{b['id']} aponta para {caminho}, que não existe"


# ------------------------------------------------------------------ credenciais
#
# O `422` do Pydantic devolve `input` — o valor que chegou. Em `credentials` isso
# é o `client_secret` e a senha do certificado mTLS voltando no corpo da
# resposta, de onde vão para log de aplicação, APM e console do navegador. O
# cabeçalho do `core/vault.py` manda NUNCA logar credencial; devolver na
# resposta é pior, porque nem passa por um filtro de log.
SEGREDO = "s3cr3t-do-banco"
SENHA_PFX = "senha-do-pfx"


@pytest.mark.parametrize("chamada", [
    lambda c: c.post("/credenciais", json={"tenant_id": "a", "credentials": {
        "client_id": "cid", "client_secret": SEGREDO, "pfx_password": SENHA_PFX}}),
    lambda c: c.post("/credenciais", json={"tenant_id": "a", "provider": "on",
                                           "banco": "c6", "credentials": SEGREDO}),
    lambda c: c.post("/cobranca", json={"tenant_id": "a", "provider": "on", "banco": "c6",
                                        "credentials": {"client_secret": SEGREDO}}),
    lambda c: c.post("/checkout", json={"tenant_id": "a", "provider": "on", "banco": "c6",
                                        "credentials": {"pfx_password": SENHA_PFX}}),
    lambda c: c.get("/cobranca/1", params={"tenant_id": "a"},
                    headers={"X-Bank-Credentials": json.dumps({"client_secret": SEGREDO})}),
])
def test_422_nao_devolve_credencial(client, chamada):
    r = chamada(client)
    assert r.status_code == 422, r.text
    assert SEGREDO not in r.text and SENHA_PFX not in r.text, r.text[:300]


def test_422_continua_dizendo_o_que_chegou_fora_de_credentials(client):
    """A redação não pode custar o diagnóstico: `input` é o que torna o 422 útil."""
    r = client.post("/cobranca", json={"tenant_id": "a", "provider": "xyz", "banco": "c6"})
    assert r.status_code == 422
    erro = r.json()["detail"][0]
    assert erro["input"] == "xyz" and erro["loc"] == ["body", "provider"]


def test_cofre_guarda_cifrado_e_sem_o_token(client, tmp_path, monkeypatch):
    """Zero-knowledge: sem o token, a linha no banco é um blob inútil."""
    import hashlib
    import sqlite3

    caminho = tmp_path / "cred.db"
    monkeypatch.setenv("CREDENTIAL_DB_PATH", str(caminho))
    token = client.post("/credenciais", json={
        "tenant_id": "acme", "provider": "on", "banco": "c6",
        "credentials": {"client_id": "cid", "client_secret": SEGREDO}}).json()["token"]

    linha = sqlite3.connect(caminho).execute(
        "SELECT token_hash, tenant_id, provider, salt, nonce, ciphertext FROM credential_tokens"
    ).fetchone()
    bruto = b"".join(x if isinstance(x, bytes) else str(x).encode() for x in linha)
    assert SEGREDO.encode() not in bruto, "credencial em claro no cofre"
    assert token.encode() not in bruto, "o token não pode ser guardado"
    assert linha[0] == hashlib.sha256(token.encode()).hexdigest()


def test_revogacao_invalida_o_token_na_hora(client):
    token = client.post("/credenciais", json={
        "tenant_id": "rev", "provider": "on", "banco": "c6",
        "credentials": {"client_id": "i"}}).json()["token"]
    cab = {"Authorization": f"Bearer {token}"}
    alvo = ("/cobranca/1", {"tenant_id": "rev", "provider": "on", "banco": "c6"})
    assert client.get(alvo[0], params=alvo[1], headers=cab).status_code == 200
    assert client.delete("/credenciais", headers=cab).status_code == 204
    assert client.get(alvo[0], params=alvo[1], headers=cab).status_code == 401
    assert client.delete("/credenciais", headers=cab).status_code == 401


def test_apelido_legado_e_o_modelo_novo_compartilham_a_credencial(client):
    """Promessa escrita no router: token emitido antes da mudança segue valendo."""
    t_legado = client.post("/credenciais", json={
        "tenant_id": "b", "provider": "c6",
        "credentials": {"client_id": "i"}}).json()["token"]
    r = client.get("/cobranca/1", params={"tenant_id": "b", "provider": "on", "banco": "c6"},
                   headers={"Authorization": f"Bearer {t_legado}"})
    assert r.status_code == 200, r.text

    t_novo = client.post("/credenciais", json={
        "tenant_id": "d", "provider": "on", "banco": "c6",
        "credentials": {"client_id": "i"}}).json()["token"]
    r = client.get("/cobranca/1", params={"tenant_id": "d", "provider": "c6"},
                   headers={"Authorization": f"Bearer {t_novo}"})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------- cobrança
#
# `201 Created` é a afirmação mais forte que o HTTP tem de "criei o recurso", e a
# rota a usa para dizer que NÃO criou: dados recusados pela engine voltam `201`
# com `status: "erro"` e `id: null`. Quem faz `raise_for_status()` dá o boleto
# por emitido.
#
# Que é defeito, e não estilo, está na comparação interna abaixo: a MESMA
# violação responde `400` em duas rotas `/api/*` e `422` quando é o banco que a
# detecta — só aqui ela passa por sucesso.
CONTA_BB = {"agencia": "3073", "conta_corrente": "12345678", "convenio": "1234567",
            "carteira": "18", "cedente": "E", "documento_cedente": "11222333000181",
            "nosso_numero": "123"}
COBRANCA = {"valor": 150.0, "vencimento": "2027-12-30", "seu_numero": "P1",
            "pagador": {"nome": "J", "documento": "52998224725"}}


def _registrar(client, **conta):
    return client.post("/cobranca", json={
        "tenant_id": "t", "provider": "off", "banco": "banco_brasil",
        "account_config": {**CONTA_BB, **conta}, "cobranca": COBRANCA})


def test_mesma_violacao_tem_codigos_opostos_por_rota(client):
    """A evidência de que o `201` com erro é inconsistência, não convenção."""
    dados = {"valor": 150.0, "cedente": "E", "documento_cedente": "11222333000181",
             "sacado": "J", "sacado_documento": "52998224725", "agencia": "3073",
             "conta_corrente": "12345678", "convenio": "1234567", "carteira": "999",
             "nosso_numero": "123", "data_vencimento": "2027-12-30"}
    assert client.get("/api/boleto/validate", params={
        "bank": "banco_brasil", "data": json.dumps(dados)}).status_code == 400
    assert client.post("/api/render/boleto",
                       json={"bank": "banco_brasil", "data": dados}).status_code == 400
    # e a mesma carteira em POST /cobranca, no default
    r = _registrar(client, carteira="999")
    assert r.status_code == 201 and r.json()["status"] == "erro"


def test_default_mantem_o_201_com_status_erro(client, monkeypatch):
    """Contrato atual, ensinado em três documentos — não muda sozinho."""
    monkeypatch.delenv("COBRANCA_ERRO_HTTP", raising=False)
    r = _registrar(client, carteira="999")
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["status"] == "erro" and corpo["id"] is None
    assert "Location" not in r.headers
    assert corpo["raw"]["validation_errors"]


def test_flag_faz_a_recusa_virar_422_com_o_mesmo_corpo(client, monkeypatch):
    monkeypatch.setenv("COBRANCA_ERRO_HTTP", "1")
    r = _registrar(client, carteira="999")
    assert r.status_code == 422, r.text
    corpo = r.json()
    # o corpo é o MESMO: quem migra continua lendo raw.validation_errors
    assert corpo["status"] == "erro" and corpo["id"] is None
    assert corpo["raw"]["validation_errors"]


def test_flag_nao_afeta_o_caminho_de_sucesso(client, monkeypatch):
    monkeypatch.setenv("COBRANCA_ERRO_HTTP", "1")
    r = _registrar(client)
    assert r.status_code == 201 and r.json()["status"] == "registrado"
    assert r.headers["Location"].startswith("/cobranca/123?")


def test_location_do_201_e_seguivel(client):
    """Location sem tenant_id e provider devolveria 422 a quem confia no header."""
    r = _registrar(client)
    caminho, _, query = r.headers["Location"].partition("?")
    seguido = client.get(caminho, params=dict(p.split("=") for p in query.split("&")))
    assert seguido.status_code == 200, seguido.text


@pytest.mark.parametrize("provider,banco", [("off", "banco_brasil"), ("on", "c6"), ("c6", None)])
def test_location_e_seguivel_nos_dois_modelos(client, provider, banco):
    """O `banco` ficou de fora do `Location` quando o segundo eixo nasceu: o
    header apontava para `422` justamente no modelo NOVO, e são no legado
    (`provider=c6`), que carrega o banco no próprio valor."""
    conta = {**CONTA_BB, "carteira": "10"} if provider != "off" else dict(CONTA_BB)
    corpo = {"tenant_id": "t", "provider": provider, "account_config": conta,
             "cobranca": COBRANCA}
    if banco:
        corpo["banco"] = banco
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 201 and "Location" in r.headers, r.text
    caminho, _, query = r.headers["Location"].partition("?")
    seguido = client.get(caminho, params=dict(p.split("=") for p in query.split("&")))
    assert seguido.status_code == 200, f"Location {r.headers['Location']} -> {seguido.text[:160]}"


def test_location_do_pix_tambem_carrega_o_banco(client):
    """Mesmo `_location`, mesmo defeito — `/pix` e `/pix/lote` também."""
    import inspect

    from app.routers import pix
    assert "banco" in inspect.signature(pix._location).parameters
    fonte = inspect.getsource(pix)
    assert fonte.count("body.provider, body.banco") >= 2, "alguma chamada ficou sem o banco"


# ------------------------------------------------------------------------ pix
#
# O txid é do BACEN — `[a-zA-Z0-9]{26,35}` — e a mensagem da cobv já CITAVA a
# regra sem aplicá-la: `txid="abc"`, txid com hífen e txid de 40 caracteres
# chegavam ao banco e voltavam como `400` dele, traduzido em `422` com
# `upstream`. Validar no schema recusa antes da ida à rede, com mensagem
# própria, e vale para cob, cobv e itens de lote de uma vez — mesmo movimento
# do `POST /bolepix` na 2.1.1.
@pytest.fixture
def _c6_sem_rede(monkeypatch):
    monkeypatch.setenv("VAULT__e1__c6__client_id", "cid")
    monkeypatch.setenv("VAULT__e1__c6__client_secret", "sec")
    caminhos: list[str] = []
    monkeypatch.setattr(
        "app.clients.oauth_mtls.OAuthMtlsClient.request",
        lambda self, method, path, json=None, params=None: (
            caminhos.append(path),
            {"txid": "X", "status": "ATIVA", "pixCopiaECola": "0", "loc": {"location": "x"}},
        )[1])
    return caminhos


TXID_BACEN = "TX1234567890123456789012345"


def _criar_pix(client, txid=None, vencimento=False):
    pix = {"valor": "10.00", "descricao": "x"}
    if txid:
        pix["txid"] = txid
    if vencimento:
        pix.update(data_vencimento="2027-12-30",
                   devedor={"nome": "J", "documento": "52998224725"})
    return client.post("/pix", json={"tenant_id": "e1", "provider": "on", "banco": "c6",
                                     "account_config": {"chave_pix": "c@e.com"}, "pix": pix})


@pytest.mark.parametrize("txid", ["abc", "A" * 40, "TX-234567890123456789012345"])
@pytest.mark.parametrize("vencimento", [False, True])
def test_txid_fora_do_padrao_bacen_nao_chega_ao_banco(client, _c6_sem_rede, txid, vencimento):
    r = _criar_pix(client, txid, vencimento)
    assert r.status_code == 422, r.text
    assert not _c6_sem_rede, f"foi ao banco em {_c6_sem_rede}"


@pytest.mark.parametrize("vencimento", [False, True])
def test_txid_valido_passa_e_vira_o_identificador(client, _c6_sem_rede, vencimento):
    r = _criar_pix(client, TXID_BACEN, vencimento)
    assert r.status_code == 201, r.text
    alvo = "cobv" if vencimento else "cob"
    assert _c6_sem_rede[-1].endswith(f"/{alvo}/{TXID_BACEN}")


def test_cob_sem_txid_deixa_o_banco_gerar(client, _c6_sem_rede):
    assert _criar_pix(client).status_code == 201
    assert _c6_sem_rede[-1].endswith("/cob"), _c6_sem_rede


def test_location_da_cobv_leva_a_cobv_e_nao_a_cob(client, _c6_sem_rede):
    """`vencimento=true` no Location é o que separa consultar a cobv de
    consultar uma cob que não existe."""
    r = _criar_pix(client, TXID_BACEN, vencimento=True)
    loc = r.headers["Location"]
    assert "vencimento=true" in loc and "banco=c6" in loc
    caminho, _, query = loc.partition("?")
    _c6_sem_rede.clear()
    seguido = client.get(caminho, params=dict(p.split("=") for p in query.split("&")))
    assert seguido.status_code == 200, seguido.text
    assert "/cobv/" in _c6_sem_rede[-1], _c6_sem_rede


def test_dialeto_bacen_e_o_mesmo_nos_tres_bancos(client, monkeypatch):
    """A tag promete "dialeto idêntico em todos os bancos" — só o path muda."""
    corpos = {}
    for banco in ("c6", "sicoob", "inter"):
        monkeypatch.setenv(f"VAULT__e1__{banco}__client_id", "cid")
        monkeypatch.setenv(f"VAULT__e1__{banco}__client_secret", "sec")
        monkeypatch.setattr(
            "app.clients.oauth_mtls.OAuthMtlsClient.request",
            lambda self, method, path, json=None, params=None, _b=banco: (
                corpos.__setitem__(_b, sorted(json or {})),
                {"txid": "X", "status": "ATIVA", "loc": {"location": "x"}})[1])
        r = client.post("/pix", json={"tenant_id": "e1", "provider": "on", "banco": banco,
                                      "account_config": {"chave_pix": "c@e.com"},
                                      "pix": {"valor": "10.00", "descricao": "x"}})
        assert r.status_code == 201, (banco, r.text)
    assert len(set(map(tuple, corpos.values()))) == 1, corpos


# --- revisao de /api ---------------------------------------------------------------
#
# A superficie offline ja tinha sido varrida por 500 e por contrato de erro nas
# revisoes anteriores. O que sobrou sao as duas bordas de ENTRADA: parametro
# booleano em texto e arquivo enviado.

@pytest.mark.parametrize("valor", ["1", "0", "yes", "on", "sim", "", "talvez"])
def test_parametro_booleano_fora_do_enum_nao_e_false_silencioso(client, valor):
    """A spec publicada declara `enum: ['true','false']` e o codigo aceitava so
    `"true"`, tratando TODO o resto como `false`. `include_data=1` respondia 200
    com o PDF BINARIO quando o chamador pediu JSON — o parametro era aceito,
    ignorado, e a resposta mudava de tipo."""
    r = client.get("/api/boleto", params={"bank": "banco_brasil",
                                          "data": json.dumps(DADOS_BB),
                                          "include_data": valor})
    assert r.status_code == 400, r.text
    assert "include_data" in str(r.json()["validation_errors"])


@pytest.mark.parametrize("valor", ["true", "True", "TRUE", "false", "FALSE"])
def test_o_enum_declarado_continua_valendo(client, valor):
    r = client.get("/api/boleto", params={"bank": "banco_brasil",
                                          "data": json.dumps(DADOS_BB),
                                          "include_data": valor})
    assert r.status_code == 200, r.text
    json_esperado = valor.lower() == "true"
    eh_json = r.headers["content-type"].startswith("application/json")
    assert eh_json is json_esperado


def test_pix_da_remessa_tambem_segue_o_enum(client):
    r = client.post("/api/remessa", params={"bank": "banco_brasil", "type": "cnab400",
                                            "pix": "1"},
                    files={"data": ("d.json", json.dumps(DADOS_BB), "application/json")})
    assert r.status_code == 400, r.text
    assert "`pix`" in str(r.json()["validation_errors"])


def test_somente_creditos_do_ofx_tambem_segue_o_enum(client):
    r = client.post("/api/ofx/parse", files={"file": ("x.ofx", b"<OFX>", "text/plain")},
                    data={"somente_creditos": "1"})
    assert r.status_code == 400, r.text
    assert "somente_creditos" in str(r.json()["validation_errors"])


@pytest.mark.parametrize("rota,campo,params", [
    ("/api/ofx/parse", "file", {}),
    ("/api/retorno", "data", {"bank": "banco_brasil", "type": "cnab400"}),
    ("/api/remessa", "data", {"bank": "banco_brasil", "type": "cnab400"}),
    ("/api/boleto/multi", "data", {}),
])
def test_upload_acima_do_teto_responde_413_e_nao_derruba_o_processo(client, monkeypatch,
                                                                    rota, campo, params):
    """As quatro rotas faziam `await ler()` do arquivo INTEIRO para a memoria,
    sem olhar o tamanho: um POST grande derruba o processo antes de qualquer
    validacao. O teto vem antes da leitura util."""
    from app.routers import offline

    monkeypatch.setattr(offline, "UPLOAD_MAX", 1024)
    r = client.post(rota, params=params,
                    files={campo: ("g.bin", b"x" * 4096, "application/octet-stream")})
    assert r.status_code == 413, r.text
    assert r.json()["campo"] == campo and r.json()["recebidos"] == 4096


@pytest.mark.parametrize("rota,campo,params", [
    ("/api/retorno", "data", {"bank": "banco_brasil", "type": "cnab400"}),
    ("/api/remessa", "data", {"bank": "banco_brasil", "type": "cnab400"}),
])
def test_arquivo_vazio_e_recusado_pelo_nome_do_campo(client, rota, campo, params):
    r = client.post(rota, params=params, files={campo: ("v.txt", b"", "text/plain")})
    assert r.status_code == 400, r.text
    assert "vazio" in str(r.json()["validation_errors"])


def test_erro_do_retorno_usa_a_chave_canonica(client):
    """Esta rota era a unica com `details`; quem escreve um handler generico de
    erro tinha de conhecer as duas. A antiga fica como alias."""
    r = client.post("/api/retorno", params={"bank": "banco_brasil", "type": "cnab400"},
                    files={"data": ("r.ret", b"lixo", "text/plain")})
    assert r.status_code == 400
    corpo = r.json()
    assert corpo["validation_errors"] == corpo["details"]


def test_erro_do_ofx_usa_a_chave_canonica(client):
    """`erro` em portugues era o unico do tipo na superficie."""
    r = client.post("/api/ofx/parse", files={"file": ("x.ofx", b"lixo", "text/plain")})
    assert r.status_code == 400
    corpo = r.json()
    assert corpo["error"] == corpo["erro"]
    assert corpo["validation_errors"]


# --- o nome do arquivo de remessa é regra do BANCO, não convenção nossa -----------
#
# O Inter só aceita o upload se o arquivo se chamar `CI400_001_<sequencial>.REM`
# com o MESMO sequencial gravado no header. A engine expõe `nome_arquivo()` e a
# docstring dela diz, com todas as letras, que "a biblioteca gera o conteúdo,
# quem nomeia é o chamador" — e o chamador é esta API, que vinha inventando
# `remessa-inter-cnab400.rem`. Arquivo correto, recusado por causa do nome.

def _remessa_inter(client, sequencial: int):
    import io
    import json as _json
    data = {
        "beneficiario": {"nome": "M&S", "documento": "05230380000174",
                         "agencia": "0001", "conta_corrente": "123456",
                         "convenio": "123456"},
        "digito_conta": "7", "carteira": "110",
        "pagamentos": [{"nosso_numero": "1234567890", "numero_documento": "A-1",
                        "valor": "100.00", "data_vencimento": "2027-09-10",
                        "sacado": "Fulano", "sacado_documento": "52998224725",
                        "endereco_sacado": "Av. Teste, 100", "cep_sacado": "35700000"}],
        "sequencial_remessa": sequencial,
    }
    return client.post("/api/remessa?bank=inter&type=cnab400", files={
        "data": ("d.json", io.BytesIO(_json.dumps(data).encode()), "application/json")})


@pytest.mark.parametrize("sequencial,esperado", [
    (1, "CI400_001_0000001.REM"),
    (42, "CI400_001_0000042.REM"),
    (1234567, "CI400_001_1234567.REM"),
])
def test_a_remessa_do_inter_sai_com_o_nome_que_o_banco_exige(client, sequencial, esperado):
    r = _remessa_inter(client, sequencial)
    assert r.status_code == 200, r.text[:200]
    assert f"filename={esperado}" in r.headers["content-disposition"]


def test_banco_sem_regra_de_nome_mantem_o_descritivo(client):
    """Mudar o nome onde não há regra de banco quebraria quem automatiza o
    download por nada — a troca vale só onde o layout manda.

    A fixture vem de `FIXTURES`, ancorado em `__file__`: com caminho relativo
    este caso passava da raiz do repo e falhava no CI, que roda de `gateway/`.
    """
    with open(FIXTURES / "remessa_cnab240_bb.json", "rb") as f:
        r = client.post("/api/remessa?bank=banco_brasil&type=cnab240",
                        files={"data": ("d.json", f, "application/json")})
    assert r.status_code == 200, r.text[:200]
    assert "filename=remessa-banco_brasil-cnab240.rem" in r.headers["content-disposition"]


def test_o_nome_vem_do_layout_e_nao_de_uma_copia_da_regra_aqui(monkeypatch):
    """A regra mora na engine; aqui só se pergunta.

    Provado por comportamento e não por texto: um dublê devolve outro nome e a
    rota tem de usar ESSE. Conferir a string `CI400` no nosso código passaria
    igual se alguém reimplementasse o formato aqui — e aí o dia em que o banco
    mudasse a exigência, a engine saberia e a API não.
    """
    from app.core import pycob

    class LayoutQueNomeia:
        def nome_arquivo(self):
            return "NOME_DO_LAYOUT.REM"

    class LayoutQueNaoNomeia:
        pass

    assert pycob.nome_de_remessa(LayoutQueNomeia()) == "NOME_DO_LAYOUT.REM"
    # Sem regra, `None` — e não um nome de reserva. Quem chama precisa
    # distinguir "o banco exige este nome" de "não há regra": o lote registra
    # o de upload só quando ele existe, e um descritivo ali anunciaria uma
    # exigência que nenhum banco fez.
    assert pycob.nome_de_remessa(LayoutQueNaoNomeia()) is None
    # E o layout do Inter continua publicando o nome — se parar, a rota
    # silenciosamente voltaria a inventar um nome que o banco recusa.
    assert hasattr(pycob._REMESSAS[("inter", "cnab400", False)], "nome_arquivo")
