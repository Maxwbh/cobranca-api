"""Erros no idioma de quem chama: `Accept-Language: es` (ou `?lang=es`).

A API fala português — é a língua do código, dos bancos e do contrato. O que
muda aqui é só o texto das MENSAGENS DE ERRO, que é o que um integrador em
Ciudad del Este lê quando a chamada falha. Nome de campo, código HTTP, chave
do JSON: nada disso se traduz.

Um ponto só, de propósito: o middleware abaixo reescreve o corpo de toda
resposta de erro (`4xx`/`5xx` em JSON, e o `201` com `status: "erro"` do
`POST /cobranca`, que é erro com outro número) — rota nova herda sem ninguém
lembrar, que é o mesmo princípio de `core.pycob._erros`.

O catálogo é uma lista ORDENADA de regras (regex → substituição): primeiro as
mensagens estruturadas que o gateway e a engine emitem, depois um vocabulário
curto para o que sobra. Trechos entre crases ou aspas, e os nomes de banco,
são preservados — "Banco do Brasil" não vira "Banco del Brasil".

O guarda (`tests/test_erros_em_espanhol.py`) dispara erros reais em espanhol
e cobra que nenhuma palavra portuguesa sobre; e cobra que, sem o cabeçalho,
tudo continue em português.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs

from starlette.datastructures import Headers, MutableHeaders

from app.core.i18n_openapi import idioma_pedido

#: Chaves do JSON cujo valor é mensagem para humano. `detail` do FastAPI (texto
#: ou lista de erros do Pydantic), `error`/`erro`/`message` das superfícies,
#: `validation_errors`/`details`/`errors` (listas planas).
CHAVES_DE_MENSAGEM = ("detail", "error", "erro", "message", "validation_errors",
                      "details", "errors", "msg", "aviso", "hint")

# ---------------------------------------------------------------------------
# Regras. Regex sobre a mensagem inteira, aplicadas em ordem; `\g<nome>` copia
# grupo. Cada regra traz um exemplo em português que o guarda usa para provar
# que a regra casa e que o resultado não tem português sobrando.
# ---------------------------------------------------------------------------
REGRAS: list[tuple[str, str, str]] = [
    # --- gateway: documento, campo desconhecido, apelidos ---------------------
    (r"^(?P<c>\w+): CPF/CNPJ brasileiro inválido$",
     r"\g<c>: CPF/CNPJ brasileño inválido",
     "sacado_documento: CPF/CNPJ brasileiro inválido"),
    (r"^campo desconhecido em `data`: (?P<c>'[^']*') — você quis dizer (?P<d>.+)\?$",
     r"campo desconocido en `data`: \g<c> — ¿quiso decir \g<d>?",
     "campo desconhecido em `data`: 'data_processamento' — você quis dizer 'data_documento'?"),
    (r"^campo desconhecido em `data`: (?P<c>'[^']*')$",
     r"campo desconocido en `data`: \g<c>",
     "campo desconhecido em `data`: 'moeda'"),
    (r"^Campo aceito por (?P<b>.+?) é um destes: (?P<l>.+)$",
     r"Un campo aceptado por \g<b> es uno de estos: \g<l>",
     "Campo aceito por C6 Bank (336) é um destes: aceite, agencia, carteira"),
    (r"^Campo não suportado no pagamento: (?P<c>.+)$",
     r"Campo no soportado en el pago: \g<c>",
     "Campo não suportado no pagamento: 'multa'"),
    (r"^Campos aceitos: (?P<l>.+)$", r"Campos aceptados: \g<l>",
     "Campos aceitos: nosso_numero, valor"),
    (r"^(?P<a>`\w+` \(.+?\)) e (?P<b>`\w+` \(.+?\)) são o mesmo campo(?P<r>.*)$",
     r"\g<a> y \g<b> son el mismo campo\g<r>",
     "`conta_corrente` ('1') e `conta` ('2') são o mesmo campo"),
    (r"^(?P<c>\w+): (?P<n>\d+) linhas, máximo (?P<m>\d+) em (?P<o>.+)$",
     r"\g<c>: \g<n> líneas, máximo \g<m> en \g<o>",
     "instrucoes: 9 linhas, máximo 7 em moderno"),
    (r"^(?P<c>\w+): máximo (?P<n>\d+) caracteres por linha em (?P<r>.+)$",
     r"\g<c>: máximo \g<n> caracteres por línea en \g<r>",
     "instrucoes: máximo 100 caracteres por linha em moderno (linha 2 tem 140)"),
    (r"^Banco não registrado na engine: (?P<r>.+)$", r"Banco no registrado en la engine: \g<r>",
     "Banco não registrado na engine: 'xpto' (999)"),
    (r"^Banco não suportado: (?P<r>.+)$", r"Banco no soportado: \g<r>", "Banco não suportado: 'xpto'"),
    # --- gateway: `hint` das rotas (texto literal; o guarda estático varre os routers) ---
    (r"^Corrija os erros de validação antes de gerar o boleto$",
     "Corrija los errores de validación antes de generar el boleto",
     "Corrija os erros de validação antes de gerar o boleto"),
    (r"^divida o arquivo \(o teto vem de UPLOAD_MAX_BYTES\)$",
     "divida el archivo (el tope viene de UPLOAD_MAX_BYTES)",
     "divida o arquivo (o teto vem de UPLOAD_MAX_BYTES)"),
    (r"^divida o lote \(processamento assíncrono: ver docs/development/plano-jobs-lote\.md\)$",
     "divida el lote (procesamiento asincrónico: ver docs/development/plano-jobs-lote.md)",
     "divida o lote (processamento assíncrono: ver docs/development/plano-jobs-lote.md)"),
    (r"^o item_id vem de external_id, seu_numero ou numero_documento — cada item( do lote)? precisa de um valor distinto$",
     lambda m: "el item_id viene de external_id, seu_numero o numero_documento — cada ítem"
               + (" del lote" if m.group(1) else "") + " necesita un valor distinto",
     "o item_id vem de external_id, seu_numero ou numero_documento — cada item do lote precisa de um valor distinto"),
    (r"^falha no agrupamento determinístico de títulos — reporte o caso$",
     "falla en el agrupamiento determinístico de títulos — reporte el caso",
     "falha no agrupamento determinístico de títulos — reporte o caso"),
    (r"^`desenhar` é um callback Python \(recebe a tela do PDF\) e não trafega por JSON\. Use o nível 1 \(`itens`\) ou o nível 2 \(`fatura\.blocos`\); para arte livre, chame a engine pyCobrança in-process na própria aplicação\.$",
     "`desenhar` es un callback Python (recibe el lienzo del PDF) y no viaja por JSON. Use el nivel 1 (`itens`) o el nivel 2 (`fatura.blocos`); para arte libre, llame a la engine pyCobrança in-process en la propia aplicación.",
     "`desenhar` é um callback Python (recebe a tela do PDF) e não trafega por JSON. Use o nível 1 (`itens`) ou o nível 2 (`fatura.blocos`); para arte livre, chame a engine pyCobrança in-process na própria aplicação."),
    (r"^Arquivo de retorno inválido: (?P<r>.+)$", r"Archivo de retorno inválido: \g<r>",
     "Arquivo de retorno inválido: header ausente"),
    (r"^O arquivo é retorno do banco (?P<a>.+?), mas o request pediu (?P<b>.+?)\. Cada banco põe os campos em posições diferentes: ler com o layout errado devolveria valores plausíveis e errados\. Confira o `bank` ou o arquivo\.$",
     r"El archivo es un retorno del banco \g<a>, pero el request pidió \g<b>. Cada banco pone los campos en posiciones distintas: leer con el layout equivocado devolvería valores plausibles y equivocados. Verifique el `bank` o el archivo.",
     "O arquivo é retorno do banco 'sicoob' (756), mas o request pediu 'banco_c6' (336). Cada banco põe os campos em posições diferentes: ler com o layout errado devolveria valores plausíveis e errados. Confira o `bank` ou o arquivo."),
    # --- gateway: rotas offline -----------------------------------------------
    (r"^Dados do boleto inválidos$", "Datos del boleto inválidos", "Dados do boleto inválidos"),
    (r"^Verifique se todos os campos obrigatórios estão preenchidos$",
     "Verifique que todos los campos obligatorios estén completos",
     "Verifique se todos os campos obrigatórios estão preenchidos"),
    (r"^use include_data=true \(metadados no corpo\)$", "use include_data=true (metadatos en el cuerpo)",
     "use include_data=true (metadados no corpo)"),
    (r"^Boleto\(s\) com erros de validação$", "Boleto(s) con errores de validación",
     "Boleto(s) com erros de validação"),
    (r"^Erro ao gerar remessa$", "Error al generar la remesa", "Erro ao gerar remessa"),
    (r"^Erro ao processar retorno$", "Error al procesar el retorno", "Erro ao processar retorno"),
    (r"^Arquivo OFX inválido$", "Archivo OFX inválido", "Arquivo OFX inválido"),
    (r"^Falha ao gerar carnê$", "Falla al generar el carnet", "Falha ao gerar carnê"),
    (r"^Nível 3 \(fatura\.desenhar\) não é suportado via REST$",
     "El nivel 3 (fatura.desenhar) no está soportado vía REST",
     "Nível 3 (fatura.desenhar) não é suportado via REST"),
    (r"^`type` deve ser 'pdf'$", "`type` debe ser 'pdf'", "`type` deve ser 'pdf'"),
    (r"^Formato (?P<t>'[^']*') descontinuado — a engine pyCobranca gera PDF$",
     r"Formato \g<t> discontinuado — la engine pyCobranca genera PDF",
     "Formato 'jpg' descontinuado — a engine pyCobranca gera PDF"),
    (r"^template (?P<t>'[^']*') inválido(?:; use um de: (?P<l>.+))?$",
     lambda m: f"template {m.group('t')} inválido" + (f"; use uno de: {m.group('l')}" if m.group("l") else ""),
     "template 'xpto' inválido; use um de: classico, moderno"),
    (r"^use um de: (?P<l>.+)$", r"use uno de: \g<l>", "use um de: classico, moderno, carne"),
    (r"^Lote acima do limite de (?P<n>\d+) itens$", r"Lote por encima del límite de \g<n> ítems",
     "Lote acima do limite de 200 itens"),
    (r"^Arquivo acima do limite de (?P<n>\d+) bytes$", r"Archivo por encima del límite de \g<n> bytes",
     "Arquivo acima do limite de 10485760 bytes"),
    (r"^Itens com identificador duplicado no lote$", "Ítems con identificador duplicado en el lote",
     "Itens com identificador duplicado no lote"),
    (r"^Sublotes com identificador duplicado$", "Sublotes con identificador duplicado",
     "Sublotes com identificador duplicado"),
    (r"^`formato` deve ser 'json' ou 'csv' — recebi (?P<r>.+)$",
     r"`formato` debe ser 'json' o 'csv' — recibí \g<r>",
     "`formato` deve ser 'json' ou 'csv' — recebi 'xlsx'"),
    (r"^(?P<c>`[^`]+`) deve ser (?P<t>um objeto|uma lista) JSON — recebi (?P<r>.+)$",
     lambda m: f"{m.group('c')} debe ser {'un objeto' if m.group('t') == 'um objeto' else 'una lista'} JSON — recibí {m.group('r')}",
     "`data` deve ser um objeto JSON — recebi texto"),
    (r"^JSON inválido no parâmetro data: (?P<r>.+)$", r"JSON inválido en el parámetro data: \g<r>",
     "JSON inválido no parâmetro data: Expecting value: line 1 column 1 (char 0)"),
    # --- gateway: jobs ---------------------------------------------------------
    (r"^campo obrigatório: (?P<c>\w+)(?: \(não vazio\))?$",
     lambda m: f"campo obligatorio: {m.group('c')}" + (" (no vacío)" if "não vazio" in m.group(0) else ""),
     "campo obrigatório: boletos (não vazio)"),
    (r"^Job acima do limite de (?P<n>\d+) (?P<u>itens|títulos)$",
     lambda m: f"Job por encima del límite de {m.group('n')} " + ("ítems" if m.group("u") == "itens" else "títulos"),
     "Job acima do limite de 200 itens"),
    (r"^job não encontrado para o tenant$", "job no encontrado para el tenant", "job não encontrado para o tenant"),
    (r"^item não encontrado no job$", "ítem no encontrado en el job", "item não encontrado no job"),
    (r"^artefatos? expirados?$", "artefactos expirados", "artefatos expirados"),
    (r"^artefato não encontrado$", "artefacto no encontrado", "artefato não encontrado"),
    (r"^arquivos expirados$", "archivos expirados", "arquivos expirados"),
    (r"^arquivo não encontrado$", "archivo no encontrado", "arquivo não encontrado"),
    # --- gateway: roteamento, credenciais, upstream ---------------------------
    (r"^banco (?P<b>'[^']*') não tem caminho (?P<c>'[^']*'); com (?P<c2>'[^']*'): (?P<l>.+)$",
     r"el banco \g<b> no tiene camino \g<c>; con \g<c2>: \g<l>",
     "banco 'inter' não tem caminho 'off'; com 'off': banco_brasil, bradesco"),
    (r"^banco (?P<b>'[^']*') não tem caminho (?P<c>'[^']*'); disponíveis: (?P<l>.+)$",
     r"el banco \g<b> no tiene camino \g<c>; disponibles: \g<l>",
     "banco 'bradesco' não tem caminho 'on'; disponíveis: c6, sicoob, inter, itau"),
    (r"^banco (?P<b>'[^']*') não é tratado; use um destes: (?P<l>.+)$",
     r"el banco \g<b> no se reconoce; use uno de estos: \g<l>",
     "banco 'xpto' não é tratado; use um destes: c6, sicoob"),
    (r"^informe o `banco` \(caminho (?P<c>'[^']*')\); (?P<l>.+)$",
     r"informe el `banco` (camino \g<c>); \g<l>",
     "informe o `banco` (caminho 'on'); c6, sicoob, inter, itau"),
    (r"^operação só existe no caminho ON \(API do banco\); bancos com ON: (?P<l>.+)$",
     r"la operación solo existe en el camino ON (API del banco); bancos con ON: \g<l>",
     "operação só existe no caminho ON (API do banco); bancos com ON: c6, sicoob"),
    (r"^registro em processamento no banco \(CIP\); re-tente em instantes$",
     "registro en procesamiento en el banco (CIP); reintente en instantes",
     "registro em processamento no banco (CIP); re-tente em instantes"),
    (r"^este banco não suporta alteração online; baixe e reemita$",
     "este banco no soporta modificación online; dé de baja y reemita",
     "este banco não suporta alteração online; baixe e reemita"),
    (r"^banco indisponível ou tempo esgotado$", "banco no disponible o tiempo agotado",
     "banco indisponível ou tempo esgotado"),
    (r"^credenciais do tenant/banco ausentes no cofre$", "credenciales del tenant/banco ausentes en la bóveda",
     "credenciais do tenant/banco ausentes no cofre"),
    (r"^o banco recusou os dados enviados$", "el banco rechazó los datos enviados", "o banco recusou os dados enviados"),
    (r"^credenciais do banco rejeitadas \(401/403 no upstream\)$",
     "credenciales del banco rechazadas (401/403 en el upstream)",
     "credenciais do banco rejeitadas (401/403 no upstream)"),
    (r"^credenciais do banco rejeitadas na autenticação$", "credenciales del banco rechazadas en la autenticación",
     "credenciais do banco rejeitadas na autenticação"),
    (r"^recurso não encontrado no banco$", "recurso no encontrado en el banco", "recurso não encontrado no banco"),
    (r"^operação não suportada pelo banco para este recurso$",
     "operación no soportada por el banco para este recurso",
     "operação não suportada pelo banco para este recurso"),
    (r"^conflito no banco \(registro já existe ou estado não permite\)$",
     "conflicto en el banco (el registro ya existe o el estado no lo permite)",
     "conflito no banco (registro já existe ou estado não permite)"),
    (r"^limite de requisições do banco atingido$", "límite de solicitudes del banco alcanzado",
     "limite de requisições do banco atingido"),
    (r"^erro na API do banco$", "error en la API del banco", "erro na API do banco"),
    (r"^corpo deve conter valor$", "el cuerpo debe contener valor", "corpo deve conter valor"),
    (r"^corpo do webhook não é JSON$", "el cuerpo del webhook no es JSON", "corpo do webhook não é JSON"),
    (r"^corpo do webhook vazio$", "cuerpo del webhook vacío", "corpo do webhook vazio"),
    (r"^informe url_recorrencia e/ou url_cobranca$", "informe url_recorrencia y/o url_cobranca",
     "informe url_recorrencia e/ou url_cobranca"),
    # --- engine pyCobrança (mensagens literais de `raise`) ---------------------
    (r"^Banco não registrado: (?P<r>.+)$", r"Banco no registrado: \g<r>", "Banco não registrado: '999'"),
    (r"^Tipo de convênio não implementado\.$", "Tipo de convenio no implementado.", "Tipo de convênio não implementado."),
    (r"^arquivo de retorno vazio \(nenhuma linha com conteúdo\)$",
     "archivo de retorno vacío (ninguna línea con contenido)",
     "arquivo de retorno vazio (nenhuma linha com conteúdo)"),
    (r"^banco (?P<b>.+?) não suporta PIX$", r"el banco \g<b> no soporta PIX", "banco 041 (Banrisul) não suporta PIX"),
    (r"^bank (?P<b>.+?) não corresponde a banco suportado$", r"bank \g<b> no corresponde a un banco soportado",
     "bank 'xpto' não corresponde a banco suportado"),
    (r"^byte_idt é obrigatório \(1=agência, 2-9=beneficiário\)$",
     "byte_idt es obligatorio (1=sucursal, 2-9=beneficiario)",
     "byte_idt é obrigatório (1=agência, 2-9=beneficiário)"),
    (r"^campo EMV (?P<i>\S+) excede 99 caracteres: (?P<n>\d+)$", r"el campo EMV \g<i> excede 99 caracteres: \g<n>",
     "campo EMV 26 excede 99 caracteres: 120"),
    (r"^campo livre deve ter 25 dígitos: (?P<r>.+)$", r"el campo libre debe tener 25 dígitos: \g<r>",
     "campo livre deve ter 25 dígitos: '123'"),
    (r"^chave PIX é obrigatória$", "la clave PIX es obligatoria", "chave PIX é obrigatória"),
    (r"^cidade do recebedor é obrigatória$", "la ciudad del receptor es obligatoria", "cidade do recebedor é obrigatória"),
    (r"^nome do recebedor é obrigatório$", "el nombre del receptor es obligatorio", "nome do recebedor é obrigatório"),
    (r"^conteúdo não parece um OFX \(faltam <OFX>/OFXHEADER\)$",
     "el contenido no parece un OFX (faltan <OFX>/OFXHEADER)",
     "conteúdo não parece um OFX (faltam <OFX>/OFXHEADER)"),
    (r"^código de barras deve ter 44 dígitos: (?P<r>.+)$", r"el código de barras debe tener 44 dígitos: \g<r>",
     "código de barras deve ter 44 dígitos: '123'"),
    (r"^código deve conter apenas dígitos: (?P<r>.+)$", r"el código debe contener solo dígitos: \g<r>",
     "código deve conter apenas dígitos: 'AB'"),
    (r"^código do cedente \(convênio/conta\) deve ter no máximo 7 dígitos$",
     "el código del beneficiario (convenio/cuenta) debe tener como máximo 7 dígitos",
     "código do cedente (convênio/conta) deve ter no máximo 7 dígitos"),
    (r"^código do cedente \(convênio/conta\) é obrigatório$",
     "el código del beneficiario (convenio/cuenta) es obligatorio",
     "código do cedente (convênio/conta) é obrigatório"),
    (r"^data_vencimento é obrigatória para carteira CNR$", "data_vencimento es obligatoria para la cartera CNR",
     "data_vencimento é obrigatória para carteira CNR"),
    (r"^digito_agencia e digito_conta são obrigatórios para o Safra$",
     "digito_agencia y digito_conta son obligatorios para Safra",
     "digito_agencia e digito_conta são obrigatórios para o Safra"),
    (r"^empresa_mae obrigatória$", "empresa_mae obligatoria", "empresa_mae obrigatória"),
    (r"^fator de vencimento fora do intervalo \((?P<l>.+?)\): (?P<r>.+)$",
     r"factor de vencimiento fuera del intervalo (\g<l>): \g<r>",
     "fator de vencimento fora do intervalo (>9999): 2200-01-01"),
    (r"^fator de vencimento inválido: (?P<r>.+)$", r"factor de vencimiento inválido: \g<r>",
     "fator de vencimento inválido: 'abcd'"),
    (r"^fator inválido: (?P<r>.+)$", r"factor inválido: \g<r>", "fator inválido: 0"),
    (r"^incremento \(3 dígitos\) é obrigatório para o BRB$", "incremento (3 dígitos) es obligatorio para BRB",
     "incremento (3 dígitos) é obrigatório para o BRB"),
    (r"^pagamento PIX incompleto: (?P<r>.+)$", r"pago PIX incompleto: \g<r>", "pagamento PIX incompleto: codigo_chave_dict"),
    (r"^remessa sem pagamentos$", "remesa sin pagos", "remessa sem pagamentos"),
    (r"^schema desconhecido: (?P<r>.+)$", r"schema desconocido: \g<r>", "schema desconhecido: 'xpto'"),
    (r"^sequência sem dígitos: (?P<r>.+)$", r"secuencia sin dígitos: \g<r>", "sequência sem dígitos: 'abc'"),
    (r"^txid inválido \(A-Za-z0-9, até 25\): (?P<r>.+)$", r"txid inválido (A-Za-z0-9, hasta 25): \g<r>",
     "txid inválido (A-Za-z0-9, até 25): 'a-b'"),
    (r"^valor deve ser positivo: (?P<r>.+)$", r"el valor debe ser positivo: \g<r>", "valor deve ser positivo: Decimal('0')"),
    (r"^valor em centavos inválido: (?P<r>.+)$", r"valor en centavos inválido: \g<r>", "valor em centavos inválido: 'x'"),
    (r"^valor monetário inválido: (?P<r>.+)$", r"valor monetario inválido: \g<r>", "valor monetário inválido: 'abc'"),
    (r"^vencimento anterior à base do fator: (?P<r>.+)$", r"vencimiento anterior a la base del factor: \g<r>",
     "vencimento anterior à base do fator: 1990-01-01"),
    (r"^(?P<p>\S+): esperado array$", r"\g<p>: se esperaba un array", "Remessa.pagamentos: esperado array"),
    (r"^(?P<p>\S+): esperado (?P<t>\S+), recebido bool$", r"\g<p>: se esperaba \g<t>, se recibió bool",
     "Remessa.valor: esperado number, recebido bool"),
    (r"^(?P<p>\S+): valor (?P<v>.+) fora do enum$", r"\g<p>: valor \g<v> fuera del enum",
     "Pagamento.tipo_mora: valor '9' fora do enum"),
    (r"^campo obrigatório ausente: (?P<c>.+)$", r"campo obligatorio ausente: \g<c>",
     "campo obrigatório ausente: data_vencimento"),
    (r"^data_documento é obrigatória para o Sicredi \(ano do nosso número\)$",
     "data_documento es obligatoria para Sicredi (año del nosso número)",
     "data_documento é obrigatória para o Sicredi (ano do nosso número)"),
    (r"^data_multa deve ser posterior ao vencimento \(nota 6\.1\.5\)$",
     "data_multa debe ser posterior al vencimiento (nota 6.1.5)",
     "data_multa deve ser posterior ao vencimento (nota 6.1.5)"),
    (r"^data_multa é obrigatória quando há multa \(posições 206–211\)$",
     "data_multa es obligatoria cuando hay multa (posiciones 206–211)",
     "data_multa é obrigatória quando há multa (posições 206–211)"),
    (r"^dias_limite_pagamento deve estar entre 01 e 60$", "dias_limite_pagamento debe estar entre 01 y 60",
     "dias_limite_pagamento deve estar entre 01 e 60"),
    (r"^digito_conta é obrigatório \(item 06 do registro tipo 1\)$",
     "digito_conta es obligatorio (ítem 06 del registro tipo 1)",
     "digito_conta é obrigatório (item 06 do registro tipo 1)"),
    (r"^uf_sacado deve ter 2 letras$", "uf_sacado debe tener 2 letras", "uf_sacado deve ter 2 letras"),
    (r"^valor deve ser positivo$", "el valor debe ser positivo", "valor deve ser positivo"),
    (r"^Dados de PIX inválidos para montagem do BR Code\.$", "Datos de PIX inválidos para montar el BR Code.",
     "Dados de PIX inválidos para montagem do BR Code."),
    (r"^banco_cobrador (?P<v>.+?) inválido \(use um de: (?P<l>.+)\)$",
     r"banco_cobrador \g<v> inválido (use uno de: \g<l>)",
     "banco_cobrador '999' inválido (use um de: 001, 237)"),
    (r"^bloco de fatura inválido: (?P<v>.+?) \(use um de: (?P<l>.+)\)$",
     r"bloque de factura inválido: \g<v> (use uno de: \g<l>)",
     "bloco de fatura inválido: 'xpto' (use um de: campos, tabela, texto)"),
    (r"^modelo inválido: (?P<v>.+?) \(use 'classico' ou 'moderno'\)$",
     r"modelo inválido: \g<v> (use 'classico' o 'moderno')",
     "modelo inválido: 'xpto' (use 'classico' ou 'moderno')"),
    (r"^combinação inválida no Banco do Nordeste: (?P<r>.+)$",
     lambda m: "combinación inválida en Banco do Nordeste: " + traduzir_mensagem(m.group("r"), "es"),
     "combinação inválida no Banco do Nordeste: carteira '21' com convênio de 6 dígitos"),
    (r"^(?P<c>\w+) (?P<q>'[^']*') não suportad[ao] \(use uma de: (?P<l>.+)\)$",
     r"\g<c> \g<q> no soportada (use una de: \g<l>)",
     "carteira '1' não suportada (use uma de: 10, 20)"),
    (r"^(?P<c>[\wçãéêíóõú ]+?) deve ter (?P<r>.+?) dígitos(?P<s> para este convênio)?$",
     lambda m: (f"{m.group('c').replace('convênio', 'convenio')} debe tener "
                f"{m.group('r').replace('no máximo', 'como máximo').replace(' ou ', ' o ')} dígitos"
                + (" para este convenio" if m.group("s") else "")),
     "nosso número deve ter no máximo 10 dígitos para este convênio"),
    (r"^(?P<c>\w+) é obrigatóri[oa](?: para o (?P<b>.+))?$",
     lambda m: f"{m.group('c')} es obligatorio" + (f" para {m.group('b')}" if m.group("b") else ""),
     "documento_cedente é obrigatório para o CrediSIS"),
    (r"^(?P<c>\w+) inválid[oa]$", r"\g<c> inválido", "carteira inválida"),
    # --- Pydantic (inglês → espanhol) ------------------------------------------
    (r"^Field required$", "Campo obligatorio", "Field required"),
    (r"^Extra inputs are not permitted$", "No se permiten campos adicionales", "Extra inputs are not permitted"),
    (r"^Input should be a valid string$", "La entrada debe ser una cadena válida", "Input should be a valid string"),
    (r"^Input should be a valid integer.*$", "La entrada debe ser un entero válido",
     "Input should be a valid integer, unable to parse string as an integer"),
    (r"^Input should be a valid number.*$", "La entrada debe ser un número válido",
     "Input should be a valid number, unable to parse string as a number"),
    (r"^Input should be a valid boolean.*$", "La entrada debe ser un booleano válido",
     "Input should be a valid boolean, unable to interpret input"),
    (r"^Input should be a valid date.*$", "La entrada debe ser una fecha válida",
     "Input should be a valid date or datetime, input is too short"),
    (r"^Input should be a valid dictionary.*$", "La entrada debe ser un objeto JSON válido",
     "Input should be a valid dictionary or object to extract fields from"),
    (r"^Input should be a valid list.*$", "La entrada debe ser una lista válida", "Input should be a valid list"),
    (r"^Input should be a valid URL.*$", "La entrada debe ser una URL válida",
     "Input should be a valid URL, relative URL without a base"),
    (r"^Input should be greater than or equal to (?P<n>.+)$", r"La entrada debe ser mayor o igual que \g<n>",
     "Input should be greater than or equal to 1"),
    (r"^Input should be greater than (?P<n>.+)$", r"La entrada debe ser mayor que \g<n>",
     "Input should be greater than 0"),
    (r"^Input should be less than or equal to (?P<n>.+)$", r"La entrada debe ser menor o igual que \g<n>",
     "Input should be less than or equal to 500"),
    (r"^Input should be less than (?P<n>.+)$", r"La entrada debe ser menor que \g<n>",
     "Input should be less than 100"),
    (r"^String should have at most (?P<n>\d+) characters?$", r"La cadena debe tener como máximo \g<n> caracteres",
     "String should have at most 25 characters"),
    (r"^String should have at least (?P<n>\d+) characters?$", r"La cadena debe tener al menos \g<n> caracteres",
     "String should have at least 26 characters"),
    (r"^String should match pattern (?P<p>.+)$", r"La cadena debe coincidir con el patrón \g<p>",
     "String should match pattern '^[A-Z0-9]{26}$'"),
    (r"^List should have at least (?P<n>\d+) items? after validation.*$",
     r"La lista debe tener al menos \g<n> ítem(s)",
     "List should have at least 1 item after validation, not 0"),
    (r"^Input should be (?P<l>'.+')$", lambda m: "La entrada debe ser " + m.group("l").replace(" or ", " o "),
     "Input should be 'on', 'off' or 'c6'"),
    (r"^JSON decode error$", "Error al decodificar el JSON", "JSON decode error"),
    (r"^Invalid JSON: (?P<r>.+)$", r"JSON inválido: \g<r>", "Invalid JSON: expected value at line 1 column 1"),
    (r"^Value error, (?P<r>.+)$", lambda m: "Error de valor, " + traduzir_mensagem(m.group("r"), "es"),
     "Value error, valor deve ser positivo: 0"),
]

#: Vocabulário de reserva, para mensagem que nenhuma regra acima casou. Só
#: palavras inequívocas, por fronteira de palavra, e com crases/aspas/nomes de
#: banco protegidos antes. Não tenta ser gramática; tenta não deixar
#: português óbvio passar.
#:
#: Aplicado em UMA passada, como alternativas de um regex só, casando sempre
#: sobre o texto ORIGINAL: a versão sequencial traduzia "não" para "no" e, três
#: regras depois, lia esse "no" como o português de "em o" — "Banco não
#: suportado" virava "Banco en el soportado", e a negação sumia da frase. A
#: ordem ainda importa: alternativa mais longa antes do seu prefixo.
VOCABULARIO: list[tuple[str, str | Any]] = [
    (r"\bnão suportad[oa]s?\b", lambda s: "no soportad" + s[len("não suportad"):]),
    (r"\bdeve ter no máximo\b", "debe tener como máximo"),
    (r"\bdeve ter no mínimo\b", "debe tener como mínimo"),
    (r"\bdevem? ter\b", "debe tener"),
    (r"\bdevem? ser\b", "debe ser"),
    (r"\bdevem? conter\b", "debe contener"),
    (r"\bnão pode ser\b", "no puede ser"),
    (r"\bpode ser\b", "puede ser"),
    (r"\bzero\b", "cero"),
    (r"\bé obrigatória\b", "es obligatoria"),
    (r"\bé obrigatório\b", "es obligatorio"),
    (r"\bsão obrigatóri[oa]s\b", "son obligatorios"),
    (r"\bobrigatóri[oa]\b", "obligatorio"),
    (r"\buse uma de:", "use una de:"),
    (r"\buse um de:", "use uno de:"),
    (r"\bdesconhecid[oa]\b", lambda s: "desconocid" + s[-1]),
    (r"\bconvênio\b", "convenio"),
    (r"\barquivos?\b", lambda s: "archivos" if s.endswith("s") else "archivo"),
    (r"\bitens\b", "ítems"),
    (r"\bacima do limite de\b", "por encima del límite de"),
    (r"\bvazi[oa]\b", "vacío"),
    (r"\bcorpo\b", "cuerpo"),
    (r"\bchave\b", "clave"),
    (r"\blinhas\b", "líneas"),
    (r"\blinha\b", "línea"),
    (r"\bpara o\b", "para el"),
    (r"\bpara a\b", "para la"),
    (r"\bnão\b", "no"),
    (r"\bou\b", "o"),
    (r"\be\b", "y"),
    (r"\bem\b", "en"),
    (r"\bcom\b", "con"),
    (r"\bsem\b", "sin"),
    (r"\bdo\b", "del"),
    (r"\bda\b", "de la"),
    (r"\bdos\b", "de los"),
    (r"\bdas\b", "de las"),
    (r"\bno\b", "en el"),
    (r"\bna\b", "en la"),
    (r"\bnos\b", "en los"),
    (r"\bnas\b", "en las"),
    (r"\baté\b", "hasta"),
    (r"\bapós\b", "después de"),
    (r"\bjá\b", "ya"),
    (r"\bmesmo\b", "mismo"),
    (r"\bé\b", "es"),
    (r"\bsão\b", "son"),
]

_REGRAS = [(re.compile(p), r) for p, r, _ in REGRAS]
#: Um regex só, uma alternativa nomeada por entrada do vocabulário.
_VOCAB_UNICO = re.compile("|".join(f"(?P<v{i}>{p})" for i, (p, _) in enumerate(VOCABULARIO)))


def _substituir_vocabulo(m: re.Match) -> str:
    _, subst = VOCABULARIO[int(m.lastgroup[1:])]
    return subst(m.group(0)) if callable(subst) else subst


_PROTEGIDO = re.compile(r"`[^`]*`|'[^']*'|\"[^\"]*\"")


def _nomes_de_banco() -> list[str]:
    """Nomes de exibição dos bancos da engine ("Banco do Brasil", "Banco do
    Nordeste"…), do mais longo ao mais curto, para proteger antes do
    vocabulário de reserva."""
    from app.core import pycob
    nomes = set()
    for slug in pycob.bancos_suportados():
        try:
            nomes.add(str(pycob._classe_banco(slug).nome))
        except Exception:  # banco sem classe carregável: nada a proteger dele
            continue
    return sorted((n for n in nomes if n), key=len, reverse=True)


_BANCOS: list[str] | None = None


def traduzir_mensagem(texto: str, idioma: str = "es") -> str:
    """Uma mensagem, no idioma. `pt` devolve o texto intacto."""
    global _BANCOS
    if idioma == "pt" or not isinstance(texto, str) or not texto:
        return texto
    for regex, subst in _REGRAS:
        m = regex.match(texto)
        if m:
            return regex.sub(subst, texto, count=1)
    # Reserva: protege crases, aspas e nomes de banco; traduz o vocabulário.
    if _BANCOS is None:
        _BANCOS = _nomes_de_banco()
    guardados: list[str] = []

    def guardar(m: re.Match) -> str:
        guardados.append(m.group(0))
        return f"\x00{len(guardados) - 1}\x00"

    protegido = _PROTEGIDO.sub(guardar, texto)
    for nome in _BANCOS:
        if nome in protegido:
            guardados.append(nome)
            protegido = protegido.replace(nome, f"\x00{len(guardados) - 1}\x00")
    protegido = _VOCAB_UNICO.sub(_substituir_vocabulo, protegido)
    return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], protegido)


def traduzir_corpo(dados: Any, idioma: str) -> Any:
    """Percorre o JSON e traduz só o que é mensagem (ver CHAVES_DE_MENSAGEM)."""
    if isinstance(dados, dict):
        novo = {}
        for k, v in dados.items():
            if k in CHAVES_DE_MENSAGEM:
                if isinstance(v, str):
                    novo[k] = traduzir_mensagem(v, idioma)
                elif isinstance(v, list):
                    novo[k] = [traduzir_mensagem(i, idioma) if isinstance(i, str)
                               else traduzir_corpo(i, idioma) for i in v]
                else:
                    novo[k] = traduzir_corpo(v, idioma)
            else:
                novo[k] = traduzir_corpo(v, idioma)
        return novo
    if isinstance(dados, list):
        return [traduzir_corpo(i, idioma) for i in dados]
    return dados


#: Respostas que carregam erro por ITEM dentro de um 200: o estado de um job
#: (`GET /jobs/...`) lista cada item falhado com `errors`. É erro para quem lê,
#: com outro status — entra pelo caminho, não pelo código.
_PREFIXOS_COM_ERRO_NO_200 = ("/jobs/",)


def _vale_traduzir(status: int, caminho: str, tipo: str) -> bool:
    if "json" not in tipo:
        return False
    if status >= 400 or status == 201:
        return True
    return status == 200 and caminho.startswith(_PREFIXOS_COM_ERRO_NO_200)


class ErrosNoIdiomaDoChamador:
    """Middleware ASGI puro: reescreve o corpo das respostas de erro em JSON
    quando o chamador pediu outro idioma. Sem `Accept-Language`/`lang`, não
    toca em nada — nem lê o corpo. Quando lê e nada muda, devolve a resposta
    como veio, sem `Content-Language`: rotular de `es` um corpo que continua
    igual mentiria para cache e cliente."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cabecalhos = Headers(scope=scope)
        lang_query = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("lang", [None])[0]
        idioma = idioma_pedido(cabecalhos.get("accept-language"), lang_query)
        if idioma == "pt":
            return await self.app(scope, receive, send)

        caminho = scope.get("path", "")
        inicio: dict | None = None
        corpo = bytearray()

        async def enviar(mensagem):
            nonlocal inicio
            if mensagem["type"] == "http.response.start":
                tipo = Headers(raw=mensagem["headers"]).get("content-type", "")
                if _vale_traduzir(mensagem["status"], caminho, tipo):
                    inicio = mensagem
                    return
                return await send(mensagem)
            if mensagem["type"] == "http.response.body" and inicio is not None:
                corpo.extend(mensagem.get("body", b""))
                if mensagem.get("more_body"):
                    return
                original = bytes(corpo)
                novo = original
                # O 201 só interessa quando é o `status: "erro"` do POST /cobranca
                # (erro com outro número). Um 201 de sucesso nem é parseado.
                if inicio["status"] != 201 or b'"erro"' in original:
                    try:
                        dados = json.loads(original)
                        if inicio["status"] != 201 or dados.get("status") == "erro":
                            traduzido = traduzir_corpo(dados, idioma)
                            if traduzido != dados:
                                novo = json.dumps(traduzido, ensure_ascii=False).encode()
                    except (ValueError, AttributeError):
                        pass
                if novo is not original:
                    h = MutableHeaders(raw=inicio["headers"])
                    h["content-length"] = str(len(novo))
                    h["content-language"] = idioma
                    h.append("vary", "Accept-Language")
                await send(inicio)
                return await send({"type": "http.response.body", "body": novo})
            return await send(mensagem)

        await self.app(scope, receive, enviar)
