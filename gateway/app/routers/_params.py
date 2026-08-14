# Parâmetros de query compartilhados entre os routers.
#
# O eixo `banco` é o MESMO em toda a API. Declarado uma vez, a descrição não
# diverge rota a rota — que é exatamente como o `provider` chegou a significar
# duas coisas diferentes conforme o endpoint.
from __future__ import annotations

from fastapi import Query

from app.schemas import Provider

_CAMINHO = ("**Caminho**: `on` = API do banco · `off` = engine pyCobrança. "
            "Diz por onde, não qual banco — a instituição é o `banco`. Nome de "
            "banco aqui (`c6`) é apelido legado de `on` + `banco`, e sai na 3.0.0.")

# O `banco` tinha descrição e o `provider` não: no Swagger, o par que só faz
# sentido lido junto aparecia com metade explicada.
PROVIDER = Query(description=_CAMINHO)
PROVIDER_ON = Query(default=Provider.c6, description=_CAMINHO)


def banco_query(descricao: str | None = None):
    return Query(
        None,
        description=descricao or (
            "Instituição (`c6`, `sicoob`, `inter`, `itau`…). Use com "
            "`provider=on`. Omitido, o `provider` legado (nome do banco) resolve."
        ),
    )


BANCO = banco_query()
