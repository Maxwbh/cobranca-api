#!/usr/bin/env python3
"""Roteiro de homologação do Sicoob **contra a API**, no mesmo molde do C6.

Cada caso é uma requisição HTTP às rotas do gateway — router, schema, validação,
`exige_capacidade` e tradução de erro incluídos. O que está sendo homologado é o
**serviço**, não o provider: chamar `SicoobProvider` direto pularia a camada que
o integrador enxerga.

**Nada é inventado.** O que sai daqui é resposta real; caso que falha entra com
o status e o corpo do erro, porque a recusa também é evidência.

## O sandbox do Sicoob não é o do C6 — e isso muda o que este roteiro prova

O sandbox do Sicoob é **mock de schema**: devolve dados aleatórios válidos, sem
relação com o que foi enviado. Observado em 04/08/2026, pedindo uma cob de
R$ 1,00:

    valor          -> "0.39"
    pixCopiaECola  -> "ex sed sit anim velit"      (lorem ipsum)
    location       -> "http://MmVXnVBKn.ssrC-v3XE2ugrn"
    expira_em      -> 2021-11-20                   (no passado)

e Pix recebidos com `fim: 1966-09-28`. Então este roteiro atesta **roteamento,
contrato e normalização** — que a rota existe, aceita o payload, chama o
endpoint certo do Sicoob e traduz a resposta para o nosso formato. Ele **não**
atesta comportamento do banco: nenhum boleto é de fato registrado, nenhum Pix
é de fato criado.

Onde o C6 provou integração ponta a ponta, aqui a prova é de contrato. Dizer o
contrário seria vender um teste que não existe — e é por isso que cada caso
carrega `mock_do_banco: true` na evidência.

Uso:

    export SICOOB_SANDBOX_CLIENT_ID=... SICOOB_SANDBOX_TOKEN=...
    PYTHONPATH=gateway python scripts/homologacao_sicoob.py            # legível
    PYTHONPATH=gateway python scripts/homologacao_sicoob.py --json     # evidência
    PYTHONPATH=gateway python scripts/homologacao_sicoob.py B_01 P_01  # alguns
    PYTHONPATH=gateway python scripts/homologacao_sicoob.py --base-url https://...

Sem `--base-url` a app roda em processo (ASGI) — mesma pilha de rotas, só não
cruza um socket.
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import uuid
from datetime import date, datetime, timedelta

FALTANDO = [v for v in ("SICOOB_SANDBOX_CLIENT_ID", "SICOOB_SANDBOX_TOKEN")
            if not os.environ.get(v)]
if FALTANDO:
    sys.exit(f"faltam credenciais no ambiente: {', '.join(FALTANDO)}")

TENANT = os.environ.get("HML_TENANT", "homologacao")
BASE_SANDBOX = os.environ.get("SICOOB_SANDBOX_BASE_URL",
                              "https://sandbox.sicoob.com.br/sicoob/sandbox")

# O provider resolve a base no import do módulo; e o gateway lê credenciais do
# cofre por (tenant, provider). Ambos precisam estar postos ANTES de importar a app.
os.environ["SICOOB_BASE_URL"] = BASE_SANDBOX
os.environ[f"VAULT__{TENANT}__sicoob__client_id"] = os.environ["SICOOB_SANDBOX_CLIENT_ID"]
os.environ[f"VAULT__{TENANT}__sicoob__access_token"] = os.environ["SICOOB_SANDBOX_TOKEN"]
os.environ["SICOOB_REGISTERED_READY"] = "true"

CHAVE_PIX = os.environ.get("SICOOB_SANDBOX_CHAVE_PIX", "sandbox@sicoob.com.br")
NUMERO_CLIENTE = int(os.environ.get("SICOOB_SANDBOX_NUMERO_CLIENTE", "25546454"))
# Boleto que o mock do Sicoob reconhece nas consultas.
NOSSO_NUMERO = os.environ.get("SICOOB_SANDBOX_NOSSO_NUMERO", "17654321")
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
    """O Sicoob identifica o boleto por numeroCliente + codigoModalidade +
    nossoNumero, então as rotas de leitura precisam da conta na query."""
    return {"tenant_id": TENANT, "provider": "sicoob",
            "numero_cliente": NUMERO_CLIENTE, "codigo_modalidade": 1, **extra}


def _conta() -> dict:
    return {"numeroCliente": NUMERO_CLIENTE, "codigoModalidade": 1, "chave_pix": CHAVE_PIX}


def _txid() -> str:
    return "".join(random.SystemRandom().choices(string.ascii_lowercase + string.digits, k=30))


def _janela(dias: int = 7) -> tuple[str, str]:
    fim = date.today()
    ini = fim - timedelta(days=dias)
    return f"{ini.isoformat()}T00:00:00Z", f"{fim.isoformat()}T23:59:59Z"


# --- casos: cada um devolve (status_code, corpo) da API ----------------------------

def at_01():
    """Token da API sobre a credencial do banco — o mecanismo que o integrador usa.

    No Sicoob o sandbox usa token estático do portal (sem OAuth/mTLS), ao
    contrário do C6; o /credenciais aceita as duas formas pelo mesmo contrato."""
    return API("POST", "/credenciais", json={
        "tenant_id": TENANT, "provider": "sicoob",
        "credentials": {"client_id": os.environ["SICOOB_SANDBOX_CLIENT_ID"],
                        "access_token": os.environ["SICOOB_SANDBOX_TOKEN"]}})


def b_01():
    """Emissão de boleto registrado."""
    st, b = API("POST", "/cobranca", json={
        "tenant_id": TENANT, "provider": "sicoob", "account_config": _conta(),
        "cobranca": {"valor": "10.00", "vencimento": VENC,
                     "seu_numero": uuid.uuid4().hex[:10],
                     "pagador": {"nome": "Teste Homologacao", "documento": "12345678909",
                                 "endereco": {"logradouro": "Av. Teste", "numero": "100",
                                              "bairro": "Centro", "cidade": "Sete Lagoas",
                                              "uf": "MG", "cep": "35700000"}}}})
    if isinstance(b, dict) and b.get("id"):
        ESTADO["boleto_id"] = str(b["id"])
    return st, b


def b_02():
    """Consulta de boleto pelo nosso número."""
    return API("GET", f"/cobranca/{ESTADO.get('boleto_id') or NOSSO_NUMERO}", params=_q())


def b_03():
    """Segunda via em PDF."""
    st, b = API("GET", f"/cobranca/{ESTADO.get('boleto_id') or NOSSO_NUMERO}/pdf", params=_q())
    if isinstance(b, dict) and b.get("pdf_base64"):
        b = {**b, "pdf_base64": f"<{len(b['pdf_base64'])} chars de base64>"}
    return st, b


def b_04():
    """Baixa/cancelamento."""
    return API("DELETE", f"/cobranca/{ESTADO.get('boleto_id') or NOSSO_NUMERO}", params=_q())


def p_01():
    """Cobrança Pix imediata (cob) com txid próprio."""
    txid = _txid()
    ESTADO["txid"] = txid
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "sicoob", "account_config": _conta(),
        "pix": {"valor": "1.00", "descricao": "homologacao", "txid": txid}})


def p_02():
    """Consulta da cob pelo txid."""
    return API("GET", f"/pix/{ESTADO.get('txid', 'x' * 30)}", params=_q())


def p_03():
    """Revisão da cob (PATCH) — capacidade `pix_revisao`."""
    return API("PATCH", f"/pix/{ESTADO.get('txid', 'x' * 30)}", params=_q(),
               json={"valor": {"original": "2.00"}})


def p_04():
    """Lista de cobranças do período."""
    ini, fim = _janela()
    return API("GET", "/pix", params=_q(inicio=ini, fim=fim))


def p_05():
    """Cobrança Pix com vencimento (cobv) — exige devedor identificado."""
    txid = _txid()
    ESTADO["txid_cobv"] = txid
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "sicoob", "account_config": _conta(),
        "pix": {"valor": "1.00", "descricao": "homologacao cobv", "txid": txid,
                "data_vencimento": VENC,
                "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"}}})


def p_06():
    """Pix recebidos no período (money-in)."""
    ini, fim = _janela()
    return API("GET", "/pix/recebidos", params=_q(inicio=ini, fim=fim))


def p_07():
    """Webhook Pix por chave — cadastro."""
    return API("PUT", "/config/webhook-pix", json={
        "tenant_id": TENANT, "provider": "sicoob", "chave": CHAVE_PIX,
        "url": "https://exemplo.com.br/webhooks/sicoob/pix"})


def p_08():
    """Webhook Pix por chave — consulta."""
    return API("GET", "/config/webhook-pix", params=_q(chave=CHAVE_PIX))


def pa_01():
    """Pix Automático: criar recorrência (rec) — mesmo dialeto BACEN do C6."""
    st, b = API("POST", "/pix-automatico/recorrencias", json={
        "tenant_id": TENANT, "provider": "sicoob", "account_config": _conta(),
        "recorrencia": {
            "contrato": uuid.uuid4().hex[:20],
            "objeto": "Assinatura de homologacao",
            "devedor": {"nome": "Teste Homologacao", "documento": "12345678909"},
            "data_inicial": VENC,
            "periodicidade": "MENSAL",
            "valor_fixo": "10.00",
            "politica_retentativa": "PERMITE_3R_7D",
        }})
    if isinstance(b, dict) and b.get("idRec"):
        ESTADO["id_rec"] = b["idRec"]
    return st, b


def pa_02():
    """Pix Automático: consultar a recorrência criada."""
    if not ESTADO.get("id_rec"):
        raise SemMassa("PA_01 não devolveu idRec — o mock do Sicoob não ecoa o recurso criado")
    return API("GET", f"/pix-automatico/recorrencias/{ESTADO['id_rec']}", params=_q())


def e_01():
    """Extrato de conta corrente (v4)."""
    # O extrato do Sicoob é mensal (GET /extrato/{mes}/{ano}) e a API recusa
    # janela que cruza meses. Usa o mês corrente, do dia 1 até hoje.
    hoje = date.today()
    return API("GET", "/extrato",
               params=_q(start_date=hoje.replace(day=1).isoformat(), end_date=hoje.isoformat()))


class SemMassa(RuntimeError):
    """O caso não pôde rodar por falta de dado no ambiente, não por defeito.

    Vira AUSENTE no relatório, com o motivo — e não falha. É exceção e não
    entrada fixa de propósito: no dia em que o mock passar a ecoar o recurso
    criado, o caso roda sem ninguém lembrar de mexer aqui.
    """


# Caso que não pertence ao produto não é testado nem "falha": consta como
# AUSENTE, com o motivo. Rodar e reportar erro poluiria a evidência.
AUSENTES: dict[str, tuple[str, str]] = {
    "PG_01": ("Pagamentos / transferências (spb, pix-pagamentos, convênios)",
              "fora do escopo do produto: saída de dinheiro; a Cobranca-API é cobrança "
              "(entrada). Vale para as APIs Pix Pagamentos, SPB Transferências e "
              "Convênios Pagamentos do catálogo do Sicoob"),
    "IN_01": ("Investimentos (RDC) e Poupança",
              "fora do escopo do produto: não é cobrança nem conciliação de cobrança"),
    "OF_01": ("Open Finance — Iniciação de Pagamento",
              "fora do escopo do produto: iniciação de pagamento é saída de dinheiro"),
    "B_05": ("Alteração de boleto emitido",
             "LACUNA DE SUPERFÍCIE, não de escopo: o C6 expõe PUT /cobranca/{id} e o "
             "Sicoob não implementa `alterar` no provider — a rota responde 422 pelo "
             "exige_capacidade, dizendo para onde ir. ADIADO por decisão de produto: o "
             "sandbox do Sicoob é mock de schema, então implementar agora provaria "
             "contrato e nunca comportamento — o caso continuaria sem evidência real"),
}


CASOS = [
    ("AT_01", "Token da API sobre a credencial do banco", at_01),
    ("B_01", "Emissão de boleto registrado", b_01),
    ("B_02", "Consulta de boleto", b_02),
    ("B_03", "Segunda via em PDF", b_03),
    ("B_04", "Baixa / cancelamento", b_04),
    ("P_01", "Cobrança Pix imediata (cob)", p_01),
    ("P_02", "Consulta da cob", p_02),
    ("P_03", "Revisão da cob", p_03),
    ("P_04", "Lista de cobranças do período", p_04),
    ("P_05", "Cobrança Pix com vencimento (cobv)", p_05),
    ("P_06", "Pix recebidos no período", p_06),
    ("P_07", "Webhook Pix por chave — cadastro", p_07),
    ("P_08", "Webhook Pix por chave — consulta", p_08),
    ("PA_01", "Pix Automático — criar recorrência", pa_01),
    ("PA_02", "Pix Automático — consultar recorrência", pa_02),
    ("E_01", "Extrato de conta corrente", e_01),
]

# B_04 (baixa) vem depois de B_02/B_03 de propósito: consultar e imprimir um
# boleto cancelado não teria sentido, e a ordem do papel esconderia isso.

NOTA_MOCK = ("sandbox do Sicoob é mock de schema: devolve dados aleatórios válidos, sem "
             "relação com o que foi enviado. Esta evidência atesta roteamento, contrato e "
             "normalização — não o comportamento do banco.")


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
        print(f"# roteiro Sicoob contra a API — {onde}, tenant '{TENANT}'")
        print(f"# {NOTA_MOCK}\n")

    resultados = []
    for cid, nome, fn in CASOS:
        if alvos and cid not in alvos:
            continue
        try:
            status, corpo = fn()
            item = {"caso": cid, "nome": nome, "ok": 200 <= status < 300,
                    "status_code": status, "response_body": corpo, "mock_do_banco": True}
        except SemMassa as e:
            item = {"caso": cid, "nome": nome, "ausente": True, "motivo": str(e),
                    "ok": None, "status_code": None, "response_body": None}
        except Exception as e:  # noqa: BLE001 — o erro É o resultado a reportar
            item = {"caso": cid, "nome": nome, "ok": False, "status_code": None,
                    "erro": f"{type(e).__name__}: {e}", "response_body": None}
        resultados.append(item)
        if not so_json:
            print(f"\n{'='*72}\n{cid} — {nome}\n{'='*72}")
            if item.get("ausente"):
                print(f"AUSENTE — {item['motivo']}")
                continue
            print(f"Status Code - Retornado: {item.get('status_code') or 'erro'}")
            if item.get("erro"):
                print(f"  ⚠ {item['erro']}")
            print("\nResponse Body - Retornado:")
            print(json.dumps(item["response_body"], ensure_ascii=False, indent=2, default=str))

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
                          "alvo": onde, "banco": "sicoob", "ambiente": BASE_SANDBOX,
                          "limitacao": NOTA_MOCK,
                          "resultados": [_sem_token(r) for r in resultados]},
                         ensure_ascii=False, indent=2, default=str))
    falhas = [r["caso"] for r in resultados if r.get("ok") is False]
    if falhas and not so_json:
        print(f"\n{len(falhas)} caso(s) sem 2xx: {', '.join(falhas)}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
