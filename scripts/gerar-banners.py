#!/usr/bin/env python3
"""Gera docs/assets/banner.svg e banner-mobile.svg.

Por que por script e nao SVG escrito a mao: o wordmark sai em CURVAS, lidas dos
contornos da Liberation Sans. Colar esses <path> a mao deixaria o arquivo
ilegivel e impossivel de ajustar. Aqui o codigo e a fonte, o SVG e o artefato.

Duas artes de proposito. O banner antigo era 3:1 com duas colunas e texto de
11px: num README aberto no celular (~380px) o card da direita ficava com 130px
de largura e as descricoes em ~3px. Agora o README serve as duas por media
query:

    <picture>
      <source media="(max-width: 600px)" srcset="docs/assets/banner-mobile.svg">
      <img src="docs/assets/banner.svg" alt="...">
    </picture>

Tipografia: o wordmark vai em curvas porque e a marca — Arial e Helvetica
diferem visivelmente no 'a', no 'C' e no 'R', e identidade nao pode variar por
sistema operacional. O resto fica como TEXTO, com pilha de metrica de Arial
(Liberation Sans / Arial / Helvetica): sao metricamente compativeis, entao a
LARGURA nao muda de maquina para maquina e nada estoura o seu recipiente — que
era o defeito real. Texto tambem continua selecionavel e acessivel.

    python scripts/gerar-banners.py
"""
import pathlib

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "assets"
FONTE_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

PILHA = "'Liberation Sans', Arial, Helvetica, sans-serif"

# Paleta — a mesma da marca e do social preview.
NAVY, NAVY2 = "#0F172A", "#152449"
CIANO, CIANO_ESC = "#06B6D4", "#0891B2"
CLARO, CINZA, CINZA2 = "#F8FAFC", "#CBD5E1", "#94A3B8"
BORDA = "#334155"

SUBTITULO = "Boletos, Pix, CNAB 240/400 e OFX — via API REST"

# ---------------------------------------------------------------- wordmark
_fonte = None


def _abrir():
    global _fonte
    if _fonte is None:
        f = TTFont(FONTE_BOLD)
        _fonte = (f, f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm, f["hmtx"],
                  {p: v for t in f["kern"].kernTables for p, v in t.kernTable.items()}
                  if "kern" in f else {})
    return _fonte


def curvas(texto, tamanho):
    """(svg, largura) do texto em contornos, baseline em y=0, inicio em x=0."""
    _, gs, cmap, upem, hmtx, kerns = _abrir()
    escala = tamanho / upem
    x, partes, ant = 0, [], None
    for ch in texto:
        g = cmap[ord(ch)]
        if ant is not None:
            x += kerns.get((ant, g), 0)
        pen = SVGPathPen(gs)
        gs[g].draw(pen)
        if (d := pen.getCommands()):
            partes.append(f'<path transform="translate({x} 0)" d="{d}"/>')
        x += hmtx[g][0]
        ant = g
    corpo = "\n        ".join(partes)
    return corpo, x * escala


def wordmark(x, baseline, tamanho):
    """"Cobranca" claro + "-API" ciano, em curvas."""
    a, la = curvas("Cobranca", tamanho)
    b, lb = curvas("-API", tamanho)
    e = tamanho / _abrir()[3]
    return (
        f'  <g transform="translate({x} {baseline})">\n'
        f'    <g fill="{CLARO}" transform="scale({e} {-e})">\n        {a}\n    </g>\n'
        f'    <g fill="{CIANO}" transform="translate({la} 0) scale({e} {-e})">\n        {b}\n    </g>\n'
        f'  </g>', la + lb)


# ------------------------------------------------------------------ marca
def marca(x, y, px):
    """A marca do projeto, versao clara, escalada de 64 para px."""
    s = px / 64
    return f"""  <g transform="translate({x} {y}) scale({s})">
    <g fill="{CLARO}">
      <rect x="6" y="14" width="8" height="36" rx="1.5"/>
      <rect x="18" y="14" width="6" height="36" rx="1.5"/>
      <rect x="28" y="14" width="4" height="36" rx="1.5"/>
    </g>
    <path d="M40.5 18.5 L53.5 32 L40.5 45.5" fill="none" stroke="{CIANO}"
          stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
  </g>"""


# ------------------------------------------------------------------ icones
# Desenhados em <path>, nao emoji. Emoji colorido IGNORA o atributo fill: o
# banner antigo pedia fill ciano no raio e o sistema entregava amarelo assim
# mesmo, entao o codigo de cores por recurso estava quebrado e invisivelmente.
# Emoji tambem renderiza com a fonte de quem olha — Apple no Mac, Segoe no
# Windows, Noto no Linux —, ou seja, o banner mudava de aparencia por visitante.
# Tracado de 2 em caixa de 24, estilo de biblioteca de icone.
ICONES = {
    # documento com dobra e duas linhas de texto
    "documento": 'M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z M14 3v4h4 M9 13h6 M9 17h4',
    # raio
    "raio": 'M13 2 5 13.5h5.5L9.5 22 19 10.5h-5.5z',
    # duas setas em ciclo (remessa e retorno)
    "ciclo": 'M20 11a8 8 0 0 0-13.7-5.2L3 9 M3 4v5h5 M4 13a8 8 0 0 0 13.7 5.2L21 15 M21 20v-5h-5',
    # cartao
    "cartao": 'M3 6.5h18a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z M2 10.5h20 M6 14.5h4',
}

