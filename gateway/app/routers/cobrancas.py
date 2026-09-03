# Coleção e sumário de cobranças — `INT-S05`.
#
# O gateway sempre soube emitir, consultar, alterar e baixar UM título. Não
# sabia responder "quais boletos eu tenho no período" nem "quanto está em
# aberto" — quem integrava paginava por conta própria guardando os ids da
# emissão, ou caía no arquivo de retorno.
#
# Hoje só o **Inter** publica coleção e sumário: C6 e Sicoob tratam um título
# por vez. A rota segue o padrão das capacidades exclusivas (Bolepix e checkout
# são do C6): existe para todos, e o banco que não oferece responde `422`
# dizendo quem oferece — nunca `500`.
#
# O corpo é **passthrough**, como nas demais rotas de consulta: os nomes dos
# campos são os do banco. Traduzir só a entrada e devolver o vocabulário dele
# faria a resposta contradizer o request.
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.vault import Vault, get_vault
from app.registry import (CaminhoInvalido, build_rest_provider,
                          credentials_from_header, resolver_caminho)
from app.routers._capacidades import (
    exige_capacidade,
    exige_capacidade_antes_da_credencial,
)
from app.routers._credentials import resolve_request_credentials
from app.routers._params import BANCO as _BANCO, PROVIDER_ON as _PROVIDER_ON, TENANT as _TENANT
from app.schemas import Banco, Provider

router = APIRouter(prefix="/cobrancas", tags=["cobranca"])

_CREDS_HEADER = Header(
    default=None, alias="X-Bank-Credentials",
    description="Credenciais do banco (JSON em base64) — só memória, nunca persistidas.")
_AUTH_HEADER = Header(default=None, description="Bearer bapi_... (token do /credenciais)")

#: Janela máxima. O Inter não publica limite de período, mas coleção sem teto é
#: convite a varredura de base inteira — e o custo cai no banco, não aqui.
#: Noventa dias cobre o trimestre, que é o recorte de conciliação usual.
JANELA_MAX_DIAS = 90

_ALTERNATIVA = ("coleção e sumário de cobranças existem no banco que os publica — hoje o "
                "Inter; use `banco=inter`. C6 e Sicoob tratam um título por vez "
                "(`GET /cobranca/{id}`). No caminho offline não há coleção: o estado vem "
                "do arquivo de retorno (`POST /api/retorno`) ou do OFX")

_INICIO = Query(description="Data inicial (YYYY-MM-DD)", examples=["2027-01-01"])
_FIM = Query(description=f"Data final (YYYY-MM-DD; no máximo {JANELA_MAX_DIAS} dias após a inicial)",
             examples=["2027-01-31"])
_PAGINA = Query(default=1, ge=1, description="Página, a partir de 1")
_TAMANHO = Query(default=50, ge=1, le=1000, description="Itens por página")

#: Filtros do contrato. Nomes em português, como o resto da API; o provider
#: traduz para o vocabulário do banco — e confere o valor contra a lista dele
#: antes de sair daqui, para valor inválido virar `422` explicando, e não `400`
#: genérico do banco.
_SITUACAO = Query(default=None, description="Situação do título (vocabulário do banco)",
                  examples=["A_RECEBER"])
_SEU_NUMERO = Query(default=None, description="Seu número, como enviado na emissão")
_PAGADOR = Query(default=None, description="Nome do pagador (busca parcial no banco)")
_DOC_PAGADOR = Query(default=None, description="CPF/CNPJ do pagador (só dígitos)")
_FILTRAR_POR = Query(default=None, description="Qual data o período filtra (vocabulário do banco)",
                     examples=["VENCIMENTO"])
_TIPO = Query(default=None, description="Tipo da cobrança (vocabulário do banco)",
              examples=["SIMPLES"])
_ORDENAR_POR = Query(default=None, description="Campo de ordenação (vocabulário do banco)",
                     examples=["DATA_VENCIMENTO"])
_ORDENACAO = Query(default=None, description="Sentido da ordenação (vocabulário do banco)",
                   examples=["DESC"])


def _periodo(inicio: date, fim: date) -> tuple[str, str]:
    """Confere o período ANTES da ida ao banco.

    Período invertido é o erro mais silencioso: o banco costuma responder lista
    vazia, e quem chama lê como "não houve movimento".
    """
    if fim < inicio:
        raise HTTPException(
            status_code=422,
            detail=f"fim ({fim}) é anterior a inicio ({inicio}); período invertido volta "
                   "vazio e parece ausência de cobranças")
    dias = (fim - inicio).days
    if dias > JANELA_MAX_DIAS:
        raise HTTPException(
            status_code=422,
            detail=f"período de {dias} dias acima do máximo de {JANELA_MAX_DIAS}; "
                   "divida a consulta em janelas menores")
    return inicio.isoformat(), fim.isoformat()


