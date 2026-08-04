# Homologação — artefatos e como reproduzir

Esta pasta guarda o **resultado** da homologação dos três bancos, não o
processo. O formulário é do C6; o que é nosso são as decisões de escopo e a
evidência. Sicoob e Inter seguem o mesmo roteiro, sem formulário do banco.

| Arquivo | O que é |
|---|---|
| `Roteiro de Testes - C6 Developers v3.0 - PREENCHIDO.docx` | O formulário do C6 com escopo marcado e os retornos reais do sandbox |
| `evidencia-sandbox-c6.json` | A evidência crua do C6 — status HTTP e corpo de cada caso, como o banco devolveu |
| `evidencia-sandbox-sicoob.json` | A evidência crua do Sicoob (veja a ressalva abaixo) |
| `evidencia-sandbox-inter.json` | A evidência crua do Banco Inter — **13 casos em 2xx, zero falhas**, com o banco ecoando o que foi enviado |

## O que cada sandbox prova — e a diferença não é detalhe

| Banco | Comportamento do sandbox | O que a evidência atesta |
|---|---|---|
| **C6** | Real | Integração ponta a ponta |
| **Inter** | Real, **verificado** — a sonda de eco gravou `sandbox_ecoa_o_enviado: true` | Integração ponta a ponta |
| **Sicoob** | **Mock de schema** — cada caso carrega `mock_do_banco: true` | Roteamento, contrato e normalização |

Ler as três como equivalentes seria o erro caro: no Sicoob **nenhum boleto foi
registrado e nenhum Pix foi criado**.

## Sicoob — o que o roteiro dele prova, e o que não prova

`scripts/homologacao_sicoob.py` segue o mesmo molde do C6: cada caso é uma
requisição HTTP às rotas do gateway. **Mas o sandbox do Sicoob é mock de
schema** — devolve dados aleatórios válidos, sem relação com o que foi enviado.
Pedindo uma cob de R$ 1,00 em 04/08/2026 ele respondeu `valor: "0.39"`,
`pixCopiaECola: "ex do consectetur enim magna"` e expiração em 2008.

Então essa evidência atesta **roteamento, contrato e normalização**; não atesta
comportamento do banco. Nenhum boleto é de fato registrado, nenhum Pix é de
fato criado. Cada caso carrega `mock_do_banco: true` para que ninguém leia mais
do que está lá.

Onde o C6 provou integração ponta a ponta, aqui a prova é de contrato — e ainda
assim valeu: o roteiro do Sicoob achou dois defeitos que o do C6 não podia
achar (a conta ausente nas rotas de leitura e o estouro no cálculo de prazo).

Última execução: **14 casos em 2xx, 5 ausentes, 1 recusa** — a recusa é a
emissão, que no mock responde `400` enlatado com `"string"` no lugar da
mensagem.

