# Changelog

Mudanças **do produto** — o que muda para quem consome a API ou roda a imagem.

Mudança de **processo** não entra aqui: CI, workflows, templates de issue e PR,
scripts de release, configuração de deploy e convenção de branches vivem no
histórico do git e nos próprios arquivos. O critério é uma pergunta só: *isso
muda alguma coisa para quem usa o serviço?* Se a resposta for não, fica fora.

Entradas **curtas**: o que mudou e qual é o comportamento novo, em uma a três
linhas. Diagnóstico, causa e medição pertencem ao commit e ao PR — quem lê o
changelog quer saber se precisa mexer na integração, não como o defeito surgiu.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- **`GET /cobrancas` e `GET /cobrancas/sumario` — a coleção de boletos do
  período.** Antes só se consultava um título por vez: quem queria a lista
  guardava os ids da emissão ou caía no arquivo de retorno. Filtros por
  situação, tipo, pagador e `seu_numero`; janela máxima de **90 dias**; `pagina`
  começa em 1, como no resto da API. O sumário devolve os totais por situação em
  `sumario`. Hoje só o **Inter** publica as duas — nos demais bancos a rota
  responde `422` dizendo quem publica.
- **`ambiente_confere` no `/credenciais` — certificado do ambiente errado, dito
  na hora do cadastro.** Os bancos carimbam o host no CN (`baas-api-sandbox` ×
  `baas-api`) e a API agora compara com a base para onde está apontada. Sem isso,
  o desencontro só aparecia no primeiro handshake, como `403 mTLS` — que se lê
  como credencial inválida e manda conferir `client_id` e `secret`, que estão
  certos. Vêm junto `host` e `base_em_uso`; `null` quando o banco não carimba
  host (o CN do Inter é só o nome da aplicação).
- **`GET /credenciais` — quando a integração para de funcionar.** O certificado
  mTLS dos bancos vale um ano e não tem renovação in-place: vence e toda chamada
  falha no handshake, de uma vez. A rota diz a validade, os dias restantes, o
  titular (é o **host** dentro do CN que separa sandbox de produção) e se a
  chave privada é a **deste** certificado — o erro clássico da troca. Sem
  segredo: certificado, chave e `client_secret` não saem, e o token volta
  mascarado. O mesmo bloco vem no `POST /credenciais`.
- **`X-Remessa-Avisos` em `POST /api/remessa`.** Header presente só quando há
  aviso: diz o que o layout **não gravou** do que você mandou. `carteira` está
  na base de toda remessa, mas oito layouts não têm esse campo — quem monta a
  remessa com o mesmo dicionário do boleto acreditava ter escolhido a carteira,
  e o arquivo saía com a do padrão. O arquivo está correto; faltava o sinal.
- **Inter (077) é o 19º banco offline.** A engine passou a ter o layout, então
  `provider=off&banco=inter` emite boleto, remessa e retorno CNAB 400 — só a
  **carteira 110** (na 112 quem numera é o banco). Antes o caminho `off` do Inter
  respondia `422`, porque cair em outro banco registraria a cobrança no lugar
  errado. Ele passa a existir nos dois caminhos, como C6, Sicoob e Itaú.
- **`pix_vinculado` na resposta** de `/cobranca`, `/api/boleto/data`,
  `/api/render/boleto` e `/api/render/fatura`: diz se o QR do boleto **liquida o
  título** (`true`) ou se é um QR avulso que só credita a chave (`false`).
- **`pix_copia_cola` e `pix_observacao` no `data` do boleto.** Mande em
  `pix_copia_cola` o EMV que o banco devolveu ao registrar e o PDF sai com o QR
  que dá baixa — em qualquer banco, inclusive nos que a engine não sabe montar
  BR Code. Tem precedência sobre `chave_pix`.
- **`codigo_barras` e `linha_digitavel` no `data` do boleto — conferidos, não
  usados.** Mande o que o banco já atribuiu ao título e a API responde `400` se
  o cálculo local discordar, em vez de imprimir um boleto que não corresponde ao
  título registrado. Serve ao ciclo `on`→`off`: no **Inter** quem numera é o
  banco, então renderizar offline com o seu próprio número produz outro título.
- **`layout_generico` em cada item de `POST /api/retorno`:** `true` avisa que o
  arquivo foi lido com um layout de reserva, e não com o mapa do banco — os
  campos podem ter vindo de outras posições. Antes esse aviso era engolido.

### Corrigido
- **`service=COBRANCA` voltou a ser aceito em `/config/webhook-banco`.** O campo
  virou enum com o vocabulário do C6 (`BANK_SLIP`, `CHECKOUT`) e passou a recusar
  com `422` a palavra que a documentação do **Inter** usa para o webhook de
  boleto — numa rota que atende os dois bancos. `COBRANCA` vale como sinônimo; no
  C6 é traduzido antes de sair, para o alias não virar `400` do banco.
- **Pix Automático do Inter: confirmado e ligado.** A spec OpenAPI do banco usa
  a mesma base `/pix/v2` e traz `rec`, `solicrec`, `cobr`, `locrec` e os dois
  webhooks — as 17 chamadas do nosso dialeto batem uma a uma. O token do Inter
  **não pedia nenhum** dos escopos do recurso, o que daria `403` com os paths
  certos; os doze entraram. ⚠️ Restrição do BACEN: só para **CNPJ com 6+ meses
  de atividade**.
- **`capacidades_nao_confirmadas` no `GET /bancos`.** Capacidade cujo dialeto o
  provider herda de um mixin e que ninguém confirmou naquele banco some de
  `capacidades` e aparece aqui, com a variável que a libera — e a rota responde
  `422` dizendo *não foi confirmado*, diferente de *não oferece*. Hoje sai vazio
  para todos; existe para o próximo mixin herdado por um banco que não o exponha
  não virar promessa sem lastro.
- ⚠️ **O QR montado de `chave_pix` não é Bolepix.** Ele é **estático**: credita
  a chave, mas o banco não sabe que aquele PIX quitou o título, que fica **em
  aberto** — risco de segunda cobrança ou de protesto de boleto já pago. O
  comportamento não muda; a documentação parava de chamá-lo do que ele não é, e
  `pix_vinculado` diz qual dos dois saiu no papel.
- **A ocorrência do retorno saía no vocabulário errado.** O `40` é *baixa por
  ter sido liquidado* no mapa geral e *baixa de título protestado* no **Safra**;
  o `07` é *liquidação parcial* no geral e *cancelado* no **Inter**. Agora a
  descrição vem do banco do arquivo.
- ⚠️ **`POST /api/retorno` recusa arquivo de outro banco.** O `bank` era exigido
  e **nunca lido**: subir o retorno errado devolvia `200` com campos lidos pelo
  layout de outro banco. Agora divergir do header do arquivo responde `400`.
- ⚠️ **Encargo sem posição no layout responde `400` em vez de sumir.**
  `valor_multa` e `percentual_desconto` passaram a ser aceitos pela engine, mas
  só o **Inter** os grava; nos demais entravam e sumiam, e o título ia ao banco
  sem o encargo pedido. `percentual_mora` segue válido no CNAB 240 e recusado
  no 400 (exceto Inter). O erro diz quem grava o campo e qual é a alternativa.
