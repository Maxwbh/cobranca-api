# Engine de cobrança offline — pyCobranca (100% Python, in-process).
#
# Substitui a conexão com o Banking Core BrCobrança (Ruby), DESCONTINUADA.
# Mantém os contratos da superfície /api/* (nomes de campos = contrato REST
# v1.5.0, que o pycobranca.contracts espelha).
from __future__ import annotations

import io
import inspect
import os
import re
import warnings
from contextlib import contextmanager
from datetime import date
from difflib import get_close_matches
from functools import lru_cache
from typing import Any

from pycobranca import __version__ as PYCOBRANCA_VERSION
from pycobranca.bancos import Bancos
from pycobranca.contracts import (NOMES_DO_CONTRATO, SLUG_POR_CODIGO,
                                  TEMA_DO_CONTRATO, tema_de_api)
from pycobranca.exceptions import (BancoNaoRegistrado, BoletoInvalido,
                                   CampoIgnorado, LayoutGenerico, OFXInvalido,
                                   PyCobrancaError, RetornoInvalido)
from pycobranca.pix import PixInvalido
from pycobranca.render import (emite_boleto, render_boleto_pdf, render_carne_pdf,
                               render_fatura_pdf)
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
    except PixInvalido as e:
        # O `txid` do Bolepix e o do Pix cob/cobv têm o MESMO nome e limites
        # incompatíveis: o BR Code estático aceita até 25 alfanuméricos, e o
        # txid do BACEN exige de 26 a 35. Copiar um para o outro é o caminho
        # natural de quem usa as duas rotas — e devolvia 500, porque
        # `PixInvalido` não é `BoletoInvalido` e escapava dos handlers.
        raise DadosInvalidos([f"{e}. No Bolepix o `txid` vai dentro do BR Code e"
                              " aceita até 25 alfanuméricos — é outro campo que o"
                              " `txid` do Pix cob/cobv, que exige de 26 a 35"]) from e


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


# Contrato REST -> kwargs do BancoBase (o inverso de contracts.boleto_para_api).
#
# Vem da engine: são os quatro nomes que divergem entre o payload e o domínio,
# e `documento_cedente`/`cedente_documento` inverte as palavras — exatamente o
# tipo de detalhe em que duas cópias escritas à mão acabam discordando. Se a
# engine acrescentar um par, ele passa a valer aqui sem ninguém lembrar.
_MAPA_CAMPOS = dict(NOMES_DO_CONTRATO)

#: Nome público do mapa acima, para quem monta payload para a engine.
NOMES_DO_CONTRATO = _MAPA_CAMPOS
_CAMPOS_DATA = {"data_vencimento", "data_documento", "data_processamento"}
# A engine desenha estes campos linha a linha e espera uma LISTA. Recebendo
# string ela itera os caracteres: o boleto sai com "A", "p", "o", "s"... um por
# linha, até estourar a caixa — sem erro, sem aviso, com o texto perdido.
#
# JSON não tem tipo "várias linhas", então o cliente naturalmente manda string
# com `\n`. Normalizar aqui é o que torna as duas formas equivalentes.
_CAMPOS_MULTILINHA = {"instrucoes", "demonstrativo"}

# A engine DESENHA um número limitado de linhas de instrução e, do que desenha,
# só imprime o que couber na largura da moldura. Os dois limites falham calados:
# linha além da última simplesmente NÃO é desenhada, e linha comprida sai
# truncada (ou, em versões anteriores, atravessando a coluna de Desconto/Mora/
# Valor cobrado). Nos dois casos: `200`, PDF bonito, cláusula perdida.
#
# O gateway NÃO reformata o texto — quebrar linha por conta própria mudaria o
# conteúdo de um documento de cobrança. Ele mede e recusa; reescrever é do
# cliente, que sabe onde a frase pode ser cortada.
#
# Largura de recuo quando a engine instalada não corta — versões antigas deixam
# o texto atravessar a coluna de valores em vez de truncar, e aí não há corte
# para medir. Calibrada em MAIÚSCULAS, que é como quase toda instrução de boleto
# chega; o limite real da engine é em PONTOS, então uma linha inteira de "M"
# cabe menos e uma de "l" cabe mais. É proxy, e assumido como tal: serve para
# recusar o exagero cedo, com mensagem, em vez de descobrir no papel.
LARGURA_INSTRUCAO = 69

#: Piso usado quando a medição na engine não pode ser feita (render indisponível
#: na instalação). É o menor valor já observado em qualquer modelo — recusar de
#: menos é pior que recusar demais, mas nunca vale a pena aceitar de mais.
_LINHAS_INSTRUCAO_PISO = 6

#: Teto: a sonda conta o que a engine DESENHA, e desenhar não é caber. Há versão
#: em que o clássico não corta — a 12ª linha sai impressa POR BAIXO da moldura,
#: em cima do bloco do sacado. Nenhum layout medido comporta mais de 8 linhas
#: dentro da própria moldura, então é aqui que a contagem para.
#:
#: Os dois lados são necessários: a sonda pega a moldura que ENCOLHEU (foi o que
#: passou despercebido antes), o teto pega a engine que desenha sem cortar.
_LINHAS_INSTRUCAO_TETO = 8

#: Marcador improvável de aparecer no resto do boleto, para a contagem da sonda
#: não confundir a instrução com outro texto da página.
_MARCA_SONDA = "ZQXJINSTR"
_SONDA_LINHAS = 12

#: Instrução real, em maiúsculas, para sondar a largura. Um texto de verdade —
#: com espaço, dígito e "%" — mede o que o cliente vai mandar; uma fileira de
#: "M" mediria o pior caso teórico e recusaria o uso normal.
_SONDA_PROSA = "APOS O VENCIMENTO COBRAR MULTA DE 2% E JUROS DE 1% AO MES PRO RATA DIE"

#: Reticências que a engine usa ao cortar. É por elas que a sonda de largura
#: reconhece o corte.
_RETICENCIAS = "…"

