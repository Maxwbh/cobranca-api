# Catálogo /bancos + autenticação unificada entre os bancos.


def test_bancos_lista_capacidades_reais(client):
    r = client.get("/bancos")
    assert r.status_code == 200
    data = r.json()
    bancos = {b["id"]: b for b in data["bancos"]}
    assert set(bancos) == {"c6", "sicoob", "inter", "itau", "pycobranca"}

    # capacidades refletem o código (introspecção)
    assert "pix_automatico" in bancos["c6"]["capacidades"]
    assert "pix_automatico" in bancos["sicoob"]["capacidades"]
    assert "bolepix" in bancos["c6"]["capacidades"]
    assert "bolepix" not in bancos["sicoob"]["capacidades"]  # exclusivo C6
    assert "extrato" in bancos["sicoob"]["capacidades"]      # paridade nova
    assert "carne" in bancos["pycobranca"]["capacidades"]
    assert len(bancos["pycobranca"]["bancos_cnab"]) == 18

    # mecanismo da API é único (bapi_); o ESQUEMA de credenciais é próprio por banco
    assert "bapi_" in data["autenticacao_api"]["cadastro"]
    assert "pfx_base64" in bancos["c6"]["credentials"]          # esquema C6
    assert "access_token" in bancos["sicoob"]["credentials"]     # esquema Sicoob
    assert bancos["c6"]["credentials"] != bancos["sicoob"]["credentials"]


def test_mecanismo_da_api_igual_nos_dois_bancos(client, monkeypatch):
    """O mecanismo (recebe -> armazena -> Bearer bapi_) é o MESMO nos 2 bancos,
    ainda que cada banco tenha o próprio esquema de parâmetros."""
    chamadas = []

    def fake_request(self, method, path, json=None, params=None):
        chamadas.append({"path": path, "token": self.token()})
        return {"txid": "T", "status": "ATIVA", "pixCopiaECola": "000201..."}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    for prov in ("c6", "sicoob"):
        body = {"tenant_id": "t", "provider": prov,
                "account_config": {"chave_pix": "k"}, "pix": {"valor": "1.00"},
                "credentials": {"client_id": "cid", "access_token": "tok-estatico-sandbox"}}
        r = client.post("/pix", json=body)
        assert r.status_code == 201, (prov, r.text)

    # o token estático foi usado direto (sem fluxo OAuth) em AMBOS
    assert [c["token"] for c in chamadas] == ["tok-estatico-sandbox"] * 2


def test_extrato_sicoob_mapeia_mes_ano(client, monkeypatch):
    monkeypatch.setenv("VAULT__t__sicoob__client_id", "cid")
    monkeypatch.setenv("VAULT__t__sicoob__client_secret", "s")
    captured = {}

    def fake_request(self, method, path, json=None, params=None):
        captured.update(path=path, params=params)
        return {"resultado": {"saldoAtual": "100.00"}}

    monkeypatch.setattr("app.clients.oauth_mtls.OAuthMtlsClient.request", fake_request)

    r = client.get("/extrato", params={"tenant_id": "t", "provider": "sicoob",
                                       "start_date": "2026-07-01", "end_date": "2026-07-15"})
    assert r.status_code == 200, r.text
    assert captured["path"] == "/conta-corrente/v4/extrato/7/2026"
    assert captured["params"]["diaInicial"] == 1 and captured["params"]["diaFinal"] == 15

    # multi-mês -> 422 com mensagem clara
    r = client.get("/extrato", params={"tenant_id": "t", "provider": "sicoob",
                                       "start_date": "2026-06-15", "end_date": "2026-07-15"})
    assert r.status_code == 422
    assert "mesmo mês" in r.json()["detail"]


def test_catalogo_anuncia_checkout_so_no_banco_que_oferece(client):
    """O catálogo e' como o consumidor DESCOBRE o que cada banco faz, e a rota de
    checkout existia sem aparecer nele.

    So o C6 lista `checkout_cartao` -- e' a decisao 4 virada em dado: cartao
    existe onde a instituicao OFERECE, e o catalogo tem de dizer onde."""
    bancos = {b["id"]: b["capacidades"] for b in client.get("/bancos").json()["bancos"]}
    assert "checkout_cartao" in bancos["c6"]
    assert "checkout_cartao" not in bancos["sicoob"]
    assert "checkout_cartao" not in bancos["pycobranca"]


