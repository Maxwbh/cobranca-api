#!/usr/bin/env python3
"""Gera os derivados da marca a partir dos SVG em docs/assets/.

Os SVG sao a fonte; PNG, .ico e apple-touch-icon sao gerados. Ao mexer na
marca, rode isto — senao o .ico fica mostrando a marca antiga por meses sem
ninguem notar, porque navegador cacheia favicon de forma agressiva.

Renderiza em Chromium headless via Playwright e monta o .ico com PNGs
embutidos. Sem ImageMagick, sem Inkscape, sem cairo.

    pip install playwright && playwright install chromium
    python scripts/gerar-icones.py
"""
import os
import pathlib, struct, tempfile
from playwright.sync_api import sync_playwright
A = pathlib.Path(__file__).resolve().parent.parent / "docs" / "assets"

def svg_de(nome): return A.joinpath(nome).read_text(encoding="utf-8")

# Para o .ico e o apple-touch-icon a arte vai sobre CHAPA navy: os dois são
# formatos sem media query, e marca navy sobre barra de abas escura some.
CHAPA = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="{rx}" fill="#0F172A"/>
  <g fill="#F8FAFC">
    <rect x="10" y="18" width="7" height="28" rx="1.5"/>
    <rect x="21" y="18" width="5" height="28" rx="1.5"/>
    <rect x="30" y="18" width="3" height="28" rx="1.5"/>
  </g>
  <path d="M40 22 L50 32 L40 42" fill="none" stroke="#06B6D4"
        stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

alvos = [
    ("marca-512.png",         svg_de("marca.svg"),        512, True),
    ("marca-escura-512.png",  svg_de("marca-escura.svg"), 512, True),
    ("apple-touch-icon.png",  CHAPA.format(rx=0),         180, False),
]
ico_tam = [16, 32, 48]
TMP = pathlib.Path(tempfile.mkdtemp(prefix="icones-"))

with sync_playwright() as p:
    exe = os.environ.get("CHROMIUM_PATH")
    b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
    def render(svg, px, transparente, saida):
        pg = b.new_page(viewport={"width": px, "height": px}, device_scale_factor=1)
        inner = svg.replace("<svg ", '<svg style="width:100vw;height:100vh;display:block" ', 1)
        pg.set_content(f"<!doctype html><meta charset=utf-8>"
                       f"<body style='margin:0;background:{'transparent' if transparente else '#0F172A'}'>{inner}</body>")
        pg.wait_for_timeout(250)
        pg.screenshot(path=saida, omit_background=transparente)
        pg.close()

    for nome, svg, px, transp in alvos:
        render(svg, px, transp, str(A / nome))
        print(f"  {nome:24} {px}x{px}")

    # Social preview: nao e quadrado, e o GitHub so aceita PNG/JPG em
    # Settings > General > Social preview — o SVG e apenas a fonte.
    pg = b.new_page(viewport={"width": 1280, "height": 640}, device_scale_factor=1)
    pg.set_content("<!doctype html><meta charset=utf-8><body style='margin:0'>"
                   + svg_de("social-preview.svg") + "</body>")
    pg.wait_for_timeout(250)
    pg.screenshot(path=str(A / "social-preview.png"))
    pg.close()
    print(f"  {'social-preview.png':24} 1280x640")

    for px in ico_tam:
        render(CHAPA.format(rx=12), px, True, str(TMP / f"ico-{px}.png"))

    b.close()

# monta o .ico com PNGs embutidos (suportado por todo navegador moderno)
pngs = [(px, pathlib.Path(str(TMP / f"ico-{px}.png")).read_bytes()) for px in ico_tam]
cab = struct.pack("<HHH", 0, 1, len(pngs))
desloc = 6 + 16 * len(pngs)
entradas, corpo = b"", b""
for px, dados in pngs:
    entradas += struct.pack("<BBBBHHII", px, px, 0, 0, 1, 32, len(dados), desloc)
    corpo += dados
    desloc += len(dados)
(A / "favicon.ico").write_bytes(cab + entradas + corpo)
print(f"  {'favicon.ico':24} {'+'.join(map(str, ico_tam))}  ({len(cab+entradas+corpo)} bytes)")
