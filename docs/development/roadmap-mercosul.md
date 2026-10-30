# Roadmap Mercosul — cobrar no Brasil a partir do Paraguai

> **Público:** empresa paraguaia — Ciudad del Este, Encarnación, Pedro Juan —
> que vende a brasileiros e precisa **cobrar em reais**. Hoje é **hipotético**:
> não há lead concreto, e a integração, quando houver, passa pela **M&S**.
> Linguagens mais difundidas nesse público: **PHP e Python**.
>
> **Premissa que define tudo abaixo:** para esse público, a Cobranca-API **já
> funciona** — boleto, Pix e CNAB em reais, num banco brasileiro. O que falta
> não é funcionalidade: é a API explicar-se a quem está do outro lado da ponte.
> Por isso o roadmap gasta pouco enquanto o público é hipótese, e deixa pronto
> o que destrava quando virar lead.
>
> Salvo o que está marcado ✅, cada linha é **planejada**, não implementada.

## O que foi medido antes de planejar

Nenhum item abaixo veio de opinião. Os números são do código e do serviço, em
30/10/2026:

| Medição | Resultado | O que decide |
|---|---|---|
| Vocabulário brasileiro no gateway | `boleto` em 26 arquivos, `Pix` em 27, `CNAB` em 11 | O produto não se traduz para outro trilho; se traduz para outro **leitor** |
| Módulos sem vocabulário brasileiro | 12 de 47 (cofre, webhook, outbox, OAuth+mTLS, conciliação…) | É o que seria reaproveitável num produto para outro país — e não é o que vende |
| Documentação inteira | **57.021** palavras em 34 arquivos | Traduzir tudo é ativo que apodrece em duas línguas |
| Só a spec (descrições de API, rotas e campos) | **3.890** palavras | Um décimo do custo, é o que o integrador lê, e é gerada — guarda de paridade prende as duas versões ao código |
| Campos do boleto (`BoletoData`) | **63**, 6 obrigatórios | O glossário tem de cobrir todos, ou promete o que não cumpre |
| Primeiro erro que um paraguaio recebe | `sacado_documento inválido (CPF/CNPJ)` | Não diz que o documento tem de ser o **brasileiro** do pagador |
| Mesmo erro, no beneficiário | `cedente_documento inválido (CPF/CNPJ)` | **Cita um campo que a API não tem** — o campo é `documento_cedente`. Defeito para qualquer integrador, em qualquer língua |
| Origem dessas mensagens | engine pyCobrança, `bancos/base.py:217,220` | A raiz é em outro repositório; o gateway pode traduzir antes de devolver |
| Exemplos por linguagem | Python, Oracle PL/SQL, APEX | **Não há PHP** — a linguagem mais difundida no público-alvo |
| `<html lang>` do site | lê só `site.lang` (`pt-BR`) | Página em espanhol sairia rotulada como português para o Google e o leitor de tela |

### Os trilhos vizinhos (por que não entram)

| País | Trilho | Estado medido | API pública |
|---|---|---|---|
| Argentina | Transferencias 3.0, QR interoperável | implantação concluída (BCRA) | não encontrada — integração via PSP/billetera |
| Paraguai | SIPAP → **SIP** (abr/2026), QR Hub | QR Hub ainda **em testes** em ago/2026 | não encontrada |
| Uruguai | Sistema de Pagos Rápidos; QR em comércio é "próximo passo" | não confirmado em produção | não encontrada |
| Pix internacional | Nexus (BIS) | o Brasil **não aderiu**; sem cronograma | — |

"Não encontrada" é resultado de busca, não varredura dos portais de cada banco
central. Mas o ponto decisivo não é a API: **o dinheiro desse público entra
em reais, no Brasil.** O trilho paraguaio não é o problema deles.

### Linguagens — o que dá para afirmar

A pergunta era "que linguagens o Mercosul usa para integração bancária". O
dado por país da pesquisa do Stack Overflow não é alcançável deste ambiente
(o arquivo bruto fica em repositório fora do escopo da sessão), e os
levantamentos secundários só trazem números globais. O que sobra é mais
específico e mais útil: **em que linguagem os próprios PSPs da região
publicam SDK**, que é onde o integrador de fato escreve.

| Fonte | Linguagens | Peso |
|---|---|---|
| **Mercado Pago** (PSP dominante em AR/UY/PY/BR), SDKs oficiais de servidor | PHP, Java, Node, Ruby, .NET, Python, Go | Alto — é o padrão de referência da região |
| **Bancard** (adquirente nacional do Paraguai), vPOS | **sem SDK oficial**; comunidade: PHP (dois pacotes no Packagist), Dart, TypeScript, módulo Odoo (Python). **Nenhum Java** | Alto para o Paraguai — mostra o que a comunidade local escreve sozinha |
| **dLocal** (origem uruguaia, pan-LatAm) | comunidade: PHP/Laravel, Node, Ruby | Médio |
| Bancos argentinos (Galicia, BBVA, Santander) | sem portal público de desenvolvedor nos rastreadores de open banking | Baixo — confirma que a integração é via PSP |
| Relato de quem conhece o mercado | **PHP e Python** | Decisivo para este roadmap |

Conclusão operacional: **PHP primeiro, Python já coberto.** Java fica para
quando um lead pedir — nenhuma fonte paraguaia o aponta.

## Princípios

