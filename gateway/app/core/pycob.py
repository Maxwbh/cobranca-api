# Engine de cobrança offline — pyCobranca (100% Python, in-process).
#
# Substitui a conexão com o Banking Core BrCobrança (Ruby), DESCONTINUADA.
# Mantém os contratos da superfície /api/* (nomes de campos = contrato REST
# v1.5.0, que o pycobranca.contracts espelha).
from __future__ import annotations

import io
import inspect
import re
import tempfile
from contextlib import contextmanager
from datetime import date
from typing import Any

from pycobranca import __version__ as PYCOBRANCA_VERSION
from pycobranca.bancos import Bancos
from pycobranca.contracts import SLUG_POR_CODIGO
from pycobranca.exceptions import (BancoNaoRegistrado, BoletoInvalido,
                                   OFXInvalido, PyCobrancaError, RetornoInvalido)
from pycobranca.render import render_boleto_pdf, render_carne_pdf, render_fatura_pdf
from pycobranca.render.marcas import logo_do_banco
from pycobranca.render.modelos import MODELOS_BOLETO
from pycobranca import cnab as _cnab
from pycobranca.cnab import Pagamento, PagamentoPix, Retorno
from pycobranca.contracts.contrato_rest import retorno_item_para_api
from pycobranca.ofx import Extrato

CODIGO_POR_SLUG: dict[str, str] = {v: k for k, v in SLUG_POR_CODIGO.items()}


class DadosInvalidos(ValueError):
    """Erros de validação do boleto (equivalente ao 400 do contrato)."""

    def __init__(self, erros: list[str]):
        super().__init__("; ".join(erros))
        self.erros = erros



@contextmanager
def erro_do_banco():
    """Converte `BoletoInvalido` em `DadosInvalidos` — 400, não 500.

    `boleto.validar()` não pega tudo: há layout que só descobre a falta na hora
    de FORMATAR. O Sicredi é o caso limite — sem `data_documento` (de onde sai o
    ano do nosso número) e sem `byte_idt`, ele levanta ao montar o nosso número
    formatado, depois de `validar()` ter dito que estava tudo certo.

    Antes disto a exceção escapava dos handlers e o consumidor recebia
    **500 Internal Server Error** por um campo que faltava no payload dele — e a
    mensagem da engine, que dizia exatamente qual campo era, ficava no log do
    servidor em vez de chegar a quem podia agir.
    """
    try:
        yield
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e


def _erros(e: Exception) -> list[str]:
    """Extrai a lista estruturada de erros da engine.

    `BoletoInvalido` (e o nosso `DadosInvalidos`) carregam `.erros` — UMA
    entrada por campo violado. Colapsar em `str(e)` jogaria fora a granularidade
    que a PyCobranca 1.0.1 fornece (doc 14-validacao-campos). Sem `.erros`
    (ValueError/TypeError cru), cai no texto.
    """
    lst = getattr(e, "erros", None)
    return list(lst) if lst else [str(e)]


def bancos_suportados() -> list[str]:
    return sorted(CODIGO_POR_SLUG)


def _classe_banco(bank: str):
    codigo = CODIGO_POR_SLUG.get(bank)
    if not codigo:
        raise DadosInvalidos([f"Banco não suportado: {bank!r}"])
    try:
        return Bancos.find(codigo)
    except BancoNaoRegistrado as e:
        raise DadosInvalidos([f"Banco não registrado na engine: {bank!r} ({codigo})"]) from e


def _para_date(valor: Any) -> Any:
    if isinstance(valor, str) and valor:
        limpo = valor.replace("/", "-")
        try:
            return date.fromisoformat(limpo)
        except ValueError:
            pass
    return valor