def test_inter_nao_anuncia_capacidade_que_nao_tem(client):
    """O Inter herda os mixins BACEN, entao Pix vem de graca — mas boleto com
    cartao e conciliacao de cartao sao do C6, e o catalogo nao pode sugerir
    que existam aqui."""
    inter = {b["id"]: b for b in client.get("/bancos").json()["bancos"]}["inter"]
    assert inter["codigo_banco"] == "077"
    for tem in ("boleto", "boleto_pdf", "boleto_baixa", "pix", "extrato", "webhook_banco"):
        assert tem in inter["capacidades"], tem
    for nao_tem in ("checkout_cartao", "conciliacao_cartao", "bolepix", "boleto_alteracao"):
        assert nao_tem not in inter["capacidades"], nao_tem


# --- a documentacao tem de ser copiavel --------------------------------------------
#
# Apertar contrato tem um custo escondido: o exemplo que o Swagger/Redoc INVENTA
# quando o campo nao tem `examples` (`"string"`, `0`, `2019-08-24`) deixa de
# passar. Quem abre a doc, clica em "Try it out" e "Execute" leva 422 de cara --
# a doc ensinando errado.

def _sem_null(schema):
    for chave in ("anyOf", "oneOf"):
        reais = [x for x in schema.get(chave, []) if x.get("type") != "null"]
        if reais:
            return {**reais[0], **{k: v for k, v in schema.items() if k != chave}}
    return schema


def _schemas_de_request(spec):
    """Só os schemas alcançáveis a partir de um requestBody."""
    comps = spec["components"]["schemas"]
    vistos = set()

    def anda(s, prof=0):
        if prof > 8 or not isinstance(s, dict):
            return
        if "$ref" in s:
            nome = s["$ref"].split("/")[-1]
            if nome not in vistos:
                vistos.add(nome)
                anda(comps.get(nome, {}), prof + 1)
            return
        for chave in ("anyOf", "oneOf", "allOf"):
            for x in s.get(chave, []):
                anda(x, prof + 1)
        for v in (s.get("properties") or {}).values():
            anda(v, prof + 1)
        if "items" in s:
            anda(s["items"], prof + 1)

    for ops in spec["paths"].values():
        for op in ops.values():
            corpo = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            if corpo.get("schema"):
                anda(corpo["schema"])
    return {n: comps[n] for n in vistos if n in comps}


def test_todo_campo_de_texto_do_request_tem_exemplo(client):
    """Sem `examples`, a UI mostra `"string"` (ou uma data de 2019) — e onde o
    campo tem `pattern` ou validador, esse valor inventado nao passa. Aconteceu
    com `redirect_url` (exige http(s)), `txid` (padrao BACEN) e
    `data_vencimento` do Pix Automatico (recusa passado)."""
    spec = client.get("/openapi.json").json()
    sem_exemplo = []
    for nome, sch in _schemas_de_request(spec).items():
        for campo, s in (sch.get("properties") or {}).items():
            achatado = _sem_null(s)
            tem = (s.get("examples") or "example" in s or "default" in s
                   or achatado.get("examples") or "example" in achatado)
            if tem or achatado.get("enum"):
                continue
            if achatado.get("type") == "string":
                sem_exemplo.append(f"{nome}.{campo}")
    assert not sem_exemplo, (
        "campos de request sem `examples` — a UI vai inventar um valor que pode "
        f"nao passar na propria validacao: {sem_exemplo}")


def test_exemplo_declarado_respeita_a_restricao_do_proprio_campo(client):
    """Exemplo que o schema recusa e pior que exemplo nenhum: o usuario copia e
    leva 422 sem entender por que."""
    import re

    spec = client.get("/openapi.json").json()
    ruins = []
    for nome, sch in _schemas_de_request(spec).items():
        for campo, s in (sch.get("properties") or {}).items():
            achatado = _sem_null(s)
            exemplos = s.get("examples") or achatado.get("examples") or []
            for ex in exemplos:
                padrao = achatado.get("pattern")
                if padrao and isinstance(ex, str) and not re.match(padrao, ex):
                    ruins.append(f"{nome}.{campo}={ex!r} viola {padrao}")
                minimo = achatado.get("exclusiveMinimum")
                if minimo is not None and isinstance(ex, (int, float)) and ex <= minimo:
                    ruins.append(f"{nome}.{campo}={ex!r} viola exclusiveMinimum {minimo}")
    assert not ruins, ruins
