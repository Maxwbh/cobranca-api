# Marca da M&S do Brasil

Os dois arquivos desta pasta são a assinatura horizontal da **M&S do Brasil
LTDA**, tirados sem alteração do kit de marca **v0.7** (novembro de 2026).
Servem ao endosso "um projeto M&S do Brasil" no rodapé do README e do site.

| Arquivo | Onde |
|---|---|
| `ms-assinatura-horizontal-fundo-claro.svg` | fundo branco ou claro: site e README no tema claro |
| `ms-assinatura-horizontal-fundo-escuro.svg` | fundo escuro: README no tema escuro do GitHub |

**A licença MIT deste repositório não se aplica a estes arquivos.** Ela cobre o
código e a documentação. O nome e a marca da M&S do Brasil identificam a
empresa, e usá-los fora de "um projeto M&S do Brasil" ou "com apoio da M&S do
Brasil", quando isso for verdadeiro, depende de autorização: msbrasil.inf.br.

**Não edite à mão.** Os SVG saem do gerador do kit de marca, que não está neste
repositório. Versão nova do kit entra trocando os arquivos inteiros e o hash
em `gateway/tests/test_marca_ms.py`, que confere byte a byte.

**Uso, pelo manual v0.7:**

- altura mínima em tela de 28 px; abaixo disso, use o símbolo;
- área de proteção de um terço da altura da arte em volta, sem texto nem outra
  marca dentro;
- variante `fundo-claro` só em fundo claro, `fundo-escuro` só em fundo escuro;
- sem esticar, girar, recolorir, sombra ou contorno.

**Situação:** o kit v0.7 tem o conceito visual congelado, mas ainda não está
homologado. Faltam a busca de anterioridade no INPI e a prova de impressão.
