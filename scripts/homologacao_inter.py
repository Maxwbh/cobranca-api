#!/usr/bin/env python3
"""Roteiro de homologação do Banco Inter **contra a API**, no molde do C6.

Cada caso é uma requisição HTTP às rotas do gateway — router, schema, validação,
`exige_capacidade` e tradução de erro incluídos. O que está sendo homologado é o
**serviço**, não o provider.

**Nada é inventado.** O que sai daqui é resposta real; caso que falha entra com
o status e o corpo do erro, porque a recusa também é evidência.

O contrato exercitado veio do SDK oficial do banco (`inter-co/pj-sdk-java`), e
não de suposição — inclusive o detalhe de que **cancelar é `POST .../cancelar`**,
não `DELETE`.

O sandbox do Inter tem **comportamento real**, como o do C6 — e não é mock de
schema como o do Sicoob. Isso não é suposição: a sonda de eco compara o que foi
enviado com o que voltou (`seuNumero`, valor e vencimento) e sai no relatório
como `sandbox_ecoa_o_enviado`. A sonda continua rodando a cada execução porque é
ela que autoriza o relatório a afirmar integração ponta a ponta em vez de só
contrato — se o banco trocar o ambiente por um mock, o campo vira `False` no
mesmo instante.

Uso:

    export INTER_SANDBOX_CLIENT_ID=... INTER_SANDBOX_CLIENT_SECRET=...
    export INTER_SANDBOX_CERT_PEM="$(cat Sandbox_InterAPI_Certificado.crt)"
    export INTER_SANDBOX_KEY_PEM="$(cat Sandbox_InterAPI_Chave.key)"
    export INTER_SANDBOX_CONTA=...          # opcional (header x-conta-corrente)

    PYTHONPATH=gateway python scripts/homologacao_inter.py            # legível
    PYTHONPATH=gateway python scripts/homologacao_inter.py --json     # evidência
    PYTHONPATH=gateway python scripts/homologacao_inter.py B_01 P_01  # alguns
    PYTHONPATH=gateway python scripts/homologacao_inter.py --base-url https://...

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

FALTANDO = [v for v in ("INTER_SANDBOX_CLIENT_ID", "INTER_SANDBOX_CLIENT_SECRET")
            if not os.environ.get(v)]
if FALTANDO:
    sys.exit(f"faltam credenciais no ambiente: {', '.join(FALTANDO)}")

TENANT = os.environ.get("HML_TENANT", "homologacao")
BASE_SANDBOX = os.environ.get("INTER_SANDBOX_BASE_URL",
                              "https://cdpj-sandbox.partners.uatinter.co")

# O provider resolve a base no import do módulo; o gateway lê credenciais do
# cofre por (tenant, provider). Ambos antes de importar a app.
os.environ["INTER_BASE_URL"] = BASE_SANDBOX
os.environ["INTER_AUTH_URL"] = f"{BASE_SANDBOX}/oauth/v2/token"
# O Inter entrega .crt + .key (PEM), não PKCS12 — as duas formas são aceitas.
for alvo, fonte in (("client_id", "INTER_SANDBOX_CLIENT_ID"),
                    ("client_secret", "INTER_SANDBOX_CLIENT_SECRET"),
                    ("cert_pem", "INTER_SANDBOX_CERT_PEM"),
                    ("key_pem", "INTER_SANDBOX_KEY_PEM"),
                    ("pfx_base64", "INTER_SANDBOX_PFX_BASE64"),
                    ("pfx_password", "INTER_SANDBOX_PFX_PASSWORD")):
    valor = os.environ.get(fonte, "")
    if valor:
        os.environ[f"VAULT__{TENANT}__inter__{alvo}"] = valor
# Sem isto o provider não é usado — e, no caso do Inter, não há fallback offline
# (a engine não tem o layout do 077), então a chamada falharia por credencial.
os.environ["INTER_REGISTERED_READY"] = "true"

CONTA = os.environ.get("INTER_SANDBOX_CONTA", "")
CHAVE_PIX = os.environ.get("INTER_SANDBOX_CHAVE_PIX", "")
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


class SemMassa(RuntimeError):
    """Caso que não pôde rodar por falta de dado no ambiente, não por defeito.

    Vira AUSENTE no relatório, com o motivo. É exceção e não entrada fixa: no
    dia em que o dado existir, o caso roda sem ninguém lembrar de mexer aqui.
    """


def _q(**extra) -> dict:
    return {"tenant_id": TENANT, "provider": "inter", **extra}


def _conta() -> dict:
    cfg: dict = {}
    if CONTA:
        cfg["conta_corrente"] = CONTA
    if CHAVE_PIX:
        cfg["chave_pix"] = CHAVE_PIX
    return cfg


def _txid() -> str:
    return "".join(random.SystemRandom().choices(string.ascii_lowercase + string.digits, k=30))


def _janela(dias: int = 7) -> tuple[str, str]:
    fim = date.today()
    ini = fim - timedelta(days=dias)
    return ini.isoformat(), fim.isoformat()


# --- casos: cada um devolve (status_code, corpo) da API ----------------------------

#: Campos que NUNCA saem na evidência versionada. `token` é a chave que decifra
#: as credenciais guardadas (`core/credential_store`); `client_id` é metade do
#: par de autenticação — e o C6 o devolve de volta no eco do cadastro de
#: webhook, então ele entra na evidência sem ninguém ter escrito.
#: `core/vault.py`: "NUNCA versionar em git".
_MASCARAR = {"token": "bapi_<mascarado>", "client_id": "<mascarado>"}


def _mascara(valor):
    if isinstance(valor, dict):
        return {k: (_MASCARAR[k] if k in _MASCARAR and isinstance(v, str) else _mascara(v))
                for k, v in valor.items()}
    if isinstance(valor, list):
        return [_mascara(v) for v in valor]
    return valor


def _sem_token(item: dict) -> dict:
    """Tira o segredo do caso antes de ele virar arquivo versionado.

    Em profundidade: o corpo do banco é passthrough e aninha como quiser — uma
    varredura só no primeiro nível deixaria passar o que estivesse um degrau
    abaixo, que é exatamente onde ninguém procura.
    """
    corpo = item.get("response_body")
    return {**item, "response_body": _mascara(corpo)} if corpo is not None else item


def at_01():
    """Token da API sobre a credencial do banco."""
    return API("POST", "/credenciais", json={
        "tenant_id": TENANT, "provider": "inter",
        "credentials": {
            "client_id": os.environ["INTER_SANDBOX_CLIENT_ID"],
            "client_secret": os.environ["INTER_SANDBOX_CLIENT_SECRET"],
            "cert_pem": os.environ.get("INTER_SANDBOX_CERT_PEM", ""),
            "key_pem": os.environ.get("INTER_SANDBOX_KEY_PEM", ""),
            "pfx_base64": os.environ.get("INTER_SANDBOX_PFX_BASE64", ""),
            "pfx_password": os.environ.get("INTER_SANDBOX_PFX_PASSWORD", ""),
        }})


def b_01():
    """Emissão de boleto. O `seuNumero` e o valor são a sonda de eco: se o
    sandbox devolver outros, é mock de schema e o relatório muda de alcance."""
    seu = uuid.uuid4().hex[:10].upper()
    ESTADO["seu_numero"] = seu
    st, b = API("POST", "/cobranca", json={
        "tenant_id": TENANT, "provider": "inter", "account_config": _conta(),
        "cobranca": {"valor": "150.00", "vencimento": VENC, "seu_numero": seu,
                     "pagador": {"nome": "Teste Homologacao", "documento": "12345678909",
                                 "endereco": {"logradouro": "Av. Teste", "numero": "100",
                                              "bairro": "Centro", "cidade": "Sete Lagoas",
                                              "uf": "MG", "cep": "35700000"}}}})
    if isinstance(b, dict) and b.get("id"):
        ESTADO["boleto_id"] = str(b["id"])
    return st, b


def b_02():
    """Consulta pelo codigoSolicitacao."""
    if not ESTADO.get("boleto_id"):
        raise SemMassa("B_01 não devolveu codigoSolicitacao para consultar")
    return API("GET", f"/cobranca/{ESTADO['boleto_id']}", params=_q())


def b_03():
    """PDF do boleto."""
    if not ESTADO.get("boleto_id"):
        raise SemMassa("B_01 não devolveu codigoSolicitacao para gerar o PDF")
    st, b = API("GET", f"/cobranca/{ESTADO['boleto_id']}/pdf", params=_q())
    if isinstance(b, dict) and b.get("pdf_base64"):
        b = {**b, "pdf_base64": f"<{len(b['pdf_base64'])} chars de base64>"}
    return st, b


def b_04():
    """Cancelamento — POST /{id}/cancelar com motivo, não DELETE."""
    if not ESTADO.get("boleto_id"):
        raise SemMassa("B_01 não devolveu codigoSolicitacao para cancelar")
    return API("DELETE", f"/cobranca/{ESTADO['boleto_id']}", params=_q())


def b_05():
    """Webhook de cobrança — cadastro."""
    return API("POST", "/config/webhook-banco", json={
        "tenant_id": TENANT, "provider": "inter",
        "url": "https://exemplo.com.br/webhooks/inter", "service": "COBRANCA"})


def b_06():
    """Webhook de cobrança — consulta."""
    return API("GET", "/config/webhook-banco", params=_q(service="COBRANCA"))


def p_01():
    """Cobrança Pix imediata (cob) — dialeto BACEN, base /pix/v2."""
    if not CHAVE_PIX:
        raise SemMassa("sem INTER_SANDBOX_CHAVE_PIX: a cob exige chave do recebedor")
    txid = _txid()
    ESTADO["txid"] = txid
    return API("POST", "/pix", json={
        "tenant_id": TENANT, "provider": "inter", "account_config": _conta(),
        "pix": {"valor": "1.00", "descricao": "homologacao", "txid": txid}})


def p_02():
    """Consulta da cob."""
    if not ESTADO.get("txid"):
        raise SemMassa("P_01 não criou cob para consultar")
    return API("GET", f"/pix/{ESTADO['txid']}", params=_q())


def p_03():
    """Lista de cobranças do período."""
    ini, fim = _janela()
    return API("GET", "/pix", params=_q(inicio=f"{ini}T00:00:00Z", fim=f"{fim}T23:59:59Z"))


def p_04():
    """Pix recebidos no período (money-in)."""
    ini, fim = _janela()
    return API("GET", "/pix/recebidos",
               params=_q(inicio=f"{ini}T00:00:00Z", fim=f"{fim}T23:59:59Z"))


def p_05():
    """Webhook Pix por chave."""
    if not CHAVE_PIX:
        raise SemMassa("sem INTER_SANDBOX_CHAVE_PIX: o webhook Pix é por chave")
    return API("PUT", "/config/webhook-pix", json={
        "tenant_id": TENANT, "provider": "inter", "chave": CHAVE_PIX,
        "url": "https://exemplo.com.br/webhooks/inter/pix"})


def c_01():
    """Coleção de boletos do período — `GET /cobrancas`.

    Filtra por **EMISSÃO** e não por vencimento de propósito: o boleto do B_01
    vence daqui a 30 dias, então uma janela recente por vencimento voltaria
    vazia e o caso passaria sem provar nada. Por emissão, o título recém-criado
    tem de aparecer — e é isso que o relatório afirma em `achou_o_do_b01`.
    """
    ini, fim = _janela(1)
    st, b = API("GET", "/cobrancas", params=_q(
        inicio=ini, fim=fim, pagina=1, tamanho=50, filtrar_data_por="EMISSAO"))
    if isinstance(b, dict) and ESTADO.get("seu_numero"):
        achou = ESTADO["seu_numero"] in json.dumps(b, ensure_ascii=False)
        b = {**b, "achou_o_do_b01": achou}
    return st, b


def c_02():
    """Sumário do período por situação — `GET /cobrancas/sumario`.

    O Inter devolve **array na raiz**; o gateway embrulha em `sumario`. O caso
    existe para provar isso contra o banco de verdade: com o corpo real, a rota
    respondia 500 antes do embrulho.
    """
    ini, fim = _janela(1)
    return API("GET", "/cobrancas/sumario",
               params=_q(inicio=ini, fim=fim, filtrar_data_por="EMISSAO"))


def c_03():
    """Filtro fora do vocabulário do banco para no gateway, com 422.

    Prova o lado que o banco não prova: `ABERTO` não existe no Inter (é
    `A_RECEBER`), e mandado ao banco volta 400 genérico. Aqui a recusa nomeia
    os valores aceitos e não gasta uma ida ao banco.
    """
    ini, fim = _janela(1)
    return API("GET", "/cobrancas", params=_q(inicio=ini, fim=fim, situacao="ABERTO"))


def e_01():
    """Extrato da conta (Banking v2)."""
    ini, fim = _janela(30)
    return API("GET", "/extrato", params=_q(start_date=ini, end_date=fim))


AUSENTES: dict[str, tuple[str, str]] = {
    "PG_01": ("Banking v2 — pagamentos, DARF, lote e Pix pagamento",
              "fora do escopo do produto: saída de dinheiro; a Cobranca-API é cobrança "
              "(entrada). Os scopes `pagamento-*` nem são pedidos no token"),
    "PA_01": ("Pix Automático (rec/solicrec/cobr)",
              "CONFIRMADO no banco e ligado: a spec OpenAPI do Inter publica as rotas na "
              "mesma base `/pix/v2` e as 17 chamadas do dialeto batem uma a uma (inventário "
              "em docs/homologacao/evidencia-pix-automatico-inter.json). Não roda AQUI por "
              "restrição do BACEN, não do gateway: só CNPJ com 6+ meses de atividade cria "
              "recorrência, e a conta do sandbox não atende"),
    "SA_01": ("Banking v2 — saldo",
              "LACUNA DE SUPERFÍCIE, não de escopo: o endpoint existe e o gateway não expõe "
              "rota de saldo para nenhum banco (mesma situação do SIC-S06). ADIADO por "
              "decisão de produto: saldo é posição de conta, não cobrança, e o /extrato "
              "cobre o caso de uso. Se um dia entrar, entra para todos os bancos de uma "
              "vez — não como exceção do Inter"),
}


#: Caso cujo SUCESSO é uma recusa. Sem isto o runner leria 2xx como único
#: resultado bom, e uma rota que parasse de recusar entraria no relatório como
#: aprovada — que é o inverso do que o caso prova.
ESPERADO: dict[str, int] = {"C_03": 422}


CASOS = [
    ("AT_01", "Token da API sobre a credencial do banco", at_01),
    ("B_01", "Emissão de boleto registrado", b_01),
    ("B_02", "Consulta de boleto", b_02),
    ("B_03", "PDF do boleto", b_03),
    ("B_05", "Webhook de cobrança — cadastro", b_05),
    ("B_06", "Webhook de cobrança — consulta", b_06),
    ("C_01", "Coleção de cobranças do período", c_01),
    ("C_02", "Sumário de cobranças do período", c_02),
    ("C_03", "Filtro fora do vocabulário do banco → 422", c_03),
    ("B_04", "Cancelamento", b_04),
    ("P_01", "Cobrança Pix imediata (cob)", p_01),
    ("P_02", "Consulta da cob", p_02),
    ("P_03", "Lista de cobranças do período", p_03),
    ("P_04", "Pix recebidos no período", p_04),
    ("P_05", "Webhook Pix por chave", p_05),
    ("E_01", "Extrato da conta", e_01),
]

# B_04 (cancelar) vem depois de B_05/B_06 de propósito: consultar e imprimir um
# boleto cancelado não teria sentido, e a ordem do papel esconderia isso.


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
        print(f"# roteiro Inter contra a API — {onde}, tenant '{TENANT}'")
        print(f"# banco: {BASE_SANDBOX}\n")

    resultados = []
    for cid, nome, fn in CASOS:
        if alvos and cid not in alvos:
            continue
        try:
            status, corpo = fn()
            espera = ESPERADO.get(cid)
            item = {"caso": cid, "nome": nome,
                    "ok": status == espera if espera else 200 <= status < 300,
                    "status_code": status, "response_body": corpo}
            if espera:
                item["status_esperado"] = espera
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

    # Sonda de eco: o sandbox devolve o que foi enviado, ou dado aleatório?
    # É o que decide se o relatório atesta integração ou só contrato.
    eco = None
    emissao = next((r for r in resultados if r["caso"] == "B_01" and r.get("ok")), None)
    if emissao and ESTADO.get("seu_numero"):
        corpo = json.dumps(emissao.get("response_body"), ensure_ascii=False, default=str)
        eco = ESTADO["seu_numero"] in corpo or "150" in corpo

    if so_json:
        print(json.dumps({"executado_em": datetime.now().isoformat(timespec="seconds"),
                          "alvo": onde, "banco": "inter", "ambiente": BASE_SANDBOX,
                          "sandbox_ecoa_o_enviado": eco,
                          "resultados": [_sem_token(r) for r in resultados]},
                         ensure_ascii=False, indent=2, default=str))
    elif eco is not None:
        print(f"\n{'='*72}")
        print("sandbox ecoa o que foi enviado: "
              + ("SIM — comportamento real, o relatório vale integração"
                 if eco else "NÃO — mock de schema, o relatório vale contrato"))

    falhas = [r["caso"] for r in resultados if r.get("ok") is False]
    if falhas and not so_json:
        print(f"\n{len(falhas)} caso(s) sem 2xx: {', '.join(falhas)}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