- **C6 aceita o certificado no formato que o banco entrega.** O C6 manda o par
  PEM (`.crt` + `.key`); o provider só repassava `pfx_base64`, então o material
  do banco era inutilizável e obrigava um `openssl pkcs12 -export` antes da
  primeira chamada. O PFX continua valendo. O esquema em `GET /bancos` passou a
  citar `cert_pem`/`key_pem` — ele prometia menos do que a rota aceita.
- **Sicoob: a carteira `09` gerava um boleto diferente da `9`.** São a mesma
  carteira, e o campo livre ficava com o primeiro caractere — gravava `0`, que
  não existe no Sicoob. O boleto saía estruturalmente válido, então nenhuma
  conferência de estrutura pegava. Corrigido na engine; a API normaliza enquanto
  o pin aceitar a versão com o defeito.
- **Carteira `CSB` do HSBC saiu**: o campo livre dela montava 27 posições onde
  cabem 25 — nunca produziu boleto válido. Resta a `CNR`.

### Alterado
- **A faixa FEBRABAN não vai para o boleto.** `desconto_abatimento`,
  `outras_deducoes`, `mora_multa`, `outros_acrescimos` e `valor_cobrado` são
  **aceitos e ignorados** na emissão — o PDF sai com a faixa em branco, sempre.
  Desconto, multa e juros dependem da **data do pagamento**, e quem preenche ali
  é o caixa, no ato. A **regra** vai em `instrucoes` (texto impresso) e os
  **valores** na remessa CNAB (`POST /api/remessa`), que é o arquivo que o banco
  processa para calcular na data em que o título for pago.
- ⚠️ **Campo desconhecido em `data` responde `400`.** Era descartado em
  silêncio: `numero_docmento` produzia um boleto sem número de documento, com
  `200`, e nada na resposta acusava a falta. O erro nomeia o campo e sugere o
  parecido. `account_config` continua sendo blob por provider — lá o que não se
  aplica ao banco é ignorado, como sempre foi. `BOLETO_ACEITA_CAMPO_DESCONHECIDO=1`
  devolve o comportamento antigo; sai na 3.0.0.
- ⚠️ **A mesma conta escrita nas duas grafias responde `400`.**
  `conta_corrente` e `conta` são o mesmo campo: com valores diferentes, a ordem
  do dicionário decidia qual ia para o boleto.
- ⚠️ **Engine `pyCobrança` atualizada — o boleto `moderno` tem desenho novo.**
  Chips de Vencimento/Valor/Nosso Número com mais contraste, faixa de marca,
  grade alinhada e linha de corte contínua. Junto vêm correções de layout que
  produziam PDF válido em bytes e errado no papel: texto longo saindo da
  página, primeiro dígito da linha digitável cortado no `classico`, nome do
  banco por cima do código-DV e encargo por cima do rótulo.
- Retorno CNAB é lido direto dos bytes do upload: o arquivo do banco — que traz
  nome, documento e valor de cada pagador — não passa mais por arquivo
  temporário em disco.

### Corrigido
- **Credencial incompleta responde `424`, não `500`.** Os providers online liam
  `credentials["client_id"]` direto: credencial presente sem a chave levantava
  `KeyError` cru, que escapava dos handlers. Sete rotas Pix e de webhook
  respondiam erro de servidor por um dado que faltava no cadastro do chamador.
  O `424` agora diz **qual** chave falta.
- **`POST /carne` não recusa mais por chave do `account_config`.** O carnê
  resolve o banco pelo `provider`/`banco` e não o repete no blob; sem o banco, o
  filtro do `account_config` desligava e o blob chegava cru na fronteira
  estrita.
- **`txid` longo no Bolepix responde `400`, não `500`.** O `txid` do Bolepix vai
  dentro do BR Code e aceita até 25 alfanuméricos; o do Pix cob/cobv exige de 26
  a 35 — copiar um para o outro derrubava a requisição com erro de servidor. O
  campo ganhou limite e explicação no schema.
- ⚠️ **O endereço do pagador chega inteiro ao boleto.** Bairro, cidade, UF e
  CEP eram enviados como campos próprios que o título **não tem**: o construtor
  descartava os quatro, um a um, em silêncio. O boleto saía com rua e número e
  mais nada. Agora vão na linha de endereço, como um boleto de verdade imprime.
- **`pix_copia_cola` passa a vir no caminho offline.** O campo já existia em
  `POST /cobranca` e era preenchido por C6, Inter e Sicoob; com `provider=off`
  voltava `null` mesmo com o QR Bolepix impresso no PDF. Agora sai também em
  `POST /api/render/boleto`, `/api/render/fatura`, `GET /api/boleto/data` e no
  header `X-Pix-Copia-Cola` do PDF binário. `null` continua quando o payload
  não traz `chave_pix`.
- **`POST /api/render/carne` devolve `itens`** — uma entrada por parcela, com
  `nosso_numero`, `linha_digitavel`, `codigo_barras` e `item_id`. Eram
  calculados e descartados: só o PDF voltava, e quem gerava um carnê não tinha
  como registrar nem conciliar as parcelas sem refazer a conta por fora.
- ⚠️ **A faixa de marca do boleto passa a sair no papel.** `logo_empresa`,
  `cor_marca`, `marca_dagua`, `rodape_contato`, `parcela_atual` e
  `total_parcelas` eram aceitos e descartados: o boleto saía sem marca, com
  `200`. `logo_empresa` é o **texto** da marca (não caminho de arquivo) e
  `cor_marca` aceita `RRGGBB` com ou sem `#`, e o nome ao lado do selo é o
  `cedente`. Só no modelo `moderno` e na fatura — pedir no `classico` ou no
  carnê agora responde `400`.
- ⚠️ **`instrucao1`..`instrucao6` passam a ser impressas.** Estavam
  documentadas e nenhuma chegava ao boleto. Viram o bloco `instrucoes`, em
  ordem; enviar as duas formas no mesmo payload responde `400`.
- ⚠️ **O limite de instruções agora é medido na engine, por modelo.** Era fixo
  em 7 linhas × 100 caracteres. A moldura muda de tamanho conforme o modelo e
  conforme haja Bolepix (com o QR ao lado ela encolhe ~¼), então texto que
  passava do limite real era truncado sem erro. Linha ou coluna a mais é
  recusada, com o número exato na mensagem.
- `fonte_ttf` responde **`400`**: nunca houve suporte, nem aqui nem na engine.

### Adicionado
- **Nove campos específicos de banco no `BoletoData`**: `data_documento`,
  `digito_conta`, `digito_agencia`, `digito_convenio`, `variacao`,
  `incremento`, `portfolio`, `posto` e `byte_idt`. Já eram aceitos e não
  estavam documentados — no Citibank, sem `portfolio`, o código de barras sai
  com o campo livre zerado, válido em estrutura e errado no destino.
- `instrucoes` e `demonstrativo` documentados no `BoletoData`: são os campos
  que a engine realmente desenha.
- `GET /bancos` anuncia mais três capacidades, que **discriminam**:
  `pix_consulta` (o Itaú não tem `GET /pix/{txid}`), `conciliacao_transacoes`
  (só o C6) e `webhook_entrada` (sem ela, `POST /webhooks/{banco}` não entende
  a notificação daquele banco). As rotas existiam e eram invisíveis no catálogo.
