# Homologação — artefatos e como reproduzir

Esta pasta guarda o **resultado** da homologação dos três bancos, não o
processo. O formulário é do C6; o que é nosso são as decisões de escopo e a
evidência. Sicoob e Inter seguem o mesmo roteiro, sem formulário do banco.

| Arquivo | O que é |
|---|---|
| *(formulário preenchido)* | **Não é versionado**: é documento de envio ao banco, gerado por `preencher_roteiro_c6.py` a partir da evidência JSON — regenerável a qualquer momento |
| `evidencia-sandbox-c6.json` | A evidência crua do C6 — status HTTP e corpo de cada caso, como o banco devolveu |
| `evidencia-sandbox-sicoob.json` | A evidência crua do Sicoob — **14 casos em 2xx, 1 recusa, 5 ausentes** contra um mock de schema que não valida credencial (veja a ressalva abaixo) |
| `evidencia-sandbox-inter.json` | A evidência crua do Banco Inter — **16 casos, zero falhas**, com o banco ecoando o que foi enviado |
| `evidencia-open-finance.json` | O que os quatro bancos publicam no **Diretório de Participantes** do Open Finance (fonte pública, sem credencial) — leitura em [open-finance.md](../development/open-finance.md) |

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

Última execução (**26/08/2026**): **14 casos em 2xx, 5 ausentes, 1 recusa** — a
recusa é a emissão, que no mock responde `400` enlatado com `"string"` no lugar
da mensagem. Comparada caso a caso com a de 04/08, **zero diferenças**, inclusive
o corpo enlatado do `B_01`.

### O sandbox não valida credencial — medido, não suposto

Reproduzir esta execução não exige credencial do portal, e isso foi verificado
com quatro chamadas diretas ao mock:

| O que foi mandado | Resposta |
|---|---|
| `client_id` do portal + `Authorization` qualquer | **200** |
| `client_id` **inventado** + `Authorization` qualquer | **200** |
| `client_id` do portal, **sem** `Authorization` | `401` |
| **Sem** `client_id`, com `Authorization` | `401` |

O mock exige a **presença** dos dois headers e não olha o conteúdo de nenhum —
aceita até texto que não é UUID. Não há autenticação: é um portão de forma.

Isso estreita ainda mais o que a evidência do Sicoob atesta. Já estava dito que
ela vale roteamento, contrato e normalização, e não comportamento do banco;
agora está medido que **nem a credencial é verificada**. Por isso esta execução
usou `sandbox-do-sicoob-nao-valida-credencial` no lugar do `client_id`: inventar
um valor com cara de credencial num artefato versionado sugeriria que alguma
credencial estava em uso, e não estava. Com o par oficial do portal o resultado
é idêntico — o ambiente acabou de demonstrar que é.

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
python scripts/preencher_roteiro_c6.py evidencia.json --roteiro "<docx do portal>" \
    --cnpj "..." --empresa "..." --software "..." \
    --responsavel "..." --email "..." --telefone "..."
```

Os seis argumentos finais preenchem a tabela **DADOS DA ORGANIZAÇÃO** — são
cadastro, não evidência, por isso entram na linha de comando. Os checkboxes de
"APIs que você testará" saem da própria evidência: API com caso executado é
marcada; API cujos casos são todos fora de escopo fica desmarcada. Corpo de
resposta acima de 4.000 caracteres entra cortado nos 4.000 com a marcação
`[TRUNCADO — …]` — a evidência JSON guarda o corpo inteiro.

Aceita identificadores de caso como argumento para rodar só um pedaço —
`homologacao_c6.py B_01 B_05`.

Sicoob e Inter, mesmo molde e mesmos argumentos — o que muda é a credencial:

```bash
# O mock não valida nenhum dos dois — exige só que os headers existam (ver
# "O sandbox não valida credencial", acima). Qualquer texto roda.
export SICOOB_SANDBOX_CLIENT_ID=... SICOOB_SANDBOX_TOKEN=...
PYTHONPATH=gateway python scripts/homologacao_sicoob.py --json > evidencia-sicoob.json

export INTER_SANDBOX_CLIENT_ID=... INTER_SANDBOX_CLIENT_SECRET=...
export INTER_SANDBOX_CERT_PEM="$(cat Sandbox_InterAPI_Certificado.crt)"
export INTER_SANDBOX_KEY_PEM="$(cat Sandbox_InterAPI_Chave.key)"
export INTER_SANDBOX_CHAVE_PIX=...   # sem ela, P_01/P_02/P_05 saem como AUSENTE
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

Última execução: **26/08/2026**, contra o sandbox.

| | Tabelas |
|---|---|
| Retorno `2xx` do banco | **50** |
| Recusa do banco, com o corpo do erro | **5** |
| Marcadas `N/A` com o motivo | **13** |
| Em branco | **0** |
| Total do formulário | **68** |

