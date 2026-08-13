# Itaú (341) — ESQUELETO do provider REST.
#
# O que estes testes afirmam é o NOSSO lado: roteamento, gate de homologação,
# fallback offline, normalização da resposta, mapa de status e o cuidado com o
# desconhecido. NÃO afirmam o contrato do Itaú — payload e paths ainda não são
# públicos (ver docs/development/itau-rest.md), e um teste que "provasse" nomes
# de campo inventados daria falsa confiança justamente onde não há informação.
#
# Por isso os mocks devolvem o corpo em VÁRIOS apelidos: o que se testa é que a
# leitura tolera a variação, que é a decisão de desenho enquanto o catálogo não
# abre.
import pytest

from app.schemas import Status


@pytest.fixture
def itau_env(monkeypatch):
    monkeypatch.setenv("VAULT__empresa1__itau__client_id", "cid")
    monkeypatch.setenv("VAULT__empresa1__itau__client_secret", "sec")
    monkeypatch.setenv("ITAU_REGISTERED_READY", "true")


def _capture(monkeypatch, *respostas):
    calls = []
    fila = list(respostas) or [{}]

    def fake(self, method, path, json=None, params=None):
        calls.append({"method": method, "path": path, "json": json,
                      "headers": dict(self.default_headers), "scopes": list(self.scopes or [])})
        return fila[min(len(calls) - 1, len(fila) - 1)]

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake)
    return calls


def _corpo(**extra):
    base = {"tenant_id": "empresa1", "provider": "itau",
            "account_config": {"agencia": "3073", "conta": "12345678"},
            "cobranca": {"valor": "150.00", "vencimento": "2026-12-31",
                         "nosso_numero": "123", "seu_numero": "PED-1",
                         "pagador": {"nome": "Joao da Silva", "documento": "529.982.247-25",
                                     "endereco": {"logradouro": "Rua Teste", "numero": "126A",
                                                  "cidade": "Sete Lagoas", "uf": "MG",
                                                  "cep": "35.700-000"}}}}
    base.update(extra)
    return base


# --- gate de homologação: o esqueleto não vai ao banco por acidente -----------

def test_sem_flag_cai_na_engine_offline(client, monkeypatch):
    """`provider=itau` sem `ITAU_REGISTERED_READY` NÃO chama o banco.

    O 341 existe na engine, então o fallback emite de verdade em vez de recusar
    — e é o que protege o esqueleto de ir a produção sem querer.
    """
    monkeypatch.delenv("ITAU_REGISTERED_READY", raising=False)
    calls = _capture(monkeypatch, {})
    corpo = _corpo()
    # A engine precisa dos dados do convênio para calcular o código de barras —
    # é o mesmo payload que o caminho offline sempre exigiu.
    # Conta com 5 dígitos: é regra do 341 na engine, e vale a pena o teste
    # carregá-la — foi ela que recusou a massa genérica na primeira execução.
    corpo["account_config"] = {"agencia": "3073", "conta_corrente": "12345",
                               "convenio": "1234567", "carteira": "109",
                               "cedente": "Empresa Teste LTDA",
                               "documento_cedente": "11222333000181"}
    r = client.post("/cobranca", json=corpo)
    assert r.status_code == 201
    assert calls == [], "não pode ter chamada HTTP ao banco no modo offline"
    dados = r.json()
    assert dados["status"] == "registrado", dados
    assert len(dados["codigo_barras"]) == 44, "quem emitiu foi a engine, no layout 341"


def test_com_flag_chama_o_banco(client, itau_env, monkeypatch):
    calls = _capture(monkeypatch, {"id_boleto": "IT-1", "status": "EM_ABERTO",
                                   "linha_digitavel": "34191...", "codigo_barras": "34199..."})
    r = client.post("/cobranca", json=_corpo())
    assert r.status_code == 201
    assert len(calls) == 1 and calls[0]["method"] == "POST"
    assert calls[0]["path"].endswith("/boletos")


# --- o que é decisão nossa e não muda quando o catálogo abrir -----------------

def test_documento_e_cep_vao_so_com_digitos(client, itau_env, monkeypatch):
    calls = _capture(monkeypatch, {"id_boleto": "IT-1"})
    client.post("/cobranca", json=_corpo())
    pagador = calls[0]["json"]["dado_boleto"]["pagador"]
    assert pagador["documento"] == "52998224725"
    assert pagador["cep"] == "35700000"
    assert pagador["tipo_pessoa"] == "F"


