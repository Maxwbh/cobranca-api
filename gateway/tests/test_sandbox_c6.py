# E2E contra o SANDBOX real do C6 — roda só com credenciais no ambiente.
#
# Requisitos (nunca commitar valores):
#   C6_SANDBOX_CLIENT_ID / C6_SANDBOX_CLIENT_SECRET  (e-mail de onboarding C6)
#   C6_SANDBOX_PFX_BASE64 / C6_SANDBOX_PFX_PASSWORD  (certificado mTLS do portal)
#   C6_SANDBOX_CHAVE_PIX                             (chave Pix do sandbox)
# Janela do sandbox: seg-sex, 7h-23h (BRT). Fora disso o banco não responde.
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not (os.environ.get("C6_SANDBOX_CLIENT_ID") and os.environ.get("C6_SANDBOX_CLIENT_SECRET")),
    reason="sem credenciais C6_SANDBOX_* no ambiente",
)


@pytest.fixture
def provider():
    import httpx

    from app.providers.c6 import C6Provider

    p = C6Provider(
        account_config={"chave_pix": os.environ.get("C6_SANDBOX_CHAVE_PIX", "")},
        credentials={
            "client_id": os.environ["C6_SANDBOX_CLIENT_ID"],
            "client_secret": os.environ["C6_SANDBOX_CLIENT_SECRET"],
            "pfx_base64": os.environ.get("C6_SANDBOX_PFX_BASE64", ""),
            "pfx_password": os.environ.get("C6_SANDBOX_PFX_PASSWORD", ""),
        },
    )
    # Fora da janela (seg-sex 7h-23h BRT) o banco responde 403/503 no /v1/auth.
    # Sem esta sonda, rodar 23h05 pinta a suíte de vermelho por horário — e falha
    # que não é defeito treina todo mundo a ignorar falha.
    try:
        p._client().token()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (403, 503):
            pytest.skip(f"sandbox fora da janela (auth respondeu {e.response.status_code})")
        raise
    except httpx.TransportError as e:
        pytest.skip(f"sandbox inacessível: {type(e).__name__}")
    return p


def test_sandbox_emitir_consultar_cancelar_boleto(provider):
    import time
    from datetime import date, timedelta

    import httpx

    from app.schemas import Cobranca, Pagador, Status

    ref = uuid.uuid4().hex[:10]  # external_reference_id: alfanum 1-10
    out = provider.registrar(Cobranca(
        valor="10.00",
        vencimento=date.today() + timedelta(days=30),
        seu_numero=ref,
        pagador=Pagador(
            nome="Teste Sandbox",
            documento="12345678909",
            endereco={"street": "Av. Teste", "number": 1, "city": "Sao Paulo",
                      "state": "SP", "zip_code": "01000000"},
        ),
    ))
    assert out.id, out.raw
    assert out.linha_digitavel

    consultado = provider.consultar(out.id)
    assert consultado.status in (Status.registrado, Status.pendente)

    # O registro no banco é assíncrono: cancelar logo após emitir responde 400
    # ("já existe uma requisição em processamento"). Aguarda e re-tenta — o
    # tempo de processamento do sandbox varia (observado de ~10s a minutos).
    # O provider JÁ re-tenta internamente (C6_CIP_RETRIES/WAIT) e converte o 400
    # da CIP em ProcessamentoPendente. Capturar só HTTPStatusError, como estava,
    # deixava o laço morrer no primeiro ciclo com exceção não tratada — o teste
    # parecia esperar 180s e não esperava nada.
    from app.providers.c6 import ProcessamentoPendente

    ultimo_erro = ""
    for _ in range(6):
        try:
            baixado = provider.baixar(out.id)
            break
        except ProcessamentoPendente as e:
            ultimo_erro = str(e)
            time.sleep(10)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 400:
                raise
            ultimo_erro = e.response.text[:200]
            time.sleep(10)
    else:
        pytest.skip(f"CIP não liberou o cancelamento no sandbox: {ultimo_erro}")
    assert baixado.status == Status.baixado
    assert provider.consultar(out.id).status == Status.baixado  # CANCELLED no banco


def test_sandbox_pix_cob_imediata(provider):
    from app.schemas import PixCobranca

    if not provider.account_config.get("chave_pix"):
        pytest.skip("sem C6_SANDBOX_CHAVE_PIX")
    out = provider.criar_pix(PixCobranca(valor="1.00", descricao="teste sandbox"))
    assert out.txid, out.raw
    assert out.pix_copia_cola or out.location


def test_sandbox_extrato_e_conciliacao(provider):
    """Leituras puras: nao criam nada, nao esperam CIP, nao deixam residuo.

    Afirma FORMATO, nao conteudo -- o sandbox pode nao ter movimento no periodo,
    e teste que exige dado que o banco nao garante vira flaky."""
    from datetime import date, timedelta

    fim = date.today()
    ini = fim - timedelta(days=30)

    extrato = provider.extrato(start_date=ini.isoformat(), end_date=fim.isoformat())
    assert isinstance(extrato, dict), extrato

    receb = provider.listar_recebiveis(start_date=ini.isoformat(), end_date=fim.isoformat(),
                                       page=1, size=10)
    assert receb.page is not None or receb.items is not None

    trans = provider.listar_transacoes(start_date=ini.isoformat(), end_date=fim.isoformat(),
                                       page=1, size=10)
    assert trans.page is not None or trans.items is not None


def test_sandbox_pix_cobv_revisao_e_listagem(provider):
    """cobv exige devedor identificado (regra BACEN) e txid proprio.
    Encadeia revisao e consulta no mesmo txid -- Pix nao passa por CIP."""
    import random
    import string
    from datetime import date, timedelta

    from app.schemas import Pagador, PixCobranca

    if not provider.account_config.get("chave_pix"):
        pytest.skip("sem C6_SANDBOX_CHAVE_PIX")

    txid = "".join(random.SystemRandom().choices(string.ascii_lowercase + string.digits, k=30))
    out = provider.criar_pix(PixCobranca(
        valor="1.00", descricao="e2e cobv",
        data_vencimento=date.today() + timedelta(days=30), txid=txid,
        devedor=Pagador(nome="Teste E2E", documento="12345678909"),
    ))
    assert out.txid == txid, out.raw

    revisado = provider.revisar_pix(txid, {"valor": {"original": "2.00"}}, vencimento=True)
    assert revisado, "PATCH de revisão não devolveu corpo"

    assert provider.consultar_pix(txid, vencimento=True).txid == txid

    inicio = (date.today() - timedelta(days=1)).isoformat()
    lista = provider.listar_pix(inicio=f"{inicio}T00:00:00Z",
                                fim=f"{date.today().isoformat()}T23:59:59Z",
                                vencimento=True)
    assert isinstance(lista, dict)


def test_sandbox_checkout_criar_consultar_cancelar(provider):
    """Link de pagamento com cartão. Não passa pela CIP, então roda em segundos
    e é determinístico — ao contrário do boleto, que espera aprovação.

    Não tenta PAGAR: o PAN é digitado na página do C6, e é isso que a decisão 3
    do estudo quer. Chegar a `PAID` é roteiro manual."""
    from app.schemas import Status

    out = provider.criar_checkout({
        "amount": 150.0, "description": "e2e checkout",
        "payment": {"card": {"type": "CREDIT", "installments": 1}},
    })
    assert out.id, out.raw
    assert out.url and out.url.startswith("http"), out.raw
    assert out.status == Status.pendente

    consultado = provider.consultar_checkout(out.id)
    assert consultado.status == Status.pendente

    cancelado = provider.cancelar_checkout(out.id)
    assert cancelado.status == Status.baixado