#: Teto da busca binária de largura. Acima disto nenhuma moldura de boleto A4
#: chega, e o carnê — que não corta — sairia procurando para sempre.
_SONDA_LARGURA_MAX = 160


def _sonda_pdf(modelo: str, instrucoes: list[str], tem_pix: bool) -> str:
    """Renderiza um boleto de sonda e devolve o texto do PDF.

    Levanta se a engine não conseguir desenhar — quem chama decide o recuo.
    """
    import io as _io

    from pypdf import PdfReader

    dados = {"nosso_numero": "12345678", "valor": 100, "cedente": "SONDA",
             "cedente_documento": "11.222.333/0001-81", "sacado": "SONDA",
             "sacado_documento": "529.982.247-25", "carteira": "109",
             "agencia": "0057", "conta": "12345",
             "data_vencimento": date(2030, 1, 10), "instrucoes": instrucoes}
    if tem_pix:
        dados["pix_chave"] = "11222333000181"
    contexto = Bancos.find("341")(**dados).contexto_render()
    pdf = (render_carne_pdf({"parcelas": [contexto]}) if modelo == "carne"
           else render_boleto_pdf(contexto, modelo=modelo))
    return "".join(p.extract_text() for p in PdfReader(_io.BytesIO(pdf)).pages)


@lru_cache(maxsize=None)
def largura_de_instrucao(modelo: str, tem_pix: bool) -> int:
    """Maior linha que **este** layout imprime inteira, medido na engine.

    Não é um número só: a moldura de instruções do moderno encolhe cerca de um
    quarto quando há Bolepix, para abrir espaço ao QR. Uma constante única
    aceitaria no boleto com PIX uma linha que só cabe no boleto sem — e o texto
    excedente sai truncado, com `200`.

    Busca binária pelo ponto em que a engine passa a cortar. Engine que não
    corta (o texto atravessa a coluna de valores em vez de truncar) não dá o que
    medir: aí vale `LARGURA_INSTRUCAO`.
    """
    def corta(n: int) -> bool:
        linha = (_SONDA_PROSA * (n // len(_SONDA_PROSA) + 1))[:n]
        return _RETICENCIAS in _sonda_pdf(modelo, [linha], tem_pix)

    try:
        if not corta(_SONDA_LARGURA_MAX):
            return LARGURA_INSTRUCAO  # engine não corta: nada a medir
        baixo, alto = 1, _SONDA_LARGURA_MAX
        while baixo < alto:
            meio = (baixo + alto + 1) // 2
            if corta(meio):
                alto = meio - 1
            else:
                baixo = meio
        return baixo
    except Exception:  # noqa: BLE001 — sonda é diagnóstico; nunca derruba requisição
        return LARGURA_INSTRUCAO


@lru_cache(maxsize=None)
def linhas_de_instrucao(modelo: str, tem_pix: bool) -> int:
    """Quantas linhas de instrução **este** modelo desenha, medido na engine.

    Era uma constante — 7, com o comentário afirmando ser "idêntico com e sem
    PIX". Valia para a versão em que foi medida. A moldura de instruções muda de
    altura conforme o modelo e conforme haja Bolepix, e quando a engine mexeu no
    layout a constante ficou para trás **sem nada acusar**: o gateway seguiu
    aceitando uma linha a mais do que o modelo imprimia, que é exatamente a
    perda silenciosa que esta guarda existe para impedir.

    Medir na própria engine é o que torna a guarda imune a isso. Custa um render
    por combinação (`modelo` × `tem_pix`), uma vez por processo.

    `modelo="carne"` mede o layout de 3 vias por A4, que tem moldura própria.
    """
    try:
        texto = _sonda_pdf(modelo, [f"{_MARCA_SONDA}{i}" for i in range(_SONDA_LINHAS)],
                           tem_pix)
    except Exception:  # noqa: BLE001 — sonda é diagnóstico; nunca derruba requisição
        return _LINHAS_INSTRUCAO_PISO
    desenhadas = sum(1 for i in range(_SONDA_LINHAS) if f"{_MARCA_SONDA}{i}" in texto)
    if not desenhadas:
        return _LINHAS_INSTRUCAO_PISO
    return min(desenhadas, _LINHAS_INSTRUCAO_TETO)


def _limite_de_linhas(modelo: str | None, tem_pix: bool) -> tuple[int, str]:
    """(linhas aceitas, de onde vem o limite) para o modelo que vai desenhar.

    `modelo=None` é o caminho sem render — `validar`, `dados_boleto` — onde
    ainda não se sabe qual layout o cliente vai pedir. Ali vale o teto do modelo
    mais generoso: recusar por antecipação um texto que o clássico imprime
    inteiro seria inventar um erro que o render não teria.
    """
    if modelo is None:
        cabem = max(linhas_de_instrucao(m, p)
                    for m in MODELOS_BOLETO for p in (False, True))
        return cabem, "o modelo mais generoso"
    return linhas_de_instrucao(modelo, tem_pix), f"o modelo '{modelo}'"


def _limite_de_largura(modelo: str | None, tem_pix: bool) -> tuple[int, str]:
    """(caracteres por linha, de onde vem o limite). Mesma regra do `None`."""
    if modelo is None:
        cabe = max(largura_de_instrucao(m, p)
                   for m in MODELOS_BOLETO for p in (False, True))
        return cabe, "o modelo mais generoso"
    return largura_de_instrucao(modelo, tem_pix), f"o modelo '{modelo}'"


def _linhas(valor: Any, campo: str, modelo: str | None = None,
            tem_pix: bool = False) -> Any:
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

    cabem, origem = _limite_de_linhas(modelo, tem_pix)
    largura, origem_largura = _limite_de_largura(modelo, tem_pix)
    erros: list[str] = []
    if len(linhas) > cabem:
        erros.append(f"{campo}: {len(linhas)} linhas, máximo {cabem} em {origem}"
                     f" (a partir da {cabem + 1}ª a engine não imprime)")
    compridas = [(i + 1, len(linha)) for i, linha in enumerate(linhas)
                 if len(linha) > largura]
    if compridas:
        detalhe = ", ".join(f"linha {n} com {c}" for n, c in compridas)
        erros.append(f"{campo}: máximo {largura} caracteres por linha em"
                     f" {origem_largura} ({detalhe}) — texto mais longo é"
                     " truncado pela engine")
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

#: `fonte_ttf` estava documentado como "Suportado pela engine pyCobrança" e não
#: existe consumidor nenhum — nem aqui, nem lá (a pyCobrança o lista entre os
#: campos que ignora na construção). Recusar é o que evita a terceira temporada
#: do mesmo enredo: campo anunciado, aceito, descartado, `200`.
_CAMPO_SEM_SUPORTE = {
    "fonte_ttf": "a engine desenha o PDF com as fontes-padrão do PDF (Helvetica);"
                 " não há como injetar TTF pelo payload",
}

#: A faixa FEBRABAN — `(-) Desconto/Abatimento`, `(+) Mora/Multa`,
#: `(=) Valor cobrado` — **não é preenchida por quem emite**. Desconto, multa e
#: juros dependem da DATA DO PAGAMENTO, que não se sabe na emissão: quem calcula
#: e escreve ali é o caixa, no ato. Imprimir um número antecipado induz o pagador
#: a erro, e ele estará errado em qualquer data que não a suposta.
#:
#: São **aceitos e ignorados** na emissão, não recusados: o mesmo registro de
#: cobrança costuma alimentar o boleto E a remessa, e é natural que o payload
#: traga os encargos. Recusar aqui obrigaria quem integra a montar dois objetos
#: para o mesmo título — atrapalha sem proteger ninguém, porque o valor não
#: chega ao papel de qualquer forma.
#:
#: Onde eles têm efeito de verdade:
#:
#: - a **regra** vai em `instrucoes`, impressa no boleto ("após o vencimento,
#:   multa de 2% e juros de 1% ao mês") — texto, não valor, e por isso continua
#:   verdadeiro em qualquer data;
#: - os **valores** vão na remessa CNAB (`POST /api/remessa`), em
#:   `codigo_multa`/`percentual_multa`/`data_multa`, `tipo_mora`/`valor_mora`
#:   ou `percentual_mora`/`data_mora`, `cod_desconto`/`valor_desconto`/
#:   `data_desconto` e `valor_abatimento`. É o arquivo que o banco processa, e
#:   é lá que ele aprende a calcular na data em que o título for pago.
_TOTALIZADORES_DO_CAIXA = (
    "desconto_abatimento", "outras_deducoes", "mora_multa",
    "outros_acrescimos", "valor_cobrado",
)

#: Campos que o gateway consome mas o construtor do banco não conhece: as
#: instruções numeradas e a faixa de marca são traduzidas aqui antes de chegar
#: à engine, e `tipo_chave_pix` é aceito-e-ignorado por decisão documentada (a
#: engine deduz o tipo do valor da chave).
#:
#: `external_id` e `seu_numero` identificam o ITEM dentro de um lote (é de onde
#: sai o `item_id` que acusa parcela duplicada) — não são campos do título, mas
#: são nomes do contrato e chegam no mesmo objeto.
#:
#: `emv`, `pix_label` e `fonte_ttf` entram aqui para que **vazio continue sendo
#: ausência**: preenchidos, param antes com a mensagem que explica por que não
#: funcionam; em branco, são como se não tivessem sido enviados.
#: Número que o BANCO já atribuiu ao título, mandado de volta para CONFERIR o
#: que a engine calcula. Não entra no boleto — o desenho continua saindo do
#: cálculo local; estes campos só dizem "o resultado tem de ser este".
#:
#: Existem porque os dois caminhos passaram a se sobrepor. Registrar no `on` e
#: renderizar o PDF no `off` é o ciclo que dá o QR que liquida
#: (`pix_copia_cola`), e nele o papel sai de um cálculo NOSSO enquanto o título
#: registrado é do BANCO. Divergir ali imprime um boleto que não corresponde ao
#: título — papel correto em bytes, pagamento que não concilia. Não é hipótese
#: remota: no **Inter** o caminho `on` nunca manda nosso número (quem numera é o
#: banco), então renderizar com o seu próprio número produz OUTRO título.
_CONFERIDOS_DO_BANCO: dict[str, str] = {
    "codigo_barras": "codigo_barras",
    "linha_digitavel": "linha_digitavel",
}

_CAMPOS_DO_GATEWAY = frozenset(
    {f"instrucao{n}" for n in range(1, 7)}
    | set(TEMA_DO_CONTRATO) | {"parcela_atual", "total_parcelas"}
    | {"tipo_chave_pix", "external_id", "seu_numero"}
    | {"emv", "pix_label", "fonte_ttf"}
    | set(_CONFERIDOS_DO_BANCO)
)

#: Volta ao descarte silencioso de campo desconhecido. Existe para quem
#: descobrir em produção que mandava um campo a mais e precisar de uma noite
#: para arrumar a integração — não para ficar ligado. Sai na 3.0.0.
FLAG_CAMPO_DESCONHECIDO = "BOLETO_ACEITA_CAMPO_DESCONHECIDO"


def _campos_aceitos(klass) -> set[str]:
    """Tudo que este banco entende, nos dois vocabulários.

    O construtor fala o nome do domínio (`conta`, `cedente_documento`); o
    contrato REST fala o do payload (`conta_corrente`, `documento_cedente`).
    Os dois valem na entrada — recusar o nome nativo quebraria quem já o usa.
    """
    construtor = set(inspect.signature(klass.__init__).parameters) - {"self"}
    return construtor | set(_MAPA_CAMPOS) | set(_CAMPOS_DO_GATEWAY)


def campos_aceitos(bank: str) -> set[str]:
    """Campos que o `data` deste banco aceita. Recusa banco desconhecido."""
    return _campos_aceitos(_classe_banco(bank))


def _recusar_desconhecidos(klass, data: dict[str, Any]) -> None:
    """Campo fora do contrato é erro, não sobra.

    O descarte silencioso era o mecanismo por trás de quase toda a família de
    defeitos deste módulo: o campo entrava no payload, não era nome de nada, e
    sumia — com `200` e um boleto que não tem o que o chamador achou que tinha.
    `numero_docmento` produzia um título sem número de documento, e nada no
    corpo da resposta dizia que faltava.

    A engine fechou a mesma fronteira em `contracts.boleto_de_api`. Aqui a
    recusa vem com sugestão: quase todo caso é erro de digitação, e apontar o
    campo certo resolve mais rápido que listar os 40 aceitos.
    """
    if os.environ.get(FLAG_CAMPO_DESCONHECIDO, "").strip().lower() in ("1", "true"):
        return
    aceitos = _campos_aceitos(klass)
    estranhos = sorted(c for c in data if c not in aceitos)
    if not estranhos:
        return
    erros = []
    for campo in estranhos:
        perto = get_close_matches(campo, aceitos, n=2, cutoff=0.75)
        dica = f" — você quis dizer {' ou '.join(repr(p) for p in perto)}?" if perto else ""
        erros.append(f"campo desconhecido em `data`: {campo!r}{dica}")
    erros.append(f"Campo aceito por {klass.nome} ({klass.codigo}) é um destes: "
                 + ", ".join(sorted(aceitos)))
    raise DadosInvalidos(erros)


def _recusar_apelido_em_conflito(data: dict[str, Any]) -> None:
    """O mesmo campo escrito nos dois vocabulários, com valores diferentes.

    `conta_corrente` e `conta` são o MESMO campo; mandar os dois deixava a
    ordem do dicionário decidir qual sobrevive. Um dos dois valores ia para o
    boleto e o outro sumia, sem erro — e nos dois casos é o número da conta
    que se está errando.
    """
    erros = []
    for contrato, nativo in _MAPA_CAMPOS.items():
        a, b = data.get(contrato), data.get(nativo)
        if a not in (None, "") and b not in (None, "") and str(a) != str(b):
            erros.append(f"`{contrato}` ({a!r}) e `{nativo}` ({b!r}) são o mesmo campo"
                         f" com valores diferentes — envie só `{contrato}`")
    if erros:
        raise DadosInvalidos(erros)


#: Instruções numeradas do contrato REST -> a lista que a engine desenha.
#:
#: `instrucao1`..`instrucao6` estavam na doc, e NENHUMA chegava ao boleto: não
#: são campos do construtor, então caíam no descarte de campo desconhecido. Quem
#: seguia a documentação recebia `200` e um boleto SEM instrução alguma. Quem
#: mandava `instrucoes` — que a doc não citava — é que via o texto impresso.
_INSTRUCOES_NUMERADAS = tuple(f"instrucao{n}" for n in range(1, 7))


def _instrucoes_do_payload(data: dict[str, Any]) -> Any:
    """Junta `instrucao1..6` numa lista, na ordem, ou devolve `instrucoes`.

    Mandar as duas formas é ambíguo e uma delas seria descartada em silêncio —
    de novo. Recusa nomeando o conflito.
    """
    numeradas = [(c, data[c]) for c in _INSTRUCOES_NUMERADAS
                 if str(data.get(c) or "").strip()]
    if numeradas and data.get("instrucoes"):
        raise DadosInvalidos(
            [f"`instrucoes` e {', '.join(f'`{c}`' for c, _ in numeradas)} no mesmo"
             " payload: as duas formas escrevem o mesmo bloco e uma seria"
             " descartada. Use só `instrucoes` (lista ou texto com quebras)"])
    if numeradas:
        return [str(v).rstrip() for _, v in numeradas]
    return data.get("instrucoes")


#: Modelos que desenham a faixa de marca. Medido: `classico` e o carnê ignoram o
#: bloco `tema` por completo; a fatura desenha porque monta o boleto moderno.
MODELOS_COM_TEMA = ("moderno",)


def tema_do_payload(data: dict[str, Any], *, modelo: str | None = None
                    ) -> dict[str, Any] | None:
    """Bloco `tema` do contexto de render, a partir do payload do contrato.

    Os sete campos de tema estavam documentados como "Suportado pela engine
    pyCobrança" e **nenhum** chegava ao PDF: não são campos do construtor do
    banco, e o gateway nunca montava o bloco que o renderizador de fato lê. O
    boleto saía idêntico ao de um payload sem tema nenhum, com `200`.

    A tradução de vocabulário (`cor_marca` × `cor`, `rodape_contato` × `rodape`,
    `parcela_atual`/`total_parcelas` × `parcela_texto`) é da engine —
    `contracts.tema_de_api`. Aqui fica só o que é da fronteira HTTP: normalizar
    a cor e recusar o que não teria efeito.
    """
    pedidos = {c for c in (*TEMA_DO_CONTRATO, "parcela_atual", "total_parcelas")
               if data.get(c) not in (None, "")}
    if not pedidos:
        return None
    if modelo is not None and modelo not in MODELOS_COM_TEMA:
        raise DadosInvalidos(
            [f"o modelo '{modelo}' não desenha faixa de marca, então"
             f" {', '.join(f'`{c}`' for c in sorted(pedidos))} não teria efeito."
             f" Use um destes: {', '.join(MODELOS_COM_TEMA)}"])

    # A engine recebe os campos já saneados: `cor_marca` sem `#` é a forma que
    # a doc mandava usar e a que faz o reportlab levantar lá no fundo do render,
    # e `logo_empresa` é o TEXTO da marca — caminho de arquivo sairia impresso
    # na faixa.
    saneado = dict(data)
    if data.get("cor_marca") not in (None, ""):
        saneado["cor_marca"] = _cor_tema(data["cor_marca"])
    if data.get("logo_empresa") not in (None, ""):
        saneado["logo_empresa"] = _logo_texto(str(data["logo_empresa"]))
    tema = tema_de_api(saneado)
    if tema is None:
        return None

    # O contrato não tem campo para o NOME da empresa na faixa, então a engine
    # o herda de `logo_empresa` — e a faixa saía com o mesmo texto duas vezes,
    # no selo e ao lado dele. O nome do beneficiário já está no payload, é
    # obrigatório, e é o que uma faixa de marca mostra ao lado do logo.
    #
    # `cedente` sozinho NÃO liga a faixa: quem a liga são os campos de tema, e
    # `pedidos` acima só olha para eles.
    cedente = str(data.get("cedente") or "").strip()
    if cedente:
        tema["empresa"] = cedente
    return tema


def _cor_tema(valor: Any) -> str:
    """`RRGGBB` ou `#RRGGBB` -> o `#RRGGBB` que o renderizador espera.

    A doc mandava enviar "sem `#`" e dava `006B3F` de exemplo — que é justamente
    a forma com que o reportlab levanta `ValueError` lá no fundo do render. Com
    o tema ligado, o exemplo da própria documentação viraria **500**.
    """
    cor = str(valor).strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", cor):
        raise DadosInvalidos(
            [f"`cor_marca`: {valor!r} não é uma cor hexadecimal RRGGBB"
             " (ex.: '006B3F' ou '#006B3F')"])
    return f"#{cor}"


def _logo_texto(valor: str) -> str:
    """`logo_empresa` é o TEXTO da marca desenhado na faixa, não um arquivo.

    A doc dizia "Path de arquivo (PNG/JPG) acessível ao servidor" e dava
    `/assets/logo.png`. A engine desenha o valor como texto: ligar o tema sem
    esta checagem faria a faixa de marca do boleto sair escrita
    "/assets/logo.png". O logo do BANCO continua vindo empacotado na engine.
    """
    if "/" in valor or "\\" in valor or valor.lower().endswith(
            (".png", ".jpg", ".jpeg", ".svg", ".gif")):
        raise DadosInvalidos(
            [f"`logo_empresa`: {valor!r} parece um caminho de arquivo. O campo é o"
             " TEXTO da marca desenhado na faixa (ex.: 'LAGOA REAL') — a engine"
             " não lê arquivo do servidor"])
    return valor


def construir_boleto(bank: str, data: dict[str, Any], *, modelo: str | None = None):
    """Constrói a instância do banco a partir do payload do contrato REST.

    `modelo` é o layout que vai desenhar, quando já se sabe: só ele diz quantas
    linhas de instrução cabem. Sem ele vale o teto do modelo mais generoso.
    """
    data = dict(data or {})
    mortos = sorted(c for c in _CAMPOS_SEM_CONSUMIDOR if data.get(c))
    if mortos:
        raise DadosInvalidos(
            [f"`{c}` não gera QR Pix — {_CAMPOS_SEM_CONSUMIDOR[c]}. Para o Bolepix,"
             " envie `chave_pix` (e `txid`, se quiser rastrear): a engine monta"
             " o EMV e desenha o QR" for c in mortos])
    sem_suporte = sorted(c for c in _CAMPO_SEM_SUPORTE if data.get(c))
    if sem_suporte:
        raise DadosInvalidos([f"`{c}` não tem efeito — {_CAMPO_SEM_SUPORTE[c]}"
                              for c in sem_suporte])
    # Aceitos e ignorados: a faixa do caixa não é preenchida na emissão. Sair
    # daqui é o que garante que a engine não os desenhe — a 1.1.0 os aceita no
    # construtor e imprimiria o valor.
    for campo in _TOTALIZADORES_DO_CAIXA:
        data.pop(campo, None)

    # Saem antes da engine: são conferência, não dado do título. A comparação
    # acontece em `_conferir_com_o_banco`, depois do cálculo.
    for campo in _CONFERIDOS_DO_BANCO:
        data.pop(campo, None)

    instrucoes = _instrucoes_do_payload(data)
    for numerada in _INSTRUCOES_NUMERADAS:
        data.pop(numerada, None)
    if instrucoes is not None:
        data["instrucoes"] = instrucoes

    klass = _classe_banco(bank)
    _recusar_desconhecidos(klass, data)
    _recusar_apelido_em_conflito(data)
    aceitos = set(inspect.signature(klass.__init__).parameters) - {"self"}
    tem_pix = bool(data.get("chave_pix") or data.get("pix_chave"))
    kwargs: dict[str, Any] = {}
    for chave, valor in data.items():
        destino = _MAPA_CAMPOS.get(chave, chave)
        if destino not in aceitos or valor in (None, ""):
            continue
        if chave in _CAMPOS_DATA:
            kwargs[destino] = _para_date(valor)
        elif chave in _CAMPOS_MULTILINHA:
            kwargs[destino] = _linhas(valor, chave, modelo, tem_pix)
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
    _construido_e_validado(bank, data)


def _construido_e_validado(bank: str, data: dict[str, Any],
                           modelo: str | None = None):
    """Monta o título e passa pelo `validar()` do banco. Ponto único."""
    boleto = construir_boleto(bank, data, modelo=modelo)
    try:
        boleto.validar()
    except BoletoInvalido as e:
        raise DadosInvalidos(_erros(e)) from e
    return boleto


def _nosso_numero_impresso(boleto) -> tuple[str, str]:
    """(formatado, dígito) — o dígito vem vazio nos bancos que já o embutem."""
    formatado = boleto.nosso_numero_formatado()
    dv = getattr(boleto, "nosso_numero_dv", None)
    if callable(dv):
        dv = dv()
    if dv is None:
        m = re.search(r"-(\w+)$", formatado)
        dv = m.group(1) if m else ""
    return formatado, str(dv)


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _conferir_com_o_banco(data: dict[str, Any], calculado: dict[str, Any]) -> None:
    """O que o banco já atribuiu tem de bater com o que a engine calcula.

    Chamado DEPOIS do cálculo, com o `data` original — `construir_boleto` já
    tirou estes campos do caminho da engine.

    Recusar é o único desfecho seguro. Imprimir o número do banco por cima de um
    cálculo divergente esconderia dados de conta errados; imprimir o nosso
    ignorando o do banco entregaria ao pagador um boleto que não corresponde ao
    título registrado. Nos dois casos o PDF sai bonito e a conciliação quebra
    semanas depois, quando ninguém mais liga uma coisa à outra.

    Compara só os DÍGITOS: a linha digitável circula formatada
    (`00190.00009 01234...`) e exigir a mesma pontuação recusaria por espaço.
    """
    erros: list[str] = []
    for campo, no_calculo in _CONFERIDOS_DO_BANCO.items():
        do_banco = _so_digitos(data.get(campo))
        if not do_banco:
            continue
        nosso = _so_digitos(calculado.get(no_calculo))
        if do_banco != nosso:
            erros.append(
                f"`{campo}`: o banco registrou {do_banco}, o cálculo com estes dados dá"
                f" {nosso}. O boleto impresso não corresponderia ao título registrado."
                " Confira a conta e o `nosso_numero` — quando o banco é quem numera"
                " (Inter), use o `nossoNumero` que ele devolveu na consulta")
    if erros:
        raise DadosInvalidos(erros)


def _dados_do_boleto(bank: str, boleto, contexto: dict[str, Any] | None = None
                     ) -> dict[str, Any]:
    """Campos CALCULADOS do título, a partir de um boleto já montado.

    Só o que a API calcula entra: valor e vencimento não voltam porque o
    chamador acabou de mandá-los. `pix_copia_cola` volta porque **não** foi
    mandado — a engine monta o EMV a partir da chave, e sem ele quem integra vê
    o QR no PDF e não tem o texto para pôr ao lado, que é como um pagador de
    celular paga (não dá para escanear a própria tela).
    """
    with erro_do_banco():
        contexto = contexto if contexto is not None else boleto.contexto_render()
        formatado, dv = _nosso_numero_impresso(boleto)
        pix = contexto.get("pix") or {}
        return {
            "bank": bank,
            "nosso_numero": str(boleto.nosso_numero),
            "nosso_numero_formatado": formatado,
            "nosso_numero_dv": dv,
            "codigo_barras": contexto.get("codigo_barras") or boleto.codigo_barras,
            "linha_digitavel": contexto.get("linha_digitavel") or boleto.linha_digitavel,
            "pix_copia_cola": pix.get("copia_cola") if pix.get("habilitado") else None,
            # `True` = QR do banco, liquida o título (Bolepix). `False` = QR
            # montado da chave, credita e deixa o título em aberto. `None` = sem
            # PIX. Ver a nota em `emitir_boleto`.
            "pix_vinculado": pix.get("vinculado") if pix.get("habilitado") else None,
        }


def dados_boleto(bank: str, data: dict[str, Any]) -> dict[str, Any]:
    """Campos calculados do boleto — contrato: SEMPRE os 3 campos de nosso_numero."""
    calculado = _dados_do_boleto(bank, _construido_e_validado(bank, data))
    _conferir_com_o_banco(data, calculado)
    return calculado


def emitir_boleto(bank: str, data: dict[str, Any], template: str = "moderno"
                  ) -> tuple[bytes, dict[str, Any]]:
    """PDF **e** dados calculados, de uma montagem só.

    Quem precisa dos dois chamava `dados_boleto` e `pdf_boleto` em seguida: duas
    construções do título e quatro `validar()` para um boleto — 36 ms onde 8
    bastam, e, pior, dois objetos diferentes servindo de fonte para o papel e
    para o JSON. Nada garantia que descreviam o mesmo boleto.

    Quem monta é a engine, por `render.emite_boleto`: ela desenha e lê os
    números do MESMO contexto, então não há como o papel e o JSON discordarem.
    Aqui fica o que é da fronteira HTTP — o nome do banco, o nosso número
    impresso e o dígito, que a engine não devolve.
    """
    if template not in MODELOS_BOLETO:
        raise DadosInvalidos([f"template '{template}' inválido"
                              f" (use: {', '.join(MODELOS_BOLETO)})"])
    boleto = _construido_e_validado(bank, data, modelo=template)
    tema = tema_do_payload(data, modelo=template)
    with erro_do_banco():
        emitido = emite_boleto(boleto, modelo=template, tema=tema)
        formatado, dv = _nosso_numero_impresso(boleto)
    calculado = {
        "bank": bank,
        "nosso_numero": str(boleto.nosso_numero),
        "nosso_numero_formatado": formatado,
        "nosso_numero_dv": dv,
        "codigo_barras": emitido.codigo_barras,
        "linha_digitavel": emitido.linha_digitavel,
        "pix_copia_cola": emitido.pix_copia_cola,
        # Os dois QR não são a mesma coisa e a diferença é dinheiro. Bolepix é o
        # QR DINÂMICO que o banco devolve ao registrar (`pix_copia_cola` no
        # payload): pagar por ele LIQUIDA o título. O montado a partir de
        # `chave_pix` é estático — credita a chave e deixa o título EM ABERTO,
        # com risco de segunda cobrança ou protesto de boleto já pago.
        # A engine 1.1.1 passou a dizer qual dos dois está no papel; sem repassar
        # aqui, quem integra não tem como saber o que imprimiu.
        "pix_vinculado": emitido.pix_vinculado,
    }
    _conferir_com_o_banco(data, calculado)
    return emitido.pdf, calculado


def pdf_boleto(bank: str, data: dict[str, Any], template: str = "moderno") -> bytes:
    """PDF de um boleto. `template` escolhe o modelo visual da engine.

    O modelo era fixo em `moderno`: o parâmetro existia na rota, era aceito
    sem erro e nunca chegava aqui, então `classico` — que a engine sempre
    ofereceu — era inalcançável pela API.
    """
    return emitir_boleto(bank, data, template)[0]


def _com_tema(contexto: dict[str, Any], tema: dict[str, Any] | None
              ) -> dict[str, Any]:
    """Enxerta o bloco `tema` no contexto de render, quando há."""
    return {**contexto, "tema": tema} if tema else contexto


def pdf_fatura(bank: str, data: dict[str, Any], corpo: dict[str, Any] | None = None) -> bytes:
    """Fatura: corpo livre (itens/blocos) no topo + o boleto abaixo, num só PDF.

    O engine (`render_fatura_pdf`) recebe o contexto do boleto MERJADO com as
    chaves de corpo — `itens` (nível 1, tabela simples) e/ou `fatura` (nível 2,
    blocos declarativos). O nível 3 (`fatura.desenhar`, callback Python) não é
    expressável por JSON e fica fora da superfície REST.
    """
    return emitir_fatura(bank, data, corpo)[0]


def emitir_fatura(bank: str, data: dict[str, Any], corpo: dict[str, Any] | None = None
                  ) -> tuple[bytes, dict[str, Any]]:
    """PDF da fatura **e** os dados do boleto embutido, de uma montagem só."""
    # A fatura desenha o boleto MODERNO abaixo do corpo — medido: a faixa de
    # marca sai na fatura exatamente como sai no boleto moderno.
    boleto = _construido_e_validado(bank, data, modelo="moderno")
    tema = tema_do_payload(data, modelo="moderno")
    with erro_do_banco():
        contexto = boleto.contexto_render()
        desenho = _com_tema(contexto, tema)
        if corpo:
            desenho = {**desenho, **corpo}
        pdf = render_fatura_pdf(desenho)
    return pdf, _dados_do_boleto(bank, boleto, contexto)


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
    # `carne` não é modelo de boleto: é o layout de 3 vias/A4, e ele ignora o
    # bloco `tema` (medido). Nos demais, o modelo do lote é o que desenha cada
    # via — e é ele quem diz quantas linhas de instrução cabem.
    modelo_do_lote = template if template in MODELOS_BOLETO or template == "carne" \
        else "moderno"
    contextos: list[Any] = []
    itens: list[dict[str, Any]] = []
    for indice, item in enumerate(boletos):
        bank = item.get("bank") or item.get("banco") or ""
        data = {k: v for k, v in item.items() if k not in ("bank", "banco")}
        iid = item_id(item, indice)
        try:
            # Uma construção por item. Eram três — `construir_boleto`,
            # `validar` e o `dados_boleto`, que montava tudo de novo.
            boleto = _construido_e_validado(bank, data, modelo=modelo_do_lote)
            tema = tema_do_payload(data, modelo=modelo_do_lote)
            contexto = boleto.contexto_render()
            info = _dados_do_boleto(bank, boleto, contexto)
        except (DadosInvalidos, BoletoInvalido) as e:
            erros = _erros(e)
            if not tolerante:
                raise DadosInvalidos([f"{iid}: {'; '.join(erros)}"]) from e
            itens.append({"item_id": iid, "indice": indice, "bank": bank,
                          "status": "failed", "errors": erros})
            continue
        contextos.append(_com_tema(contexto, tema))
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



#: Onde cada campo de encargo TEM posicao no arquivo.
#:
#: `campo -> {layout: bancos que gravam}`; `None` = todos os bancos daquele
#: layout. Fora dali o campo entra, nao e' gravado e some — o descarte silencioso
#: que esta guarda existe para impedir. Pior ainda quando a unidade muda: mandar
#: multa em VALOR onde o campo e' PERCENTUAL faria o banco cobrar R$ 50 como 50%
#: — R$ 750 num titulo de R$ 1.500.
#:
#: Medido A/B em todos os layouts da engine: gerar o arquivo com dois valores
#: diferentes do campo e comparar byte a byte.
#:
#: - **CNAB 400**: so o **Inter** grava os tres. Ele tem os dois campos de cada
#:   encargo (itens 10/11, 14/15 e 30/31 do registro tipo 1) e escolhe pelo
#:   codigo. O **Safra** recusa a multa em valor sozinho, com mensagem propria
#:   (nota 6.1.8). Os outros 12 aceitam e descartam calados.
#: - **CNAB 240**: `percentual_mora` e' o normal e vale para todos;
#:   `valor_multa` e `percentual_desconto` nao tem posicao em layout nenhum.
#:
#: `percentual_mora` no 400 ja era barrado. `valor_multa` e `percentual_desconto`
#: entraram no `Pagamento` da engine 1.1.1 — chegaram aceitos pela assinatura e
#: passavam calados nos dois layouts ate aqui.
_ENCARGO_COM_POSICAO: dict[str, tuple[dict[str, frozenset[str] | None], str]] = {
    "valor_multa": (
        {"cnab400": frozenset({"inter"}), "cnab240": frozenset()},
        "a multa é percentual (use codigo_multa='2' + percentual_multa)"),
    "percentual_mora": (
        {"cnab400": frozenset({"inter"}), "cnab240": None},
        "a mora é valor ao dia (use tipo_mora='1' + valor_mora)"),
    "percentual_desconto": (
        {"cnab400": frozenset({"inter"}), "cnab240": frozenset()},
        "o desconto é em valor (use cod_desconto + valor_desconto)"),
}

#: Codigo/tipo do encargo que pede um campo de valor especifico. Sem esta
#: checagem o codigo entraria coerente e o VALOR sumiria — o banco cobraria pela
#: regra errada sem que nada no arquivo denunciasse.
_CODIGO_PEDE_CAMPO: dict[tuple[str, str], str] = {
    ("codigo_multa", "1"): "valor_multa",
    ("tipo_mora", "2"): "percentual_mora",
    ("cod_desconto", "4"): "percentual_desconto",
}


def _grava(campo: str, cnab_type: str, bank: str) -> bool:
    bancos = _ENCARGO_COM_POSICAO[campo][0].get(cnab_type)
    return bancos is None or bank in bancos


def _onde_grava(campo: str, cnab_type: str) -> str:
    bancos = _ENCARGO_COM_POSICAO[campo][0].get(cnab_type)
    if bancos is None:
        return "todos"
    return ", ".join(sorted(bancos)) if bancos else "nenhum banco neste layout"


def _valida_encargos(pagamentos_raw: list[dict[str, Any]], bank: str,
                     cnab_type: str) -> None:
    erros: list[str] = []
    for i, p in enumerate(pagamentos_raw):
        for campo, (_, alternativa) in _ENCARGO_COM_POSICAO.items():
            if _grava(campo, cnab_type, bank) or p.get(campo) in (None, ""):
                continue
            erros.append(
                f"pagamento[{i}]: `{campo}` não tem posição no {cnab_type} de {bank!r} e "
                f"seria ignorado — {alternativa}. Gravam este campo: "
                + _onde_grava(campo, cnab_type))
        for (campo, codigo), pedido in _CODIGO_PEDE_CAMPO.items():
            if _grava(pedido, cnab_type, bank) or str(p.get(campo, "")) != codigo:
                continue
            erros.append(
                f"pagamento[{i}]: {campo}={codigo!r} pede `{pedido}`, que não tem posição "
                f"no {cnab_type} de {bank!r} — " + _ENCARGO_COM_POSICAO[pedido][1])
    if erros:
        raise DadosInvalidos(erros)


def gerar_remessa(bank: str, cnab_type: str, dados: dict[str, Any], pix: bool = False,
                  avisos: list[str] | None = None) -> str:
    """Gera a remessa CNAB. `avisos` recebe o que o layout ignorou, se houver.

    Lista de saída em vez de valor de retorno porque a rota devolve o ARQUIVO —
    e o aviso é sobre o pedido, não sobre o conteúdo. Quem não passa a lista
    continua chamando como antes.
    """
    avisos = avisos if avisos is not None else []
    return _gerar_remessa(bank, cnab_type, dados, pix, avisos)


def _gerar_remessa(bank: str, cnab_type: str, dados: dict[str, Any], pix: bool,
                   avisos: list[str]) -> str:
    klass = _REMESSAS.get((bank, cnab_type, pix))
    if klass is None:
        combos = sorted({f"{b}/{t}{'+pix' if p else ''}" for b, t, p in _REMESSAS})
        raise DadosInvalidos(
            [f"Remessa {cnab_type}{'+pix' if pix else ''} não suportada para {bank!r}. "
             f"Suportadas: {', '.join(combos)}"])
    pagamentos_raw = dados.get("pagamentos") or []
    if not pagamentos_raw:
        raise DadosInvalidos(["Campo 'pagamentos' é obrigatório no payload da remessa"])
    _valida_encargos(pagamentos_raw, bank, cnab_type)
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
        # A engine avisa quando um campo informado NÃO é gravado por aquele
        # layout — `carteira` em oito remessas, porque o campo está na base e
        # nem todo layout o tem. O arquivo sai correto; o que faltava era o
        # sinal de que a escolha do chamador não teve efeito. Engolir o aviso
        # devolveria 200 com um arquivo que usa a carteira do padrão, e quem
        # monta a remessa com o mesmo dicionário do boleto — o caminho natural —
        # não teria como saber.
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            remessa = klass(**kwargs)
            arquivo = remessa.gera_arquivo()
    except (PyCobrancaError, ValueError, TypeError) as e:
        raise DadosInvalidos(_erros(e)) from e
    avisos.extend(str(a.message) for a in capturados
                  if issubclass(a.category, CampoIgnorado))
    return arquivo


def parse_retorno(conteudo: bytes, layout_hint: str | None = None,
                  bank: str | None = None) -> list[dict[str, Any]]:
    """Lê o retorno CNAB direto dos bytes do upload.

    Escrevia num `NamedTemporaryFile` porque `Retorno.ler` só aceitava caminho.
    A engine passou a aceitar `bytes` — como `Extrato.ler` já fazia —, então o
    arquivo do banco deixa de tocar o disco: um retorno traz nome, documento e
    valor de cada pagador, e o melhor lugar para esse dado é nenhum.

    O BANCO sai do header do arquivo, não do `bank` do request: o arquivo é a
    fonte, e é dele que dependem o layout e o sentido de cada ocorrência.
    Quando os dois discordam, o request está errado e isso vira 400 — antes o
    `bank` era exigido e nunca lido, então subir o retorno do banco errado
    devolvia 200 com dados de outro banco.
    """
    try:
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            retorno = Retorno.ler(conteudo)
            registros = list(retorno.registros)
    except RetornoInvalido as e:
        raise DadosInvalidos([f"Arquivo de retorno inválido: {e}"]) from e
    except (PyCobrancaError, ValueError) as e:
        raise DadosInvalidos(_erros(e)) from e

    codigo = getattr(retorno, "codigo_banco", None) or None
    if bank and codigo:
        esperado = CODIGO_POR_SLUG.get(bank)
        if esperado and esperado != codigo:
            do_arquivo = SLUG_POR_CODIGO.get(codigo, codigo)
            raise DadosInvalidos([
                f"O arquivo é retorno do banco {do_arquivo!r} ({codigo}), mas o request "
                f"pediu {bank!r} ({esperado}). Cada banco põe os campos em posições "
                "diferentes: ler com o layout errado devolveria valores plausíveis e "
                "errados. Confira o `bank` ou o arquivo."])

    layout = getattr(retorno, "layout", None) or layout_hint or "400"
    layout = str(layout).replace("cnab", "")
    # `banco` decide o SENTIDO da ocorrência, não só a posição: o `40` é "baixa
    # por liquidação" no mapa geral e "baixa de título protestado" no Safra;
    # o `07` do Inter é "cancelado" e não "liquidação parcial". Sem passá-lo, a
    # conciliação lia o oposto do que o banco quis dizer.
    itens = [retorno_item_para_api(r, layout=layout, banco=codigo) for r in registros]

    # A engine avisa quando não tem o mapa do banco e leu com o layout de
    # reserva. É a falha mais perigosa do parsing porque a saída é plausível —
    # o item sai completo, com campos que podem ter vindo de outras posições.
    # Engolir o aviso era devolver 200 sem dizer que os números são suspeitos.
    generico = any(issubclass(a.category, LayoutGenerico) for a in capturados)
    for item in itens:
        item["layout_generico"] = generico
    return itens


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