def test_cnpj_vira_pessoa_juridica(client, itau_env, monkeypatch):
    calls = _capture(monkeypatch, {"id_boleto": "IT-1"})
    corpo = _corpo()
    corpo["cobranca"]["pagador"]["documento"] = "11222333000181"
    client.post("/cobranca", json=corpo)
    assert calls[0]["json"]["dado_boleto"]["pagador"]["tipo_pessoa"] == "J"


def test_conta_e_carteira_saem_do_account_config(client, itau_env, monkeypatch):
    """Dados do convênio nunca vêm do payload da cobrança."""
    calls = _capture(monkeypatch, {"id_boleto": "IT-1"})
    client.post("/cobranca", json=_corpo())
    benef = calls[0]["json"]["beneficiario"]
    assert benef["agencia"] == "3073" and benef["conta"] == "12345678"
    assert benef["carteira"] == "109", "default de mercado quando o convênio não diz"


def test_carteira_do_convenio_vence_o_default(client, itau_env, monkeypatch):
    calls = _capture(monkeypatch, {"id_boleto": "IT-1"})
    corpo = _corpo()
    corpo["account_config"]["carteira"] = "112"
    client.post("/cobranca", json=corpo)
    assert calls[0]["json"]["beneficiario"]["carteira"] == "112"


def test_correlation_id_so_vai_quando_informado(client, itau_env, monkeypatch):
    """Mesma armadilha do `x-conta-corrente` do Inter: header vazio atrapalha."""
    calls = _capture(monkeypatch, {"id_boleto": "IT-1"})
    client.post("/cobranca", json=_corpo())
    assert "x-itau-correlationID" not in calls[0]["headers"]

    corpo = _corpo()
    corpo["account_config"]["correlation_id"] = "abc-123"
    calls2 = _capture(monkeypatch, {"id_boleto": "IT-1"})
    client.post("/cobranca", json=corpo)
    assert calls2[0]["headers"]["x-itau-correlationID"] == "abc-123"


# --- leitura tolerante enquanto o nome do campo não é público -----------------

@pytest.mark.parametrize("corpo_banco", [
    {"id_boleto": "IT-9", "linha_digitavel": "341A", "codigo_barras": "341B"},
    {"id": "IT-9", "codigo_linha_digitavel": "341A", "codigo_barra": "341B"},
    {"data": {"nosso_numero": "IT-9", "linha_digitavel": "341A", "codigo_barras": "341B"}},
])
def test_le_a_resposta_em_qualquer_dos_apelidos(client, itau_env, monkeypatch, corpo_banco):
    _capture(monkeypatch, corpo_banco)
    r = client.post("/cobranca", json=_corpo())
    dados = r.json()
    assert dados["id"] == "IT-9"
    assert dados["linha_digitavel"] == "341A" and dados["codigo_barras"] == "341B"


def test_nunca_devolve_pdf(client, itau_env, monkeypatch):
    """O banco não manda PDF — quem renderiza o 341 é a engine.

    Se um dia a resposta trouxer PDF, este teste falha e a decisão volta à mesa;
    inventar um `pdf_base64` vazio seria pior que declarar a ausência.
    """
    _capture(monkeypatch, {"id_boleto": "IT-1", "pdf": "JVBERi0x"})
    assert client.post("/cobranca", json=_corpo()).json()["pdf_base64"] is None


# --- status: errar para o lado seguro ----------------------------------------

@pytest.mark.parametrize("situacao,esperado", [
    ("EM_ABERTO", Status.registrado),
    ("VENCIDO", Status.registrado),
    ("PAGO", Status.liquidado),
    ("BAIXADO", Status.baixado),
    ("CANCELADO", Status.baixado),
    ("EXPIRADO", Status.expirado),
])
def test_mapa_de_status(client, itau_env, monkeypatch, situacao, esperado):
    _capture(monkeypatch, {"id_boleto": "IT-1", "status": situacao})
    assert client.post("/cobranca", json=_corpo()).json()["status"] == esperado.value


def test_status_desconhecido_vira_registrado_nunca_liquidado(client, itau_env, monkeypatch):
    """Status que o mapa não conhece é tratado como em aberto.

    É o erro barato: dizer 'pago' sem estar libera mercadoria de graça.
    """
    _capture(monkeypatch, {"id_boleto": "IT-1", "status": "SITUACAO_QUE_NAO_EXISTE_AINDA"})
    assert client.post("/cobranca", json=_corpo()).json()["status"] == Status.registrado.value


