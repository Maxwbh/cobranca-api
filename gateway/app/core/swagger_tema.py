"""Página do Swagger UI com a identidade visual da plataforma.

As duas superfícies (gateway em `/docs`, offline em `/api/docs`) usavam HTML
quase idêntico duplicado em dois arquivos — e as duas carregavam no topbar o
losango rotacionado que já saiu do social preview pela semelhança com a marca
Pix do BACEN. Aqui vive UMA página parametrizada: a marca é a oficial (barras
+ seta), a paleta é a mesma do site (navy #0F172A/#152449 + ciano #06B6D4) e
o corpo do Swagger recebe o mesmo tratamento de cartões do restante da
plataforma.
"""
from __future__ import annotations

from pathlib import Path

# A marca em 64x64, geometria idêntica a docs/assets/marca-escura.svg.
_MARCA = (
    '<svg class="cob-mark" width="30" height="30" viewBox="0 0 64 64" aria-hidden="true">'
    '<g fill="#F8FAFC"><rect x="6" y="14" width="8" height="36" rx="1.5"/>'
    '<rect x="18" y="14" width="6" height="36" rx="1.5"/>'
    '<rect x="28" y="14" width="4" height="36" rx="1.5"/></g>'
    '<path d="M40.5 18.5 L53.5 32 L40.5 45.5" fill="none" stroke="#06B6D4"'
    ' stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

# O favicon inline, pelo mesmo motivo dos assets do swagger-ui: buscá-lo no
# GitHub Pages deixa a página esperando um terceiro que a rede do cliente pode
# não alcançar. Desenho idêntico a docs/assets/favicon.svg, sem os comentários
# — inclusive o `prefers-color-scheme`, que é o motivo de ele ser SVG.
_FAVICON = (
    "data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%2016%2016%22%20width=%2216%22%20height=%2216%22%20role=%22img%22%20aria-label=%22Cobranca-API%22%3E%3Cstyle%3E%20.barra%20%7B%20fill:%20#0F172A;%20%7D%20.seta%20%7B%20stroke:%20#0891B2;%20%7D%20@media%20(prefers-color-scheme:%20dark)%20%7B%20.barra%20%7B%20fill:%20#F8FAFC;%20%7D%20.seta%20%7B%20stroke:%20#06B6D4;%20%7D%20%7D%20%3C/style%3E%3Cg%20class=%22barra%22%3E%3Crect%20x=%221%22%20y=%223%22%20width=%223%22%20height=%2210%22%20rx=%220.5%22/%3E%3Crect%20x=%225.5%22%20y=%223%22%20width=%222.5%22%20height=%2210%22%20rx=%220.5%22/%3E%3C/g%3E%3Cpath%20class=%22seta%22%20d=%22M11.25%204.25%20L14%208%20L11.25%2011.75%22%20fill=%22none%22%20stroke-width=%222.5%22%20stroke-linecap=%22round%22%20stroke-linejoin=%22round%22/%3E%3C/svg%3E"
)

#: CSS do cabeçalho, compartilhado pelas três páginas de documentação
#: (`/docs`, `/api/docs` e `/redoc`) — uma identidade só, num lugar só.
_CSS_TOPBAR = """    /* Paleta da plataforma: navy #0F172A/#152449 · ciano #06B6D4 · ação #0891B2 */
    body { margin: 0; background: #FFFFFF; }
    .cob-topbar {
      background: linear-gradient(120deg, #0F172A, #152449);
      padding: 13px 28px; color: #fff; border-bottom: 3px solid #06B6D4;
      display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
      font-family: -apple-system, 'Segoe UI', Roboto, Ubuntu, sans-serif;
    }
    .cob-topbar h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: .2px; }
    .cob-topbar h1 span { color: #06B6D4; }
    .cob-topbar .surface { color: #67E8F9; font-size: 12px; font-weight: 700;
                           text-transform: uppercase; letter-spacing: 1.2px; }
    .cob-topbar small { color: #94A3B8; font-size: 12px; }
    .cob-topbar .pill { background: rgba(6,182,212,.14); border: 1px solid #06B6D4;
                        color: #A5F3FC; font-size: 11px; font-weight: 600;
                        border-radius: 999px; padding: 3px 10px; letter-spacing: .4px; }
    .cob-topbar .links { margin-left: auto; display: flex; gap: 8px; }
    .cob-topbar a { color: #fff; font-size: 13px; font-weight: 600; text-decoration: none;
                    border: 1px solid rgba(248,250,252,.4); border-radius: 6px; padding: 5px 12px; }
    .cob-topbar a:hover { border-color: #06B6D4; background: rgba(6,182,212,.15); }
    .cob-topbar a.primario { background: #06B6D4; border-color: #06B6D4; color: #0F172A; }
    .cob-topbar a.primario:hover { background: #22D3EE; border-color: #22D3EE; }
    .cob-mark { flex: none; }"""

_PAGINA = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITULO__</title>
  <link rel="stylesheet" href="__ASSETS__/swagger-ui.css">
  <link rel="icon" href="__FAVICON__" type="image/svg+xml">
  <style>
__CSS_TOPBAR__

    /* O topbar nativo do swagger-ui sai; o nosso assume. */
    .swagger-ui .topbar { display: none; }

    /* Cabeçalho da spec: cartão claro separando a apresentação dos endpoints */
    .swagger-ui .info {
      margin: 26px 0; padding: 22px 26px 18px;
      background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px;
    }
    .swagger-ui .info .title { color: #0F172A; }
    .swagger-ui .info a { color: #0891B2; }
    .swagger-ui .info .description h2, .swagger-ui .info .description h3 { color: #0F172A; }
    .swagger-ui .info .description h2 {
      border-bottom: 1px solid #E2E8F0; padding-bottom: .3em; margin-top: 1.4em;
    }

    /* Código na descrição vira terminal navy — o mesmo do site. O swagger-ui
       pinta `code` de roxo sobre cinza, que destoa de tudo. */
    .swagger-ui .info .description pre {
      background: #0F172A; border: 0; border-radius: 10px; padding: 14px 16px;
      box-shadow: 0 8px 22px rgba(2,6,23,.18);
    }
    .swagger-ui .info .description pre code,
    .swagger-ui .info .description pre span { color: #E2E8F0 !important; background: transparent; }
    .swagger-ui .info .description p code,
    .swagger-ui .info .description li code,
    .swagger-ui .info .description td code {
      background: #E8EEF6; color: #0F172A; border-radius: 4px; padding: 1px 5px;
    }

    /* Tabela da descrição como cartão (igual ao site). */
    .swagger-ui .info .description table {
      border-collapse: separate; border-spacing: 0; width: 100%;
      border: 1px solid #E2E8F0; border-radius: 10px; overflow: hidden; margin: .9em 0;
    }
    .swagger-ui .info .description th {
      background: #0F172A; color: #F8FAFC; text-align: left;
      border: 0; border-bottom: 2px solid #06B6D4; padding: 8px 12px;
    }
    .swagger-ui .info .description td { border: 0; border-bottom: 1px solid #EEF2F7; padding: 8px 12px; }
    .swagger-ui .info .description tr:last-child td { border-bottom: 0; }
    .swagger-ui .info .description tr:nth-child(even) td { background: #FFFFFF; }

    /* Contato e licença: o swagger-ui empilha como links soltos ("Send email
       to…", "MIT"). Viram chips numa linha só. */
    .swagger-ui .info .info__contact, .swagger-ui .info .info__license,
    .swagger-ui .info .info__extdocs { display: inline-block; margin: 6px 8px 0 0; }
    .swagger-ui .info .info__contact a, .swagger-ui .info .info__license a,
    .swagger-ui .info .info__extdocs a {
      display: inline-block; background: #FFFFFF; border: 1px solid #CBD5E1;
      border-radius: 999px; padding: 3px 11px; font-size: 12px; font-weight: 600;
      color: #0F172A; text-decoration: none; margin-right: 6px;
    }
    .swagger-ui .info .info__contact a:hover, .swagger-ui .info .info__license a:hover,
    .swagger-ui .info .info__extdocs a:hover { border-color: #06B6D4; background: #ECFEFF; }

    /* Barra de servidores/autorização */
    .swagger-ui .scheme-container { background: #F8FAFC; box-shadow: none;
                                    border-bottom: 1px solid #E2E8F0; }
    .swagger-ui .btn.authorize { border-color: #0891B2; color: #0891B2; }
    .swagger-ui .btn.authorize svg { fill: #0891B2; }

    /* Grupos (tags) e operações como cartões */
    .swagger-ui .opblock-tag { color: #0F172A; border-bottom: 1px solid #E2E8F0;
                               font-weight: 700; }
    .swagger-ui .opblock-tag:hover { background: #F8FAFC; }
    .swagger-ui .opblock { border-radius: 8px; box-shadow: 0 1px 4px rgba(2,6,23,.08); }
    .swagger-ui .opblock .opblock-summary-method {
      border-radius: 6px; font-weight: 700; min-width: 84px;
    }
    .swagger-ui .opblock .opblock-summary { border-radius: 8px; }
    .swagger-ui .opblock .opblock-summary-path { font-weight: 600; }
    .swagger-ui .btn.execute { background-color: #0891B2; border-color: #0891B2; }
    .swagger-ui .btn.execute:hover { background-color: #0E7490; border-color: #0E7490; }

    /* Modelos */
    .swagger-ui section.models { border: 1px solid #E2E8F0; border-radius: 8px; }
    .swagger-ui section.models h4 { color: #0F172A; }

    @media (max-width: 640px) {
      .cob-topbar { padding: 10px 14px; gap: 8px; }
      .cob-topbar h1 { font-size: 17px; }
      .cob-topbar small, .cob-topbar .pill { display: none; }
      .cob-topbar .links { margin-left: 0; width: 100%; }
      .cob-topbar .links a { flex: 1; text-align: center; }

      /* A tabela da descrição não cabe em 390px: sem isto ela é cortada no
         limite da tela e a última coluna some. Vira bloco com rolagem
         horizontal própria — a página continua rolando só na vertical. */
      .swagger-ui .info .description table {
        display: block; overflow-x: auto; white-space: nowrap;
      }
      .swagger-ui .info { padding: 16px 14px 12px; }
      .swagger-ui .info .description pre { padding: 12px; font-size: 12px; }

      /* O swagger põe nome do grupo e descrição lado a lado; em 390px a
         descrição vira uma coluna de 3 palavras e o grupo ocupa meia tela de
         altura. Empilhado, o nome fica na linha de cima e o texto usa a
         largura inteira. */
      .swagger-ui .opblock-tag { flex-wrap: wrap; padding: 10px 12px; }
      .swagger-ui .opblock-tag small {
        flex: 1 1 100%; padding: 4px 0 0; font-size: 12px; line-height: 1.45;
      }
      .swagger-ui .opblock .opblock-summary-method { min-width: 66px; font-size: 12px; }
      .swagger-ui .opblock .opblock-summary-path { font-size: 13px; word-break: break-all; }
    }
  </style>
</head>
<body>
  <div class="cob-topbar">
    __MARCA__
    <h1>Cobranca<span>-API</span></h1>
    <span class="surface">__SUPERFICIE__</span>
    <span class="pill">__PILL__</span>
    <small>__DETALHE__</small>
    <div class="links">__LINKS__</div>
  </div>
  <div id="swagger-ui"></div>
  <script src="__ASSETS__/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: '__SPEC__',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [SwaggerUIBundle.presets.apis],
        tryItOutEnabled: true,
        validatorUrl: null,
      });
    };
  </script>
</body>
</html>"""


_PAGINA_REDOC = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITULO__</title>
  <link rel="icon" href="__FAVICON__" type="image/svg+xml">
  <!-- O bundle do Redoc traz o logo do rodape apontando para cdn.redoc.ly. Num
       deploy sem saida para a internet isso vira um request morto no console —
       a mesma classe de problema que tirou o renderizador da CDN. Nao da para
       remover do bundle (ele e vendorizado SEM modificacao, e e assim que a
       licenca de terceiro fica limpa), entao a pagina simplesmente nao permite
       imagem de fora: o credito de texto continua, o request nao acontece. -->
  <meta http-equiv="Content-Security-Policy" content="img-src 'self' data:">
  <style>
__CSS_TOPBAR__
    /* O HTML padrao do FastAPI puxa a fonte do Google. Aqui a pilha e a do
       sistema, como no resto da plataforma — e sem buscar nada fora. */
    redoc { font-family: -apple-system, 'Segoe UI', Roboto, Ubuntu, sans-serif; }
  </style>
</head>
<body>
  <div class="cob-topbar">
    __MARCA__
    <h1>Cobranca<span>-API</span></h1>
    <span class="surface">__SUPERFICIE__</span>
    <span class="pill">__PILL__</span>
    <small>__DETALHE__</small>
    <div class="links">__LINKS__</div>
  </div>
  <redoc spec-url="__SPEC__"></redoc>
  <script src="__ASSETS__/redoc.standalone.js"></script>
</body>
</html>"""


# De onde vêm o CSS e o JS do swagger-ui.
#
# Da PRÓPRIA aplicação, quando os arquivos estão na imagem. A regra que valia
# para a doc publicada — "uma página que existe para NÃO sair do ar não deve
# depender de um terceiro" — vale igual aqui, e por um motivo mais concreto:
# este produto é **self-hosted**, em rede que libera saída host a host (é o que
# o `examples/oracle/acl_setup.sql` configura). Alcançar a API não implica
# alcançar a unpkg.com: onde não alcança, `/docs` abre com o cabeçalho da
# plataforma e o Swagger não renderiza — página em branco, sem erro.
#
# A CDN fica como plano B para quem roda do checkout sem os arquivos (eles vêm
# de `docs/`, que o `.dockerignore` corta por padrão). Versão pinada: `@5`
# flutuante deixaria a página mudar sozinha a cada release menor do upstream.
CDN_SWAGGER = "https://unpkg.com/swagger-ui-dist@5.17.14"

#: Onde os arquivos ficam — no repositório (dev) e na imagem (produção).
VENDOR_SWAGGER = next(
    (p for p in (Path(__file__).resolve().parents[3] / "docs" / "swagger" / "vendor",
                 Path("/swagger-ui"))
     if (p / "swagger-ui-bundle.js").is_file()),
    None,
)

#: Prefixo servido pela aplicação, ou a CDN quando não há o que servir.
ASSETS_SWAGGER = "/swagger-ui" if VENDOR_SWAGGER else CDN_SWAGGER


def _ancoras(links: list[tuple[str, str, bool]]) -> str:
    """`links` é (rótulo, href, primário?). Externo abre em aba nova."""
    return "".join(
        f'<a href="{href}"{" class=\"primario\"" if primario else ""}'
        f'{" target=\"_blank\" rel=\"noopener\"" if href.startswith("http") else ""}>{rotulo}</a>'
        for rotulo, href, primario in links
    )


def pagina_swagger(*, titulo: str, superficie: str, pill: str, detalhe: str,
                   links: list[tuple[str, str, bool]], spec_url: str,
                   assets: str = ASSETS_SWAGGER) -> str:
    """Monta a página do Swagger. `links` é (rótulo, href, primário?)."""
    ancoras = _ancoras(links)
    return (_PAGINA
            .replace("__TITULO__", titulo)
            .replace("__CSS_TOPBAR__", _CSS_TOPBAR)
            .replace("__MARCA__", _MARCA)
            .replace("__FAVICON__", _FAVICON)
            .replace("__SUPERFICIE__", superficie)
            .replace("__PILL__", pill)
            .replace("__DETALHE__", detalhe)
            .replace("__LINKS__", ancoras)
            .replace("__SPEC__", spec_url)
            .replace("__ASSETS__", assets.rstrip("/")))


def pagina_redoc(*, titulo: str, superficie: str, pill: str, detalhe: str,
                 links: list[tuple[str, str, bool]], spec_url: str,
                 assets: str = ASSETS_SWAGGER) -> str:
    """A mesma casca, com o Redoc no lugar do Swagger UI.

    O `/redoc` vinha pronto do FastAPI e era a única pagina de documentacao sem
    nada disto: sem o tema da plataforma, com o favicon do
    `fastapi.tiangolo.com` e buscando renderizador, fonte e icone em tres
    terceiros diferentes.
    """
    return (_PAGINA_REDOC
            .replace("__TITULO__", titulo)
            .replace("__CSS_TOPBAR__", _CSS_TOPBAR)
            .replace("__MARCA__", _MARCA)
            .replace("__FAVICON__", _FAVICON)
            .replace("__SUPERFICIE__", superficie)
            .replace("__PILL__", pill)
            .replace("__DETALHE__", detalhe)
            .replace("__LINKS__", _ancoras(links))
            .replace("__SPEC__", spec_url)
            .replace("__ASSETS__", assets.rstrip("/")))
