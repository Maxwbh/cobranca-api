<?php
/**
 * 12 boletos de teste — 6 comuns e 6 com QR Pix — de C6 e Sicoob, via
 * `GET /api/boleto`, para conferência visual. Espelho de
 * `examples/python/generate_test_boletos.py`.
 *
 *     php generate_test_boletos.php
 *     API=https://meu-host php generate_test_boletos.php
 */
declare(strict_types=1);

$API = rtrim(getenv('API') ?: 'http://localhost:8000', '/');
$API_URL = "$API/api/boleto";
$OUTPUT_DIR = __DIR__ . '/../test_output';
if (!is_dir($OUTPUT_DIR)) {
    mkdir($OUTPUT_DIR, 0777, true);
}
$OUTPUT_DIR = realpath($OUTPUT_DIR);

// Payloads base. `moeda` e `especie` NÃO são campos da API (eram da gem Ruby):
// o gateway recusa campo desconhecido com 400. O rótulo da moeda, se quiser
// mudá-lo, é `especie_moeda` (padrão `R$`).
$BASE_C6 = [
    'cedente' => 'Empresa C6 LTDA',
    'documento_cedente' => '33445566000186',
    'sacado' => 'Pedro Almeida',
    'sacado_documento' => '33344455508',
    'sacado_endereco' => 'Av. Faria Lima, 1500, Itaim Bibi, Sao Paulo, SP, CEP 04538133',
    'agencia' => '0001',
    'conta_corrente' => '1234567',
    'digito_conta' => '0',
    'carteira' => '10',
    'convenio' => '100',
    'nosso_numero' => '12345678',
    'numero_documento' => 'INV-2026-001',
    'valor' => 2750.00,
    'data_vencimento' => '2026/12/31',
    'especie_documento' => 'DM',
    'aceite' => 'N',
    'local_pagamento' => 'Pagavel em qualquer banco',
    'instrucao1' => 'Apos vencimento cobrar multa de 2%',
    'data_documento' => '2026/04/09',
];

$BASE_SICOOB = [
    'cedente' => 'Cooperativa Teste',
    'documento_cedente' => '98765432000198',
    'sacado' => 'Maria Santos',
    'sacado_documento' => '98765432100',
    'sacado_endereco' => 'Av. Principal, 50, Bairro, Rio de Janeiro, RJ, CEP 20000000',
    'agencia' => '4327',
    'conta_corrente' => '417270',
    'carteira' => '1',
    'variacao' => '01',
    'convenio' => '229385',
    'nosso_numero' => '7890',
    'numero_documento' => 'NF-2025-1234',
    'valor' => 2500.00,
    'data_vencimento' => '2027/12/31',
    'especie_documento' => 'DM',
    'aceite' => 'N',
    'local_pagamento' => 'Pagavel em qualquer banco ate o vencimento',
    'instrucao1' => 'Não receber após 30 dias',
    'data_documento' => '2026/11/26',
];

// Bolepix: quem desenha o QR é a CHAVE, não um payload pronto. A engine monta
// o EMV a partir de `chave_pix` (+ `tipo_chave_pix`, e `txid` se você quiser
// rastrear a transação) e desenha o QR no PDF. `emv` e `pix_label` são da era
// Ruby e respondem 400.
$PIX_C6 = ['chave_pix' => '33445566000186', 'tipo_chave_pix' => 'cnpj', 'txid' => 'C6TESTE001'];
$PIX_SICOOB = ['chave_pix' => '98765432000198', 'tipo_chave_pix' => 'cnpj', 'txid' => 'SICOOBTESTE1'];

$FALHAS = [];

function generate_boleto(string $bank, string $type_name, int $index, array $payload, string $template = 'moderno'): void
{
    global $API_URL, $OUTPUT_DIR, $FALHAS;
    $p = $payload;
    $p['nosso_numero'] = (string) ((int) $payload['nosso_numero'] + $index);
    $p['numero_documento'] = "{$payload['numero_documento']}-$index";
    $p['valor'] = $payload['valor'] + $index * 100.50;

    $url = $API_URL . '?' . http_build_query([
        'bank' => $bank,
        'type' => 'pdf',
        'template' => $template,
        'data' => json_encode($p, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
    ]);

    $ctx = stream_context_create(['http' => ['ignore_errors' => true, 'timeout' => 60]]);
    $corpo = @file_get_contents($url, false, $ctx);
    if ($corpo === false) {
        $FALHAS[] = "$bank $type_name $index: sem resposta de $API_URL — a API está no ar?";
        echo "[ERR] $bank $type_name $index: sem resposta\n";
        return;
    }
    $status = (int) explode(' ', $http_response_header[0])[1];
    if ($status !== 200) {
        // O corpo do 400 traz `validation_errors` dizendo QUAL campo recusou —
        // engolir isso obriga quem roda o exemplo a adivinhar.
        $detalhe = substr($corpo, 0, 300);
        $FALHAS[] = "$bank $type_name $index: HTTP $status $detalhe";
        echo "[ERR] $bank $type_name $index: HTTP $status — $detalhe\n";
        return;
    }
    $filename = "{$bank}_{$type_name}_{$index}.pdf";
    file_put_contents("$OUTPUT_DIR/$filename", $corpo);
    printf("[OK] Gerado: %s (R$ %.2f)\n", $filename, $p['valor']);
}

echo "Iniciando geracao de boletos de teste em $OUTPUT_DIR...\n";

// 3 padrao
for ($i = 1; $i <= 3; $i++) {
    generate_boleto('banco_c6', 'padrao', $i, $BASE_C6, 'moderno');
    generate_boleto('sicoob', 'padrao', $i, $BASE_SICOOB, 'moderno');
}

// 3 pix
for ($i = 1; $i <= 3; $i++) {
    generate_boleto('banco_c6', 'pix', $i, array_merge($BASE_C6, $PIX_C6), 'moderno');
    generate_boleto('sicoob', 'pix', $i, array_merge($BASE_SICOOB, $PIX_SICOOB), 'moderno');
}

// Carnê NÃO é template de boleto: é o endpoint POST /api/render/carne, que
// recebe a lista de parcelas e devolve 3 vias por folha A4.

// Sem isto o script sairia 0 mesmo com os 12 falhando — em CI, um verde que
// não significa nada.
if ($FALHAS) {
    echo "\nFALHOU: " . count($FALHAS) . " de 12 boletos não foram gerados.\n";
    foreach ($FALHAS as $f) {
        echo "  - $f\n";
    }
    exit(1);
}

// 200 não prova QR. Status 200, arquivo gravado, e o PDF "pix" byte a byte do
// mesmo tamanho do padrão foi exatamente o defeito que estes seis boletos
// esconderam por meses. Conferir o ARQUIVO pega — o QR ocupa uns 4 KB.
foreach (['banco_c6', 'sicoob'] as $banco) {
    for ($i = 1; $i <= 3; $i++) {
        $padrao = filesize("$OUTPUT_DIR/{$banco}_padrao_$i.pdf");
        $pix = filesize("$OUTPUT_DIR/{$banco}_pix_$i.pdf");
        if ($pix <= $padrao) {
            echo "\nFALHOU: {$banco}_pix_$i.pdf ($pix B) não é maior que o padrão"
                . " ($padrao B) — o QR Pix não foi desenhado.\n";
            exit(1);
        }
    }
}

echo "Pronto! Os 12 boletos de teste foram salvos em $OUTPUT_DIR.\n";
echo "Os 6 com Pix trazem o QR — conferido pelo tamanho do arquivo.\n";
