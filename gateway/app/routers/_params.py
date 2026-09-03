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

# `tenant_id` aparecia CRU (`tenant_id: str`) em dez routers: sem descrição e
# sem exemplo, o Swagger mostrava um campo vazio e obrigatório, sem dizer o que
# cabe ali. O mesmo campo no CORPO já trazia `examples=["empresa_123"]` — a doc
# ensinava o valor num lugar e não no outro.
TENANT = Query(
    description="Identificador do tenant — é ele que resolve as credenciais do "
                "banco no cofre. Não é o número da conta.",
    examples=["empresa_123"],
)

# `inicio`/`fim` do `/pix` eram `str` cru. O docstring da rota dizia "RFC3339",
# mas docstring é resumo da ROTA e não documenta o campo: no Swagger o
# integrador via dois textos livres sem formato, e a data errada vira 400 do
# banco. O `/pix-automatico` já declarava os dois assim.
INICIO = Query(description="Início do período, RFC3339 (ex.: 2026-01-01T00:00:00Z)",
               examples=["2026-01-01T00:00:00Z"])
FIM = Query(description="Fim do período, RFC3339",
            examples=["2026-01-31T23:59:59Z"])