def _provider(tenant_id: str, provider: Provider, banco: Banco | None, vault: Vault,
              credentials_header: str | None, authorization: str | None):
    try:
        explicit = credentials_from_header(credentials_header)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    creds = resolve_request_credentials(
        authorization=authorization, explicit=explicit,
        tenant_id=tenant_id, provider=provider, banco=banco)
    try:
        return build_rest_provider(provider=provider, banco=banco, tenant_id=tenant_id,
                                   account_config={}, vault=vault, credentials=creds)
    except (CaminhoInvalido, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _cap(obj, metodo: str, provider: Provider, banco: Banco | None, recurso: str):
    try:
        _, alvo = resolver_caminho(provider, banco, {})
    except CaminhoInvalido:
        alvo = provider
    return exige_capacidade(obj, metodo, alvo, recurso=recurso, alternativa=_ALTERNATIVA)


def _cap_antes(metodo: str, provider: Provider, banco: Banco | None, recurso: str) -> None:
    """A mesma checagem, na classe, antes de pedir credencial."""
    exige_capacidade_antes_da_credencial(provider, banco, None, metodo,
                                         recurso=recurso, alternativa=_ALTERNATIVA)


def _filtros(situacao, seu_numero, pagador, documento_pagador, filtrar_data_por,
             tipo_cobranca=None, **extra) -> dict[str, Any]:
    return {"situacao": situacao, "seu_numero": seu_numero, "pagador": pagador,
            "documento_pagador": documento_pagador, "filtrar_data_por": filtrar_data_por,
            "tipo_cobranca": tipo_cobranca, **extra}


def _chamar(fn, **kwargs) -> dict:
    """Filtro fora do vocabulário do banco é erro de quem chama, não do banco.

    O provider confere e levanta `ValueError`; sem esta tradução ele subiria
    como `500`, e o texto que diz exatamente qual valor usar se perderia.
    """
    try:
        return fn(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("", response_model=dict)
def listar(tenant_id: str = _TENANT, inicio: date = _INICIO, fim: date = _FIM,
           provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
           pagina: int = _PAGINA, tamanho: int = _TAMANHO,
           situacao: str | None = _SITUACAO, seu_numero: str | None = _SEU_NUMERO,
           pagador: str | None = _PAGADOR, documento_pagador: str | None = _DOC_PAGADOR,
           filtrar_data_por: str | None = _FILTRAR_POR, tipo_cobranca: str | None = _TIPO,
           ordenar_por: str | None = _ORDENAR_POR, tipo_ordenacao: str | None = _ORDENACAO,
           x_bank_credentials: str | None = _CREDS_HEADER,
           authorization: str | None = _AUTH_HEADER,
           vault: Vault = Depends(get_vault)) -> dict:
    """Boletos do período — a coleção que a API não sabia devolver.

    `pagina` começa em **1**, como no resto da API. O Inter pagina a partir de
    zero e o provider converte: repassar a página crua devolveria a segunda
    para quem pediu a primeira, sem erro nenhum.
    """
    de, ate = _periodo(inicio, fim)
    _cap_antes("listar_cobrancas", provider, banco, "coleção de cobranças")
    p = _provider(tenant_id, provider, banco, vault, x_bank_credentials, authorization)
    fn = _cap(p, "listar_cobrancas", provider, banco, "coleção de cobranças")
    return _chamar(fn, inicio=de, fim=ate, pagina=pagina, tamanho=tamanho,
                   filtros=_filtros(situacao, seu_numero, pagador, documento_pagador,
                                    filtrar_data_por, tipo_cobranca,
                                    ordenar_por=ordenar_por, tipo_ordenacao=tipo_ordenacao))


@router.get("/sumario", response_model=dict)
def sumario(tenant_id: str = _TENANT, inicio: date = _INICIO, fim: date = _FIM,
            provider: Provider = _PROVIDER_ON, banco: Banco | None = _BANCO,
            situacao: str | None = _SITUACAO, seu_numero: str | None = _SEU_NUMERO,
            pagador: str | None = _PAGADOR, documento_pagador: str | None = _DOC_PAGADOR,
            filtrar_data_por: str | None = _FILTRAR_POR, tipo_cobranca: str | None = _TIPO,
            x_bank_credentials: str | None = _CREDS_HEADER,
            authorization: str | None = _AUTH_HEADER,
            vault: Vault = Depends(get_vault)) -> dict:
    """Totais do período por situação — o mesmo recorte da coleção, sem paginar.

    Responde "quanto está em aberto" sem baixar a coleção inteira para somar no
    cliente, que é o que fazia quem precisava do número.

    Os totais vêm em `sumario`: o Inter devolve array na raiz, e array na raiz
    não tem onde crescer. Os itens seguem passthrough, com os nomes do banco.

    Ordenação não entra aqui — o banco não a aceita no sumário, e aceitá-la na
    rota só para descartar prometeria um recorte que não acontece.
    """
    de, ate = _periodo(inicio, fim)
    _cap_antes("sumario_cobrancas", provider, banco, "sumário de cobranças")
    p = _provider(tenant_id, provider, banco, vault, x_bank_credentials, authorization)
    fn = _cap(p, "sumario_cobrancas", provider, banco, "sumário de cobranças")
    return _chamar(fn, inicio=de, fim=ate,
                   filtros=_filtros(situacao, seu_numero, pagador, documento_pagador,
                                    filtrar_data_por, tipo_cobranca))