Formulário em branco: [portal do C6](https://developers.c6bank.com.br/test-scripts/Roteiro%20de%20Testes%20-%20C6%20Developers%20v3.0.docx)
(etapa 4 do *get-started*). Não é versionado aqui — é material do banco, sujeito
a atualização por eles.

## Reproduzir

Dentro da janela do sandbox — **seg-sex, 7h-23h BRT**, fora dela o `POST /v1/auth`
responde `403` e não é credencial inválida:

```bash
export C6_SANDBOX_CLIENT_ID=... C6_SANDBOX_CLIENT_SECRET=...
export C6_SANDBOX_PFX_BASE64=... C6_SANDBOX_PFX_PASSWORD=...
export C6_SANDBOX_CHAVE_PIX=...

PYTHONPATH=gateway python scripts/homologacao_c6.py --json > evidencia.json
python scripts/preencher_roteiro_c6.py evidencia.json --roteiro "<docx do portal>"
```

Aceita identificadores de caso como argumento para rodar só um pedaço —
`homologacao_c6.py B_01 B_05`.

Sicoob e Inter, mesmo molde e mesmos argumentos — o que muda é a credencial:

```bash
export SICOOB_SANDBOX_CLIENT_ID=... SICOOB_SANDBOX_ACCESS_TOKEN=...
PYTHONPATH=gateway python scripts/homologacao_sicoob.py --json > evidencia-sicoob.json

export INTER_SANDBOX_CLIENT_ID=... INTER_SANDBOX_CLIENT_SECRET=...
export INTER_SANDBOX_CERT_PEM="$(cat Sandbox_InterAPI_Certificado.crt)"
export INTER_SANDBOX_KEY_PEM="$(cat Sandbox_InterAPI_Chave.key)"
PYTHONPATH=gateway python scripts/homologacao_inter.py --json > evidencia-inter.json
```

O do Inter roda uma **sonda de eco** a cada execução: compara `seuNumero`, valor
e vencimento enviados com os que voltaram, e publica o veredito em
`sandbox_ecoa_o_enviado`. É ela que autoriza o relatório a afirmar integração
ponta a ponta em vez de só contrato — se o banco trocar o ambiente por um mock,
o campo vira `false` no mesmo instante.

**O runner exercita a API, não o provider.** Cada caso é uma requisição HTTP às
rotas do gateway — router, schema, validação, `exige_capacidade` e tradução de
erro incluídos. É o serviço que está sendo homologado; chamar `C6Provider`
direto pularia exatamente a camada que o integrador enxerga, e o relatório
atestaria uma coisa enquanto o cliente consome outra.

Sem `--base-url`, a app roda em processo (ASGI) — mesma pilha de rotas, só não
cruza um socket. Com `--base-url https://...`, vai contra uma instância real.

O corpo registrado é a resposta **da API**, que carrega a do banco em `raw` —
estritamente mais evidência do que o retorno cru do C6.

Nenhum dos dois scripts aceita retorno na linha de comando. É deliberado: o
documento vai ao banco como atestado de teste, e não deve existir caminho em que
alguém digite um corpo que a API não devolveu.

Uma exceção declarada: `C_05_01` reentrega na nossa rota de webhook o corpo que
o banco devolveu em `C_01` — não há URL pública neste ambiente para o sandbox
chamar de volta. O corpo entregue é do banco e o retorno registrado é da API; o
que muda é quem fez a chamada, e está dito no documento.

## Resultado da execução — C6

Última execução: **04/08/2026**, contra o sandbox.

| | Tabelas |
|---|---|
| Retorno `2xx` do banco | **50** |
| Recusa do banco, com o corpo do erro | **4** |
| Marcadas `N/A` com o motivo | **14** |
| Em branco | **0** |
| Total do formulário | **68** |

> O formulário tem **68** tabelas de retorno, não 51. Ele usa duas formas —
> Pix Automático e `BP_01` trazem um subtítulo entre o título e o cabeçalho — e
> o preenchedor lia só a primeira, deixando 17 tabelas fora da conta **e** em
> branco. Corrigido; a contagem acima é sobre o formulário inteiro.

O código de criação é `201` com `Location`, salvo o lote de cobv, que é `202` —
o banco responde *"lote solicitado para criação"*, e o lote é enfileirado, não
criado.

## Resultado da execução — Banco Inter

**13 casos em 2xx, zero falhas, 3 ausentes.** O sandbox tem comportamento real:
a sonda de eco confirmou que `seuNumero`, valor e vencimento voltam idênticos ao
que foi enviado.

Os três ausentes, e o motivo de cada um:

| Caso | Por quê |
|---|---|
| `PG_01` — pagamentos | **Fora de escopo.** Saída de dinheiro; a [régua de escopo](../development/roadmap-providers.md) exclui pagamento em qualquer provider |
| `PA_01` — Pix Automático | **Produto não habilitado na conta.** O provider implementa (dialeto BACEN, herdado do mixin) e `GET /bancos` declara a capacidade — o que falta é contratação, não código |
| `SA_01` — saldo | Rota não exposta pelo gateway; o extrato cobre o caso de uso |

Dois defeitos nossos só apareceram aqui, contra o banco de verdade: a emissão
voltava `502` por causa da **barra final** no path (o Inter responde `307` onde
o C6 exige a barra), e o default `formasRecebimento: BOLETO` **suprimia o QR
Pix** — o híbrido é `BOLETO_PIX`, hoje o default.

> **O certificado do sandbox expira em 03/09/2026.** Vencido, toda chamada falha
> na autenticação e responde `424` — que é o diagnóstico certo, mas convém não
> descobrir pelo alerta do cliente.

## Escopo — o que foi marcado e o que não foi

O banco manda **não marcar** o checkbox de API que a aplicação não usa. Das nove,
sete estão marcadas. As 14 tabelas `N/A` se dividem em três motivos, e a
diferença importa — só o primeiro é decisão de produto:

| Caso | Motivo |
|---|---|
| `AP_01`…`AP_06` — Agendamento de pagamentos / DDA | **Fora de escopo.** Saída de dinheiro; o produto é cobrança (entrada), e a [régua de escopo](../development/roadmap-providers.md) exclui pagamento em qualquer provider |
| `P_04_01`…`P_04_04` — Gerenciamento de location | **Fora de escopo.** O gateway *consome* a `location` que a cob devolve; não gerencia o recurso |
| `P_03_02` — Revisar cobranças dentro do lote | **Lacuna de superfície, não de escopo.** `provider.revisar_lote_cobv` existe; o router não expõe |
| `P_05_01`, `P_05_03`, `P_05_04` — Pix recebido e devolução | **Limite do ambiente**, mesma família do `C_05_02`. A conta sandbox nunca recebeu Pix: `GET /pix` responde `200` com lista vazia até em janela de 180 dias, e o único lançamento do extrato é uma tarifa. **Não há como gerar a massa por API** — a de Agendamento de Pagamentos do C6 não executa pagamento, apenas enfileira para aprovação manual no internet banking. As rotas existem e estão cobertas por `test_pix_recebidos_e_devolucao` |

## O que o sandbox não deixou concluir

Quatro casos foram executados e não fecharam em 2xx. Nenhum é defeito de
integração, e isso precisa estar dito no e-mail ao banco:

| Caso | O que aconteceu |
|---|---|
| `C_05_02` — Evento de pagamento de link | **`403` do próprio banco.** O evento nasce do pagamento na página hospedada do C6, e essa página não abre: `payment-h.c6pay.com.br` responde `403` (Cloudflare, *"Sorry, you have been blocked"*) na URL do checkout e na raiz do domínio, de navegador e de `curl`. A API cria o link e o banco devolve a URL — falta o acesso à página. **Não é `N/A`**: o caso está no escopo e implementado (`checkout.atualizado` → `liquidado`, com teste), e marcá-lo "não se aplica" esconderia um defeito do C6 atrás da nossa declaração de escopo |
| `P_03_01`, `P_03_03`, `P_03_04` — lote de cobv | `502` do próprio banco, em `PUT` e em `GET`. Isolado: o `id` do lote foi testado em 20, 26, 30 e 35 caracteres (a spec exige `[a-zA-Z0-9]{26,35}`) e o payload confere com o exemplo `loteCobVBody1` da própria documentação; `/cob`, `/cobv` e `/pix` respondem `200` na mesma conexão, mesmo token e mesma janela. O corpo do `502` é HTML de Cloudflare, e a spec do C6 nem documenta `502` — só `400`, `403`, `404` e `503` |

**A recusa também é evidência.** A operação foi tentada e o banco respondeu; o
corpo do erro está no documento, não um campo vazio.

`B_04`, `B_08` e `BP_04` — alterar, baixar e cancelar — dependem de a CIP ter
aprovado o registro e **oscilam entre execuções**: numa rodada responderam
`409`/*"já existe uma requisição à CIP sujeita a aprovação"* mesmo após ~25 min
de re-tentativa, na seguinte fecharam em 2xx. É o assíncrono do banco, descrito
em [c6-rest.md](../development/c6-rest.md#particularidades-do-banco--observadas-na-execução);
o roteiro re-tenta e ainda faz uma repescagem no fim, mas quem decide é a CIP.

## Defeito no formulário v3.0 do banco

Vale mencionar ao C6 — duas tabelas carregam o identificador da seção anterior,
e o bloco de checkout escreve os sub-passos sem separador:

| Tabela | Rótulo no formulário | O que a tabela realmente é |
|---|---|---|
| 75 | `P_02_03` | *Consultar lote específico* → `P_03_03` (seção **P_03 – Cobrança Pix em lote**) |
| 85 | `P_02_04` | *Desvincular cobrança de uma location* → `P_04_04` (seção **P_04 – Gerenciamento de location**) |
| 45, 47 | `C_0501`, `C_0502` | `C_05_01` e `C_05_02` — sem o `_`, os dois viram `C_05` e colidem |

O preenchedor corrige as duas primeiras **por índice**, que é o que identifica a
tabela de fato, e continua avisando se aparecer outra repetição. Casar só pelo
identificador faria a segunda tabela disputar a evidência da primeira — e ficar
vazia sem explicação.

## O que reportar ao C6

Três coisas dependem do banco, e nenhuma tem contorno do nosso lado:

1. **`/v2/pix/lotecobv` responde `502`** em `PUT` e em `GET`, enquanto `/cob`,
   `/cobv` e `/pix` respondem `200` na mesma conexão. A spec do C6 nem documenta
   `502`.
2. **A página de pagamento do checkout não abre** — `payment-h.c6pay.com.br`
   devolve `403` do Cloudflare. Sem ela não há como pagar um link, e `C_05_02`
   fica sem gatilho possível.
3. **Os identificadores repetidos no formulário v3.0**, na tabela acima.

E uma pergunta: **como injetar um Pix recebido na conta sandbox?** Sem isso
`P_05_01/03/04` não têm `e2eid` para exercitar, e a API de Agendamento de
Pagamentos não resolve — ela não executa pagamento, só enfileira para aprovação
manual no internet banking.

## Depois da aprovação

- [ ] `C6_REGISTERED_READY=true`
- [ ] `billing_scheme` 21 → **15**
- [ ] `C6_BASE_URL` de produção (`baas-api.c6bank.info`)
- [ ] Credenciais de produção no cofre (`VAULT__<tenant>__c6__*`)
- [ ] Reexecutar o smoke da coleção Postman contra produção

> Conta **PJ** no mesmo CNPJ inscrito no Portal do Desenvolvedor. MEI não é
> elegível.