- **Swagger publicado no site**, gerado do código e sem depender do serviço no
  ar: [gateway](https://maxwbh.github.io/cobranca-api/swagger/) e
  [offline](https://maxwbh.github.io/cobranca-api/swagger/offline.html).
- Boleto sai com o **logo do banco emissor** no cabeçalho, por padrão, em todos
  os caminhos (avulso, lote, carnê e fatura). Citibank não tem marca empacotada
  e segue com a sigla; `logo` em `data` continua sobrepondo.
- **`banco`** em todas as rotas e corpos: `provider` passa a ser o **caminho**
  (`on` = API do banco · `off` = engine pyCobrança) e `banco` a instituição
  (`c6`, `sicoob`, `itau`, `banco_brasil`…). O nome do banco no `provider`
  (`provider=c6`) segue valendo como apelido e sai na 3.0.0.
- `GET /bancos` diz o que **esta instalação** faz com cada banco:
  `registrado_pronto`, `fallback_offline`, `caminho_efetivo` e a flag que liga.

### Alterado
- `COBRANCA_ERRO_HTTP=1` faz `POST /cobranca` responder **`422`** quando a engine
  recusa os dados, em vez do `201` com `status: "erro"` — mesmo corpo, só o
  código muda. Default segue `201` nesta versão; **na 3.0.0 o `422` vira padrão**.
- Credenciais são guardadas e procuradas pelo **banco**, não pelo `provider`.
  Token emitido antes continua valendo; ao cadastrar com `provider=on`, informe
  o `banco`.
- ⚠️ **`/docs`, `/api/docs` e `/redoc` não dependem mais da internet.** Os
  renderizadores vão na imagem e são servidos em `/swagger-ui`; antes vinham de
  CDN, e num deploy sem essa saída as páginas abriam em branco. O `/redoc` ganha
  o tema da plataforma (vinha com o favicon do FastAPI). A imagem cresce ~2,5 MB.
- ⚠️ **Parâmetro `true`/`false` fora do enum passa a ser `400`.** A spec já
  declarava `enum: ['true','false']` para `include_data`, `pix` e
  `somente_creditos`, e o código aceitava só `"true"`, tratando todo o resto
  como `false`: `include_data=1` respondia `200` com o **PDF binário** quando o
  chamador pediu JSON.
- ⚠️ **As quatro rotas `/api/*` de upload ganham teto** (`UPLOAD_MAX_BYTES`,
  default 10 MB → `413`). O arquivo era lido inteiro para a memória antes de
  qualquer validação. Arquivo vazio também passa a ser recusado pelo nome do
  campo.
- ⚠️ **O `{banco}` de `POST /webhooks/{banco}` virou lista fechada** (`c6`,
  `sicoob`, `inter`, em minúsculas). Slug fora da lista respondia **`200` com
  `event: "ignorado"`** — e `200` faz o banco parar de reentregar, então a
  notificação sumia. `/webhooks/C6` era o caso pior: o token batia (a checagem
  faz `.upper()`) e o evento era descartado assim mesmo. Agora é `422`.
- ⚠️ **`/pix-automatico` confere o pedido antes de ir ao banco.** O `txid` da
  `cobr` passa a seguir o padrão BACEN (`^[a-zA-Z0-9]{26,35}$`, o mesmo da
  cob/cobv), `inicio`/`fim` precisam ser RFC3339 e não invertidos, a `{data}` da
  retentativa precisa ser data, `valor` do ciclo maior que zero e `PATCH` com ao
  menos um campo. **`data_vencimento` no passado é recusada** — cobrança do
  ciclo cinco dias atrás era aceita com `201`.
- ⚠️ **A URL de `/pix-automatico/config/webhooks` passa pela mesma regra do
  `/config/webhook-*`**: https e alcançável de fora. Era repassada crua.
- ⚠️ **Os itens de `/jobs/boletos/{id}/items` ganham faixa e vocabulário.**
  `limite` passa a exigir 1–500 (`limite=-1` devolvia o lote inteiro, com a
  paginação desligada por acidente), `offset` não pode ser negativo e `status`
  só aceita `pending`, `completed` ou `failed` — texto livre respondia `200` com
  lista vazia, que se lê como "nenhum item nesse estado".
- ⚠️ **`POST /bolepix` exige a chave Pix.** Sem ela o banco emitia boleto **sem
  o segmento Pix** e a resposta era `201` — um Bolepix sem QR, que é o que o
  nome promete. Boleto puro continua em `POST /cobranca`.
- ⚠️ **`external_reference_id` do Bolepix é validado** (`^[A-Z0-9]{26}$`), no
  corpo e no caminho das consultas. O padrão estava escrito em três lugares e
  não valia em nenhum. `valor` passa a exigir maior que zero e
  `dias_apos_vencimento`, não negativo.
- ⚠️ **A `url` de `/config/webhook-*` passa a ser conferida.** Quem chama é o
  banco, de fora: exige `https` e destino alcançável. `http://localhost` e IP
  privado eram aceitos com `200` — o cadastro parecia feito e a notificação
  nunca chegava. `WEBHOOK_URL_PERMITE_LOCAL=1` libera para homologação local.
- ⚠️ **`service` em `/config/webhook-banco` virou enum** (`BANK_SLIP` |
  `CHECKOUT`): qualquer texto ia para o banco, `""` inclusive.
- **`PUT /config/webhook-pix` ganhou schema** (`WebhookPixIn`). Era corpo livre:
  o Swagger não descrevia campo nenhum e campo com nome errado passava calado.
- **`GET /extrato` ganha `numero_conta`.** O Sicoob exige a conta na consulta e
  a rota não tinha onde recebê-la: toda chamada ia com `numeroContaCorrente: 0`.
  Omitido, segue `0` — quem já chamava não muda.
- `GET /extrato` confere as datas (`YYYY-MM-DD`, `end_date` não anterior a
  `start_date`) antes de ir ao banco, e a spec passa a dizer que a resposta é
  **crua do banco**, com um exemplo de C6, Sicoob e Inter — os três shapes
  diferem e não há como normalizá-los sem inventar um formato.
- ⚠️ **`GET /conciliacao/*` confere o período antes de ir ao banco.** `start_date`
  e `end_date` passam a ser datas de verdade (`YYYY-MM-DD`), a janela de 60 dias
  do C6 é aplicada e período invertido é `422` — antes o banco respondia lista
  vazia, que quem chama lê como "não houve movimento". `page` ganha mínimo 1 e
  `size` passa a aceitar de 1 a 100 (só tinha teto).
- ⚠️ **`POST /carne` recusa antes de registrar.** Teto de 200 parcelas (`413`),
  parcela duplicada, banco sem layout na engine e dado que a engine não desenha
  agora respondem `4xx` **antes** da primeira ida ao banco — antes o erro vinha
  depois de N boletos já registrados, e a resposta não dizia quais.
- **`bank` no `POST /carne` virou opcional**: o layout vem do `banco`. Enviado e
  divergente, `422` — carnê com a marca de um banco e parcelas registradas em
  outro não é pagável.
- `POST /carne` aceita `Authorization: Bearer bapi_...`, como as demais rotas —
  a rota não lia o header, e o caminho de credencial recomendado não valia nela.
- ⚠️ **`POST /checkout` recusa campo desconhecido no nível de cima do corpo.**
  Só `checkout` recusava; fora dele, `card_number` e `save_card` respondiam
  `201` e sumiam — o chamador concluía que a API tinha aceitado o dado de
  cartão. Corpo com campo fora do envelope agora é `422`.
- **`Idempotency-Key` do `/checkout` passa a considerar `provider` e `banco`.**
  A mesma chave apontada para outro banco devolvia o link do primeiro sem
  chamar o segundo; agora é `422`, como qualquer outro pedido diferente.
- `GET /bancos` e `GET /health` passam a **descrever a própria resposta** na
  spec: as duas respondiam "objeto qualquer", sem exemplo — e `/bancos` é para
  onde o resto da documentação manda quem precisa da matriz exata.
- `GET /openapi.json` ganha `ETag`: recarregar o `/docs` devolve `304` em vez de
  324 KB — o `/api/openapi.json` já fazia isso.
- `GET /api/openapi.json` responde em **~5 ms** (eram ~150 ms: o YAML era lido e
  parseado a cada chamada). Com `ETag`, recarregar o Swagger devolve `304`.
- Doc offline sem o arquivo `docs/openapi.yaml` responde **503 dizendo onde ele
  foi procurado**, em vez de `500` anônimo nas três rotas.

### Corrigido
- **`txid` fora do padrão BACEN ia para o banco.** `[a-zA-Z0-9]{26,35}` era
  citado na mensagem de erro da cobv e não aplicado em lugar nenhum: `"abc"`,
  txid com hífen e txid de 40 caracteres viravam `400` do banco (traduzido em
  `422` com `upstream`). Agora é `422` do contrato, antes da ida à rede, e vale
  para cob, cobv e itens de lote.
- **Três chaves diferentes para a mesma coisa nos erros de `/api/*`**:
  `validation_errors` (remessa), `details` (retorno) e `erro` em português
  (OFX). A canônica é `validation_errors` com `error`, e as antigas seguem
  presentes como alias — quem lê por elas não quebra.
- **Webhook com JSON válido de forma errada respondia `500`.** `"texto"` e
  `[1,2,3]` estouravam no normalizador, e o banco reentregava em loop um payload
  que nunca funcionaria. Corpo `{}` virava evento com todos os campos nulos,
  empurrado ao consumidor assinado. Ambos agora são `422`.
- Os quatro corpos livres de `/pix-automatico` (três `PATCH` e o de webhooks)
  apareciam na spec como "objeto qualquer", sem um campo nem um exemplo. O dict
  segue livre — o `PATCH` do BACEN é subconjunto variável por jornada — mas
  agora o contrato descreve o que cabe ali.
- **Os links das respostas de `/jobs` não eram seguíveis.** `self`, `items`,
  `files` e os `href` do manifesto — inclusive o do `.zip` consolidado e o do
  push de conclusão — saíam sem `tenant_id`, que as rotas exigem: seguir o que a
  resposta oferecia dava `422`. Agora todos vêm prontos.
- **Item de job além do 500º respondia `404`.** A busca varria um teto fixo, e
  `JOB_MAX_ITENS` é configurável — o item existia e a API afirmava que não.
- `410` (artefato expirado) passa a ser declarado nas cinco rotas de artefato:
  estava no código e fora do contrato.
- **O `external_reference_id` gerado pela API podia não voltar.** O `id` saía só
  da resposta do banco; quando ela não o ecoava, o identificador se perdia e o
  Bolepix ficava inconsultável. Agora volta sempre, e `POST /bolepix` ganha
  `Location`.
- **`/config/webhook-pix` em banco sem Pix respondia `500`** (Itaú, nas três
  rotas). Agora é `422` dizendo quais bancos têm o webhook BACEN por chave.
- **O `422` de capacidade dizia "banco 'on'"** em `/config/webhook-banco` e nas
  quatro rotas de `/bolepix`: a checagem recebia o caminho no lugar da
  instituição. Agora nomeia o banco.
- **`GET /extrato` em banco sem API de conta respondia `500`** (Itaú). Agora é
  `422` apontando para o retorno CNAB ou o OFX.
- **`GET /conciliacao/*` em banco sem a funcionalidade respondia `500`.** A rota
  não checava capacidade, e a checagem que as outras usam não via método apenas
  herdado da classe base — o `NotImplementedError` virava "Internal Server
  Error". Agora é `422` dizendo que a conciliação é do C6, e o critério passou a
  ser o mesmo que o `GET /bancos` publica em `capacidades`.
- ⚠️ **Parcela inválida sumia do carnê em silêncio.** A engine descarta o item
  que não desenha e monta o resto: 12 parcelas entravam, 11 saíam no PDF, e a
  resposta era `201` — o pagador não recebia o boleto de uma parcela que
  continuava sendo cobrada. Agora é `422` com o índice e o motivo de cada uma.
- **`POST /carne` respondia `500` sem corpo JSON** em cinco casos (lista de
  parcelas vazia, `bank` inválido, dado que a engine recusa): "Internal Server
  Error" em 21 bytes, sem dizer o que estava errado.
- **`POST /checkout` não devolvia `Location`.** O `201` trazia o `id` e cabia a
  quem chama montar a URL de consulta, adivinhando que `tenant_id`, `provider` e
  `banco` são obrigatórios lá. Agora vem pronto, como em `/cobranca` e `/pix`.
- **`valor` zero ou negativo virava link de pagamento.** `amount: -10.0` saía
  daqui para o banco; agora é `422` do contrato.
- ⚠️ **`redirect_url` aceitava qualquer esquema, `javascript:` inclusive** — e
  quem publica essa URL é o banco, na página dele, na frente de quem está
  digitando o cartão. Só `http://` e `https://` passam.
- **O `422` de campo recusado devolvia o valor enviado.** `card_number` no corpo
  do checkout voltava inteiro no `input`, e daí para o log de quem chamou. Campo
  fora do schema agora ecoa `"<redigido>"`; o nome do campo continua ali.
- **O `Location` do `201` levava a `422` no modelo novo.** Faltava o `banco`, que
  o segundo eixo passou a exigir — quebrado em `POST /cobranca`, `/pix` e
  `/pix/lote`, e são no apelido legado. Seguir o header agora funciona nos dois.
- ⚠️ **O `422` de validação devolvia as credenciais do banco no corpo.** O
  `input` do Pydantic ecoava `client_secret` e a senha do certificado mTLS de
  volta ao chamador — e daí para log, APM e console do navegador. O envelope
  `credentials` (e o header `X-Bank-Credentials`) agora vem `"<redigido>"`;
  o resto do `input` continua ali, que é o que torna o `422` útil.
- A spec declarava os erros vindos **do banco** e omitia os do **token**: `401`
  aparecia em 4 das 67 operações e `403` em nenhuma, enquanto a API responde os
  dois nas 61 que aceitam `bapi_`. Agora estão declarados onde acontecem.
- ⚠️ **Boleto com `emv`/`pix_label` saía sem QR Pix**, com `200` e sem aviso: a
  engine nunca leu esses campos. Agora respondem `400` apontando para
  `chave_pix`, que é o que gera o QR (nos sete bancos que o suportam). Quem
  enviava `emv` estava entregando boleto sem Pix — troque o campo.
- JSON válido de forma errada (`"texto"`, `123`, objeto onde se espera lista)
  respondia `500` em sete rotas `/api/*`; agora é `400` dizendo qual campo e que
  tipo chegou.
- `POST /api/boleto/multi` ignorava `template` inválido e gerava o lote em
  `moderno`; agora responde `400`, como `GET /api/boleto` já fazia.
- Formato descontinuado (`type=png`) devolvia `validation_errors` como objeto —
  em todo o resto da API é lista plana. Agora é lista nas duas rotas.
- Swagger offline (`/api/docs`) prometia campos que a resposta não tem: sete em
  `/api/boleto/data`, três em `/api/boleto/nosso_numero`, e `fitid`/`name` no OFX
  (o identificador vem em `id`). No resumo do OFX, `total_creditos` e
  `total_debitos` são **somas em reais**, não contagens.
- ⚠️ `POST /api/ofx/parse` marcava **todo lançamento como `credito`** e deixava
  `total_debitos` em `0` — débito entrava na soma de créditos. Quem concilia por
  este endpoint deve reprocessar os totais.
- Boleto de layout que exige campo extra (Sicredi: `data_documento`, `byte_idt`)
  respondia `500`; agora responde `400` nomeando o campo que falta.
- Rotas de `/pix-automatico` num banco que não oferece Pix Automático (Itaú)
  respondiam `500`; agora respondem `422` dizendo quais bancos oferecem.

## [2.2.0] - 2026-08-08

### Adicionado
- **Banco Inter (077)**: boleto registrado, Pix, extrato e webhook
  (`provider=inter`). Sem fallback offline.
- **`POST/GET/DELETE /checkout`**: link de pagamento com cartão no C6, em modo
  link.
- `Idempotency-Key` no `POST /checkout`: mesma chave devolve o mesmo link;
  corpo diferente é `422`.
- Push ao consumidor com fila e re-tentativa (5s a 15min); pendência sinalizada
  em `pendente_de_entrega`.
- Limpeza por idade das tabelas de entrega: dedup 7 dias; fila e idempotência
  30.
- Imagem Docker publicada no GHCR a cada release:
  `docker run -p 8000:8000 ghcr.io/maxwbh/cobranca-api:latest`.
- OpenAPI declara os erros de banco (`404`, `409`, `424`, `429`, `502`, `504`).

### Alterado
- ⚠️ `POST /webhooks/{banco}` exige `WEBHOOK_TOKEN__<BANCO>` e responde `401`
  sem ele; cadastre a URL no banco com `?token=<segredo>`.
  `WEBHOOK_ALLOW_UNAUTHENTICATED=1` mantém o modo antigo na migração.
- `liquidado` só propaga após reconsulta ao banco; o evento ganha `confirmado`.
  Desliga com `WEBHOOK_CONFIRM=0`.
- Notificação repetida do banco responde `200` com `event: "duplicado"`.
  Desliga com `WEBHOOK_DEDUP=0`.
- ⚠️ `POST /cobranca`, `/carne` e `/pix` respondem `201` com `Location`;
  `PUT /pix/lote/{id}` responde `202`.
- Erro no endpoint de token do banco responde `424`, não `422`.
- `POST /credenciais` aceita certificado em PEM, além de PKCS12.

### Corrigido
- Consultar, imprimir e baixar boleto do Sicoob: as rotas de leitura aceitam
  `numero_cliente` e `codigo_modalidade` (antes iam sem conta e falhavam).
- Evento de criação de checkout do C6 chegava como `cobranca.atualizada`.
- Número de endereço com sufixo (`126A`) fazia o C6 recusar o registro.
- Boleto offline levava só o logradouro do pagador para o CNAB.
- Prazo absurdo devolvido pelo banco derrubava a rota Pix com `500`.
- Cancelar boleto no C6 podia transformar sucesso em erro.

## [2.1.1] - 2026-08-01

### Corrigido
- **`POST /bolepix` sem endereço do pagador respondia `502`.** O C6 `/v2` exige
  `city`, `state` e `zip_code`; a API mandava o endereço vazio e traduzia o `400`
  do banco em erro de servidor. Agora recusa com `422` dizendo qual campo falta,
  antes de chamar o banco.
- **Erro do banco virava `502` quase sempre.** Só `401`/`403` escapavam. Agora
  `400`/`422`/`405` do banco respondem `422` (payload do chamador), `404`
  responde `404`, `409` responde `409` e `429` responde `429` repassando
  `Retry-After`. `5xx` e status não mapeado seguem `502`; o corpo original do
  banco continua em `upstream`.

## [2.1.0] - 2026-07-31

### Adicionado
- **`POST /api/render/fatura`** — corpo livre (itens ou blocos) no topo e boleto
  abaixo, num só PDF. Passthrough: o `valor` cobrado vem no payload.

### Corrigido
- **Item duplicado no lote era impresso em silêncio** em `POST /api/render/carne`
  e `POST /api/boleto/multi` — o título sobrescrito sumia do PDF. Agora `422`
  com os identificadores repetidos.
- **`POST /jobs/boletos` respondia `500`** com identificador de item repetido.
  Agora `422`. Mesma proteção em `POST /jobs/cnab/remessas`.
- **`template` era aceito e ignorado** em `GET /api/boleto`,
  `POST /api/boleto/multi`, `POST /api/render/boleto` e `POST /jobs/boletos`:
  `classico` saía idêntico a `moderno`. Valor inválido agora responde `400`
  (`422` no job), e `carne` deixa de ser oferecido no job.
- **`instrucoes` em texto virava um caractere por linha no boleto.** Agora `\n`
  separa as linhas, no máximo 7 de 100 caracteres — acima disso, `400`.
- **`LOG_LEVEL` não tinha efeito.** Passa a definir o nível de log do uvicorn;
  valor inválido cai para `info` com aviso, sem derrubar o container.
- **Links 404 servidos no Swagger público** — `_DOC_REPO` e 5 em
  `docs/openapi.yaml` apontavam para `master`, branch que não existe.

### Alterado
- **Python mínimo 3.14 → 3.12** e engine **`pycobranca >= 1.0.2`**: wheels
  prontos, sem compilação a partir do código-fonte. Imagem em `python:3.12-slim`.

### Removido
- **Cliente pip (`python-client/`) saiu deste repositório.** Ele é um produto à
  parte, com versão própria, e o serviço nunca o importou. Quem usava
  `pip install "git+...#subdirectory=python-client"` passa a chamar a API por
  HTTP direto — a spec OpenAPI e a coleção Postman continuam aqui.

## [2.0.0] - 2026-07-28

### 🐍 Serviço único, 100% Python (engine PyCobrança)

**BREAKING:** a conexão com o **Banking Core BrCobrança (Ruby) foi
DESCONTINUADA**. A superfície offline (`/api/*`) passa a ser servida
**nativamente** pela engine [PyCobrança](https://github.com/Maxwbh/pyCobranca)
dentro do próprio processo FastAPI — um container, um processo, sem sidecar.

A v2 **não carrega o vocabulário da v1**: o que existia só por compatibilidade
foi removido (ver "Removido").

### Adicionado
- `app/core/pycob.py` — adaptador da engine (boleto, multi/carnê, remessa
  CNAB 240/400, retorno, leitura de OFX).
- `/api/*` nativo: health, info, metadata, bancos, boleto (validate/data/
  nosso_numero/PDF/multi), remessa, retorno, OFX, render/* e Swagger próprio.
- **Jobs em lote assíncrono** (`/jobs/boletos`, `/jobs/cnab/remessas`): 202 +
  `job_id`, isolamento por item, idempotência, artefatos com `sha256`, webhook
  de conclusão (HMAC) e métricas.
- **Encargos na remessa CNAB** validados e documentados: multa, juros/mora,
  desconto (1º/2º/3º), IOF, abatimento e protesto — modelo de trio
  código/tipo → valor → data, com a unidade recusada quando o layout não a
  expressa (guia `docs/api/encargos.md`, schema `Pagamento` no Swagger).
- `provider: "pycobranca"` — valor canônico do caminho offline/CNAB.
- **Validação de campos por banco** (engine PyCobrança ≥ 1.0.1): tipos,
  tamanhos, formatos, carteiras válidas, nosso número e campos especiais;
  os erros vêm em **lista** (`validation_errors`), um por campo. Inclui
  **CNPJ alfanumérico** (formato 2026). Guia: `docs/api/validacao-campos.md`.

### Alterado
- Imagem Docker `python:3.14-slim` (exigência da engine), processo único,
  usuário não-root; `git` sai da imagem (a engine vem do PyPI, não de git).
- Dependência da engine: `pycobranca>=1.0.1,<2` (PyPI) — build reprodutível.
- OFX passa a ser lido pela engine (regra de nosso número **por banco**).

### Removido
- Engine Ruby (`lib/`, `spec/`, `config/`, `config.ru`, `Gemfile*`), variantes
  de Dockerfile e o entrypoint de sidecar.
- Geração de **imagens** (JPG/PNG/TIF) — a engine emite **PDF** (`jpg/png/tif`
  respondem 400).
- `provider: "brcobranca"` — **removido**; enviar o valor antigo responde 422
  listando os válidos.
- Campo `nosso_numero_extraido` no OFX — ficou só `nosso_numero`.
- Dependência `ofxparse` (OFX agora é da engine).
- Pacote pip `boleto-cnab-client` → **`cobranca-api-client`** (import
  `boleto_cnab_client` → `cobranca_api`).

## [1.5.0] - 2026-06-17

### Adicionado

- 🧩 **Endpoints de renderização** `POST /api/render/boleto`, `/api/render/carne`
  e `/api/render/remessa`: corpo JSON e resposta normalizada (boleto → dados +
  PDF base64; carnê 3-vias A4 em PDF; remessa → conteúdo CNAB). São a superfície
  consumida pelo gateway **Boleto-API (Python)** via proxy — o `boleto_cnab_api`
  passa a atuar como **engine de renderização** (BrCobrança). Documentados no
  `openapi.yaml` (tag `Render`) e no Swagger (`/api/docs`).

### Modificado

- 📦 **brcobranca atualizado**: `12.10.2` → `12.10.3` (revision `2613452` →
  `e555745`). Corrige o template **PrawnCarne** (faltava o `autoload` de
  `PrawnCarne`/`PrawnTema` e o método `PrawnTema.texto_logo_banco`), restaurando
  o carnê 3-vias A4 sem GhostScript (`template=carne`).

### Corrigido

- 🛡️ **Robustez de campos (boleto e remessa)**:
  - Campos com default (`aceite`, `especie_documento`, `especie`, `moeda`,
    `local_pagamento`) enviados **em branco** agora caem no default do brcobrança
    (antes falhavam com "não pode estar em branco").
  - A remessa **ignora campos não suportados** pela classe do banco (ex.:
    `variacao` no CNAB 240 do Sicoob) e campos extras dentro de cada `pagamento`
    (ex.: `cedente`), em vez de gerar `500` (`NoMethodError`). Códigos de formato
    do pagamento em branco também caem no default.
  - **`bairro_sacado` ausente** não quebra mais a remessa. O brcobrança usa
    `bairro_sacado.format_size` no detalhe (ex.: BB CNAB 400) sem validar
    presença; sem o campo, dava `undefined method 'format_size' for nil` → `500`.
    Agora o campo é normalizado para `''` quando ausente.
  - **Swagger/OpenAPI em produção**: o `docs/openapi.yaml` era excluído da imagem
    pelo `.dockerignore`, então `/api/openapi.json` e `/api/docs` davam `500`.
    Agora o arquivo é incluído na imagem (`!docs/openapi.yaml`) e o endpoint tem
    fallback para uma spec mínima válida (nunca `500`).

## [1.4.1] - 2026-06-14

### Modificado

- 📦 **brcobranca atualizado**: `12.10.1` → `12.10.2` (revision `cca5f1a` → `2613452`).
  O módulo `Brcobranca::Bancos` passa a permitir **registro/remoção de bancos em
  runtime** (`Bancos.registrar`, `Bancos.classe_boleto/classe_remessa/classe_pix`),
  com bancos customizados aparecendo em `todos`/`find`/`as_json` sem afetar os 18
  bancos nativos. Inclui correção menor de metadados na gemspec. Sem mudanças no
  contrato público desta API (o `/api/bancos` continua funcionando como antes).

## [1.4.0] - 2026-06-12

### Adicionado

- 🧾 **Template de carnê** no `/api/boleto` e `/api/boleto/multi` via
  `template=carne`: gera carnê em PDF (1 via por página; no `/multi`, 3 vias por
  folha A4) usando `Brcobranca::Boleto::Template::PrawnCarne` (sem GhostScript).
- 🎨 **Tema visual** nos templates Prawn (`prawn` e `carne`) — novos campos
  **opcionais** aceitos em `data`, passados direto ao boleto (attr_accessor na
  Base do brcobranca v12.10):
  - `logo_empresa` — logo da empresa (path PNG/JPG)
  - `cor_marca` — cor da marca em hex `RRGGBB` (contraste automático)
  - `marca_dagua` — texto da marca d'água diagonal antifraude
  - `rodape_contato` — rodapé com contato da empresa
  - `fonte_ttf` — fonte TTF (UTF-8 completo)
  - `parcela_atual` / `total_parcelas` — selo "PARCELA n/N"
- 🧱 Constantes `TEMPLATES`, `PDF_ONLY_TEMPLATES` e `THEME_FIELDS` +
  helpers `template_supported?` / `pdf_only_template?` em `Config::Constants`.
- 🧪 Specs de integração `spec/integration/carne_boleto_spec.rb` (carnê single,
  carnê em lote e tema no template prawn).
- 📖 OpenAPI: parâmetro `template` documentado (`rghost`/`prawn`/`carne`) e
  campos de tema adicionados ao schema `BoletoData`.

### Modificado

- 📦 **brcobranca atualizado**: `12.9.0` → `12.10.1` (revision `fa43157` → `cca5f1a`),
  que traz PrawnCarne, PrawnTema, marca d'água, fontes TTF e fixes de PIX/QR.
- 🐳 **Docker focado em Prawn**: a imagem principal (`Dockerfile`) passa a ser a
  variante **sem GhostScript** (PDF-only, mais leve e com menor uso de memória —
  ideal para o Render Free Tier). A antiga imagem com GhostScript foi movida para
  **`Dockerfile.rghost`** (use-a para gerar JPG/PNG/TIF). O `render.yaml` e o
  `docker-compose` (serviço padrão) usam a imagem Prawn; a variante rghost fica no
  profile `rghost`.
- ⚙️ **Template padrão por ambiente**: o default de `template` em `/api/boleto` e
  `/api/boleto/multi` agora vem de `BOLETO_TEMPLATE` (helper `Constants.default_template`).
  Na imagem principal o padrão é `prawn`; na `Dockerfile.rghost`, `rghost`.

### Corrigido (herdado do brcobranca)

- 🐛 **PIX/QR Code**: correção de sobreposição QR × código de barras no Bolepix
  (Prawn e RGhost) e nível de correção de erro do QR ajustado para M (padrão BACEN).
- 🐛 **Normalização de remessa**: além do Sicoob CNAB400 (`carteira`/`convenio`),
  agora também Banco do Brasil CNAB 240/400 recebe padding automático de campos.

## [1.3.2] - 2026-06-12

### Modificado

- 📦 **brcobranca atualizado**: `12.8.1` → `12.9.0` (revision `5e85c31` → `fa43157`).

### Corrigido

- 🐛 **Remessa Sicoob (CNAB400) — `carteira`/`convenio`**: a versão 12.9.0 do
  brcobranca adiciona *setters* que normalizam os campos automaticamente
  (`carteira` → `rjust(2, '0')`, `convenio` → `rjust(9, '0')`). Isso resolve os
  erros de validação `"Carteira deve ter 2 dígitos."` e `"Convenio deve ter 9
  dígitos."` que ocorriam ao gerar a remessa Sicoob com dados que geravam o
  boleto sem problemas (a classe de boleto era mais leniente que a de remessa).
  Agora `carteira: "1"` é aceito e tratado como `"01"`.

## [1.3.1] - 2026-06-12

### Otimizações de Docker / Render Free Tier (512MB RAM)

#### Memória
- ✅ **jemalloc** ativado via `LD_PRELOAD` no `Dockerfile` e `Dockerfile.prawn`.
  Substitui o allocator padrão do musl (Alpine), que tem alta fragmentação sob
  múltiplas threads — ganho real de RAM no free tier.
- ❌ Removido `MALLOC_ARENA_MAX`: é um tunable **exclusivo do glibc** e não tinha
  efeito algum em Alpine/musl (era um no-op).
- ✅ `MALLOC_CONF` (jemalloc) e `RUBY_GC_MALLOC_LIMIT` / `RUBY_GC_OLDMALLOC_LIMIT`
  ajustados para devolver memória ociosa ao SO de forma mais agressiva.

#### Imagem mais enxuta
- ✅ `bundle clean --force` + `deployment mode` no build stage.
- ✅ `.dockerignore` exclui `python-client/`, `*.md`, `scripts/` e `Dockerfile.prawn`
  → contexto de build reduzido para ~330KB.

#### Robustez de deploy
- ✅ `tini` como PID 1 (`ENTRYPOINT`) → propaga `SIGTERM` ao Puma, garantindo
  shutdown gracioso durante deploys.
- ✅ `PUMA_WORKER_TIMEOUT=60` → evita kill do worker durante o cold start
  (wake-up do sleep no free tier).
- ✅ `config/puma.rb`: `min_threads=1` (elimina latência na 1ª requisição) e
  `preload_app!` apenas em cluster mode (workers ≥ 1).
- ✅ `HEALTHCHECK` usa `${PORT}` em vez de porta fixa.

#### render.yaml
- ✅ Valores de env como strings (padrão exigido pelo Render).
- ✅ `PORT` não é mais fixado — o Render injeta a porta e o Puma faz bind via
  `ENV['PORT']`.
- 📖 `DEPLOY.md` atualizado com as novas variáveis de ambiente e dicas de OOM.

## [1.3.0] - 2026-04-10

### Adicionado

#### Banco C6 (336) — NOVO
- ✅ `banco_c6` adicionado em `SUPPORTED_BANKS` e `CNAB400_BANKS`
- ✅ Suporte completo a geração de boletos C6 (código 336)
- ✅ Remessa e retorno CNAB 400 para Banco C6
- ✅ PIX híbrido suportado (campo `emv`)
- ✅ Fixture `banco_c6_valido` em `spec/fixtures/sample_data.json`
- ✅ Testes no `all_banks_spec.rb` incluindo PDF generation

#### PIX Híbrido documentado
- 📄 `docs/api/pix.md` — Guia completo de PIX híbrido
- 📄 Bancos com PIX: Banco do Brasil, Bradesco, Itaú, Sicoob, Caixa, Banco C6, Santander, Sicredi
- 📄 Campos `emv` e `pix_label` adicionados no schema OpenAPI `BoletoData`
- 📄 Objeto `pix` no schema `BoletoResponse`

#### Documentação brcobranca-fork.md reescrita
- 📄 Tabela completa de 18 bancos com colunas Boleto, CNAB 400, CNAB 240, PIX
- 📄 Histórico de versões do fork (v12.0 → v12.6.1)
- 📄 Métodos modernos da gem: `to_hash`, `dados_calculados`, `dados_entrada`, `dados_pix`, `valido?`, `to_hash_seguro`
- 📄 Factory methods: `Brcobranca::Remessa.criar`, `Brcobranca::Retorno.parse`
- 📄 Seção detalhada por banco com particularidades

### Modificado
- 📦 **brcobranca atualizado**: 12.6.0 → 12.6.1 (traz suporte nativo a Banco C6)
- 📖 OpenAPI v1.2.0 → v1.3.0, schema `BankCode` inclui `banco_c6`
- 📖 README.md, ARCHITECTURE.md, python-client/README.md atualizados para v1.3.0
- 📖 `docs/fields/all-banks.md` inclui seção detalhada do Banco C6

### Versão da Gem

Este release atualiza brcobranca de 12.6.0 → 12.6.1, trazendo:
- Banco C6 (336) com CNAB 400 completo
- PIX expandido (6 bancos: Bradesco, Itaú, Banco C6, Sicoob, Caixa, Banco Brasil)
- Sicoob: suporte a Carteira 9 e Layout 810
- PrawnBolepix (alternativa ao Ghostscript para PIX)

---

## [1.2.0] - 2026-04-09

### Adicionado

#### Endpoint OFX (Extrato Bancário)
- `POST /api/ofx/parse` - Parsing de arquivos OFX com retorno JSON estruturado
- Suporte a OFX v1 (SGML) e v2 (XML)
- Conversão automática de encoding Latin-1 para UTF-8
- Filtro `somente_creditos=true` para retornar apenas créditos
- Extração automática de `nosso_numero` do campo memo por banco

#### Módulo NossoNumeroExtractor
- Extração por regex para Sicoob (756), Itaú (341), BB (001), Bradesco (237), Caixa (104)
- Fallback genérico para bancos não mapeados

#### Testes
- 20 testes unitários para NossoNumeroExtractor
- 14 testes unitários para OFXParserService
- 7 testes de integração para endpoint OFX
- Fixtures OFX para Sicoob e Itaú
- **Total: 158 testes Ruby + 44 testes Python (202 passando)**

#### Documentação
- `docs/README.md` - Índice central da documentação
- `docs/api/ofx-parsing.md` - Guia detalhado do endpoint OFX
- `docs/openapi.yaml` atualizado com schemas `OfxResponse`, `OfxTransacao`, `OfxError`
- Troubleshooting reescrito com seções por endpoint incluindo OFX

### Modificado
- Gemfile: adicionada gem `ofx` para parsing de extratos bancários
- Gemfile: adicionadas gems `rspec` e `rack-test` no grupo de teste
- ErrorHandler: trata `Grape::Exceptions::ValidationErrors` e `Brcobranca::NaoImplementado` como HTTP 400
- BoletoService.create: filtra campos não suportados por banco (evita NoMethodError em Bradesco por `digito_conta`)
- BoletoService.data: normaliza contrato público (`documento_numero` → `numero_documento` alias)
- BoletoService.nosso_numero: mantém compatibilidade com `nosso_numero` como chave formatada
- BoletoService.generate_multi: valida array vazio
- RemessaService: factory method usa `**kwargs` corretamente (Ruby 3.0+)
- RemessaService: converte hashes em objetos `Brcobranca::Remessa::Pagamento`
- FieldMapper: novo mapeamento `PAGAMENTO_FIELD_MAPPINGS` (sacado → nome_sacado, etc)
- Endpoints POST retornam explicitamente status 200 para binários (boleto, remessa, retorno, multi)
- Dockerfile: `BUNDLE_WITHOUT=development:test` no runtime stage
- Dockerfile: label de versão atualizado para 1.2.0
- docker-compose: serviço test instala dev deps antes de rodar rspec
- CI workflow: tag Docker em lowercase, dependências pytest instaladas via pip install -e

### Corrigido
- Remessa: `tipo:` → `formato:` (chave correta para `Brcobranca::Remessa.criar`)
- Remessa: passagem posicional → keyword arguments em Ruby 3.0+
- Remessa: formato correto `cnab400`/`cnab240` (não apenas `400`/`240`)
- Client Python: `RetryError` convertido para `BoletoAPIError`
- Fixtures: `caixa_valido` carteira `"SR"` → `"1"`, `santander_valido` ajustado para convenio válido
- `spec_helper.rb`: forçar encoding UTF-8 para arquivos com acentos
- `all_banks_spec.rb`: correção de scoping (`let` dentro de `context.each`)

### Removido
- `docs/DEPLOY.md` (duplicado do `DEPLOY.md` na raiz)
- `docs/TODO_INTEGRACAO.md` (roadmap concluído, histórico disponível em commits)
- `docs/swagger.html` (deve ser gerado sob demanda do `openapi.yaml`)

---

## [1.1.0] - 2026-01-06

### Adicionado

#### Arquitetura Modular (Fase 1)
- ✅ Refatoração completa: de 444 linhas em 1 arquivo para 12 arquivos modulares
- ✅ `lib/boleto_api/config/constants.rb` - Constantes centralizadas
- ✅ `lib/boleto_api/services/` - Camada de serviços (BoletoService, RemessaService, RetornoService)
- ✅ `lib/boleto_api/endpoints/` - Endpoints separados por domínio
- ✅ `lib/boleto_api/middleware/` - Error handler e request logger

#### Cliente Python (Fase 3)
- ✅ `pyproject.toml` - Configuração moderna PEP 517/518
- ✅ `types.py` - TypedDict para tipagem estática (BoletoDataDict, BoletoResponseDict, etc.)
- ✅ Suite de testes pytest completa (test_client.py, test_models.py, test_exceptions.py, test_types.py)
- ✅ Compatibilidade com Python 3.8+ via typing_extensions

#### Infraestrutura (Fase 4)
- ✅ Testes de integração: `spec/integration/` (remessa, retorno, multi_boleto)
- ✅ Documentação OpenAPI 3.0: `docs/openapi.yaml`
- ✅ Interface Swagger UI: `docs/swagger.html`
- ✅ Docker multi-stage build otimizado (~150MB)

#### Integração brcobranca v12.5+ (Fase 5)
- ✅ BoletoService usa `boleto.to_hash` e `dados_calculados`
- ✅ RemessaService usa `Brcobranca::Remessa.criar` factory method
- ✅ RetornoService usa `Brcobranca::Retorno.parse` com detecção automática
- ✅ Fallback mantido para versões anteriores da gem

### Modificado
- 📦 Gemfile atualizado para usar fork @maxwbh do brcobranca
- 📝 TODO_INTEGRACAO.md - Todas as 5 fases concluídas
- 🔧 Services refatorados para usar novos métodos da gem

### Repositórios
- brcobranca: https://github.com/Maxwbh/brcobranca (v12.5.0)
- boleto_cnab_api: https://github.com/Maxwbh/cobranca-api (v1.1.0)

---

## [1.0.0] - 2025-11-27

### Adicionado
- 🎉 Versão inicial estável
- ✅ Suporte completo para 6+ bancos brasileiros
- ✅ API REST com Grape framework
- ✅ Endpoints para validação, geração de dados e PDF
- ✅ Mapeamento automático `numero_documento` ↔ `documento_numero`
- ✅ Logs estruturados com timestamps e tempo de processamento
- ✅ Tratamento seguro de métodos que podem não existir em todos os bancos
- ✅ Testes automatizados com RSpec para múltiplos bancos
- ✅ Docker e Docker Compose para desenvolvimento
- ✅ Configuração otimizada para Render Free Tier
- ✅ Documentação completa de campos por banco
- ✅ Guia de deploy detalhado
- ✅ Health check endpoint

### Bancos Suportados
- Banco do Brasil (001)
- Sicoob (756)
- Bradesco (237)
- Itaú (341)
- Caixa Econômica Federal (104)
- Santander (033)
- Sicredi (748)
- Banrisul (041)
- Banestes (021)
- BRB (070)

### Endpoints
- `GET /api/health` - Health check
- `GET /api/boleto/validate` - Validar dados do boleto
- `GET /api/boleto/data` - Obter dados completos sem gerar PDF
- `GET /api/boleto/nosso_numero` - Gerar nosso número
- `GET /api/boleto` - Gerar boleto (PDF/JPG/PNG/TIF)
- `POST /api/boleto/multi` - Gerar múltiplos boletos
- `POST /api/remessa` - Gerar arquivo de remessa CNAB
- `POST /api/retorno` - Processar arquivo de retorno CNAB

### Segurança
- ✅ Validação de tipos de parâmetros
- ✅ Tratamento robusto de erros
- ✅ Logs sem informações sensíveis
- ✅ Execução como usuário não-root no Docker

### Performance
- ✅ Otimizações para 512MB RAM (Render Free Tier)
- ✅ Puma com 1 worker e até 5 threads
- ✅ MALLOC_ARENA_MAX=2 para reduzir uso de memória
- ✅ Build Docker otimizado

### Documentação
- ✅ README completo e profissional
- ✅ Guia de campos por banco
- ✅ Exemplos práticos Python/Ruby
- ✅ Troubleshooting detalhado
- ✅ Deploy guide para Render
- ✅ Documentação de API inline

### Testes
- ✅ Suite completa com RSpec
- ✅ Testes de integração para todos os bancos
- ✅ Fixtures com dados válidos
- ✅ Cobertura de casos de erro
- ✅ Testes de mapeamento de campos

---

## Tipos de Mudanças

- `Adicionado` - Novas funcionalidades
- `Modificado` - Mudanças em funcionalidades existentes
- `Obsoleto` - Funcionalidades que serão removidas
- `Removido` - Funcionalidades removidas
- `Corrigido` - Correção de bugs
- `Segurança` - Correções de vulnerabilidades

---

**Formato:** [MAJOR.MINOR.PATCH]
- **MAJOR** - Mudanças incompatíveis na API
- **MINOR** - Novas funcionalidades compatíveis
- **PATCH** - Correções de bugs compatíveis