RECURSOS = [
    ("documento", CIANO,     "Boletos PDF e carnês",   "OFFLINE", "Layouts A4 de 19 bancos e carnê 3 vias"),
    ("raio",      "#38BDF8", "Pix e Bolepix híbrido",  "ONLINE",  "QR dinâmico e Pix Automático BACEN"),
    ("ciclo",     "#34D399", "CNAB 240/400 e OFX",     "OFFLINE", "Remessa, retorno e conciliação"),
    ("cartao",    "#A78BFA", "Link de pagamento",      "ONLINE",  "Checkout com crédito e débito"),
]

# 19 = 4 online (C6, Sicoob, Inter, Itaú) + 19 offline da engine, menos os 4
# que estão nos dois caminhos. O Inter era o único banco `on` sem `off`; a
# pyCobrança 1.1.1 implementou o layout 077, então ele passou para os dois lados
# e o offline foi de 18 para 19 — o TOTAL segue 19, porque nenhuma instituição
# nova entrou. Detalhamento no ALT e no site.
PILLS = ["19 bancos", "REST + Python", "MIT Open Source"]


def icone(nome, x, y, px, cor):
    s = px / 24
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{cor}"'
            f' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="{ICONES[nome]}"/></g>')


def pill(x, y, rotulo, tamanho, alt=34):
    """Pill de fundo ciano com texto navy: 7,35 de contraste.

    O material aprovado trazia texto BRANCO sobre ciano, que da 2,43 e reprova
    AA. Inverter o texto conserta sem trocar uma cor da paleta.
    """
    larg = round(len(rotulo) * tamanho * 0.56) + 30
    return (f'<g transform="translate({x} {y})">'
            f'<rect width="{larg}" height="{alt}" rx="{alt/2}" fill="{CIANO}"/>'
            f'<text x="{larg/2}" y="{alt/2 + tamanho*0.36:.0f}" font-size="{tamanho}"'
            f' font-weight="700" fill="{NAVY}" text-anchor="middle">{rotulo}</text></g>'), larg


def fundo(w, h):
    return f"""  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{NAVY}"/><stop offset="1" stop-color="{NAVY2}"/>
    </linearGradient>
  </defs>
  <rect width="{w}" height="{h}" rx="14" fill="url(#bg)"/>"""


ALT = ("Cobranca-API — boletos, Pix, CNAB 240/400 e OFX via API REST. "
       "4 bancos online (C6, Sicoob, Inter, Itaú) e 19 offline, 100% Python, licença MIT.")