- **Nunca traduzir nome de campo.** `cedente`, `sacado`, `nosso_numero` são o
  contrato. Traduz-se a descrição, o erro e o guia — nunca a chave.
- **O dinheiro é em reais.** Nada de campo de moeda, cotação ou conversão: quem
  precisar de referência em guaraníes ou dólares escreve em `instrucoes`.
- **Trilho vizinho não entra** enquanto não houver API pública **e** demanda. As
  duas condições, não uma.
- **O regulatório é serviço, não software.** CNPJ, conta e convênio no Brasil
  são a barreira real, e quem a cruza com o cliente é a M&S. A documentação
  aponta para isso em vez de fingir que a API resolve.
- **Toda melhoria entra com guarda**, no mesmo padrão do resto do repositório:
  glossário derivado da spec, paridade entre versões, nenhuma instância pública,
  nenhum link quebrado. Doc que não é cobrada envelhece — foi medido semana a
  semana nesta revisão.

## Fases

### 🛠 Fase 0 — Defeito de hoje (independe do mercado)

| Item | O que muda | Guarda |
|---|---|---|
| ✅ **Mensagem de documento** | `CPF/CNPJ brasileiro inválido`, citando o campo **certo** (`documento_cedente` / `sacado_documento`). O gateway reescreve a mensagem da engine antes de devolver. | Caso para cada um dos dois campos, com CI e RUC paraguaios como entrada |
| **Raiz na pyCobrança** | Reportar que `base.py:217` nomeia `cedente_documento`, campo que a API não expõe | — (outro repositório; não se escreve nele daqui) |

Era defeito em português. Entrou primeiro, mercado ou não — a mensagem agora é
`documento_cedente: CPF/CNPJ brasileiro inválido`, traduzida em
`core.pycob.traduzir_erro_da_engine`, o ponto único por onde todo erro da
engine passa. O reporte à pyCobrança segue em aberto.

### 🎯 Fase 1 — Porta aberta (barato; feito antes do lead)

| Item | Esforço | Guarda |
|---|---|---|
| **Página de entrada em espanhol** (`/es/`): o que precisa antes, os dois caminhos, primeiro boleto em 5 min, **glossário dos 63 campos** | rascunho pronto | todo campo do `BoletoData` no glossário; nenhum campo inventado; os 6 obrigatórios na seção certa; links resolvem; sem instância pública |
| **`<html lang>` por página** no layout | 1 linha | o layout lê `page.lang` |
| **Exemplo em PHP** (`examples/php/`), espelho do `examples/python` | pequeno | o exemplo cobre as mesmas rotas que o de Python |
| **Link na capa** para `/es/` | 1 linha | — |

A página em espanhol diz, sobre o regulatório, que **a M&S acompanha a
abertura de empresa, conta e convênio no Brasil** — a barreira vira serviço.

### 🔌 Fase 2 — Só com lead real

| Item | Esforço | Por que esperar |
|---|---|---|
| **Swagger em espanhol** — descrições de API, rotas e campos | 3.890 palavras + mecanismo de geração bilíngue a partir das docstrings | Custo de manutenção contínua; sem demanda vira ativo que envelhece |
| **Erros por `Accept-Language: es`** | medir quantas mensagens existem; mapa PT→ES | Toca a API (aditivo); só vale com alguém lendo |
| **Landing comercial** "cobre en Brasil sin intermediario" — o argumento é o modelo: MIT, self-hosted, sem percentual por venda | texto | Depende de saber como a M&S quer vender |
| **Segundo exemplo** na stack do lead | pequeno | Só se não for PHP nem Python |

### 🕓 Fase 3 — Avaliar

- **Argentina e Uruguai como leitores**: a mesma página em espanhol serve;
  diferença é só o documento de identidade de origem, que não entra na API.
- **Exportação de liquidações com cabeçalho em espanhol** — o que o retorno
  CNAB e o `/conciliacao` já devolvem, num CSV para a contabilidade de lá.
  Medir o que existe antes de prometer.
- **Trilho paraguaio** (SIP / QR Hub): reavaliar quando houver API pública
  publicada pelo BCP **e** um cliente que receba em guaraníes. Hoje nenhuma das
  duas.

## Fora de escopo (decidido)

- Integrar SIP, QR Hub, Transferencias 3.0 ou qualquer trilho vizinho.
- Traduzir a documentação inteira (57 mil palavras).
- Traduzir nomes de campo.
- Campo de moeda de referência, cotação ou conversão.
- Pix internacional — não existe para aderir.

## Como cada item entra (checklist)

1. Mede-se o estado antes de escrever — o número vai para o commit.
2. O guarda é escrito e visto **vermelho** no defeito que o motivou, antes de
   ficar verde.
3. Nenhuma referência a instância pública; `localhost:8000` é o endereço.
4. Nenhum nome de campo traduzido.
5. Swagger publicado regerado quando a casca mudar (`--conferir` no CI reprova
   se ficar atrás).
6. Commit e PR sem menção a assistente de IA — o `guarda-ia.yml` cobra.

## Perguntas abertas

- Que banco brasileiro esse público usaria? Define se a trilha de entrada é
  offline (CNAB) ou online (C6, Sicoob, Inter, Itaú).
- A landing comercial é do site do produto ou do site da M&S?
- Quando um lead aparecer: PHP ou Python? Decide o segundo exemplo.