# Contrato REST -> kwargs do BancoBase (o inverso de contracts.boleto_para_api)
_MAPA_CAMPOS = {
    "conta_corrente": "conta",
    "documento_cedente": "cedente_documento",
    "chave_pix": "pix_chave",
    "txid": "pix_txid",
}
_CAMPOS_DATA = {"data_vencimento", "data_documento", "data_processamento"}
# A engine desenha estes campos linha a linha e espera uma LISTA. Recebendo
# string ela itera os caracteres: o boleto sai com "A", "p", "o", "s"... um por
# linha, até estourar a caixa — sem erro, sem aviso, com o texto perdido.
#
# JSON não tem tipo "várias linhas", então o cliente naturalmente manda string
# com `\n`. Normalizar aqui é o que torna as duas formas equivalentes.
_CAMPOS_MULTILINHA = {"instrucoes", "demonstrativo"}

# Medidos no PDF gerado pela engine: a caixa de instruções tem 404pt de largura
# e comporta exatamente 7 linhas — **idêntico com e sem PIX**. O QR do Bolepix
# não encolhe a área de instruções (conferido gerando as duas variantes).
#
# Exceder cada limite falha de um jeito diferente, e nenhum dos dois avisa:
# linha comprida ATRAVESSA a coluna de Desconto/Mora/Valor cobrado, deixando as
# duas ilegíveis; linha além da sétima simplesmente NÃO é desenhada.
#
# O gateway NÃO reformata o texto — quebrar linha por conta própria mudaria o
# conteúdo de um documento de cobrança. Ele mede e recusa; reescrever é do
# cliente, que sabe onde a frase pode ser cortada.
LARGURA_INSTRUCAO = 100
MAX_LINHAS_INSTRUCAO = 7


def _linhas(valor: Any, campo: str) -> Any:
    """Campo multilinha: string vira lista de linhas e os tamanhos são validados.

    A separação por `\\n` não é reformatação — é adaptação de tipo. JSON não tem
    "várias linhas", então o cliente manda string; a engine espera lista e,
    recebendo string, iterava os CARACTERES (o boleto saía com "A", "p", "o",
    "s"… um por linha). Cada linha chega ao PDF exatamente como foi enviada.

    O que não couber é **recusado**, não ajustado: em documento de cobrança,
    perder cláusula em silêncio é pior que devolver erro.
    """
    if isinstance(valor, str):
        linhas = [linha.rstrip() for linha in valor.splitlines() if linha.strip()]
    elif isinstance(valor, (list, tuple)):
        linhas = [str(item).rstrip() for item in valor if str(item).strip()]
    else:
        return valor

    erros: list[str] = []
    if len(linhas) > MAX_LINHAS_INSTRUCAO:
        erros.append(f"{campo}: {len(linhas)} linhas, máximo {MAX_LINHAS_INSTRUCAO}"
                     f" (a partir da {MAX_LINHAS_INSTRUCAO + 1}ª a engine não imprime)")
    compridas = [(i + 1, len(linha)) for i, linha in enumerate(linhas)
                 if len(linha) > LARGURA_INSTRUCAO]
    if compridas:
        detalhe = ", ".join(f"linha {n} com {c}" for n, c in compridas)
        erros.append(f"{campo}: máximo {LARGURA_INSTRUCAO} caracteres por linha"
                     f" ({detalhe}) — texto mais longo invade a coluna de valores")
    if erros:
        raise DadosInvalidos(erros)
    return linhas


#: Campos que a documentação anunciava e a engine NUNCA leu — herança da era
#: Ruby, onde o QR vinha pronto no payload. Hoje quem desenha o Bolepix é
#: `chave_pix` (+ `tipo_chave_pix`/`txid`): a engine monta o EMV e o QR ela
#: mesma, e um payload pronto não tem por onde entrar.
#:
#: Sem esta lista eles caíam no descarte silencioso de campo desconhecido lá
#: embaixo: 200, boleto sem QR, e o pagador sem como pagar por Pix — o pior
#: desfecho possível, porque nada indica que faltou algo.
_CAMPOS_SEM_CONSUMIDOR = {
    "emv": "o payload EMV pronto não é lido pela engine",
    "pix_label": "o rótulo do QR é do modelo, não do payload",
}


