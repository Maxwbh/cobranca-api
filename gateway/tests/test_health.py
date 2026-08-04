def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_lists_all_routes(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/cobranca" in paths
    assert "/cobranca/{cobranca_id}" in paths
    assert "/webhooks/{banco}" in paths
    assert "post" in paths["/cobranca"]
    assert {"get", "delete"} <= set(paths["/cobranca/{cobranca_id}"])


# --- a spec tem de admitir os erros que a app realmente devolve --------------------
#
# Os erros de banco nascem em exception handler, nao na assinatura da rota, e o
# FastAPI nao tem como enxerga-los: a spec declarava so 200/201/422 enquanto a app
# respondia 409 e 424. Quem integra lia o Swagger e descobria em producao.

_DO_BANCO = {"404", "409", "424", "429", "502", "504"}


def test_rotas_que_falam_com_o_banco_declaram_os_erros_do_banco(client):
    paths = client.get("/openapi.json").json()["paths"]
    for caminho in ("/cobranca", "/pix", "/checkout", "/extrato", "/carne"):
        for metodo, op in paths[caminho].items():
            faltando = _DO_BANCO - set(op["responses"])
            assert not faltando, f"{metodo.upper()} {caminho} nao declara {sorted(faltando)}"


def test_o_erro_do_banco_carrega_o_upstream(client):
    """Traduzir a faixa nao pode custar o diagnostico — e a spec tem de dizer
    que o original vem junto, senao ninguem procura por ele."""
    spec = client.get("/openapi.json").json()
    ref = spec["paths"]["/cobranca"]["post"]["responses"]["502"]
    assert ref["content"]["application/json"]["schema"]["$ref"].endswith("/ErroDoBanco")
    props = spec["components"]["schemas"]["ErroDoBanco"]["properties"]
    assert {"status", "url", "body"} <= set(props["upstream"]["properties"])


def test_rota_que_nao_sai_do_processo_nao_promete_erro_de_banco(client):
    """`/bancos` e introspeccao e `/health` e sonda — anexar 502/504 nelas seria
    ruido que ensina o integrador a tratar erro que nunca chega."""
    paths = client.get("/openapi.json").json()["paths"]
    for caminho in ("/bancos", "/health"):
        assert not (_DO_BANCO & set(paths[caminho]["get"]["responses"]))