# --- catálogo: o que o provider DECLARA ---------------------------------------

def test_catalogo_declara_so_o_que_existe(client):
    """`GET /bancos` é introspecção — não pode anunciar o que não foi escrito.

    PDF, Pix e webhook ficam de fora enquanto o contrato não é confirmado; o dia
    em que forem implementados, o catálogo os anuncia sozinho.
    """
    itau = next(b for b in client.get("/bancos").json()["bancos"] if b["id"] == "itau")
    assert itau["codigo_banco"] == "341"
    caps = set(itau["capacidades"])
    assert {"boleto", "boleto_alteracao", "boleto_baixa"} <= caps
    assert not caps & {"boleto_pdf", "pix", "pix_automatico", "bolepix", "webhook_banco"}


def test_consulta_e_baixa_usam_o_id(client, itau_env, monkeypatch):
    calls = _capture(monkeypatch, {"id_boleto": "IT-7", "status": "PAGO"}, {})
    r = client.get("/cobranca/IT-7", params={"tenant_id": "empresa1", "provider": "itau"})
    assert r.status_code == 200 and r.json()["status"] == Status.liquidado.value
    assert calls[0]["method"] == "GET" and calls[0]["path"].endswith("/boletos/IT-7")

    r2 = client.delete("/cobranca/IT-7", params={"tenant_id": "empresa1", "provider": "itau"})
    assert r2.status_code == 200 and r2.json()["status"] == Status.baixado.value
    assert calls[1]["method"] == "DELETE"


# --- PDF pela engine: a decisão de produto e a armadilha dela ------------------
#
# O Itaú registra e devolve linha digitável + código de barras, mas não o PDF.
# A decisão é: quem precisa do PDF renderiza pela engine (o 341 já existe lá).
#
# Isso só é seguro por uma propriedade: o código de barras é DETERMINÍSTICO —
# função pura de banco, vencimento, valor, agência/conta/carteira e nosso
# número. Renderizar com o que o banco registrou dá o MESMO boleto; renderizar
# com um dígito diferente dá um boleto que ninguém consegue conciliar.
#
# Estes dois testes existem para que essa propriedade não se perca em silêncio
# numa versão futura da engine.

_CONVENIO_341 = {"agencia": "3073", "conta_corrente": "12345", "carteira": "109",
                 "cedente": "Empresa Teste LTDA", "documento_cedente": "11222333000181",
                 "sacado": "Joao da Silva", "sacado_documento": "52998224725",
                 "valor": 150.0, "data_vencimento": "2026-12-31"}


def test_barras_e_deterministico_mesma_entrada_mesmo_boleto():
    from app.core import pycob
    registrado = {**_CONVENIO_341, "nosso_numero": "12345678"}
    assert (pycob.dados_boleto("itau", registrado)["codigo_barras"]
            == pycob.dados_boleto("itau", registrado)["codigo_barras"])


def test_divergencia_de_nosso_numero_muda_o_barras_e_e_detectavel():
    """Um dígito diferente do registrado já muda o código de barras.

    É por isso que o fluxo de PDF do Itaú **exige conferência**: comparar a
    linha digitável que a engine calculou com a que o banco devolveu. Iguais,
    o PDF é o boleto registrado; diferentes, algum campo divergiu e o PDF não
    pode ser entregue ao pagador.
    """
    from app.core import pycob
    do_banco = pycob.dados_boleto("itau", {**_CONVENIO_341, "nosso_numero": "12345678"})
    renderizado = pycob.dados_boleto("itau", {**_CONVENIO_341, "nosso_numero": "12345679"})
    assert do_banco["linha_digitavel"] != renderizado["linha_digitavel"]


def test_pdf_online_responde_422_dizendo_para_onde_ir(client, itau_env, monkeypatch):
    """`GET /cobranca/{id}/pdf` no Itaú não pode falhar em silêncio.

    O banco não devolve PDF, mas ele EXISTE pelo caminho offline — a mensagem
    entrega o slug pronto em vez de deixar o integrador procurar defeito onde
    não há.
    """
    _capture(monkeypatch, {})
    r = client.get("/cobranca/IT-1/pdf", params={"tenant_id": "empresa1", "provider": "itau"})
    assert r.status_code == 422
    detalhe = r.json()["detail"]
    assert "não devolve PDF" in detalhe
    assert "/api/render/boleto" in detalhe and "bank='itau'" in detalhe
    assert "linha digitável" in detalhe, "tem de lembrar da conferência"