def construir_boleto(bank: str, data: dict[str, Any]):
    """Constrói a instância do banco a partir do payload do contrato REST."""
    mortos = sorted(c for c in _CAMPOS_SEM_CONSUMIDOR if (data or {}).get(c))
    if mortos:
        raise DadosInvalidos(
            [f"`{c}` não gera QR Pix — {_CAMPOS_SEM_CONSUMIDOR[c]}. Para o Bolepix,"
             " envie `chave_pix` (e `txid`, se quiser rastrear): a engine monta"
             " o EMV e desenha o QR" for c in mortos])
    klass = _classe_banco(bank)
    aceitos = set(inspect.signature(klass.__init__).parameters) - {"self"}
    kwargs: dict[str, Any] = {}
    for chave, valor in (data or {}).items():
        destino = _MAPA_CAMPOS.get(chave, chave)
        if destino not in aceitos or valor in (None, ""):
            continue
        if chave in _CAMPOS_DATA:
            kwargs[destino] = _para_date(valor)
        elif chave in _CAMPOS_MULTILINHA:
            kwargs[destino] = _linhas(valor, chave)
        else:
            kwargs[destino] = valor
    try:
        boleto = klass(**kwargs)
    except (PyCobrancaError, ValueError, TypeError) as e:
        raise DadosInvalidos(_erros(e)) from e
    # Logo do banco no cabeçalho — padrão, e não opção. A engine empacota os
    # PNGs por código FEBRABAN, mas a capacidade é opt-in: sem esta linha o
    # boleto saía com a sigla em texto, e quem recebe compara com o boleto do
    # internet banking. Vale para TODOS os caminhos porque todos passam por
    # aqui — boleto avulso, lote, carnê e fatura.
    #
    # Só preenche o que veio vazio: logo enviado pelo chamador continua
    # mandando. Banco sem PNG empacotado devolve None e o layout cai na sigla,
    # como antes — nunca no logo de outro banco.
    if getattr(boleto, "logo", None) is None:
        boleto.logo = logo_do_banco(boleto.codigo)
    return boleto


def validar(bank: str, data: dict[str, Any]) -> None:
    boleto = construir_boleto(bank, data)
    try:
        boleto.validar()
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e


def dados_boleto(bank: str, data: dict[str, Any]) -> dict[str, Any]:
    """Campos calculados do boleto — contrato: SEMPRE os 3 campos de nosso_numero."""
    boleto = construir_boleto(bank, data)
    try:
        boleto.validar()
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e
    with erro_do_banco():
        formatado = boleto.nosso_numero_formatado()
        dv = getattr(boleto, "nosso_numero_dv", None)
        if callable(dv):
            dv = dv()
        if dv is None:
            m = re.search(r"-(\w+)$", formatado)
            dv = m.group(1) if m else ""
        return {
            "bank": bank,
            "nosso_numero": str(boleto.nosso_numero),
            "nosso_numero_formatado": formatado,
            "nosso_numero_dv": str(dv),
            "codigo_barras": boleto.codigo_barras,
            "linha_digitavel": boleto.linha_digitavel,
        }


def pdf_boleto(bank: str, data: dict[str, Any], template: str = "moderno") -> bytes:
    """PDF de um boleto. `template` escolhe o modelo visual da engine.

    O modelo era fixo em `moderno`: o parâmetro existia na rota, era aceito
    sem erro e nunca chegava aqui, então `classico` — que a engine sempre
    ofereceu — era inalcançável pela API.
    """
    if template not in MODELOS_BOLETO:
        raise DadosInvalidos([f"template '{template}' inválido"
                              f" (use: {', '.join(MODELOS_BOLETO)})"])
    boleto = construir_boleto(bank, data)
    try:
        boleto.validar()
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e
    with erro_do_banco():
        return render_boleto_pdf(boleto.contexto_render(), modelo=template)