> **`P_03_02` saiu dos `N/A` e a próxima execução respondeu.** Ele era ausente
> porque `revisar_lote_cobv` existia no mixin BACEN e o router não expunha; a
> rota `PATCH /pix/lote/{id}` fechou a lacuna. Executado agora, o banco responde
> **`502`** — o mesmo dos outros três casos do lote de cobv. É por isso que as
> recusas passaram de 4 para 5 sem nenhuma regressão: um `N/A` virou recusa
> medida, que é estritamente mais evidência do que "não se aplica".

> **Comparação caso a caso com 04/08: uma diferença só**, a do `P_03_02` acima.
> Vinte e dois dias, nenhuma regressão — e `B_04`, `B_08` e `BP_04`, que dependem
> da CIP e oscilam entre rodadas, fecharam em 2xx desta vez.

> O formulário tem **68** tabelas de retorno, não 51. Ele usa duas formas —
> Pix Automático e `BP_01` trazem um subtítulo entre o título e o cabeçalho — e
> o preenchedor lia só a primeira, deixando 17 tabelas fora da conta **e** em
> branco. Corrigido; a contagem acima é sobre o formulário inteiro.

O código de criação é `201` com `Location`, salvo o lote de cobv, que é `202` —
o banco responde *"lote solicitado para criação"*, e o lote é enfileirado, não
criado.

## Resultado da execução — Banco Inter

**16 casos, zero falhas, 3 ausentes.** O sandbox tem comportamento real: a sonda
de eco confirmou que `seuNumero`, valor e vencimento voltam idênticos ao que foi
enviado.

Os três ausentes, e o motivo de cada um:

| Caso | Por quê |
|---|---|
| `PG_01` — pagamentos | **Fora de escopo.** Saída de dinheiro; a [régua de escopo](../development/roadmap-providers.md) exclui pagamento em qualquer provider |
| `PA_01` — Pix Automático | **Confirmado no banco, mas sem massa.** A spec OpenAPI do Inter publica as rotas na mesma base `/pix/v2` e as 17 chamadas do dialeto batem uma a uma ([inventário](evidencia-pix-automatico-inter.json)). O que barra a execução é o **BACEN**: só CNPJ com 6+ meses de atividade cria recorrência |
| `SA_01` — saldo | Rota não exposta pelo gateway; o extrato cobre o caso de uso |

Três defeitos nossos só apareceram aqui, contra o banco de verdade: a emissão
voltava `502` por causa da **barra final** no path (o Inter responde `307` onde
o C6 exige a barra); o default `formasRecebimento: BOLETO` **suprimia o QR Pix**
— o híbrido é `BOLETO_PIX`, hoje o default; e `service=COBRANCA`, a palavra que a
documentação do Inter usa para o webhook de boleto, tinha passado a responder
`422` (ver abaixo).

### A coleção de cobranças, contra o banco (`C_01`…`C_03`)

Os três casos novos existem porque a coleção só podia ser provada com corpo real
do banco:

| Caso | O que prova |
|---|---|
| `C_01` — coleção | Filtra por **emissão**, não por vencimento: o boleto do `B_01` vence em 30 dias, e uma janela recente por vencimento voltaria vazia — o caso passaria sem provar nada. Por emissão, o título recém-criado aparece, e o relatório grava `achou_o_do_b01` |
| `C_02` — sumário | O Inter devolve **array na raiz**. Com esse corpo a rota respondia `500` antes do embrulho em `sumario` — defeito que nenhum teste com dado inventado teria mostrado |
| `C_03` — filtro inválido | `situacao=ABERTO` (o Inter chama de `A_RECEBER`) para no gateway com `422` listando os aceitos, **sem gastar ida ao banco**. É o único caso cujo sucesso é uma recusa: o runner o compara com o status esperado, não com 2xx |

### Uma regressão que a reexecução pegou

`B_05`/`B_06` — cadastro e consulta do webhook de cobrança — passaram em
**04/08** e responderam `422` nesta execução. Não foi o banco: entre as duas
datas o campo `service` deixou de ser texto livre e virou enum, e o enum só
tinha o vocabulário do **C6** (`BANK_SLIP`, `CHECKOUT`). `COBRANCA`, a palavra
do Inter, passou a ser recusada por uma rota que diz servir os dois bancos.

É a mesma família do `BC-044` (que saiu de `422` para `424` ao trocar dict livre
por schema): **apertar validação sem reexecutar o roteiro estreita o contrato em
silêncio.** `COBRANCA` voltou a valer, como sinônimo — e o provider do C6 traduz
para a palavra dele antes de falar com o banco, senão o alias viraria `400` lá
na frente.

> **O certificado do sandbox expira em 03/09/2026.** Vencido, toda chamada falha
> na autenticação e responde `424` — que é o diagnóstico certo, mas convém não
> descobrir pelo alerta do cliente.

## Escopo — o que foi marcado e o que não foi

O banco manda **não marcar** o checkbox de API que a aplicação não usa. Das nove,
sete estão marcadas. As 13 tabelas `N/A` se dividem em três motivos, e a
diferença importa — só o primeiro é decisão de produto:

| Caso | Motivo |
|---|---|
| `AP_01`…`AP_06` — Agendamento de pagamentos / DDA | **Fora de escopo.** Saída de dinheiro; o produto é cobrança (entrada), e a [régua de escopo](../development/roadmap-providers.md) exclui pagamento em qualquer provider |
| `P_04_01`…`P_04_04` — Gerenciamento de location | **Fora de escopo.** O gateway *consome* a `location` que a cob devolve; não gerencia o recurso |
| `P_05_01`, `P_05_03`, `P_05_04` — Pix recebido e devolução | **Limite do ambiente**, mesma família do `C_05_02`. A conta sandbox nunca recebeu Pix: `GET /pix` responde `200` com lista vazia até em janela de 180 dias, e o único lançamento do extrato é uma tarifa. **Não há como gerar a massa por API** — a de Agendamento de Pagamentos do C6 não executa pagamento, apenas enfileira para aprovação manual no internet banking. As rotas existem e estão cobertas por `test_pix_recebidos_e_devolucao` |

## O que o sandbox não deixou concluir

Cinco casos foram executados e não fecharam em 2xx. Nenhum é defeito de
integração, e isso precisa estar dito no e-mail ao banco:

| Caso | O que aconteceu |
|---|---|
| `C_05_02` — Evento de pagamento de link | **`403` do próprio banco.** O evento nasce do pagamento na página hospedada do C6, e essa página não abre: `payment-h.c6pay.com.br` responde `403` (Cloudflare, *"Sorry, you have been blocked"*) na URL do checkout e na raiz do domínio, de navegador e de `curl`. A API cria o link e o banco devolve a URL — falta o acesso à página. **Não é `N/A`**: o caso está no escopo e implementado (`checkout.atualizado` → `liquidado`, com teste), e marcá-lo "não se aplica" esconderia um defeito do C6 atrás da nossa declaração de escopo |
| `P_03_01`…`P_03_04` — lote de cobv | `502` do próprio banco, em `PUT`, `GET` e `PATCH`. Isolado: o `id` do lote foi testado em 20, 26, 30 e 35 caracteres (a spec exige `[a-zA-Z0-9]{26,35}`) e o payload confere com o exemplo `loteCobVBody1` da própria documentação; `/cob`, `/cobv` e `/pix` respondem `200` na mesma conexão, mesmo token e mesma janela. O corpo do `502` é HTML de Cloudflare, e a spec do C6 nem documenta `502` — só `400`, `403`, `404` e `503`. **`P_03_02` entrou nesta família na reexecução de 26/08**: em 04/08 ele ainda era ausente (a rota de revisão do lote não existia; veio com o `BC-088`), e agora que existe recebe o mesmo `502` dos irmãos — o defeito é do recurso inteiro, não de um verbo |

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

## Re-sondar os casos não finalizados

O C6 avisou que está ajustando o sandbox. Como sete dos oito casos abertos
dependem do banco ou do ambiente — não há o que corrigir do nosso lado, só
descobrir **quando** destravam —, o retrabalho é reexecutar só esses casos
quando o banco disser que mexeu:

```bash
# com as credenciais do sandbox já exportadas (ver "Reproduzir", acima)
PYTHONPATH=gateway python scripts/homologacao_c6.py --json \
  C_01 P_03_01 P_03_02 P_03_03 P_03_04 \
  P_05_02 P_05_01 P_05_03 P_05_04 C_05_02 \
  > "sonda-$(date -u +%F).json"
```

`C_01` e `P_05_02` não são o que se mede: são **pré-condição**. `C_01` cria o
checkout que `C_05_02` sonda e `P_05_02` popula o `e2eid` das consultas de Pix
recebido — sem eles os N/F falhariam por falta de dado nosso, que é o oposto do
que se quer observar. Rodar o roteiro completo a cada tentativa sujaria o
sandbox com dezenas de boletos por nada.

Vale a mesma janela de sempre — **seg-sex, 7h-23h BRT**. Fora dela *todo* caso
falha na autenticação, e uma rodada inteira em vermelho por horário não diz nada
sobre o que se está observando.

Compare com o estado de **26/08** na tabela acima: `502` em `P_03_01`…`P_03_04`,
`403` em `C_05_02`, e massa ausente em `P_05_01`, `P_05_03` e `P_05_04`. Qualquer
um desses virando 2xx é a notícia.

A reexecução de 26/08 fechou em **50 casos em 2xx, 5 falhas, 13 ausentes** — e a
comparação caso a caso com 04/08 acusou **uma única diferença**, o `P_03_02`
descrito acima. Nenhuma regressão em 22 dias, e os três casos que dependem da CIP
(`B_04`, `B_08`, `BP_04`) fecharam em 2xx desta vez.

Quando algo destravar: rode o roteiro **completo**, regenere o `.docx` e
atualize os números da seção acima — eles são daquela rodada e não se atualizam
sozinhos.

> **Isto não é agendado, e é de propósito.** Um cron de Actions só dispara a
> partir do branch default, e homologação não sobe para a `main`. Um `schedule:`
> num branch de HML não executa nunca — e uma sonda que promete cadência sem
> entregar é pior do que nenhuma: daqui a uma semana alguém conclui "nada mudou
> no sandbox" a partir de zero execução.

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
