# Capacidade opcional de provider — checagem antes de chamar.
#
# `BankProvider` define os métodos obrigatórios; capacidades opcionais existem
# só em quem implementa (ex.: Bolepix e webhook-no-banco são exclusivos do C6).
# Chamar direto num provider que não implementa levanta AttributeError e vira
# **500 sem mensagem útil** — que é erro do CHAMADOR, não do serviço.
from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException

from app.providers.base import BankProvider
from app.schemas import Banco, Provider


def implementa(alvo: Any, metodo: str) -> bool:
    """O provider implementa mesmo, ou só herda a declaração da base?

    `getattr is not None` não bastava: a `BankProvider` **declara** algumas
    capacidades levantando `NotImplementedError`, e para essas o `getattr`
    sempre achava alguma coisa — a checagem passava e o `NotImplementedError`
    virava 500. Aconteceu com `listar_recebiveis`/`listar_transacoes`, as duas
    únicas assim hoje.

    O critério é o mesmo que o `GET /bancos` usa para montar `capacidades`:
    sobrescrito = suportado de fato. As duas respostas passam a concordar — o
    catálogo vira previsão exata do 422, em vez de descrição paralela.
    """
    klass = alvo if isinstance(alvo, type) else type(alvo)
    impl = getattr(klass, metodo, None)
    return impl is not None and impl is not getattr(BankProvider, metodo, None)


def exige_capacidade(provider_obj: Any, metodo: str, provider: Provider | Banco,
                     *, recurso: str, alternativa: str) -> Callable[..., Any]:
    """Devolve o método, ou 422 explicando que aquele banco não o oferece.

    `recurso` e `alternativa` entram na mensagem: o erro tem de dizer PARA ONDE
    ir, não só que falhou.

    Aceita `Banco` além de `Provider` porque desde `provider=on|off` o nome do
    banco não está mais no `provider`: quem já o resolveu passa o banco, e a
    mensagem diz "banco 'itau'" em vez de "banco 'on'".
    """
    fn = getattr(provider_obj, metodo, None)
    if not implementa(provider_obj, metodo):
        raise HTTPException(
            status_code=422,
            detail=f"banco '{provider.value}' não oferece {recurso}; {alternativa}",
        )
    return fn
