#!/usr/bin/env python3
"""Executa o Roteiro de Testes C6 v3.0 **contra a API**, e imprime o que o banco pede.

O que está sendo homologado é o **serviço**, não o provider. Por isso cada caso
aqui é uma requisição HTTP às rotas do gateway — router, schema, validação,
`exige_capacidade` e tradução de erro incluídos. Chamar `C6Provider` direto
pularia exatamente a camada que o integrador enxerga, e o relatório atestaria
uma coisa enquanto o cliente consome outra.

O corpo registrado é a resposta **da API**, que carrega a do banco em `raw` —
estritamente mais evidência do que o retorno cru do C6.

**Nada é inventado.** O que sai daqui é resposta real; caso que falha entra com
o status e o corpo do erro, porque em homologação a recusa também é evidência.

Uso (dentro da janela do sandbox — seg-sex, 7h-23h BRT):

    export C6_SANDBOX_CLIENT_ID=... C6_SANDBOX_CLIENT_SECRET=...
    export C6_SANDBOX_CERT_PEM="$(cat cert.crt)" C6_SANDBOX_KEY_PEM="$(cat cert.key)"
    # ou, para quem tem o material em PKCS12:
    export C6_SANDBOX_PFX_BASE64=... C6_SANDBOX_PFX_PASSWORD=...
    export C6_SANDBOX_CHAVE_PIX=...

    PYTHONPATH=gateway python scripts/homologacao_c6.py --json > evidencia.json
    PYTHONPATH=gateway python scripts/homologacao_c6.py B_01 P_01_01   # alguns
    PYTHONPATH=gateway python scripts/homologacao_c6.py --base-url https://... # instância real

Sem `--base-url` a app é exercitada em processo (ASGI), o que percorre a mesma
pilha de rotas — só não cruza um socket.

Casos AUSENTES (declarados em `AUSENTES`, nunca executados):
  AP_01..AP_06  saída de dinheiro — fora do escopo do produto
  P_04_01..04   o gateway consome a `location` da cob; não gerencia o recurso

Ausente também sai de `SemMassa`, levantada em tempo de execução quando o caso
depende de dado que o ambiente não tem (P_05_01/03/04: a conta sandbox nunca
recebeu Pix). É exceção e não entrada fixa de propósito — no dia em que houver
um Pix na conta, os casos rodam sem ninguém lembrar de mexer aqui.

Ausente não é falha. Executar e reportar erro poluiria a evidência — o banco
leria falha de integração onde há fronteira de escopo deliberada.
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import uuid
from datetime import date, datetime, timedelta

FALTANDO = [v for v in ("C6_SANDBOX_CLIENT_ID", "C6_SANDBOX_CLIENT_SECRET")
            if not os.environ.get(v)]
if FALTANDO:
    sys.exit(f"faltam credenciais no ambiente: {', '.join(FALTANDO)}")

TENANT = os.environ.get("HML_TENANT", "homologacao")

# O gateway lê credenciais do cofre por (tenant, provider). Injeta as do sandbox
# antes de importar a app, para que os requests não precisem carregá-las.
# `cert_pem`/`key_pem` entram porque é ASSIM que o C6 entrega o certificado: o
# par .crt + .key, não PKCS12. Exigir PFX aqui obrigava um `openssl pkcs12
# -export` antes de rodar o roteiro — passo manual, com a chave privada passando
# por linha de comando. Os dois formatos valem; quem já converteu segue igual.
for env_alvo, env_fonte in (
    ("client_id", "C6_SANDBOX_CLIENT_ID"), ("client_secret", "C6_SANDBOX_CLIENT_SECRET"),
    ("pfx_base64", "C6_SANDBOX_PFX_BASE64"), ("pfx_password", "C6_SANDBOX_PFX_PASSWORD"),
    ("cert_pem", "C6_SANDBOX_CERT_PEM"), ("key_pem", "C6_SANDBOX_KEY_PEM"),
):
    valor = os.environ.get(env_fonte, "")
    if valor:
        os.environ[f"VAULT__{TENANT}__c6__{env_alvo}"] = valor
# Sem isto o provider=c6 cai no fallback CNAB offline e a homologação atestaria
# o caminho errado.
os.environ["C6_REGISTERED_READY"] = "true"
# O webhook de entrada é FAIL-CLOSED desde a 2.2.0: sem WEBHOOK_TOKEN__C6 a
# rota responde 401 antes de olhar o corpo. O roteiro configura o token e o
# envia em C_05_01 — igual a produção, onde a URL cadastrada no banco carrega
# ?token=<segredo>. Sem isto o caso atestaria o contrato antigo, que não existe
# mais.
os.environ.setdefault("WEBHOOK_TOKEN__C6", "roteiro-c6")
os.environ.setdefault("C6_BILLING_SCHEME", "21")

CHAVE_PIX = os.environ.get("C6_SANDBOX_CHAVE_PIX", "")
VENC = (date.today() + timedelta(days=30)).isoformat()
ESTADO: dict[str, str] = {}


class Api:
    """Cliente HTTP do gateway — em processo (ASGI) ou contra instância real."""

    def __init__(self, base_url: str | None) -> None:
        if base_url:
            import httpx
            self._c = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        else:
            from fastapi.testclient import TestClient

            from app.main import app
            self._c = TestClient(app, raise_server_exceptions=False)

    def __call__(self, metodo: str, path: str, **kw):
        r = self._c.request(metodo, path, **kw)
        try:
            corpo = r.json()
        except ValueError:
            corpo = {"conteudo": r.text[:2000]}
        return r.status_code, corpo


API: Api = None  # type: ignore[assignment]


def _q(**extra) -> dict:
    return {"tenant_id": TENANT, "provider": "c6", **extra}


def _pagador() -> dict:
    # `neighborhood` não é enfeite: o /v2/bank_slips do C6 recusa o Bolepix sem
    # bairro ("Debtor neighborhood is required to generate payment method").
    return {"nome": "Teste Homologacao", "documento": "12345678909",
            "endereco": {"street": "Av. Teste", "number": 100, "neighborhood": "Centro",
                         "city": "Sete Lagoas", "state": "MG", "zip_code": "35700000"}}


def _cobranca(**extra) -> dict:
    c = {"valor": "10.00", "vencimento": VENC, "seu_numero": uuid.uuid4().hex[:10],
         "pagador": _pagador()}
    c.update(extra)
    return {"tenant_id": TENANT, "provider": "c6", "cobranca": c}


def _txid() -> str:
    return "".join(random.SystemRandom().choices(string.ascii_lowercase + string.digits, k=30))


def _janela(dias: int = 7) -> tuple[str, str]:
    fim = date.today()
    ini = fim - timedelta(days=dias)
    return f"{ini.isoformat()}T00:00:00Z", f"{fim.isoformat()}T23:59:59Z"


# --- casos: cada um devolve (status_code, corpo) da API ----------------------------

def at_01():
    """Token da API — o mecanismo que o integrador usa, sobre a auth do banco."""
    return API("POST", "/credenciais", json={
        "tenant_id": TENANT, "provider": "c6",
        "credentials": {
            "client_id": os.environ["C6_SANDBOX_CLIENT_ID"],
            "client_secret": os.environ["C6_SANDBOX_CLIENT_SECRET"],
            "pfx_base64": os.environ.get("C6_SANDBOX_PFX_BASE64", ""),
            "pfx_password": os.environ.get("C6_SANDBOX_PFX_PASSWORD", ""),
            "cert_pem": os.environ.get("C6_SANDBOX_CERT_PEM", ""),
            "key_pem": os.environ.get("C6_SANDBOX_KEY_PEM", ""),
        }})


def b_01():
    st, b = API("POST", "/cobranca", json=_cobranca())
    if isinstance(b, dict) and b.get("id"):
        ESTADO["boleto_id"] = b["id"]
    return st, b


def b_02():
    return API("POST", "/cobranca", json=_cobranca(
        multa={"type": "P", "value": 2.0, "dead_line": 1},
        juros={"type": "P", "value": 1.0, "dead_line": 1}))


def b_03():
    return API("POST", "/cobranca", json=_cobranca(
        desconto={"discount_type": "V", "first": {"value": 1.0, "dead_line": 5}}))


def b_04():
    # tenant_id/provider são query nesta rota; o corpo é o dicionário `campos`
    # puro. Mandar tudo no corpo devolvia 422 da nossa própria validação — e
    # 422 nosso no relatório do banco se lê como recusa do banco.
    #
    # Boleto PRÓPRIO, não o do B_01: o B_08 cancela aquele, e o banco recusa
    # alterar boleto cancelado ("Cannot update boleto ... with status
    # CANCELLED"). Compartilhar o recurso fazia a ordem de re-tentativa decidir
    # o resultado — alterar depois de cancelar não tem sentido nenhum.
    if not ESTADO.get("boleto_alterar_id"):
        st, b = API("POST", "/cobranca", json=_cobranca())
        if not (isinstance(b, dict) and b.get("id")):
            return st, b
        ESTADO["boleto_alterar_id"] = b["id"]
    novo = (date.today() + timedelta(days=45)).isoformat()
    return API("PUT", f"/cobranca/{ESTADO['boleto_alterar_id']}", params=_q(),
               json={"due_date": novo})


def b_05():
    return API("GET", f"/cobranca/{ESTADO['boleto_id']}", params=_q())


def b_06():
    st, b = API("GET", f"/cobranca/{ESTADO['boleto_id']}/pdf", params=_q())
    if isinstance(b, dict) and b.get("pdf_base64"):
        b = {**b, "pdf_base64": f"<{len(b['pdf_base64'])} chars de base64>"}
    return st, b


def b_07():
    return API("POST", "/config/webhook-banco", json={
        "tenant_id": TENANT, "provider": "c6",
        "url": "https://exemplo.com.br/webhooks/c6", "service": "BANK_SLIP"})


def b_08():
    return API("DELETE", f"/cobranca/{ESTADO['boleto_id']}", params=_q())


def p_01_01():
    txid = _txid()
    ESTADO["txid_cob"] = txid
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "c6", "account_config": {"chave_pix": CHAVE_PIX},
        "pix": {"valor": "1.00", "descricao": "homologacao", "txid": txid}})


def p_01_02():
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "c6", "account_config": {"chave_pix": CHAVE_PIX},
        "pix": {"valor": "1.00", "descricao": "homologacao sem txid"}})


def p_01_03():
    return API("PATCH", f"/pix/{ESTADO['txid_cob']}", params=_q(),
               json={"valor": {"original": "2.00"}})


def p_01_04():
    return API("GET", f"/pix/{ESTADO['txid_cob']}", params=_q())


def p_01_05():
    ini, fim = _janela()
    return API("GET", "/pix", params=_q(inicio=ini, fim=fim))


def p_02_01():
    txid = _txid()
    ESTADO["txid_cobv"] = txid
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "c6", "account_config": {"chave_pix": CHAVE_PIX},
        "pix": {"valor": "1.00", "descricao": "homologacao cobv", "txid": txid,
                "data_vencimento": VENC,
                "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"}}})


def p_02_02():
    return API("PATCH", f"/pix/{ESTADO['txid_cobv']}", params=_q(vencimento="true"),
               json={"valor": {"original": "2.00"}})


def p_02_03():
    return API("GET", f"/pix/{ESTADO['txid_cobv']}", params=_q(vencimento="true"))


def p_02_04():
    ini, fim = _janela()
    return API("GET", "/pix", params=_q(inicio=ini, fim=fim, vencimento="true"))


class SemMassa(RuntimeError):
    """O caso não pôde rodar por falta de dado no ambiente, não por defeito.

    Vira AUSENTE no relatório, com o motivo — e não falha. O banco lê uma falha
    como recusa de integração, e essas três não são: a conta sandbox nunca
    recebeu Pix, então não há e2eid para consultar nem devolver.

    É exceção e não entrada fixa em AUSENTES de propósito: no dia em que houver
    um Pix recebido na conta, os casos rodam de verdade sem ninguém lembrar de
    mexer aqui.
    """


def p_05_02():
    ini, fim = _janela()
    st, b = API("GET", "/pix/recebidos", params=_q(inicio=ini, fim=fim))
    itens = (b or {}).get("pix") or [] if isinstance(b, dict) else []
    if itens:
        ESTADO["e2eid"] = itens[0].get("endToEndId", "")
    return st, b


def p_05_01():
    if not ESTADO.get("e2eid"):
        raise SemMassa("sem Pix recebido no sandbox: não há e2eid para consultar. A conta nunca recebeu Pix (o único lançamento do extrato é uma tarifa). A rota existe e está coberta por teste — gateway/tests/test_pix_automatico.py::test_pix_recebidos_e_devolucao; falta a massa")
    return API("GET", f"/pix/recebidos/{ESTADO['e2eid']}", params=_q())


def p_05_03():
    if not ESTADO.get("e2eid"):
        raise SemMassa("sem Pix recebido no sandbox: não há devolução a solicitar. A rota existe e está coberta por teste — gateway/tests/test_pix_automatico.py::test_pix_recebidos_e_devolucao; falta a massa")
    dev = _txid()
    ESTADO["devolucao_id"] = dev
    return API("PUT", f"/pix/recebidos/{ESTADO['e2eid']}/devolucao/{dev}",
               json={"tenant_id": TENANT, "provider": "c6", "valor": "0.01"})


def p_05_04():
    if not ESTADO.get("devolucao_id"):
        raise SemMassa("sem Pix recebido no sandbox: a etapa anterior não criou devolução. A rota existe e está coberta por teste — gateway/tests/test_pix_automatico.py::test_pix_recebidos_e_devolucao; falta a massa")
    return API("GET", f"/pix/recebidos/{ESTADO['e2eid']}/devolucao/{ESTADO['devolucao_id']}",
               params=_q())


def _exige_chave() -> None:
    if not CHAVE_PIX:
        raise RuntimeError("C6_SANDBOX_CHAVE_PIX não definida")


def p_06_01():
    _exige_chave()
    return API("PUT", "/config/webhook-pix", json={
        "tenant_id": TENANT, "provider": "c6", "chave": CHAVE_PIX,
        "url": "https://exemplo.com.br/webhooks/c6/pix"})


def p_06_02():
    _exige_chave()
    return API("GET", "/config/webhook-pix", params=_q(chave=CHAVE_PIX))


def p_06_03():
    _exige_chave()
    return API("DELETE", "/config/webhook-pix", params=_q(chave=CHAVE_PIX))


def e_01():
    fim = date.today().isoformat()
    ini = (date.today() - timedelta(days=30)).isoformat()
    return API("GET", "/extrato", params=_q(start_date=ini, end_date=fim))


def _conciliacao(rota: str):
    fim = date.today().isoformat()
    ini = (date.today() - timedelta(days=30)).isoformat()
    return API("GET", f"/conciliacao/{rota}", params=_q(start_date=ini, end_date=fim,
                                                        page=1, size=10))


def tr_01():
    return _conciliacao("recebiveis")


def tr_02():
    return _conciliacao("transacoes")


def bp_01():
    ref = "".join(random.SystemRandom().choices(string.ascii_uppercase + string.digits, k=26))
    ESTADO["bolepix_ref"] = ref
    return API("POST", "/bolepix", json={
        "tenant_id": TENANT, "provider": "c6", "account_config": {"chave_pix": CHAVE_PIX},
        "bolepix": {"external_reference_id": ref, "valor": "10.00", "vencimento": VENC,
                    "descricao": "Bolepix homologacao", "pagador": _pagador()}})


def bp_01_02():
    """O formulário pede o external_reference_id REPETIDO: o C6 devolve 201 com
    os dados da cobrança que já existe, em vez de criar outra. Reusa o ref do
    BP_01_01 de propósito — é o duplicado que está sendo testado."""
    ref = ESTADO.get("bolepix_ref")
    if not ref:
        raise RuntimeError("BP_01_01 não devolveu external_reference_id para duplicar")
    return API("POST", "/bolepix", json={
        "tenant_id": TENANT, "provider": "c6", "account_config": {"chave_pix": CHAVE_PIX},
        "bolepix": {"external_reference_id": ref, "valor": "10.00", "vencimento": VENC,
                    "descricao": "Bolepix homologacao (ref duplicado)", "pagador": _pagador()}})


def bp_02():
    return API("GET", f"/bolepix/{ESTADO['bolepix_ref']}", params=_q())


def bp_03():
    st, b = API("GET", f"/bolepix/{ESTADO['bolepix_ref']}/pdf", params=_q())
    if isinstance(b, dict) and b.get("pdf_base64"):
        b = {**b, "pdf_base64": f"<{len(b['pdf_base64'])} chars de base64>"}
    return st, b


def bp_04():
    return API("DELETE", f"/bolepix/{ESTADO['bolepix_ref']}", params=_q())


def c_01():
    st, b = API("POST", "/checkout", json={
        "tenant_id": TENANT, "provider": "c6",
        "checkout": {"valor": "150.00", "descricao": "Checkout homologacao"}})
    if isinstance(b, dict) and b.get("id"):
        ESTADO["checkout_id"] = b["id"]
        if isinstance(b.get("raw"), dict):
            ESTADO["checkout_raw"] = b["raw"]  # o corpo do banco, para C_05_01
        if b.get("url"):
            ESTADO["checkout_url"] = b["url"]  # a página hospedada, para C_05_02
    return st, b


def c_02():
    return API("GET", f"/checkout/{ESTADO['checkout_id']}", params=_q())


def c_03():
    return API("DELETE", f"/checkout/{ESTADO['checkout_id']}", params=_q())


def c_04():
    return API("POST", "/config/webhook-banco", json={
        "tenant_id": TENANT, "provider": "c6",
        "url": "https://exemplo.com.br/webhooks/c6", "service": "CHECKOUT"})


def c_05_02():
    """Evento de pagamento do link.

    NÃO é N/A: o caso está no escopo e implementado. O que impede de concluí-lo
    é o ambiente do banco — a página hospedada onde o pagamento acontece não
    abre. Marcar "não se aplica" esconderia um defeito do C6 atrás da nossa
    declaração de escopo, e é justamente o contrário do que a homologação
    serve para mostrar.

    Este é o único caso que sonda algo fora da nossa API: a evidência aqui é o
    que a página do banco responde, porque é ela que está no caminho. O
    tratamento do evento existe e está coberto por
    gateway/tests/test_c6_checkout.py (checkout.atualizado → liquidado)."""
    import httpx

    url = ESTADO.get("checkout_url")
    if not url:
        raise RuntimeError("C_01 não devolveu a URL da página de pagamento")
    ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0 Safari/537.36")
    try:
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        return None, {"observacao": "página hospedada do C6, fora da nossa API",
                      "url": url, "erro": f"{type(e).__name__}: {e}"}
    titulo = ""
    if "<title>" in r.text:
        titulo = r.text.split("<title>", 1)[1].split("</title>", 1)[0].strip()
    return r.status_code, {
        "observacao": "GET na página hospedada de pagamento do C6 — fora da nossa API. "
                      "É nela que o pagador digita o cartão, e é o pagamento que emite o "
                      "evento deste caso. Sem acesso à página não há pagamento a notificar.",
        "url": url,
        "title": titulo,
        "trecho": r.text[:400],
    }


def c_05_01():
    """Recebimento do evento de criação de link.

    O corpo entregue é **o que o C6 devolveu em C_01**, reentregue na rota que
    o banco chamaria — não há URL pública neste ambiente para o sandbox
    chamar de volta. O que se atesta aqui é o nosso lado: a rota reconhece o
    evento como checkout e normaliza o status. O retorno registrado é real."""
    corpo = ESTADO.get("checkout_raw")
    if not corpo:
        raise RuntimeError("C_01 não devolveu o corpo do banco para reentregar")
    token = os.environ["WEBHOOK_TOKEN__C6"]
    return API("POST", f"/webhooks/c6/{TENANT}", params={"token": token}, json=corpo)



# --- P_03: o roteiro decompoe o lote em 4 etapas ----------------------------------

def _lote_id() -> str:
    if "lote_id" not in ESTADO:
        ESTADO["lote_id"] = _txid()[:20]
    return ESTADO["lote_id"]


def p_03_01():
    # O campo do contrato é `cobrancas` (lista de PixCobranca canônica) — o
    # router é que traduz para o `cobsv` do BACEN. E lote vazio não é lote:
    # sem item o banco não tem o que criar, e a evidência não provaria nada.
    return API("PUT", f"/pix/lote/{_lote_id()}", json={
        "tenant_id": TENANT, "provider": "c6",
        "account_config": {"chave_pix": CHAVE_PIX},
        "descricao": "homologacao",
        "cobrancas": [{
            "valor": "1.00", "txid": _txid(), "data_vencimento": VENC,
            "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"},
        }]})



def p_03_02():
    # Revisão do lote: só as cobranças enviadas mudam. O txid é o MESMO de
    # p_03_01 — revisar um txid que não está no lote não seria revisão, seria
    # inclusão, e o banco recusaria por outro motivo que não o do caso.
    return API("PATCH", f"/pix/lote/{_lote_id()}", json={
        "tenant_id": TENANT, "provider": "c6",
        "account_config": {"chave_pix": CHAVE_PIX},
        "cobrancas": [{
            "valor": "2.00", "txid": _txid(), "data_vencimento": VENC,
            "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"},
        }]})


def p_03_03():
    return API("GET", f"/pix/lote/{_lote_id()}", params=_q())


def p_03_04():
    ini, fim = _janela()
    return API("GET", "/pix/lotes", params=_q(inicio=ini, fim=fim))


# --- PA: as quatro jornadas do Pix Automatico, etapa a etapa ----------------------

_REC = {
    "contrato": "CT-HML-001", "objeto": "Homologacao",
    "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"},
    "periodicidade": "MENSAL", "data_inicial": (date.today() + timedelta(days=7)).isoformat(),
    "valor_fixo": "10.00", "politica_retentativa": "PERMITE_3R_7D",
}


def _campo(corpo, nome: str) -> str:
    """O C6 devolve o recurso dentro de `data` no Pix Automático; outras rotas
    devolvem cru. Ler só a raiz deixava as quatro jornadas mortas na etapa 1 —
    com `201 CRIADA` no corpo e 'nao devolveu idRec' no relatório."""
    if not isinstance(corpo, dict):
        return ""
    dados = corpo.get("data") if isinstance(corpo.get("data"), dict) else corpo
    return dados.get(nome) or corpo.get(nome) or ""


def _criar_rec(chave_estado: str, **extra):
    rec = {**_REC, **extra}
    st, b = API("POST", "/pix-automatico/recorrencias",
                json={"tenant_id": TENANT, "provider": "c6", "recorrencia": rec})
    if _campo(b, "idRec"):
        ESTADO[chave_estado] = _campo(b, "idRec")
    return st, b


def _locrec():
    return API("POST", "/pix-automatico/locations", params=_q())


def _webhookrec():
    return API("PUT", "/pix-automatico/config/webhooks", params=_q(),
               json={"url_recorrencia": "https://exemplo.com.br/webhooks/c6/rec",
                     "url_cobranca": "https://exemplo.com.br/webhooks/c6/cobr"})


def _consultar_rec(chave_estado: str, com_txid: bool = False):
    id_rec = ESTADO.get(chave_estado)
    if not id_rec:
        raise RuntimeError("a etapa anterior nao devolveu idRec")
    params = _q(txid=ESTADO["txid_rec"]) if com_txid and ESTADO.get("txid_rec") else _q()
    return API("GET", f"/pix-automatico/recorrencias/{id_rec}", params=params)


# Jornada 1 — autorizacao pelo app do pagador (solicrec)
def pa_01_01():
    return _criar_rec("id_rec_j1")


def pa_01_02():
    id_rec = ESTADO.get("id_rec_j1")
    if not id_rec:
        raise RuntimeError("PA_01_01 nao devolveu idRec")
    st, b = API("POST", "/pix-automatico/solicitacoes", json={
        "tenant_id": TENANT, "provider": "c6",
        # BACEN aqui é estrito e o banco recusa duas coisas de uma vez:
        # dataExpiracaoSolicitacao é date-time RFC 3339 (não `date`), e
        # destinatario é conta bancária — {agencia, conta, cpf|cnpj,
        # ispbParticipante} — sem `nome`. Dados bancários conforme o exemplo
        # `solicRecBody1` da própria spec do C6.
        "dados": {"idRec": id_rec,
                  "calendario": {"dataExpiracaoSolicitacao": f"{VENC}T23:59:59Z"},
                  "destinatario": {"agencia": "2569", "conta": "550689",
                                   "cpf": "12345678909", "ispbParticipante": "91193552"}}})
    if _campo(b, "idSolicRec"):
        ESTADO["id_solic"] = _campo(b, "idSolicRec")
    return st, b


def pa_01_03():
    if not ESTADO.get("id_solic"):
        raise RuntimeError("PA_01_02 nao devolveu idSolicRec")
    return API("GET", f"/pix-automatico/solicitacoes/{ESTADO['id_solic']}", params=_q())


# Jornada 2 — agendamento via QR de adesao (locrec)
def pa_02_01():
    return _locrec()


def pa_02_02():
    return _criar_rec("id_rec_j2")


def pa_02_03():
    return _webhookrec()


def pa_02_04():
    return _consultar_rec("id_rec_j2")


# Jornada 3 — execucao, com txid de ativacao
def pa_03_01():
    return _locrec()


def pa_03_02():
    ESTADO["txid_rec"] = _txid()
    return _criar_rec("id_rec_j3")


def pa_03_03():
    return _webhookrec()


def pa_03_04():
    return _consultar_rec("id_rec_j3", com_txid=True)


# Jornada 4 — gestao (alteracao / cancelamento)
def pa_04_01():
    return _locrec()


def pa_04_02():
    return _criar_rec("id_rec_j4")


def pa_04_03():
    return _webhookrec()


def pa_04_04():
    id_rec = ESTADO.get("id_rec_j4")
    if not id_rec:
        raise RuntimeError("PA_04_02 nao devolveu idRec")
    return API("PATCH", f"/pix-automatico/recorrencias/{id_rec}", params=_q(),
               json={"status": "CANCELADA"})


# --- ausentes: NAO sao executados ------------------------------------------------
#
# Caso que nao pertence ao produto nao e testado nem "falha": ele consta como
# AUSENTE, com o motivo. Rodar e reportar erro poluiria a evidencia -- o banco
# leria uma falha de integracao onde ha uma fronteira de escopo deliberada.

AUSENTES: dict[str, tuple[str, str]] = {
    "AP_01": ("Enviar grupo de pagamentos para decode", "fora do escopo do produto: saída de dinheiro; a Cobranca-API é cobrança (entrada)"),
    "AP_02": ("Consultar DDA", "fora do escopo do produto: saída de dinheiro"),
    "AP_03": ("Obter itens de um grupo de pagamentos", "fora do escopo do produto: saída de dinheiro"),
    "AP_04": ("Remover lista de pagamentos de um grupo", "fora do escopo do produto: saída de dinheiro"),
    "AP_05": ("Remover pagamento específico do grupo", "fora do escopo do produto: saída de dinheiro"),
    "AP_06": ("Enviar grupo de pagamentos para aprovação", "fora do escopo do produto: saída de dinheiro"),
    "P_04_01": ("Criar location do payload", "fora do escopo: o gateway consome a location devolvida na cob; não gerencia o recurso"),
    "P_04_02": ("Consultar locations cadastradas", "fora do escopo: idem P_04_01"),
    "P_04_03": ("Recuperar location específica", "fora do escopo: idem P_04_01"),
    "P_04_04": ("Desvincular cobrança de uma location", "fora do escopo: idem P_04_01"),
}


CASOS = [
    ("AT_01", "Geração do token de sessão", at_01),
    ("B_01", "Emissão de boleto simples", b_01),
    ("B_02", "Emissão com juros e multa variáveis", b_02),
    ("B_03", "Emissão com desconto", b_03),
    ("B_05", "Consulta de boleto", b_05),
    ("B_06", "Geração de PDF do boleto", b_06),
    ("B_07", "Cadastro do webhook de boleto", b_07),
    ("B_04", "Alteração de dados do boleto", b_04),
    ("B_08", "Baixa / cancelamento", b_08),
    ("P_01_01", "Criar cobrança imediata com txid", p_01_01),
    ("P_01_02", "Criar cobrança imediata sem txid", p_01_02),
    ("P_01_03", "Revisar cobrança imediata", p_01_03),
    ("P_01_04", "Consultar cobrança imediata", p_01_04),
    ("P_01_05", "Consultar lista de cobranças imediatas", p_01_05),
    ("P_02_01", "Criar cobrança com vencimento com txid", p_02_01),
    ("P_02_02", "Revisar cobrança com vencimento", p_02_02),
    ("P_02_03", "Consultar cobrança com vencimento", p_02_03),
    ("P_02_04", "Consultar lista de cobranças com vencimento", p_02_04),
    ("P_03_01", "Criar lote de cobranças com vencimento", p_03_01),
    ("P_03_02", "Revisar cobranças dentro do lote", p_03_02),
    ("P_03_03", "Consultar lote específico", p_03_03),
    ("P_03_04", "Consultar lista de lotes", p_03_04),
    ("P_05_02", "Consultar lista de Pix recebidos", p_05_02),
    ("P_05_01", "Consultar Pix recebido específico", p_05_01),
    ("P_05_03", "Solicitar devolução", p_05_03),
    ("P_05_04", "Consultar devolução", p_05_04),
    ("P_06_01", "Cadastrar webhook Pix", p_06_01),
    ("P_06_02", "Consultar webhook", p_06_02),
    ("P_06_03", "Excluir webhook", p_06_03),
    ("E_01", "Consulta de extrato", e_01),
    ("TR_01", "Consulta de recebíveis", tr_01),
    ("TR_02", "Consulta de transações", tr_02),
    ("BP_01_01", "Criar cobrança Bolepix com sucesso", bp_01),
    ("BP_01_02", "Criar cobrança com external_reference_id duplicado", bp_01_02),
    ("BP_02", "Consultar cobrança Bolepix", bp_02),
    ("BP_03", "Consultar PDF de Bolepix", bp_03),
    ("BP_04", "Cancelar Bolepix", bp_04),
    ("C_01", "Criação de checkout", c_01),
    ("C_02", "Consulta de checkout", c_02),
    ("C_03", "Cancelamento de checkout", c_03),
    ("C_04", "Cadastro de webhook de checkout", c_04),
    ("C_05_01", "Recebimento de evento de criação de link via webhook", c_05_01),
    ("C_05_02", "Recebimento de evento de pagamento de link via webhook", c_05_02),
    ("PA_01_01", "Jornada 1 — criar recorrência (rec)", pa_01_01),
    ("PA_01_02", "Jornada 1 — solicitar autorização (solicrec)", pa_01_02),
    ("PA_01_03", "Jornada 1 — consultar solicitação", pa_01_03),
    ("PA_02_01", "Jornada 2 — criar location de adesão (locrec)", pa_02_01),
    ("PA_02_02", "Jornada 2 — criar recorrência", pa_02_02),
    ("PA_02_03", "Jornada 2 — configurar webhookrec", pa_02_03),
    ("PA_02_04", "Jornada 2 — consultar recorrência", pa_02_04),
    ("PA_03_01", "Jornada 3 — criar location", pa_03_01),
    ("PA_03_02", "Jornada 3 — criar recorrência com txid de ativação", pa_03_02),
    ("PA_03_03", "Jornada 3 — configurar webhookrec", pa_03_03),
    ("PA_03_04", "Jornada 3 — consultar recorrência por txid", pa_03_04),
    ("PA_04_01", "Jornada 4 — criar location", pa_04_01),
    ("PA_04_02", "Jornada 4 — criar recorrência", pa_04_02),
    ("PA_04_03", "Jornada 4 — configurar webhookrec", pa_04_03),
    ("PA_04_04", "Jornada 4 — gestão: alterar/cancelar", pa_04_04),
]

# B_04 e B_08 vêm depois de B_05/B_06 de propósito: alterar e baixar exigem que o
# registro tenha passado pela CIP, e o roteiro na ordem do papel falharia por
# assincronia do banco, não por defeito.


def _sem_token(item: dict) -> dict:
    """Mascara o `bapi_` antes de a evidência sair daqui.

    O token não é um identificador: é a CHAVE que decifra as credenciais
    guardadas (`core/credential_store`). A evidência é versionada — e
    `core/vault.py` é explícito: "NUNCA versionar em git". O que o relatório
    precisa provar é que o cadastro devolveu um token, não qual.
    """
    corpo = item.get("response_body")
    if isinstance(corpo, dict) and isinstance(corpo.get("token"), str):
        item = {**item, "response_body": {**corpo, "token": "bapi_<mascarado>"}}
    return item


def main() -> int:
    global API
    argv = sys.argv[1:]
    base_url = None
    for i, a in enumerate(argv):
        if a == "--base-url" and i + 1 < len(argv):
            base_url = argv[i + 1]
    so_json = "--json" in argv
    alvos = [a for a in argv if not a.startswith("--") and a != base_url]

    API = Api(base_url)
    onde = base_url or "app em processo (ASGI)"
    if not so_json:
        print(f"# roteiro contra a API — {onde}, tenant '{TENANT}'\n")

    resultados = []
    for cid, nome, fn in CASOS:
        if alvos and cid not in alvos:
            continue
        try:
            status, corpo = fn()
            ok = 200 <= status < 300
            item = {"caso": cid, "nome": nome, "ok": ok,
                    "status_code": status, "response_body": corpo}
        except SemMassa as e:
            item = {"caso": cid, "nome": nome, "ausente": True, "motivo": str(e),
                    "ok": None, "status_code": None, "response_body": None}
        except Exception as e:  # noqa: BLE001 — o erro É o resultado a reportar
            item = {"caso": cid, "nome": nome, "ok": False, "status_code": None,
                    "erro": f"{type(e).__name__}: {e}", "response_body": None}
        resultados.append(item)
        if not so_json:
            print(f"\n{'='*72}\n{cid} — {nome}\n{'='*72}")
            print(f"Status Code - Retornado: {item.get('status_code') or 'erro'}")
            if item.get("erro"):
                print(f"  ⚠ {item['erro']}")
            print("\nResponse Body - Retornado:")
            print(json.dumps(item["response_body"], ensure_ascii=False, indent=2, default=str))

    # Repescagem da CIP. O registro do boleto no C6 é assíncrono: alterar,
    # baixar ou cancelar segundos depois da emissão devolve 409 enquanto a CIP
    # não aprova — e esse 409 não é defeito de integração, é relógio. Rodar de
    # novo no fim dá ao registro o tempo do roteiro inteiro (~15 min) em vez dos
    # segundos que ele teve na primeira passada. Substitui o resultado no lugar:
    # duplicar a entrada mandaria a evidência para a tabela errada do formulário.
    # 5xx entra junto: erro interno do banco é transitório por definição
    # (PA_01_02 devolveu 500 em /solicrec e 201 na execução seguinte).
    pendentes = [i for i, r in enumerate(resultados)
                 if r.get("status_code") == 409 or (r.get("status_code") or 0) >= 500]
    if pendentes:
        por_id = {c: (n, f) for c, n, f in CASOS}
        if not so_json:
            print(f"\n# repescagem da CIP: {', '.join(resultados[i]['caso'] for i in pendentes)}")
        for i in pendentes:
            cid = resultados[i]["caso"]
            nome, fn = por_id[cid]
            try:
                status, corpo = fn()
            except Exception:  # noqa: BLE001 — re-tentativa que explode não vale nada
                continue
            # SÓ substitui se melhorou. A repescagem chegou a transformar sucesso
            # em falha: o BP_04 cancelou de fato na primeira tentativa, e a
            # segunda encontrou o recurso já cancelado e reportou o erro disso.
            # Re-tentativa que piora a evidência é pior que não re-tentar.
            if 200 <= status < 300:
                resultados[i] = {"caso": cid, "nome": nome, "ok": True,
                                 "status_code": status, "response_body": corpo}

    for cid, (nome, motivo) in AUSENTES.items():
        if alvos and cid not in alvos:
            continue
        resultados.append({"caso": cid, "nome": nome, "ausente": True, "motivo": motivo,
                           "ok": None, "status_code": None, "response_body": None})
        if not so_json:
            print(f"\n{'='*72}\n{cid} — {nome}\n{'='*72}")
            print(f"AUSENTE — {motivo}")

    if so_json:
        print(json.dumps({"executado_em": datetime.now().isoformat(timespec="seconds"),
                          "alvo": onde, "resultados": [_sem_token(r) for r in resultados]},
                         ensure_ascii=False, indent=2, default=str))
    falhas = [r["caso"] for r in resultados if r.get("ok") is False]
    if falhas and not so_json:
        print(f"\n{len(falhas)} caso(s) sem 2xx: {', '.join(falhas)}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
