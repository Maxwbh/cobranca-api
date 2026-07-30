# Capacidade opcional de provider — checagem antes de chamar.
#
# `BankProvider` define os métodos obrigatórios; capacidades opcionais existem
# só em quem implementa (ex.: Bolepix e webhook-no-banco são exclusivos do C6).
# Chamar direto num provider que não implementa levanta AttributeError e vira
# **500 sem mensagem útil** — que é erro do CHAMADOR, não do serviço.
from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException

from app.schemas import Provider


def exige_capacidade(provider_obj: Any, metodo: str, provider: Provider,
                     *, recurso: str, alternativa: str) -> Callable[..., Any]:
    """Devolve o método, ou 422 explicando que aquele banco não o oferece.

    `recurso` e `alternativa` entram na mensagem: o erro tem de dizer PARA ONDE
    ir, não só que falhou.
    """
    fn = getattr(provider_obj, metodo, None)
    if fn is None:
        raise HTTPException(
            status_code=422,
            detail=f"banco '{provider.value}' não oferece {recurso}; {alternativa}",
        )
    return fn