# ---------------------------------------------------------------- desktop
def banner_desktop():
    W, H, M = 1200, 336, 72
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"',
         f'     role="img" aria-label="{ALT}">',
         "  <!-- GERADO por scripts/gerar-banners.py — nao edite a mao. -->",
         fundo(W, H),
         f'  <rect width="{W}" height="4" rx="2" fill="{CIANO}"/>',
         marca(M, 44, 62)]

    wm, _ = wordmark(M + 78, 100, 52)
    p.append(wm)
    p.append(f'  <g font-family="{PILHA}">')
    p.append(f'    <text x="{M}" y="154" font-size="22" font-weight="500" fill="{CINZA}">{SUBTITULO}</text>')

    x = M
    for r in PILLS:
        g, larg = pill(x, 182, r, 15)
        p.append("    " + g)
        x += larg + 12

    p.append(f'    <text x="{M}" y="284" font-size="13" font-weight="500" fill="{CINZA2}"'
             f' letter-spacing="0.4">Oracle APEX · PL/SQL · Python · Java · Node · C# · PHP · Go · Delphi</text>')

    # Card da direita. Sem os tres circulos de semaforo do macOS que o banner
    # antigo tinha: era cromo de janela dizendo "aplicativo desktop" enquanto o
    # rotulo ao lado dizia "requisicao HTTP". Aqui o cabecalho e so a linha de
    # requisicao, que e o que o produto e.
    cx, cy, cw, ch = 730, 44, W - 730 - M, 248
    p.append(f'    <g transform="translate({cx} {cy})">')
    p.append(f'      <rect width="{cw}" height="{ch}" rx="12" fill="#0B1220" fill-opacity="0.55"'
             f' stroke="{BORDA}" stroke-width="1"/>')
    p.append(f'      <rect width="{cw}" height="44" rx="12" fill="#0B1220" fill-opacity="0.7"/>')
    p.append(f'      <rect y="32" width="{cw}" height="12" fill="#0B1220" fill-opacity="0.7"/>')
    p.append(f'      <line y1="44" x2="{cw}" y2="44" stroke="{BORDA}" stroke-width="1"/>')
    p.append(f'      <g transform="translate(16 12)"><rect width="52" height="20" rx="5" fill="#34D399" fill-opacity="0.16"/>'
             f'<text x="26" y="14" font-size="11" font-weight="700" fill="#34D399"'
             f' text-anchor="middle" font-family="ui-monospace, monospace">POST</text></g>')
    p.append(f'      <text x="76" y="26" font-size="13" fill="{CINZA}"'
             f' font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">/cobranca</text>')

    for i, (ic, cor, titulo, selo, desc) in enumerate(RECURSOS):
        y = 64 + i * 50
        online = selo == "ONLINE"
        sc, sw = (CIANO, 48) if online else (CINZA2, 56)
        p.append(f'      <g transform="translate(18 {y})">')
        p.append(f'        <rect width="30" height="30" rx="7" fill="{cor}" fill-opacity="0.14"/>')
        p.append("        " + icone(ic, 5, 5, 20, cor))
        p.append(f'        <text x="42" y="13" font-size="14" font-weight="600" fill="{CLARO}">{titulo}</text>')
        p.append(f'        <text x="42" y="28" font-size="11" fill="{CINZA2}">{desc}</text>')
        p.append(f'        <rect x="{cw - 36 - sw}" y="1" width="{sw}" height="17" rx="8.5"'
                 f' fill="{sc}" fill-opacity="0.14" stroke="{sc}" stroke-opacity="0.4" stroke-width="1"/>')
        p.append(f'        <text x="{cw - 36 - sw/2}" y="13" font-size="9" font-weight="700"'
                 f' letter-spacing="0.8" fill="{sc}" text-anchor="middle">{selo}</text>')
        p.append("      </g>")
    p.append("    </g>")
    p.append("  </g>")
    p.append("</svg>")
    return "\n".join(p) + "\n"


# ----------------------------------------------------------------- mobile
def banner_mobile():
    """680x430 (1,58:1). Coluna unica, tipos grandes, recursos em grade 2x2.

    Dimensionado para ~380px de largura de tela, onde a escala fica em 0,56:
    o menor texto aqui (18px) chega a 10px reais, que ainda se le. O banner
    antigo, em 4:1 com texto de 11px, chegava a 3px.
    """
    W, H, M = 680, 430, 48
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"',
         f'     role="img" aria-label="{ALT}">',
         "  <!-- GERADO por scripts/gerar-banners.py — nao edite a mao. -->",
         fundo(W, H),
         f'  <rect width="{W}" height="4" rx="2" fill="{CIANO}"/>',
         marca(M, 44, 60)]

    wm, _ = wordmark(M + 76, 98, 50)
    p.append(wm)
    p.append(f'  <g font-family="{PILHA}">')
    p.append(f'    <text x="{M}" y="152" font-size="23" font-weight="500" fill="{CINZA}">{SUBTITULO}</text>')

    x = M
    for r in PILLS:
        g, larg = pill(x, 178, r, 16, alt=36)
        p.append("    " + g)
        x += larg + 10

    for i, (ic, cor, titulo, selo, _d) in enumerate(RECURSOS):
        cx = M + (i % 2) * 300
        cy = 244 + (i // 2) * 88
        sc, sw = (CIANO, 52) if selo == "ONLINE" else (CINZA2, 60)
        p.append(f'    <g transform="translate({cx} {cy})">')
        p.append(f'      <rect width="36" height="36" rx="9" fill="{cor}" fill-opacity="0.14"/>')
        p.append("      " + icone(ic, 6, 6, 24, cor))
        p.append(f'      <text x="50" y="16" font-size="18" font-weight="600" fill="{CLARO}">{titulo}</text>')
        p.append(f'      <rect x="50" y="26" width="{sw}" height="18" rx="9" fill="{sc}" fill-opacity="0.14"'
                 f' stroke="{sc}" stroke-opacity="0.4" stroke-width="1"/>')
        p.append(f'      <text x="{50 + sw/2}" y="38.5" font-size="10" font-weight="700"'
                 f' letter-spacing="0.8" fill="{sc}" text-anchor="middle">{selo}</text>')
        p.append("    </g>")
    p.append("  </g>")
    p.append("</svg>")
    return "\n".join(p) + "\n"


if __name__ == "__main__":
    for nome, conteudo in (("banner.svg", banner_desktop()),
                           ("banner-mobile.svg", banner_mobile())):
        (SAIDA / nome).write_text(conteudo, encoding="utf-8")
        print(f"  {nome:20} {len(conteudo):6} bytes")
