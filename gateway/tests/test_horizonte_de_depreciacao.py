# Promessa de remoção não pode estar no passado.
#
# O apelido legado do `provider` é anunciado em 27 lugares — docstring de rota,
# descrição de campo, README, exemplo Oracle, página do site — sempre em texto
# corrido: "sai na 3.0.0", "apelido legado até a 3.0.0", "default novo na
# 3.0.0". Nada conferia esse número contra o `VERSION`.
#
# O defeito aparece no instante do bump: ao subir para 3.0.0, as 27 frases
# passam a prometer uma remoção para a versão que está sendo lançada — e o
# apelido continua lá, funcionando. Vinte e sete afirmações falsas, publicadas
# no Swagger, sem um teste vermelho.
#
# É a família de defeito que mais apareceu neste repositório: regra escrita e
# não cobrada. A regra, aqui, é uma só: toda versão prometida como horizonte
# tem de ser MAIOR que a versão corrente.
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
VERSAO = tuple(int(x) for x in (RAIZ / "VERSION").read_text().strip().split("."))

#: Onde procurar. Texto do produto e código — não dependência nem histórico git.
#: `.json` entra por causa de `docs/swagger/openapi.json`: é o Swagger
#: PUBLICADO, gerado das docstrings das rotas, e é lá que a promessa é lida por
#: quem integra. Deixá-lo fora faria o guarda ficar verde com a frase falsa no
#: ar — a mesma classe de furo do inventário parcial do guarda do Postman.
EXTENSOES = ("*.py", "*.md", "*.yaml", "*.yml", "*.sql", "*.txt", "*.json")
FORA = (".venv", ".git", "node_modules", "__pycache__", "site-packages")

#: Este arquivo CITA as frases para explicar o defeito e para os controles —
#: não promete nada. É a única exceção, e é nominal de propósito: carve-out por
#: padrão esconderia promessa de verdade.
SE_MESMO = Path(__file__).resolve()

#: Uma versão MAJOR.MINOR.PATCH solta no texto.
SEMVER = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")

#: O que faz de uma menção uma PROMESSA, e não um registro do passado. Verbo
#: no futuro, só: "foi removida na 2.0.0" (SECURITY.md) é história, e entrava
#: aqui enquanto o padrão aceitava particípio sem tempo.
PROMESSA = re.compile(
    r"sai na|saem na|saindo na|sair na|"
    r"legado at[eé] a|ap?elido at[eé] a|v[aá]lido at[eé] a|"
    r"default novo na|passa a ser o default na|"
    r"ser[aá] removid[oa] na|ser[aá] retirad[oa] na",
    re.IGNORECASE)

#: Janela ANTES do número. Nas 27 ocorrências o verbo vem sempre imediatamente
#: antes ("sai na 3.0.0", "legado até a 3.0.0"), inclusive quando a frase
#: quebra de linha; olhar para a frente só importava uma vizinha emprestar o
#: verbo dela — foi como `SECURITY.md:17` virou falso positivo.
JANELA = 60


def _arquivos() -> list[Path]:
    achados: list[Path] = []
    for padrao in EXTENSOES:
        achados += [p for p in RAIZ.rglob(padrao)
                    if not any(parte in FORA for parte in p.parts)
                    and p.resolve() != SE_MESMO]
    return sorted(set(achados))


def _contexto(texto: str, ini: int, fim: int) -> str:
    """Trecho ANTES do número, com quebras e prefixo de comentário virando
    espaço — é o que permite ler a frase que atravessa linhas."""
    bruto = texto[max(0, ini - JANELA):fim]
    return re.sub(r"[\s]*\n[\s]*(?:--|#|>|\*|//)?[\s]*", " ", bruto)


def _promessas() -> list[tuple[Path, int, tuple[int, int, int], str]]:
    saida = []
    for arq in _arquivos():
        try:
            texto = arq.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in SEMVER.finditer(texto):
            ctx = _contexto(texto, m.start(), m.end())
            if not PROMESSA.search(ctx):
                continue
            linha = texto.count("\n", 0, m.start()) + 1
            alvo = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            saida.append((arq, linha, alvo, ctx.strip()))
    return saida


