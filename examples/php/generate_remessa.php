<?php
/**
 * Arquivo de remessa CNAB via `POST /api/remessa`, com upload do JSON em
 * multipart/form-data. Espelho de `examples/python/generate_remessa.py`.
 *
 *     php generate_remessa.php
 *     API=https://meu-host php generate_remessa.php
 */
declare(strict_types=1);

$API = rtrim(getenv('API') ?: 'http://localhost:8000', '/');
$REMESSA_URL = "$API/api/remessa";
$OUTPUT_DIR = __DIR__ . '/../test_output';
if (!is_dir($OUTPUT_DIR)) {
    mkdir($OUTPUT_DIR, 0777, true);
}
$OUTPUT_DIR = realpath($OUTPUT_DIR);

$FALHAS = [];

// Formato padrão de pagamento esperado pela API (via FieldMapper)
$PAGAMENTO_C6 = [
    'nosso_numero' => '12345678',
    'data_vencimento' => '2026/12/31',
    'valor' => 1500.00,
    'nome_sacado' => 'Joao da Silva',
    'documento_sacado' => '12345678909',
    'endereco_sacado' => 'Rua Teste, 100',
    'bairro_sacado' => 'Centro',
    'cep_sacado' => '01000000',
    'cidade_sacado' => 'Sao Paulo',
    'uf_sacado' => 'SP',
];

$PAGAMENTO_SICOOB = [
    'nosso_numero' => '7890',
    'data_vencimento' => '2026/12/31',
    'valor' => 2500.00,
    'nome_sacado' => 'Maria Santos',
    'documento_sacado' => '98765432100',
    'endereco_sacado' => 'Av. Principal, 50',
    'bairro_sacado' => 'Centro',
    'cep_sacado' => '20000000',
    'cidade_sacado' => 'Rio de Janeiro',
    'uf_sacado' => 'RJ',
];

// Banco C6 — CNAB 400 (único tipo suportado)
// codigo_beneficiario: código do cedente fornecido pelo C6 (10 dígitos)
$DATA_C6 = [
    'empresa_mae' => 'Empresa C6 LTDA',
    'documento_cedente' => '33445566000186',
    'agencia' => '0001',
    'conta_corrente' => '1234567',
    'digito_conta' => '0',
    'carteira' => '10',
    'codigo_beneficiario' => '0012345678',
    'pagamentos' => [$PAGAMENTO_C6],
];

// Sicoob — CNAB 240 (único tipo suportado)
$DATA_SICOOB = [
    'empresa_mae' => 'Cooperativa Teste',
    'documento_cedente' => '98765432000198',
    'agencia' => '4327',
    'conta_corrente' => '417270',
    'convenio' => '229385',
    'carteira' => '1',
    'pagamentos' => [$PAGAMENTO_SICOOB],
];

/** Gera arquivo de remessa via POST /api/remessa com upload de arquivo JSON. */
function generate_remessa(string $name, string $bank, string $cnab_type, array $data): void
{
    global $REMESSA_URL, $OUTPUT_DIR, $FALHAS;

    // A remessa NÃO vai como corpo JSON — vai como ARQUIVO, no campo `data`.
    // Mandar o objeto direto no corpo responde `422 Field required: data`.
    $boundary = '------------------------abcdef1234567890';
    $json = json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    $body = "--$boundary\r\n"
        . "Content-Disposition: form-data; name=\"data\"; filename=\"$name.json\"\r\n"
        . "Content-Type: application/json\r\n\r\n"
        . $json . "\r\n--$boundary--\r\n";

    $ctx = stream_context_create(['http' => [
        'method'        => 'POST',
        'header'        => "Content-Type: multipart/form-data; boundary=$boundary\r\n",
        'content'       => $body,
        'ignore_errors' => true,
        'timeout'       => 60,
    ]]);
    $url = "$REMESSA_URL?bank=$bank&type=$cnab_type";
    $content = @file_get_contents($url, false, $ctx);
    if ($content === false) {
        $FALHAS[] = "$name $cnab_type: sem resposta de $REMESSA_URL — a API está no ar?";
        echo "[ERR] $name $cnab_type: sem resposta\n";
        return;
    }
    $status = (int) explode(' ', $http_response_header[0])[1];
    if ($status >= 400) {
        $FALHAS[] = "$name $cnab_type: HTTP $status — " . substr($content, 0, 200);
        echo "[ERR] $name $cnab_type: HTTP $status — $content\n";
        return;
    }
    $filename = "remessa_{$name}_{$cnab_type}.rem";
    file_put_contents("$OUTPUT_DIR/$filename", $content);
    printf("[OK] Gerada: %s (%d bytes)\n", $filename, strlen($content));
}

echo "Gerando arquivos de remessa em $OUTPUT_DIR...\n";
generate_remessa('c6', 'banco_c6', 'cnab400', $DATA_C6);
generate_remessa('sicoob', 'sicoob', 'cnab240', $DATA_SICOOB);

// Sem isto o script sai 0 mesmo quando nenhuma remessa foi gerada — em CI, um
// verde que não significa nada.
if ($FALHAS) {
    echo "\nFALHOU: " . count($FALHAS) . " remessa(s) não geradas.\n";
    foreach ($FALHAS as $f) {
        echo "  - $f\n";
    }
    exit(1);
}

echo "Concluído!\n";
