# Erro em espanhol quando o chamador pede — e em português quando não pede.
#
# `Accept-Language: es` (ou `?lang=es`) traduz as MENSAGENS de erro: o texto
# que um integrador em Ciudad del Este lê quando a chamada falha. Nome de
# campo, status e chave do JSON não mudam. O mecanismo é um middleware só, que
# toda rota herda; e o catálogo é uma lista de regras, cada uma com o exemplo
# em português que a motivou.
#
# Dois lados cobrados: (1) cada regra casa com o seu exemplo e o resultado não
# tem português sobrando; (2) requisições REAIS, com dados ruins de verdade,
# voltam em espanhol com o cabeçalho e em português sem ele.
from __future__ import annotations

import json
import re

import pytest

from app.core.i18n_erros import CHAVES_DE_MENSAGEM, REGRAS, traduzir_corpo, traduzir_mensagem

#: Palavras que só existem em português (ou que em espanhol se escrevem de
#: outro jeito). "no", "inválido", "valor", "banco" ficam de fora: são iguais.
PORTUGUES = re.compile(
    r"\b(não|é|são|deve|devem|você|destes|obrigatóri[oa]|desconhecid[oa]|aceito|quis|dizer|"
    r"arquivos?|itens|vazi[oa]|corpo|chave|acima|limite|mesmo|em|ou|do|dos|das|na|nas|nos|"
    r"esgotado|indisponível|recusou|atingido|digitável|convênio|conteúdo|preenchidos|estão|"
    r"os|erros|gerar|teto|vem|cada item)\b",
    re.IGNORECASE)
_PROTEGIDO = re.compile(r"`[^`]*`|'[^']*'|\"[^\"]*\"")


def _sem_portugues(texto: str) -> list[str]:
    """Português que sobrou — fora de crases/aspas e fora dos nomes de banco,
    que ficam como são ("Banco do Nordeste" não vira "Banco del Nordeste")."""
    from app.core.i18n_erros import _nomes_de_banco
    limpo = _PROTEGIDO.sub("", texto)
    for nome in _nomes_de_banco():
        limpo = limpo.replace(nome, "")
    return PORTUGUES.findall(limpo)


ES = {"Accept-Language": "es-PY,es;q=0.9,pt;q=0.4"}

CAMPOS = {"valor": 1500.00, "cedente": "Empresa LTDA", "documento_cedente": "11222333000181",
          "sacado": "Juan Pérez", "sacado_documento": "52998224725", "agencia": "3073",
          "conta_corrente": "12345678", "convenio": "1234567", "carteira": "18",
          "nosso_numero": "123", "data_vencimento": "2027-12-31"}


@pytest.mark.parametrize("regra", REGRAS, ids=lambda r: r[2][:50])
def test_cada_regra_casa_com_o_seu_exemplo_e_sai_sem_portugues(regra):
    padrao, _, exemplo = regra
    assert re.match(padrao, exemplo), f"a regra {padrao!r} não casa com o próprio exemplo {exemplo!r}"
    es = traduzir_mensagem(exemplo, "es")
    assert es != exemplo or not _sem_portugues(exemplo), f"a regra não mudou nada em {exemplo!r}"
    assert not _sem_portugues(es), f"sobrou português em {es!r}"


def test_sem_pedir_nada_muda():
    for _, _, exemplo in REGRAS:
        assert traduzir_mensagem(exemplo, "pt") == exemplo


def test_nome_de_banco_e_trecho_citado_sao_preservados():
    """O vocabulário de reserva não pode virar 'Banco del Brasil'."""
    es = traduzir_mensagem("campo xpto não aceito em Banco do Brasil (001): 'valor em reais'", "es")
    assert "Banco do Brasil" in es and "'valor em reais'" in es
    assert "não" not in es and " em " not in es.replace("'valor em reais'", "")


