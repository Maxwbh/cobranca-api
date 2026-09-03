# Capacidade antes de credencial — o 424 que mandava para o lado errado.
#
# A ordem era: resolver credencial, montar o provider, conferir a capacidade.
# Quem perguntasse por um recurso que o banco NÃO TEM, sem credencial no cofre,
# levava `424 credenciais do tenant/banco ausentes` — e ia atrás de uma
# credencial que não resolveria nada, porque o banco não oferece o recurso.
#
# É a mesma família do `403 mTLS` que se lia como credencial inválida e mandava
# conferir `client_id` e `secret`, que estavam certos: o status existe, é
# sincero sobre o que viu, e aponta para o lugar errado.
#
# Capacidade é propriedade do BANCO e do CÓDIGO, não de quem chama — e o
# `GET /bancos` já a publica sem autenticação nenhuma. Responder antes não abre
# nada que não estivesse aberto.
from __future__ import annotations

import pytest

#: (rota, chamada) para um banco que NÃO tem a capacidade, sem credencial.
#: Itaú não herda o mixin BACEN de recorrência nem tem API de conta; Bolepix e
#: checkout são exclusivos do C6, então o Inter serve de contra-exemplo.
PERIODO = {"start_date": "2027-01-01", "end_date": "2027-01-31"}
JANELA = {"inicio": "2027-01-01", "fim": "2027-01-31"}
ITAU = {"tenant_id": "sem_credencial_nenhuma", "provider": "itau"}

_BOLEPIX = {
    "tenant_id": "sem_credencial_nenhuma", "provider": "inter",
    "bolepix": {"valor": 10.0, "vencimento": "2027-12-30", "descricao": "Teste",
                "chave_pix": "11222333000181",
                "pagador": {"nome": "Maria", "documento": "52998224725",
                            "endereco": {"logradouro": "Rua 1", "numero": "10",
                                         "cidade": "SP", "uf": "SP",
                                         "cep": "01000000"}}},
}
_CHECKOUT = {"tenant_id": "sem_credencial_nenhuma", "provider": "inter",
             "checkout": {"valor": 10.0, "descricao": "x"}}


def _casos(client):
    return [
        ("GET /extrato",
         lambda: client.get("/extrato", params={**ITAU, **PERIODO})),
        ("GET /conciliacao/recebiveis",
         lambda: client.get("/conciliacao/recebiveis", params={**ITAU, **PERIODO})),
        ("GET /conciliacao/transacoes",
         lambda: client.get("/conciliacao/transacoes", params={**ITAU, **PERIODO})),
        ("GET /cobrancas",
         lambda: client.get("/cobrancas", params={**ITAU, **JANELA})),
        ("GET /cobrancas/sumario",
         lambda: client.get("/cobrancas/sumario", params={**ITAU, **JANELA})),
        ("GET /pix-automatico/recorrencias",
         lambda: client.get("/pix-automatico/recorrencias", params={**ITAU, **JANELA})),
        ("PUT /pix-automatico/config/webhooks",
         lambda: client.put("/pix-automatico/config/webhooks", params=ITAU,
                            json={"url_recorrencia": "https://api.exemplo.com/w"})),
        ("POST /bolepix", lambda: client.post("/bolepix", json=_BOLEPIX)),
        ("POST /checkout", lambda: client.post("/checkout", json=_CHECKOUT)),
    ]


def test_banco_sem_a_capacidade_responde_422_mesmo_sem_credencial(client):
    """O 422 nomeia o banco e diz quem oferece; o 424 mandava buscar segredo."""
    ruins = []
    for nome, chamar in _casos(client):
        r = chamar()
        detalhe = str(r.json().get("detail", r.json()))
        if r.status_code != 422 or "não oferece" not in detalhe:
            ruins.append(f"{nome}: {r.status_code} {detalhe[:90]}")
    assert not ruins, "rota ainda pede credencial antes de conferir capacidade:\n  " + \
        "\n  ".join(ruins)


def test_a_mensagem_diz_para_onde_ir(client):
    """Erro que só nega deixa o integrador sem próximo passo — a alternativa
    nomeia os bancos que têm o recurso."""
    r = client.get("/extrato", params={**ITAU, **PERIODO})
    detalhe = r.json()["detail"]
    assert "itau" in detalhe and "c6" in detalhe and "sicoob" in detalhe


def test_banco_que_tem_a_capacidade_ainda_cobra_credencial(client):
    """A inversão não pode virar porta aberta: quem TEM o recurso continua
    parando no 424 quando não há credencial."""
    r = client.get("/extrato", params={"tenant_id": "sem_credencial_nenhuma",
                                       "provider": "sicoob", **PERIODO})
    assert r.status_code == 424, r.text[:200]
    assert "credenciais" in r.json()["detail"]


@pytest.mark.parametrize("rota,params", [
    ("/extrato", PERIODO),
    ("/cobrancas", JANELA),
    ("/pix-automatico/recorrencias", JANELA),
])
def test_o_caminho_off_mantem_a_mensagem_dele(client, rota, params):
    """A checagem nova é silenciosa quando a combinação não resolve.

    No caminho `off` quem tem a mensagem certa é o `build_rest_provider` — "só
    existe no caminho ON". Trocá-la por um erro de capacidade mandaria o
    integrador consertar a coisa errada.
    """
    r = client.get(rota, params={"tenant_id": "t", "provider": "off",
                                 "banco": "itau", **params})
    assert r.status_code == 422, r.text[:200]
    assert "caminho ON" in r.json()["detail"]


def test_a_capacidade_sai_da_classe_e_nao_de_uma_lista(client):
    """`classe_rest` responde sem cofre e sem credencial — é o que permite a
    checagem vir antes. Banco desconhecido devolve None, e aí quem fala é o
    `build_rest_provider`, não este atalho."""
    from app.registry import classe_rest
    from app.schemas import Banco, Provider

    assert classe_rest(Provider.on, Banco.itau) is not None
    assert classe_rest(Provider.off, Banco.itau) is None      # caminho off
    assert classe_rest(Provider.on, None, {}) is None          # sem banco
