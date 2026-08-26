# Capacidade opcional de provider — checagem antes de chamar.
#
# `BankProvider` define os métodos obrigatórios; capacidades opcionais existem
# só em quem implementa (ex.: Bolepix e webhook-no-banco são exclusivos do C6).
# Chamar direto num provider que não implementa levanta AttributeError e vira
# **500 sem mensagem útil** — que é erro do CHAMADOR, não do serviço.
from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import HTTPException

from app.providers.base import BankProvider
from app.schemas import Banco, Provider

#: Capacidade cujo DIALETO o provider herda e que ninguém confirmou NO BANCO.
#:
#: `implementa()` responde "a classe tem o método". Para capacidade que vem de
#: mixin, isso é mais fraco do que parece: o método existe porque herdamos o
#: dialeto, não porque o banco exponha as rotas. Nos dois casos a introspecção
#: diz `True`, e o catálogo — que existe justamente para não envelhecer — passa
#: a anunciar o que ninguém verificou.
#:
#: O caso concreto: o **Inter** herda `BacenPixAutomaticoMixin`, então
#: `GET /bancos` listava `pix_automatico` para ele. A própria evidência de
#: homologação (`docs/homologacao/evidencia-sandbox-inter.json`, caso `PA_01`)
#: diz o contrário, com todas as letras: *"não consta no SDK oficial do Inter
#: (inter-co/pj-sdk-java) […] falta confirmar no portal se o banco expõe as
#: rotas. Prometer antes de confirmar seria vender o que não se sabe"*.
#:
#: C6 (15 casos em 4 jornadas) e Sicoob (`PA_01`, 201) estão confirmados no
#: sandbox e por isso NÃO entram aqui — a lista é de quem falta confirmar, não
#: de quem usa mixin.
#:
#: `banco -> {método: (recurso, motivo)}`.
_NAO_CONFIRMADO: dict[str, dict[str, tuple[str, str]]] = {
    "inter": {
        "criar_recorrencia": (
            "Pix Automático",
            "o provider herda o dialeto BACEN de recorrência, mas `rec`/`solicrec`"
            " não constam no SDK oficial do Inter e não foram exercitados no"
            " sandbox"),
    },
}


def flag_de_confirmacao(banco: str, metodo: str) -> str:
    """Variável que liga a capacidade depois de confirmada no banco.

    Mesmo formato do `<BANCO>_REGISTERED_READY`, que já é como esta casa libera
    o que depende de homologação: quem tiver credencial real confirma, liga a
    flag e usa — sem esperar por uma versão nossa.
    """
    recurso = _NAO_CONFIRMADO.get(banco, {}).get(metodo, ("", ""))[0]
    sufixo = recurso.upper().replace(" ", "_").replace("Á", "A").replace("Í", "I")
    return f"{banco.upper()}_{sufixo}_READY"


def confirmado(alvo: Any, metodo: str, banco: str | None) -> bool:
    """A capacidade foi confirmada NAQUELE banco?

    `True` para tudo que não está em `_NAO_CONFIRMADO` — a checagem é a exceção,
    não a regra. Para o que está, só a flag confirma.
    """
    if not banco or metodo not in _NAO_CONFIRMADO.get(banco, {}):
        return True
    return os.environ.get(flag_de_confirmacao(banco, metodo), "").lower() in (
        "1", "true", "yes")


def nao_confirmadas(banco: str) -> dict[str, str]:
    """`capacidade -> flag`, para o catálogo poder DIZER em vez de omitir.

    Some da lista de capacidades e aparece aqui: omitir sem explicar faria o
    integrador concluir que o banco não tem, quando o certo é "não sabemos".
    """
    from app.routers.bancos import _CAPACIDADES  # tardio: o catálogo importa daqui

    return {_CAPACIDADES[metodo]: flag_de_confirmacao(banco, metodo)
            for metodo in _NAO_CONFIRMADO.get(banco, {})
            if metodo in _CAPACIDADES and not confirmado(None, metodo, banco)}


def disponivel(alvo: Any, metodo: str, banco: str | None = None) -> bool:
    """Implementado no código **e** confirmado no banco.

    É o critério único do catálogo e das rotas — se as duas respostas usassem
    checagens diferentes, o `GET /bancos` voltaria a ser descrição paralela em
    vez de previsão exata do 422.
    """
    return implementa(alvo, metodo) and confirmado(alvo, metodo, banco)


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
    # Implementado, mas não confirmado NAQUELE banco. Mensagem própria: dizer
    # "não oferece" seria afirmar o que também não se sabe, e esconderia o
    # caminho de quem tem credencial real para confirmar.
    banco = provider.value
    if not confirmado(provider_obj, metodo, banco):
        _, motivo = _NAO_CONFIRMADO[banco][metodo]
        raise HTTPException(
            status_code=422,
            detail=(f"{recurso} não foi confirmado no banco '{banco}': {motivo}."
                    f" Confirme com credencial real e ligue"
                    f" {flag_de_confirmacao(banco, metodo)}=true; {alternativa}"),
        )
    return fn