def _erros(client, headers=None, **sobrescreve):
    r = client.get("/api/boleto/validate", headers=headers or {},
                   params={"bank": "banco_brasil", "data": json.dumps({**CAMPOS, **sobrescreve})})
    assert r.status_code == 400, r.text
    return r


def test_documento_estrangeiro_em_espanhol(client):
    r = _erros(client, ES, sacado_documento="80012345-6")
    assert r.headers["content-language"] == "es"
    assert "Accept-Language" in r.headers.get("vary", "")
    erros = r.json()["validation_errors"]
    assert "sacado_documento: CPF/CNPJ brasileño inválido" in erros, erros
    # e o português continua sendo o padrão
    pt = _erros(client, None, sacado_documento="80012345-6").json()
    assert "sacado_documento: CPF/CNPJ brasileiro inválido" in pt["validation_errors"]
    # `/api/boleto/data` traz também `error` e `hint` — os dois são mensagem
    dados = client.get("/api/boleto/data", headers=ES, params={
        "bank": "banco_brasil", "data": json.dumps({**CAMPOS, "sacado_documento": "80012345-6"})})
    assert dados.status_code == 400
    assert dados.json()["error"] == "Datos del boleto inválidos"
    assert dados.json()["hint"] == "Verifique que todos los campos obligatorios estén completos"


def test_campo_desconhecido_em_espanhol(client):
    erros = _erros(client, ES, moeda="9", data_processamento="2026-01-01").json()["validation_errors"]
    assert any(e.startswith("campo desconocido en `data`: 'moeda'") for e in erros), erros
    assert any("¿quiso decir 'data_documento'?" in e for e in erros), erros
    assert any(e.startswith("Un campo aceptado por Banco do Brasil (001) es uno de estos:") for e in erros), erros
    for e in erros:
        assert not _sem_portugues(e), e


def test_regra_do_banco_em_espanhol(client):
    r = client.get("/api/boleto/validate", headers=ES,
                   params={"bank": "banco_c6", "data": json.dumps({**CAMPOS, "carteira": "1", "convenio": "100"})})
    assert r.status_code == 400
    erros = r.json()["validation_errors"]
    assert any(e.startswith("carteira '1' no soportada (use una de:") for e in erros), erros


def test_lang_na_query_vale_como_o_cabecalho(client):
    r = client.get("/api/boleto/validate",
                   params={"bank": "banco_brasil", "lang": "es",
                           "data": json.dumps({**CAMPOS, "documento_cedente": "4567890"})})
    assert r.status_code == 400
    assert "documento_cedente: CPF/CNPJ brasileño inválido" in r.json()["validation_errors"]


def test_formato_descontinuado_e_roteamento_em_espanhol(client):
    r = client.get("/api/boleto", headers=ES,
                   params={"bank": "banco_brasil", "type": "jpg", "data": json.dumps(CAMPOS)})
    assert r.status_code == 400
    assert r.json()["validation_errors"] == ["`type` debe ser 'pdf'"], r.json()
    assert r.json()["error"].startswith("Formato 'jpg' discontinuado"), r.json()

    r = client.post("/cobranca", headers=ES, json={
        "tenant_id": "t", "provider": "on", "banco": "bradesco",
        "account_config": {}, "cobranca": {"valor": "10.00", "vencimento": "2027-12-31",
                                           "pagador": {"nome": "X", "documento": "52998224725"}}})
    assert r.status_code == 422, r.text
    detalhe = r.json()["detail"]
    assert isinstance(detalhe, str) and detalhe.startswith("el banco 'bradesco' no tiene camino 'on'"), detalhe
    assert not _sem_portugues(detalhe), detalhe


def test_422_do_pydantic_em_espanhol(client):
    r = client.post("/cobranca", headers=ES, json={"provider": "off"})
    assert r.status_code == 422
    msgs = [e["msg"] for e in r.json()["detail"]]
    assert msgs and all(m == "Campo obligatorio" for m in msgs), msgs
    pt = client.post("/cobranca", json={"provider": "off"})
    assert all(e["msg"] == "Field required" for e in pt.json()["detail"])


