# O erro de documento fala o nome que a API tem, e diz que o documento é o
# BRASILEIRO.
#
# Fase 0 do roadmap Mercosul — mas é defeito em português, hoje, para qualquer
# integrador. Medido antes de escrever:
#
#   campo que a API aceita:   documento_cedente
#   campo que o erro citava:  "cedente_documento inválido (CPF/CNPJ)"
#
# `cedente_documento` é o nome INTERNO da engine (pyCobrança, `bancos/base.py`
# 217 e 220); a API expõe `documento_cedente`. Quem recebia o erro procurava
# `cedente_documento` no Swagger e não achava. E "(CPF/CNPJ)" entre parênteses
# não diz a quem está em Ciudad del Este que cédula e RUC paraguaios não servem
# — o documento tem de ser o brasileiro do pagador.
#
# A raiz é na engine; o gateway traduz a mensagem no único ponto por onde todo
# erro da engine passa (`core.pycob._erros`), e todas as rotas herdam.
from __future__ import annotations

import json

import pytest

CAMPOS = {"valor": 1500.00, "cedente": "Empresa LTDA", "documento_cedente": "11222333000181",
          "sacado": "Juan Pérez", "sacado_documento": "52998224725", "agencia": "3073",
          "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
          "nosso_numero": "123", "data_vencimento": "2027-12-31"}

#: O que um integrador do outro lado da ponte manda, de boa-fé.
DOCUMENTOS_ESTRANGEIROS = [
    pytest.param("4567890", id="CI paraguaia, 7 digitos"),
    pytest.param("80012345-6", id="RUC paraguaio com DV"),
    pytest.param("800123456", id="RUC so digitos"),
    pytest.param("20-12345678-9", id="CUIT argentino"),
]


def _erros(client, **sobrescreve):
    r = client.get("/api/boleto/validate",
                   params={"bank": "banco_brasil", "data": json.dumps({**CAMPOS, **sobrescreve})})
    assert r.status_code == 400, r.text
    return r.json()["validation_errors"]


@pytest.mark.parametrize("campo", ["documento_cedente", "sacado_documento"])
@pytest.mark.parametrize("doc", DOCUMENTOS_ESTRANGEIROS)
def test_o_erro_cita_o_campo_com_o_nome_da_api(client, campo, doc):
    erros = _erros(client, **{campo: doc})
    assert any(campo in e for e in erros), (
        f"nenhum erro cita `{campo}`, que é o nome que o integrador mandou: {erros}")
    assert not any("cedente_documento" in e for e in erros), (
        f"o erro cita `cedente_documento`, nome interno da engine que a API não expõe: {erros}")


@pytest.mark.parametrize("campo", ["documento_cedente", "sacado_documento"])
def test_o_erro_diz_que_o_documento_e_o_brasileiro(client, campo):
    erros = _erros(client, **{campo: "80012345-6"})
    assert any("CPF/CNPJ brasileiro inválido" in e for e in erros), (
        f"a mensagem não diz que o documento tem de ser o brasileiro: {erros}")


def test_documento_valido_continua_passando(client):
    """Controle: a tradução da mensagem não pode mexer na regra."""
    r = client.get("/api/boleto/validate",
                   params={"bank": "banco_brasil", "data": json.dumps(CAMPOS)})
    assert r.status_code == 200, r.text


def test_a_traducao_vale_em_toda_rota_que_devolve_erro_da_engine(client):
    """Não é só o `/validate`: `/api/boleto/data` e `/api/boleto` (PDF) passam
    pelo mesmo ponto, e um deles sem tradução seria a mesma mentira em outra
    porta."""
    for rota, extra in (("/api/boleto/data", {}), ("/api/boleto", {"type": "pdf"})):
        r = client.get(rota, params={"bank": "banco_brasil", **extra,
                                     "data": json.dumps({**CAMPOS, "documento_cedente": "4567890"})})
        assert r.status_code == 400, (rota, r.text)
        erros = r.json()["validation_errors"]
        assert any("documento_cedente" in e and "brasileiro" in e for e in erros), (rota, erros)
        assert not any("cedente_documento" in e for e in erros), (rota, erros)


def test_outras_mensagens_da_engine_tambem_trocam_o_nome_interno():
    """O mapa de nomes é o da engine (`NOMES_DO_CONTRATO`), não uma lista à mão:
    `conta` vira `conta_corrente` na mesma passada. Testa a função direto, com
    a mensagem que o CrediSIS emite."""
    from app.core.pycob import traduzir_erro_da_engine
    assert traduzir_erro_da_engine("cedente_documento é obrigatório para o CrediSIS") == \
        "documento_cedente é obrigatório para o CrediSIS"
    assert traduzir_erro_da_engine("conta deve ter no máximo 5 dígitos") == \
        "conta_corrente deve ter no máximo 5 dígitos"
    # o que já fala o nome da API não muda
    assert traduzir_erro_da_engine("valor deve ser positivo") == "valor deve ser positivo"