def pdf_fatura(bank: str, data: dict[str, Any], corpo: dict[str, Any] | None = None) -> bytes:
    """Fatura: corpo livre (itens/blocos) no topo + o boleto abaixo, num só PDF.

    O engine (`render_fatura_pdf`) recebe o contexto do boleto MERJADO com as
    chaves de corpo — `itens` (nível 1, tabela simples) e/ou `fatura` (nível 2,
    blocos declarativos). O nível 3 (`fatura.desenhar`, callback Python) não é
    expressável por JSON e fica fora da superfície REST.
    """
    boleto = construir_boleto(bank, data)
    try:
        boleto.validar()
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e
    with erro_do_banco():
        contexto = boleto.contexto_render()
        if corpo:
            contexto = {**contexto, **corpo}
        return render_fatura_pdf(contexto)


def item_id(item: dict[str, Any], indice: int) -> str:
    """Identidade do item dentro do lote.

    Derivação única — antes existia em três cópias (aqui, no router de jobs e
    implícita no carnê), que é exatamente como elas passam a divergir.

    Só cai no índice quando o item não traz nenhum dos três campos. Como o
    índice nunca colide, lote sem identificador **nunca** acusa duplicidade —
    é o que faz o problema passar despercebido em teste com payload mínimo.
    """
    return str(item.get("external_id") or item.get("seu_numero")
               or item.get("numero_documento") or indice)