def test_o_201_com_status_erro_tambem_sai_em_espanhol(client):
    """`POST /cobranca` responde 201 com `status: "erro"` por compatibilidade —
    é erro com outro número, e o integrador lê `raw.validation_errors`."""
    r = client.post("/cobranca", headers=ES, json={
        "tenant_id": "t", "provider": "off", "banco": "itau",
        "account_config": {"agencia": "3073", "conta_corrente": "12345", "carteira": "109",
                           "convenio": "1234567", "cedente": "X", "documento_cedente": "05230380000174"},
        "cobranca": {"valor": "10.00", "vencimento": "2027-12-31", "nosso_numero": "1",
                     "pagador": {"nome": "Juan", "documento": "80012345-6"}}})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "erro"
    erros = r.json()["raw"]["validation_errors"]
    assert "sacado_documento: CPF/CNPJ brasileño inválido" in erros, erros


def test_accept_language_malformado_nao_derruba_a_rota(client):
    """`float("1.0.0")` estourava dentro do middleware — e o middleware roda para
    TODA requisição: um `q=` torto de qualquer proxy virava 500 em toda a API,
    inclusive para quem não pediu tradução."""
    for valor in ("es;q=1.0.0", "es;q=.", "pt;q=abc", ";;;", "es;q=1.5", "x" * 5000):
        r = client.get("/health", headers={"Accept-Language": valor})
        assert r.status_code == 200, (valor, r.status_code)


def test_a_negacao_nao_some_no_vocabulario_de_reserva(client):
    """A reserva traduzia "não" → "no" e, regras depois, lia esse "no" como o
    português de "em o": "Banco não suportado" virava "Banco en el soportado",
    e a negação sumia. Uma passada só, sobre o texto original."""
    assert traduzir_mensagem("Banco não suportado: 'xpto'", "es") == "Banco no soportado: 'xpto'"
    assert traduzir_mensagem("valor não pode ser zero", "es") == "valor no puede ser cero"
    r = client.get("/api/boleto/validate", headers=ES, params={"bank": "xpto", "data": "{}"})
    assert r.status_code == 400
    assert r.json()["validation_errors"] == ["Banco no soportado: 'xpto'"], r.json()
    assert r.json()["hint"] == "Corrija los errores de validación antes de generar el boleto"


#: `"hint": "…"`, `"error": "…"`, `"detail": "…"` literais nos routers e no
#: `core/pycob.py`. Strings quebradas em duas linhas (`"a" "b"`) são juntadas.
_LITERAL = re.compile(r'"(?:hint|error|detail)"\s*:\s*f?("(?:[^"\\]|\\.)*"(?:\s*\n?\s*"(?:[^"\\]|\\.)*")*)')


def _mensagens_literais() -> list[tuple[str, str]]:
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1] / "app"
    achadas = []
    for arq in sorted(list((raiz / "routers").glob("*.py")) + [raiz / "core" / "pycob.py"]):
        texto = arq.read_text(encoding="utf-8")
        for m in _LITERAL.finditer(texto):
            import ast
            # Lê cada pedaço como o Python lê o literal — preserva o UTF-8 e
            # resolve `\"` e `\n`; `decode("unicode_escape")` estragava os acentos.
            msg = "".join(ast.literal_eval(p) for p in re.findall(r'"(?:[^"\\]|\\.)*"', m.group(1)))
            # f-string: troca cada `{expr}` por um valor plausível
            msg = re.sub(r"\{[^}]*\}", "1", msg)
            if msg.strip():
                achadas.append((arq.name, msg))
    return achadas


def test_existe_mensagem_literal_para_varrer():
    assert len(_mensagens_literais()) > 20, "a varredura de literais não achou nada — o padrão quebrou"


