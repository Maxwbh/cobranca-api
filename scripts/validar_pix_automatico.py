#!/usr/bin/env python3
"""Valida o Pix Automático banco a banco — e diz o que cada resposta PROVA.

O catálogo (`GET /bancos`) responde "este banco tem a capacidade `pix_automatico`",
e responde por introspecção, então nunca mente sobre o CÓDIGO. Só que capacidade
declarada não é funcionalidade validada: o dialeto BACEN é o mesmo para todos, e
mesmo assim um banco pode não ter o produto contratado na conta, não expor as
rotas, ou responder 2xx com uma página de WAF. Este roteiro é a diferença entre
as duas frases.

    export C6_SANDBOX_CLIENT_ID=... C6_SANDBOX_CLIENT_SECRET=...
    PYTHONPATH=gateway python scripts/validar_pix_automatico.py c6
    PYTHONPATH=gateway python scripts/validar_pix_automatico.py --json > evid.json

Sem argumento roda os quatro bancos ON; banco sem credencial no ambiente entra
como `sem_credencial` e não como falha — ausência de segredo não é defeito de
integração.

## O veredito de cada caso, e por que ele não é só o status HTTP

| veredito | quando | o que prova |
|---|---|---|
| `suportado` | 2xx com corpo JSON | o banco aceitou e devolveu recurso |
| `nao_provado` | 2xx com corpo **não-JSON** | nada: o `OAuthMtlsClient` embrulha corpo não-JSON em `{"conteudo": ...}` e o 2xx atravessa. Foi assim que o WAF do Sicoob ("Request Rejected", HTTP 200) virou `201` na evidência de agosto |
| `recusado` | 4xx/5xx do banco | o banco respondeu e recusou — a mensagem dele é o achado |
| `nao_oferecido` | 422 do gateway | o banco não herda o mixin BACEN; é fronteira de capacidade, não falha |
| `sem_credencial` | env vazio | não foi perguntado ao banco |

`nao_provado` existir separado de `suportado` é o ponto do roteiro. Ler os dois
como a mesma coisa é o erro que esta validação existe para não repetir.

Nada aqui é destrutivo: são os sandboxes dos próprios bancos, e a recorrência
criada é cancelada no último caso (Jornada 4).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
from datetime import date, datetime, timedelta

TENANT = os.environ.get("HML_TENANT", "homologacao")

# banco -> (env do ambiente, campo da credencial). Os nomes são os mesmos dos
# roteiros de homologação: quem já exporta para `homologacao_c6.py` roda este
# sem exportar nada de novo.
CREDENCIAIS: dict[str, dict[str, str]] = {
    "c6": {"client_id": "C6_SANDBOX_CLIENT_ID", "client_secret": "C6_SANDBOX_CLIENT_SECRET",
           "pfx_base64": "C6_SANDBOX_PFX_BASE64", "pfx_password": "C6_SANDBOX_PFX_PASSWORD"},
    "sicoob": {"client_id": "SICOOB_SANDBOX_CLIENT_ID", "access_token": "SICOOB_SANDBOX_TOKEN"},
    "inter": {"client_id": "INTER_SANDBOX_CLIENT_ID", "client_secret": "INTER_SANDBOX_CLIENT_SECRET",
              "cert_pem": "INTER_SANDBOX_CERT_PEM", "key_pem": "INTER_SANDBOX_KEY_PEM",
              "pfx_base64": "INTER_SANDBOX_PFX_BASE64", "pfx_password": "INTER_SANDBOX_PFX_PASSWORD",
              "conta_corrente": "INTER_SANDBOX_CONTA"},
    "itau": {"client_id": "ITAU_SANDBOX_CLIENT_ID", "sandbox_token": "ITAU_SANDBOX_TOKEN"},
}

# Sem estas, o provider aponta para PRODUÇÃO. Um roteiro de validação que bate
# em produção por omissão é pior que um que não roda.
SANDBOX: dict[str, dict[str, str]] = {
    "sicoob": {"SICOOB_BASE_URL": "https://sandbox.sicoob.com.br/sicoob/sandbox"},
    "inter": {"INTER_BASE_URL": "https://cdpj-sandbox.partners.uatinter.co",
              "INTER_AUTH_URL": "https://cdpj-sandbox.partners.uatinter.co/oauth/v2/token"},
    # C6: o default do provider JÁ é o sandbox. Itaú: o sandbox é escolhido pela
    # presença de `sandbox_token` na credencial, não por URL.
}

# Credencial mínima para valer a pena perguntar ao banco. `sem_credencial` sai
# daqui — e sai antes de qualquer chamada, para não gastar sandbox à toa.
OBRIGATORIAS: dict[str, tuple[str, ...]] = {
    "c6": ("C6_SANDBOX_CLIENT_ID", "C6_SANDBOX_CLIENT_SECRET"),
    "sicoob": ("SICOOB_SANDBOX_CLIENT_ID", "SICOOB_SANDBOX_TOKEN"),
    "inter": ("INTER_SANDBOX_CLIENT_ID", "INTER_SANDBOX_CLIENT_SECRET"),
    "itau": ("ITAU_SANDBOX_TOKEN",),
}


def _txid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=30))


def preparar_ambiente(banco: str) -> None:
    """Cofre e flags ANTES de importar a app — depois não adianta."""
    for campo, env in CREDENCIAIS[banco].items():
        valor = os.environ.get(env, "")
        if valor:
            os.environ[f"VAULT__{TENANT}__{banco}__{campo}"] = valor
    for k, v in SANDBOX.get(banco, {}).items():
        os.environ.setdefault(k, v)
    # Sem a flag, `provider=on` é rebaixado para a engine offline — que não tem
    # Pix nenhum. A validação atestaria o caminho errado.
    os.environ[f"{banco.upper()}_REGISTERED_READY"] = "true"


class Api:
    """Gateway em processo (ASGI) ou instância real — a mesma pilha de rotas."""

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
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"conteudo": r.text[:2000]}


def classificar(status: int, corpo) -> str:
    """Status + corpo -> veredito. A tabela do docstring, em código.

    Separada e sem I/O de propósito: é a regra que a validação inteira sustenta,
    e regra sustentada por um roteiro que só roda com segredo de sandbox não é
    testável. `gateway/tests/test_validacao_pix_automatico.py` a exercita.
    """
    if 200 <= status < 300:
        # `{"conteudo": ...}` é a marca de corpo não-JSON: o cliente HTTP embrulha
        # assim o que não conseguiu desserializar. 2xx com HTML dentro é WAF,
        # página de erro ou mock — e nenhum dos três é recurso criado.
        if isinstance(corpo, dict) and set(corpo) == {"conteudo"}:
            return "nao_provado"
        if isinstance(corpo, dict) and isinstance(corpo.get("raw"), dict) and \
                set(corpo["raw"]) == {"conteudo"}:
            return "nao_provado"
        return "suportado"
    detalhe = corpo.get("detail", "") if isinstance(corpo, dict) else ""
    if status == 422 and "não oferece Pix Automático" in str(detalhe):
        return "nao_oferecido"
    return "recusado"


# --- os casos: a superfície do Pix Automático, na ordem em que ela existe ---------
#
# Cada caso devolve (status, corpo). O estado (idRec, txid) atravessa em ESTADO —
# consultar uma recorrência exige tê-la criado, e num roteiro de validação isso é
# encadeamento, não dependência escondida.

ESTADO: dict[str, str] = {}


def _rec_payload(banco: str) -> dict:
    inicio = date.today() + timedelta(days=7)
    return {
        "tenant_id": TENANT, "provider": "on", "banco": banco,
        "recorrencia": {
            "contrato": "CT-VALIDACAO-001",
            "objeto": "Validacao Pix Automatico",
            "devedor": {"nome": "Teste Validacao", "documento": "12345678909"},
            "periodicidade": "MENSAL",
            "data_inicial": inicio.isoformat(),
            "valor_fixo": "50.00",
            "politica_retentativa": "PERMITE_3R_7D",
        },
    }


def casos(api: Api, banco: str) -> list[tuple[str, str, callable]]:
    q = {"tenant_id": TENANT, "provider": "on", "banco": banco}
    inicio = f"{date.today() - timedelta(days=1)}T00:00:00Z"
    fim = f"{date.today() + timedelta(days=60)}T23:59:59Z"

    def criar_rec():
        st, b = api("POST", "/pix-automatico/recorrencias", json=_rec_payload(banco))
        dados = b.get("data", b) if isinstance(b, dict) else {}
        if isinstance(dados, dict) and dados.get("idRec"):
            ESTADO["id_rec"] = dados["idRec"]
        return st, b

    def consultar_rec():
        if not ESTADO.get("id_rec"):
            raise SemMassa("a criação da recorrência não devolveu idRec — sem recurso para consultar")
        return api("GET", f"/pix-automatico/recorrencias/{ESTADO['id_rec']}", params=q)

    def listar_rec():
        return api("GET", "/pix-automatico/recorrencias", params={**q, "inicio": inicio, "fim": fim})

    def criar_loc():
        st, b = api("POST", "/pix-automatico/locations", params=q)
        dados = b.get("data", b) if isinstance(b, dict) else {}
        if isinstance(dados, dict) and dados.get("id"):
            ESTADO["loc_id"] = str(dados["id"])
        return st, b

    def consultar_loc():
        if not ESTADO.get("loc_id"):
            raise SemMassa("a criação da location não devolveu id")
        return api("GET", f"/pix-automatico/locations/{ESTADO['loc_id']}", params=q)

    def criar_solic():
        if not ESTADO.get("id_rec"):
            raise SemMassa("solicrec exige uma recorrência criada")
        return api("POST", "/pix-automatico/solicitacoes", json={
            "tenant_id": TENANT, "provider": "on", "banco": banco,
            "dados": {"idRec": ESTADO["id_rec"],
                      "calendario": {"dataExpiracaoSolicitacao":
                                     (date.today() + timedelta(days=30)).isoformat()},
                      "destinatario": {"contato": "5531999999999"}}})

    def agendar_cobr():
        if not ESTADO.get("id_rec"):
            raise SemMassa("cobr exige uma recorrência criada")
        # >= 2 dias antes do vencimento é regra BACEN; 10 dias dá folga para o
        # sandbox recusar por outro motivo que não a janela.
        ESTADO["txid_cobr"] = _txid()
        return api("PUT", f"/pix-automatico/cobrancas/{ESTADO['txid_cobr']}", json={
            "tenant_id": TENANT, "provider": "on", "banco": banco,
            "cobranca": {"id_rec": ESTADO["id_rec"],
                         "data_vencimento": (date.today() + timedelta(days=10)).isoformat(),
                         "valor": "50.00"}})

    def consultar_cobr():
        if not ESTADO.get("txid_cobr"):
            raise SemMassa("sem txid: o agendamento não chegou a ser tentado")
        return api("GET", f"/pix-automatico/cobrancas/{ESTADO['txid_cobr']}", params=q)

    def listar_cobr():
        return api("GET", "/pix-automatico/cobrancas", params={**q, "inicio": inicio, "fim": fim})

    def webhooks():
        return api("PUT", "/pix-automatico/config/webhooks", params=q,
                   json={"url_recorrencia": f"https://exemplo.com.br/webhooks/{banco}/rec",
                         "url_cobranca": f"https://exemplo.com.br/webhooks/{banco}/cobr"})

    def cancelar_rec():
        if not ESTADO.get("id_rec"):
            raise SemMassa("nada a cancelar")
        return api("PATCH", f"/pix-automatico/recorrencias/{ESTADO['id_rec']}",
                   params=q, json={"status": "CANCELADA"})

    return [
        ("PA_01", "rec — criar recorrência", criar_rec),
        ("PA_02", "rec — consultar", consultar_rec),
        ("PA_03", "rec — listar no período", listar_rec),
        ("PA_04", "locrec — criar location de adesão", criar_loc),
        ("PA_05", "locrec — consultar", consultar_loc),
        ("PA_06", "solicrec — solicitar autorização (Jornada 1)", criar_solic),
        ("PA_07", "cobr — agendar cobrança do ciclo (Jornada 3)", agendar_cobr),
        ("PA_08", "cobr — consultar", consultar_cobr),
        ("PA_09", "cobr — listar no período", listar_cobr),
        ("PA_10", "webhookrec + webhookcobr", webhooks),
        ("PA_11", "rec — cancelar (Jornada 4)", cancelar_rec),
    ]


class SemMassa(Exception):
    """O caso depende de recurso que o passo anterior não produziu."""


def declarada_no_catalogo(api: Api, banco: str) -> bool:
    """O `GET /bancos` lista `pix_automatico` para este banco?

    Perguntar ao catálogo, e não a uma lista daqui, é de propósito: a validação
    passa a cobrir também a promessa publicada. Catálogo dizendo que oferece e
    banco devolvendo 422 seria o defeito mais caro dos dois.
    """
    status, corpo = api("GET", "/bancos")
    if not (200 <= status < 300) or not isinstance(corpo, dict):
        return True  # catálogo indisponível não decide nada: siga e pergunte ao banco
    for b in corpo.get("bancos", []):
        if b.get("id") == banco:
            return "pix_automatico" in (b.get("capacidades") or [])
    return False


def validar(banco: str, base_url: str | None) -> dict:
    preparar_ambiente(banco)
    api = Api(base_url)

    # Capacidade vem antes de credencial: um banco que não expõe Pix Automático
    # continua não expondo com o segredo em mãos, e a resposta é a mesma sem
    # gastar sandbox.
    if not declarada_no_catalogo(api, banco):
        return {"banco": banco, "veredito": "nao_oferecido",
                "motivo": ("`GET /bancos` não lista `pix_automatico` para este banco — "
                           "o provider não herda o mixin BACEN de recorrência. As rotas "
                           "de /pix-automatico respondem 422 dizendo quem oferece"),
                "casos": []}

    faltando = [v for v in OBRIGATORIAS[banco] if not os.environ.get(v)]
    if faltando:
        return {"banco": banco, "veredito": "sem_credencial",
                "motivo": f"faltam no ambiente: {', '.join(faltando)}", "casos": []}

    ESTADO.clear()
    resultados = []
    for cid, nome, fn in casos(api, banco):
        try:
            status, corpo = fn()
            item = {"caso": cid, "nome": nome, "veredito": classificar(status, corpo),
                    "status_code": status, "response_body": corpo}
        except SemMassa as e:
            item = {"caso": cid, "nome": nome, "veredito": "sem_massa",
                    "motivo": str(e), "status_code": None, "response_body": None}
        except Exception as e:  # noqa: BLE001 — o erro É o resultado a reportar
            item = {"caso": cid, "nome": nome, "veredito": "erro",
                    "erro": f"{type(e).__name__}: {e}", "status_code": None,
                    "response_body": None}
        resultados.append(item)

    return {"banco": banco, "veredito": _veredito_do_banco(resultados), "casos": resultados}


def _veredito_do_banco(casos_do_banco: list[dict]) -> str:
    """O veredito do banco é o do conjunto, e o pior manda.

    Um banco em que a criação da recorrência não passa não "suporta parcialmente"
    Pix Automático: sem `rec` não existe ciclo nenhum.
    """
    vereditos = {c["veredito"] for c in casos_do_banco}
    if "nao_oferecido" in vereditos:
        return "nao_oferecido"
    primeiro = next((c for c in casos_do_banco if c["caso"] == "PA_01"), None)
    if primeiro and primeiro["veredito"] != "suportado":
        return primeiro["veredito"]
    return "suportado" if vereditos <= {"suportado", "sem_massa"} else "parcial"


_SIMBOLO = {"suportado": "✅", "nao_provado": "⚠️ ", "recusado": "❌",
            "nao_oferecido": "⛔", "sem_massa": "—", "erro": "💥",
            "sem_credencial": "🔑", "parcial": "⚠️ "}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bancos", nargs="*", default=[], help="c6 sicoob inter itau (padrão: todos)")
    ap.add_argument("--json", action="store_true", help="evidência crua em JSON no stdout")
    ap.add_argument("--base-url", help="valida contra uma instância real em vez do ASGI em processo")
    args = ap.parse_args()

    alvos = args.bancos or list(CREDENCIAIS)
    desconhecidos = [b for b in alvos if b not in CREDENCIAIS]
    if desconhecidos:
        return print(f"banco desconhecido: {', '.join(desconhecidos)}", file=sys.stderr) or 2

    relatorio = [validar(b, args.base_url) for b in alvos]

    if args.json:
        print(json.dumps({"executado_em": datetime.now().isoformat(timespec="seconds"),
                          "alvo": args.base_url or "app em processo (ASGI)",
                          "funcionalidade": "pix_automatico",
                          "bancos": relatorio}, ensure_ascii=False, indent=2, default=str))
        return 0

    for r in relatorio:
        print(f"\n{'='*72}\n{r['banco'].upper()} — {_SIMBOLO.get(r['veredito'], '')} {r['veredito']}")
        if r.get("motivo"):
            print(f"  {r['motivo']}")
        print('='*72)
        for c in r["casos"]:
            print(f"  {_SIMBOLO.get(c['veredito'], ' ')} {c['caso']} {c['nome']:48} "
                  f"{c['veredito']:14} {c.get('status_code') or ''}")
            if c["veredito"] in ("recusado", "nao_provado", "erro"):
                corpo = c.get("erro") or c.get("response_body")
                print(f"      {json.dumps(corpo, ensure_ascii=False, default=str)[:300]}")
            elif c.get("motivo"):
                print(f"      {c['motivo']}")

    # Sem credencial não é falha: é pergunta não feita. Falha é o banco recusar.
    ruins = [r["banco"] for r in relatorio if r["veredito"] in ("recusado", "parcial", "erro")]
    if ruins:
        print(f"\n{len(ruins)} banco(s) sem validar: {', '.join(ruins)}", file=sys.stderr)
    return 1 if ruins else 0


if __name__ == "__main__":
    raise SystemExit(main())