def duplicados(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identificadores repetidos no lote, com os índices onde aparecem.

    Dois itens com o mesmo `item_id` são o mesmo título emitido duas vezes: no
    carnê, a parcela sai impressa em duplicata e a que foi sobrescrita nunca é
    cobrada — some silenciosamente do bloco.
    """
    primeiro: dict[str, int] = {}
    repetidos: dict[str, list[int]] = {}
    for indice, item in enumerate(itens):
        iid = item_id(item, indice)
        if iid in primeiro:
            repetidos.setdefault(iid, [primeiro[iid]]).append(indice)
        else:
            primeiro[iid] = indice
    return [{"item_id": k, "indices": v} for k, v in sorted(repetidos.items())]


def pdf_multi(
    boletos: list[dict[str, Any]],
    template: str = "moderno",
    tolerante: bool = True,
) -> tuple[bytes, list[dict[str, Any]]]:
    """N boletos em um único PDF, com resultado **por item**.

    Contrato de lote (pyCobrança doc 12): a falha de um item NÃO cancela o
    lote — cada item vira um registro rastreável com `item_id`, `status`
    (`completed`|`failed`) e `errors`. Só falha o lote inteiro quando NENHUM
    item é válido (erro estrutural) ou com ``tolerante=False``.

    template ``carne`` = 3 vias/A4; senão 1 boleto por página.
    """
    contextos: list[Any] = []
    itens: list[dict[str, Any]] = []
    for indice, item in enumerate(boletos):
        bank = item.get("bank") or item.get("banco") or ""
        data = {k: v for k, v in item.items() if k not in ("bank", "banco")}
        iid = item_id(item, indice)
        try:
            boleto = construir_boleto(bank, data)
            boleto.validar()
            info = dados_boleto(bank, data)
        except (DadosInvalidos, BoletoInvalido) as e:
            erros = _erros(e)
            if not tolerante:
                raise DadosInvalidos([f"{iid}: {'; '.join(erros)}"]) from e
            itens.append({"item_id": iid, "indice": indice, "bank": bank,
                          "status": "failed", "errors": erros})
            continue
        contextos.append(boleto.contexto_render())
        itens.append({"item_id": iid, "indice": indice, "bank": bank,
                      "status": "completed", **info})

    if not contextos:
        erros = [f"{i['item_id']}: {'; '.join(i['errors'])}"
                 for i in itens if i["status"] == "failed"] or ["lote vazio"]
        raise DadosInvalidos(erros)

    if template == "carne":
        return render_carne_pdf({"parcelas": contextos}), itens

    import io

    from pypdf import PdfWriter

    # `template` aqui vale duas coisas: escolhe carnê (acima) ou, no caminho
    # de 1 boleto por página, o modelo visual. Antes o modelo era descartado e
    # o lote saía sempre em `moderno`, mesmo com `template=classico`.
    modelo = template if template in MODELOS_BOLETO else "moderno"
    writer = PdfWriter()
    for ctx in contextos:
        writer.append(io.BytesIO(render_boleto_pdf(ctx, modelo=modelo)))
    saida = io.BytesIO()
    writer.write(saida)
    return saida.getvalue(), itens


# ------------------------------------------------------------------ remessa
def _slug_da_classe(nome: str) -> str:
    base = nome[len("Remessa"):]
    base = re.sub(r"(240|400)(Pix)?$", "", base).rstrip("_")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()


def _registro_remessa() -> dict[tuple[str, str, bool], type]:
    registro: dict[tuple[str, str, bool], type] = {}
    for nome in getattr(_cnab, "__all__", []):
        if not nome.startswith("Remessa"):
            continue
        layout = "cnab240" if "240" in nome else "cnab400"
        pix = nome.endswith("Pix")
        registro[(_slug_da_classe(nome), layout, pix)] = getattr(_cnab, nome)
    return registro


_REMESSAS = _registro_remessa()


#: REST -> engine, no PAGAMENTO da remessa CNAB. So renomeia campos cujo
#: significado NAO muda; encargo NAO tem alias, de proposito.
#:
#: Por que nao aliasar multa/juros/desconto: a doc da engine (06-cnab.md) define
#: cada encargo como um TRIO codigo/tipo -> valor -> data, com semantica POR
#: LAYOUT. Um alias ingenuo erra:
#:   - `juros` -> percentual_mora funciona no CNAB 240, mas no 400 a mora e
#:     VALOR/dia (`valor_mora`): percentual_mora nao entra no arquivo e o
#:     encargo some em silencio — o bug que esta checagem existe para evitar.
#:   - `multa` -> percentual_multa sem `codigo_multa` deixa o codigo neutro
#:     ("0" = isento) onde o layout tem essa posicao.
#: Entao exigimos o nome exato e explicamos no erro.
_MAPA_PAGAMENTO = {
    "sacado": "nome_sacado",
    "sacado_documento": "documento_sacado",
    "sacado_endereco": "endereco_sacado",
    "sacado_cidade": "cidade_sacado",
    "sacado_uf": "uf_sacado",
    "sacado_cep": "cep_sacado",
    "sacado_bairro": "bairro_sacado",
    # `numero_documento` era descartado em silencio: a engine chama de `numero`
    # (equivalente a `documento` — ambos gravam na mesma posicao do CNAB).
    "numero_documento": "numero",
}

#: Dica por campo tentado, para o erro ensinar em vez de so recusar.
_DICA_ENCARGO = {
    "multa": "use codigo_multa ('0' isento | '1' valor fixo | '2' percentual) "
             "+ percentual_multa + data_multa",
    "juros": "use tipo_mora ('1' valor/dia | '2' taxa mensal % | '3' isento) + "
             "valor_mora (CNAB 400) ou percentual_mora (CNAB 240) + data_mora",
    "mora": "idem `juros`",
    "desconto": "use cod_desconto + valor_desconto + data_desconto",
    "abatimento": "use valor_abatimento",
    "iof": "use valor_iof",
    "protesto": "use codigo_protesto + dias_protesto",
    "protesto_dias": "use dias_protesto",
}



#: Combinacoes que o layout CNAB 400 NAO consegue expressar.
#:
#: No 400 o codigo/tipo do encargo NAO e gravado no arquivo (verificado byte a
#: byte): a unidade e fixa pelo layout — multa sempre PERCENTUAL, mora sempre
#: VALOR/dia. Entao mandar `codigo_multa="1"` (valor fixo) faria o banco cobrar
#: o numero como PORCENTAGEM: quem quis R$ 50 de multa levaria 50%.
#: Falhar e obrigatorio; aceitar calado seria cobrar errado do pagador.
def _valida_encargos_400(pagamentos_raw: list[dict[str, Any]]) -> None:
    erros: list[str] = []
    for i, p in enumerate(pagamentos_raw):
        if str(p.get("codigo_multa", "")) == "1":
            erros.append(
                f"pagamento[{i}]: codigo_multa='1' (valor fixo) não existe no CNAB 400 — "
                "a multa é sempre percentual (use codigo_multa='2' e percentual_multa)")
        if str(p.get("tipo_mora", "")) == "2":
            erros.append(
                f"pagamento[{i}]: tipo_mora='2' (taxa mensal %) não existe no CNAB 400 — "
                "a mora é valor ao dia (use tipo_mora='1' e valor_mora)")
        if p.get("percentual_mora") not in (None, "") and p.get("valor_mora") in (None, ""):
            erros.append(
                f"pagamento[{i}]: percentual_mora não tem posição no CNAB 400 e seria "
                "ignorado — use valor_mora (R$/dia)")
    if erros:
        raise DadosInvalidos(erros)


def gerar_remessa(bank: str, cnab_type: str, dados: dict[str, Any], pix: bool = False) -> str:
    klass = _REMESSAS.get((bank, cnab_type, pix))
    if klass is None:
        combos = sorted({f"{b}/{t}{'+pix' if p else ''}" for b, t, p in _REMESSAS})
        raise DadosInvalidos(
            [f"Remessa {cnab_type}{'+pix' if pix else ''} não suportada para {bank!r}. "
             f"Suportadas: {', '.join(combos)}"])
    pagamentos_raw = dados.get("pagamentos") or []
    if not pagamentos_raw:
        raise DadosInvalidos(["Campo 'pagamentos' é obrigatório no payload da remessa"])
    if cnab_type == "cnab400":
        _valida_encargos_400(pagamentos_raw)
    # Remessa com PIX carrega campos por pagamento que so existem no
    # PagamentoPix (txid, tipo_pagamento_pix, limites). Usar Pagamento nos dois
    # casos descartaria esses campos sem avisar.
    classe_pag = PagamentoPix if pix else Pagamento
    aceitos_pag = set(inspect.signature(classe_pag.__init__).parameters) - {"self"}
    pagamentos = []
    desconhecidos: set[str] = set()
    for p in pagamentos_raw:
        kw = {}
        for chave, valor in p.items():
            destino = _MAPA_PAGAMENTO.get(chave, chave)
            if destino not in aceitos_pag:
                desconhecidos.add(chave)
                continue
            if valor in (None, ""):
                continue
            kw[destino] = _para_date(valor) if "data" in destino else valor
        pagamentos.append(classe_pag(**kw))
    if desconhecidos:
        # Falhar alto e melhor que gerar um CNAB sem o encargo que o cliente
        # pediu: o arquivo iria para o banco silenciosamente errado.
        erros = []
        for c in sorted(desconhecidos):
            dica = _DICA_ENCARGO.get(c.lower())
            erros.append(f"Campo não suportado no pagamento: {c!r}"
                         + (f" — {dica}" if dica else ""))
        erros.append(f"Campos aceitos: {', '.join(sorted(aceitos_pag))}")
        raise DadosInvalidos(erros)
    aceitos = set(inspect.signature(klass.__init__).parameters) - {"self"}
    kwargs = {k: v for k, v in dados.items() if k in aceitos and k != "pagamentos" and v not in (None, "")}
    kwargs["pagamentos"] = pagamentos
    try:
        remessa = klass(**kwargs)
        return remessa.gera_arquivo()
    except (PyCobrancaError, ValueError, TypeError) as e:
        raise DadosInvalidos(_erros(e)) from e


def parse_retorno(conteudo: bytes, layout_hint: str | None = None) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile(suffix=".ret", delete=True) as f:
        f.write(conteudo)
        f.flush()
        try:
            retorno = Retorno.ler(f.name)
        except RetornoInvalido as e:
            raise DadosInvalidos([f"Arquivo de retorno inválido: {e}"]) from e
        except (PyCobrancaError, ValueError) as e:
            raise DadosInvalidos(_erros(e)) from e
    layout = getattr(retorno, "layout", None) or layout_hint or "400"
    layout = str(layout).replace("cnab", "")
    return [retorno_item_para_api(r, layout=layout) for r in retorno.registros]


def versao() -> str:
    return PYCOBRANCA_VERSION


# ------------------------------------------------------- sublotes CNAB (doc 12)
#: Campos que definem a compatibilidade de um título dentro de UM arquivo CNAB.
CHAVE_SUBLOTE = ("bank", "cnab_type", "convenio", "carteira", "conta_corrente",
                 "agencia", "variacao_carteira", "pix")


def chave_sublote(titulo: dict[str, Any]) -> tuple:
    """Chave determinística de agrupamento (nunca mistura incompatíveis)."""
    return tuple(str(titulo.get(c, "") or "") for c in CHAVE_SUBLOTE)


def agrupar_sublotes(titulos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Separa títulos em **sublotes compatíveis** para gerar 1 arquivo CNAB cada.

    Regra da doc 12: nunca misturar banco/layout/convênio/carteira/conta
    incompatíveis no mesmo arquivo. Função pura — sem I/O, testável.
    Cada sublote: ``{sublote_id, chave, bank, cnab_type, pix, dados, itens}``
    onde ``dados`` é o payload de remessa (cabeçalho + ``pagamentos``).
    """
    grupos: dict[tuple, dict[str, Any]] = {}
    for indice, titulo in enumerate(titulos):
        chave = chave_sublote(titulo)
        grupo = grupos.setdefault(chave, {
            "chave": dict(zip(CHAVE_SUBLOTE, chave)),
            "bank": titulo.get("bank", ""),
            "cnab_type": titulo.get("cnab_type", ""),
            "pix": bool(titulo.get("pix")),
            "cabecalho": {k: v for k, v in titulo.items()
                          if k not in ("pagamentos", "bank", "cnab_type", "pix", "external_id")},
            "itens": [],
        })
        for pagamento in titulo.get("pagamentos") or []:
            grupo["itens"].append({"indice": indice, "pagamento": pagamento})

    sublotes = []
    for ordem, grupo in enumerate(grupos.values(), start=1):
        sublote_id = f"sublote-{ordem:03d}-{grupo['bank']}-{grupo['cnab_type']}"
        sublotes.append({
            "sublote_id": sublote_id,
            "chave": grupo["chave"],
            "bank": grupo["bank"],
            "cnab_type": grupo["cnab_type"],
            "pix": grupo["pix"],
            "quantidade": len(grupo["itens"]),
            "dados": {**grupo["cabecalho"],
                      "pagamentos": [i["pagamento"] for i in grupo["itens"]]},
        })
    return sublotes


# ------------------------------------------------------------------ OFX
def ler_ofx(conteudo: bytes, *, somente_creditos: bool = False) -> Extrato:
    """Extrato OFX pela engine (v1 SGML e v2 XML).

    Antes isto usava o `ofxparse` externo com um regex generico `(\\d{8,20})`
    para achar o nosso numero. A engine faz melhor: conhece o formato de memo
    de cada banco.
    """
    try:
        return Extrato.ler(io.BytesIO(conteudo), somente_creditos=somente_creditos)
    except OFXInvalido as e:
        # arquivo nao e OFX (marcador <OFX>/OFXHEADER ausente). Um OFX valido
        # SEM transacoes nao e erro — a engine devolve extrato vazio.
        raise DadosInvalidos([f"Arquivo OFX inválido: {e}"]) from e
