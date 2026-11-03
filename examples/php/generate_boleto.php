<?php
/**
 * O menor exemplo possível: uma cobrança pelos dois eixos — em PHP puro.
 *
 * `provider` diz o CAMINHO — `on` (API do banco) ou `off` (engine pyCobrança) —
 * e `banco` diz a INSTITUIÇÃO. Este script roda o caminho `off`, que não exige
 * credencial nem convênio no banco, e mostra o que muda para ir ao `on`.
 *
 *     php generate_boleto.php            # http://localhost:8000
 *     API=https://meu-host php generate_boleto.php
 *
 * Antes: `docker compose up --build` (ou `docker run -p 8000:8000
 * ghcr.io/maxwbh/cobranca-api:latest`).
 *
 * Sem Composer e sem extensão além de `json`: só `file_get_contents` com
 * contexto HTTP, que existe em qualquer PHP >= 7.4. É o espelho, rota a rota,
 * de `examples/python/generate_boleto.py` — um guarda no CI cobra que os dois
 * chamem as mesmas rotas.
 */
declare(strict_types=1);

$API = rtrim(getenv('API') ?: 'http://localhost:8000', '/');

$COBRANCA = [
    'tenant_id' => 'empresa_demo',
    // `off` = a engine pyCobrança, no próprio processo. Sem rede, sem convênio.
    // Para registrar NO BANCO: 'provider' => 'on' — e aí valem credencial
    // (POST /credenciais) e a flag <BANCO>_REGISTERED_READY no servidor.
    // `GET /bancos` responde o que ESTA instalação faz com cada banco.
    'provider' => 'off',
    'banco' => 'itau',
    'account_config' => [
        'agencia' => '3073',
        'conta_corrente' => '12345',
        'carteira' => '109',
        'convenio' => '1234567',
        'cedente' => 'M&S DO BRASIL LTDA',
        'documento_cedente' => '05230380000174',
    ],
    'cobranca' => [
        'valor' => '150.00',
        'vencimento' => '2027-12-31',
        'nosso_numero' => '123',
        'seu_numero' => 'PED-0001',
        'pagador' => ['nome' => 'Joao da Silva', 'documento' => '52998224725'],
    ],
];

function post(string $caminho, array $corpo): array
{
    global $API;
    $ctx = stream_context_create(['http' => [
        'method'        => 'POST',
        'header'        => "Content-Type: application/json\r\n",
        'content'       => json_encode($corpo, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
        'ignore_errors' => true,   // 4xx/5xx devolvem o corpo em vez de `false`
        'timeout'       => 60,
    ]]);
    $resposta = @file_get_contents("$API$caminho", false, $ctx);
    if ($resposta === false) {
        fwrite(STDERR, "não consegui falar com $API. A API está no ar?\n");
        exit(1);
    }
    // $http_response_header[0] é "HTTP/1.1 200 OK"
    $status = (int) explode(' ', $http_response_header[0])[1];
    if ($status >= 400) {
        // A API responde 422 dizendo PARA ONDE IR (por exemplo, quais bancos
        // têm o caminho pedido). Esconder o corpo aqui apagaria a resposta útil.
        fwrite(STDERR, "HTTP $status em $caminho: " . substr($resposta, 0, 400) . "\n");
        exit(1);
    }
    return json_decode($resposta, true, 512, JSON_THROW_ON_ERROR);
}

$registro = post('/cobranca', $COBRANCA);
if (($registro['status'] ?? '') === 'erro') {
    fwrite(STDERR, 'a API recusou os dados: '
        . json_encode($registro['raw'] ?? null, JSON_UNESCAPED_UNICODE) . "\n");
    exit(1);
}

printf("status          : %s\n", $registro['status']);
printf("linha digitável : %s\n", $registro['linha_digitavel']);
printf("código de barras: %s\n", $registro['codigo_barras']);

// O PDF: no caminho `off` quem desenha é a engine. No `on`, C6 e Inter devolvem
// o PDF na própria API; o Itaú não devolve — e aí `GET /cobranca/{id}/pdf`
// responde 422 apontando para cá, mandando conferir a linha digitável calculada
// contra a que o banco registrou. O código de barras é determinístico:
// renderizar com outro nosso número gera um boleto que ninguém concilia.
$render = post('/api/render/boleto', ['bank' => 'itau', 'data' => array_merge(
    $COBRANCA['account_config'],
    [
        'valor'            => (float) $COBRANCA['cobranca']['valor'],
        'data_vencimento'  => $COBRANCA['cobranca']['vencimento'],
        'nosso_numero'     => $COBRANCA['cobranca']['nosso_numero'],
        'sacado'           => $COBRANCA['cobranca']['pagador']['nome'],
        'sacado_documento' => $COBRANCA['cobranca']['pagador']['documento'],
    ]
)]);

if ($render['linha_digitavel'] !== $registro['linha_digitavel']) {
    fwrite(STDERR, "DIVERGE: o PDF não corresponde à cobrança registrada — não entregue ao pagador\n");
    exit(1);
}

$destino = __DIR__ . '/../test_output';
if (!is_dir($destino)) {
    mkdir($destino, 0777, true);
}
$arquivo = realpath($destino) . '/boleto.pdf';
file_put_contents($arquivo, base64_decode($render['pdf_base64']));
echo "PDF (com o logo do banco): $arquivo\n";