def test_o_guarda_acha_as_promessas():
    """Varredura que não acha nada passa por engano. O apelido legado está
    anunciado em dezenas de lugares; menos de vinte significa que o padrão
    parou de casar, não que as promessas sumiram."""
    achadas = _promessas()
    assert len(achadas) >= 20, (
        f"só {len(achadas)} promessas de horizonte encontradas — o padrão "
        "quebrou. Vistas: " + ", ".join(
            f"{a.relative_to(RAIZ)}:{n}" for a, n, _, _ in achadas))


def test_toda_promessa_de_remocao_aponta_para_versao_futura():
    vencidas = [
        f"  {arq.relative_to(RAIZ)}:{linha} promete "
        f"{'.'.join(map(str, alvo))} — já é <= {'.'.join(map(str, VERSAO))}"
        for arq, linha, alvo, _ in _promessas() if alvo <= VERSAO]
    assert not vencidas, (
        "promessa de remoção para versão já lançada — a frase é falsa no "
        f"instante da tag v{'.'.join(map(str, VERSAO))}:\n" + "\n".join(vencidas))


#: O lado espelhado: referência ao PASSADO. "comportamento anterior a 2.3.0"
#: estava no `gateway/README.md` e a 2.3.0 nunca existiu — o projeto foi da
#: 2.2.0 para a 3.0.0 —, enquanto dois outros arquivos diziam "fail-closed
#: desde a 2.2.0" sobre o mesmo comportamento. Três afirmações, duas certas.
RETROSPECTIVA = re.compile(
    r"(?:desde a|anterior a|na vers[aã]o)\s+\**(\d+\.\d+\.\d+)")


def _lancadas() -> set[str]:
    texto = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    return set(re.findall(r"^## \[(\d+\.\d+\.\d+)\]", texto, re.MULTILINE))


def test_referencia_ao_passado_aponta_para_versao_que_existiu():
    lancadas = _lancadas()
    assert len(lancadas) >= 10, "o CHANGELOG parou de listar seções de versão"
    fantasmas = []
    for arq in _arquivos():
        try:
            texto = arq.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in RETROSPECTIVA.finditer(texto):
            if m.group(1) in lancadas:
                continue
            linha = texto.count("\n", 0, m.start()) + 1
            fantasmas.append(f"  {arq.relative_to(RAIZ)}:{linha} cita "
                             f"{m.group(1)}, que não tem seção no CHANGELOG")
    assert not fantasmas, ("referência a versão que nunca foi lançada:\n"
                          + "\n".join(fantasmas))


# ---------------------------------------------------------------------------
# Controles: o guarda acima só vale se souber separar promessa de registro.

@pytest.mark.parametrize("frase", [
    "o apelido legado sai na 9.9.9",
    "aceito como apelido legado até a 9.9.9",
    "flag com default compatível hoje, default novo na 9.9.9",
    "-- aceito como apelido de on+banco, e sai na\n-- 9.9.9 — chamada antiga",
])
def test_controle_positivo_reconhece_promessa(frase: str):
    m = SEMVER.search(frase)
    assert m, "a frase de controle perdeu o número"
    assert PROMESSA.search(_contexto(frase, m.start(), m.end())), (
        f"promessa não reconhecida: {frase!r}")


@pytest.mark.parametrize("frase", [
    "comportamento anterior a 2.3.0 — inseguro",
    "Até a 2.2.0 isto vinha errado: a engine normalizava o valor",
    "é fail-closed desde a 2.2.0",
    "fixe a versão (ghcr.io/maxwbh/cobranca-api:2.2.0) em produção",
    "payments-pix-recurring-payments-automatic | 2.2.0 | Pix Automático",
    "a arquitetura em que ela se baseava foi removida na 2.0.0",
    "paths, campos e headers `X-*` da 1.5.0 continuam valendo",
])
def test_controle_negativo_ignora_registro_do_passado(frase: str):
    m = SEMVER.search(frase)
    assert m, "a frase de controle perdeu o número"
    assert not PROMESSA.search(_contexto(frase, m.start(), m.end())), (
        f"registro do passado lido como promessa: {frase!r}")