@pytest.mark.parametrize("arquivo,msg", _mensagens_literais(), ids=lambda x: str(x)[:60])
def test_toda_mensagem_literal_dos_routers_sai_sem_portugues(arquivo, msg):
    """A página em espanhol promete que TODA resposta de erro volta traduzida.
    O guarda por regra só prova a regra; este varre o que as rotas de fato
    escrevem — `hint` incluído, que ficava em português — e cobra que nenhuma
    saia com palavra portuguesa. Mensagem nova sem regra reprova aqui."""
    # Regra EXPLÍCITA, não a reserva: a reserva deixou "Corrija os erros de
    # validação antes de gerar o boleto" intacto e o marcador de português não
    # viu — uma regra por mensagem que a casa escreve é o mínimo cobrável.
    assert any(re.match(p, msg) for p, _, _ in REGRAS), (
        f"{arquivo}: {msg!r} não casa com nenhuma regra de i18n_erros.REGRAS — acrescente uma")
    es = traduzir_mensagem(msg, "es")
    assert not _sem_portugues(es), f"{arquivo}: {msg!r} -> {es!r}"


def test_201_de_sucesso_nao_e_rotulado_como_traduzido(client):
    """Só o `status: "erro"` interessa no 201. Um 201 de sucesso saía com
    `Content-Language: es` sobre um corpo que não mudou — mentira para cache."""
    r = client.post("/cobranca", headers=ES, json={
        "tenant_id": "t", "provider": "off", "banco": "itau",
        "account_config": {"agencia": "3073", "conta_corrente": "12345", "carteira": "109",
                           "convenio": "1234567", "cedente": "X", "documento_cedente": "05230380000174"},
        "cobranca": {"valor": "10.00", "vencimento": "2027-12-31", "nosso_numero": "1",
                     "pagador": {"nome": "Juan", "documento": "52998224725"}}})
    assert r.status_code == 201 and r.json()["status"] == "registrado", r.text
    assert "content-language" not in r.headers, "201 de sucesso não foi traduzido — não pode ser rotulado"


def test_erro_por_item_num_200_de_job_tambem_sai_em_espanhol(client, tmp_path, monkeypatch):
    """O estado do job é 200 e carrega `errors` por item falhado: é erro para
    quem lê, com outro status. Entra pelo caminho (`/jobs/`), não pelo código."""
    monkeypatch.setenv("JOB_DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))
    item = {**CAMPOS, "bank": "banco_brasil", "sacado_documento": "80012345-6", "external_id": "RUIM"}
    job_id = client.post("/jobs/boletos", json={"tenant_id": "t", "boletos": [item]}).json()["job_id"]
    falhas = client.get(f"/jobs/boletos/{job_id}/items", headers=ES,
                        params={"tenant_id": "t", "status": "failed"})
    assert falhas.status_code == 200
    erros = falhas.json()["items"][0]["resultado"]["errors"]
    assert "sacado_documento: CPF/CNPJ brasileño inválido" in erros, erros
    assert falhas.headers["content-language"] == "es"
    pt = client.get(f"/jobs/boletos/{job_id}/items", params={"tenant_id": "t", "status": "failed"})
    assert "sacado_documento: CPF/CNPJ brasileiro inválido" in pt.json()["items"][0]["resultado"]["errors"]


def test_traduzir_corpo_so_toca_nas_chaves_de_mensagem():
    corpo = {"detail": "banco indisponível ou tempo esgotado",
             "upstream": {"body": {"message": "mantido? não: é mensagem", "codigo": "não muda"}},
             "validation_errors": ["valor deve ser positivo"], "campo": "não é mensagem"}
    es = traduzir_corpo(corpo, "es")
    assert es["detail"] == "banco no disponible o tiempo agotado"
    assert es["validation_errors"] == ["el valor debe ser positivo"]
    assert es["campo"] == "não é mensagem", "chave fora de CHAVES_DE_MENSAGEM não pode mudar"
    assert es["upstream"]["body"]["codigo"] == "não muda"
    assert "message" in CHAVES_DE_MENSAGEM
