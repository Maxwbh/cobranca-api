from __future__ import annotations

from fastapi import APIRouter, Depends

from app.clients import engine
from app.core.vault import Vault, get_vault
from app.providers.offline_engine import _to_engine_payload
from app.registry import build_provider
from app.schemas import CarneIn, CarneOut

router = APIRouter(prefix="/carne", tags=["carne"])


# 201 acompanha as demais rotas de criação da API. Sem `Location`: o carnê não
# é recurso consultável — é o PDF montado mais as N cobranças, e cada uma já
# volta no corpo com o próprio id. Apontar para um único /carne/{id} seria
# inventar um recurso que não existe.
@router.post("", response_model=CarneOut, status_code=201)
def gerar_carne(body: CarneIn, vault: Vault = Depends(get_vault)) -> CarneOut:
    """Registra N parcelas no provider e monta o carnê (3-vias A4) no engine.

    Bancos registram cobranças individuais; o PDF de carnê é montado
    in-process pela engine pyCobrança. Quando o banco devolve um nosso_numero
    registrado, ele é repassado ao render para o carnê bater com a cobrança.
    """
    provider = build_provider(
        provider=body.provider, tenant_id=body.tenant_id,
        account_config=body.account_config, vault=vault,
        credentials=body.credentials,
    )

    cobrancas = [provider.registrar(p) for p in body.parcelas]

    boletos = []
    for parcela, cob in zip(body.parcelas, cobrancas):
        data = _to_engine_payload(parcela, body.account_config)
        if cob.id:  # usa o nosso_numero registrado pelo banco, se houver
            data["nosso_numero"] = cob.id
        boletos.append(data)

    rendered = engine.render_carne(body.bank, boletos)
    return CarneOut(carne_pdf_base64=rendered.get("pdf_base64"), cobrancas=cobrancas)
