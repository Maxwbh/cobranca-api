# Identidade visual

| Arquivo | Onde usar |
|---|---|
| `marca.svg` | fundo claro — barras `#0F172A`, chevron `#0891B2` |
| `marca-escura.svg` | fundo escuro — barras `#F8FAFC`, chevron `#06B6D4` |
| `marca-512.png`, `marca-escura-512.png` | onde SVG não entra (redes sociais, apresentações) |
| `favicon.svg` | aba do navegador — **desenho próprio**, ver abaixo |
| `favicon.ico` | fallback legado, 16+32+48 |
| `apple-touch-icon.png` | 180×180, atalho na tela inicial do iOS |
| `social-preview.svg` → `.png` | card de link (GitHub, Slack, Twitter/X, LinkedIn) |
| `banner.svg` | topo do README, desktop — 1200×336 |
| `banner-mobile.svg` | topo do README, celular — 680×430 |
| `demo-terminal.svg` | demo animado no README — resposta REAL de `POST /cobranca`; se o contrato mudar, atualize junto |

## A marca

Três barras de larguras decrescentes que aceleram para a direita e desembocam
num chevron. A mesma forma lê **documento** e **fluxo** — que é o produto:
gerar o boleto e falar com o banco. O chevron também é o `>` de terminal e de
colchete, para o público que o projeto quer, que é quem integra.

**Duas cianas, de propósito.** Sobre branco, o `#06B6D4` da paleta tem contraste
2,43 e lava; `marca.svg` usa `#0891B2`, que dá 3,68. Sobre navy o problema não
existe e `marca-escura.svg` volta ao ciano da identidade, com 7,35.

**O favicon não é a marca reduzida.** A marca tem três barras, e a mais fina
(4 unidades de 64) daria 1px a 16px — some ou vira cinza. `favicon.svg` é um
desenho separado, com duas barras mais grossas.

**O `.ico` e o apple-touch-icon vão sobre chapa navy.** Nenhum dos dois formatos
aceita media query, e marca navy sobre barra de abas escura desaparece. Chapa
sólida lê em qualquer fundo. O `favicon.svg` é que resolve tema de verdade: ele
carrega `prefers-color-scheme` dentro do arquivo, e Chrome, Firefox e Safari
respeitam isso na aba.

### Grade

Desenhada em `viewBox 0 0 64 64` — 64 = 4 × 16, então as arestas principais caem
em pixel inteiro quando reduzida a 16px. O vão entre elementos é constante
(4 unidades), **inclusive entre a última barra e o chevron**: sem esse respiro o
traço do chevron encosta na barra e, de 32px para baixo, os dois viram um borrão
só.

### No README, sirva as duas versões

Imagem em README não acompanha o tema do GitHub sozinha — sem isto, uma das
duas versões some no fundo:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/marca-escura.svg">
  <img src="docs/assets/marca.svg" alt="Cobranca-API" width="64">
</picture>
```

### No HTML

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
```

A ordem importa: o navegador que entende SVG pega o primeiro e ignora o resto.

## Banners

**São duas artes, servidas por media query.** O banner antigo era 3:1 com duas
colunas e texto de 11px: num README aberto no celular (~380px de largura) o card
da direita ficava com 130px e as descrições em ~3px. O README já traz o
`<picture>` que troca uma pela outra:

```html
<picture>
  <source media="(max-width: 600px)" srcset="./docs/assets/banner-mobile.svg" />
  <img src="./docs/assets/banner.svg" alt="..." width="100%" />
</picture>
```

Três defeitos do banner anterior que o gerador corrige por construção:

**Os ícones eram emoji.** Emoji colorido **ignora o atributo `fill`** — o
arquivo pedia ciano no raio e o sistema entregava amarelo assim mesmo, então o
código de cores por recurso estava quebrado sem ninguém ver. E emoji renderiza
com a fonte de quem olha (Apple, Segoe, Noto), ou seja, o banner mudava de
aparência por visitante. Agora são `<path>` com traço de 2, e a cor obedece.

**O wordmark sai em curvas**, lidas dos contornos da Liberation Sans. Arial e
Helvetica diferem visivelmente no `a`, no `C` e no `R`, e identidade não pode
variar por sistema operacional. O resto continua **texto**, com pilha de métrica
de Arial: como são metricamente compatíveis, a largura não muda de máquina para
máquina e nada estoura seu recipiente — que era o defeito real —, e o texto
segue selecionável e acessível.

**As pills têm texto navy sobre ciano**, não branco. Branco sobre `#06B6D4` dá
2,43 e reprova AA; navy dá 7,35. Inverter conserta sem trocar cor da paleta.

## Social preview

**Suba o PNG, não o SVG.** O GitHub só aceita PNG/JPG/GIF em *Settings →
General → Social preview*; o `.svg` é a fonte versionada e o `.png` é o que
se carrega.

**Saiu o losango.** Era um quadrado arredondado rotacionado a 45° com miolo
preenchido, em ciano — o comentário no arquivo antigo o chamava de "losango
Pix". A marca Pix é registrada pelo BACEN, e a semelhança era exposição
desnecessária. No lugar entrou a marca do projeto, que já é feita de barras e
cumpre o mesmo papel gráfico.

**O fundo escureceu.** O gradiente ia até `#1E40AF`, e sobre ele os rótulos em
`#94A3B8` davam contraste 3,40 — reprova AA. O par atual (`#0F172A` → `#152449`)
leva o mesmo cinza a 5,93 e o ciano a 6,27.

## Regenerar

Os SVG da marca são escritos à mão. **Todo o resto é gerado** — não edite
`banner.svg`, `banner-mobile.svg`, os PNG, o `.ico` nem o apple-touch-icon
direto, porque a próxima execução regrava.

```bash
pip install playwright fonttools && playwright install chromium

python scripts/gerar-banners.py   # banner.svg, banner-mobile.svg
python scripts/gerar-icones.py    # PNG, .ico, apple-touch-icon, social-preview.png
```

Ao mexer na marca, rode os dois. Se esquecer o segundo, o `.ico` fica mostrando
a marca antiga por meses sem ninguém notar — navegador cacheia favicon de forma
agressiva.

A saída dos dois é **determinística**: rodar de novo sem mexer nas fontes
devolve os mesmos bytes, então `git status` sujo depois do script significa que
algo mudou de verdade.

Nenhum dos dois depende de ImageMagick, Inkscape ou cairo. Se o Chromium não
estiver no lugar padrão do Playwright, aponte com `CHROMIUM_PATH=/caminho/chrome`.
