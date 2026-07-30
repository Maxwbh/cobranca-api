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
