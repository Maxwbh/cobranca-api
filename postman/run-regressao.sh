#!/usr/bin/env bash
#
# Regressão completa no HML injetando os segredos por --env-var.
#
# Os environments versionados têm os segredos VAZIOS de propósito. Este script
# lê tudo de variáveis de ambiente do shell e passa para o newman em memória —
# nada de segredo em arquivo, em git ou na linha de comando do histórico.
#
# Uso:
#   export COB_CHAVE_PIX='...'            # e as demais (ver TABELA abaixo)
#   ./postman/run-regressao.sh            # regressão completa
#   ./postman/run-regressao.sh --smoke    # só o smoke (< 5 min)
#
# Carregar de um arquivo .env NÃO versionado:
#   set -a; source .secrets.env; set +a; ./postman/run-regressao.sh
#
set -uo pipefail
cd "$(dirname "$0")/.."

COLECAO="postman/cobranca-api.postman_collection.json"
AMBIENTE="${COB_ENV_FILE:-postman/hml.postman_environment.json}"
SAIDA="postman/reports"

# TABELA: variável do shell -> variável da coleção
#   *_OBRIGATORIA marca o que precisa estar preenchido para a suíte fechar 100%.
declare -A MAPA=(
  [COB_CHAVE_PIX]=chave_pix
  [COB_AGENCIA]=agencia
  [COB_CONTA]=conta
  [COB_CONVENIO]=convenio
  [COB_E2EID]=e2eid
  [COB_WEBHOOK_TOKEN]=webhook_token
  [COB_C6_CLIENT_ID]=c6_client_id
  [COB_C6_CLIENT_SECRET]=c6_client_secret
  [COB_C6_PFX_BASE64]=c6_pfx_base64
  [COB_C6_PFX_PASSWORD]=c6_pfx_password
  [COB_SICOOB_CLIENT_ID]=sicoob_client_id
  [COB_SICOOB_ACCESS_TOKEN]=sicoob_access_token
  [COB_SICOOB_CLIENT_SECRET]=sicoob_client_secret
  [COB_SICOOB_PFX_BASE64]=sicoob_pfx_base64
  [COB_SICOOB_PFX_PASSWORD]=sicoob_pfx_password
  [COB_TENANT_ID]=tenant_id
  [COB_BASE_URL]=base_url
)

# Quem fecha quais falhas conhecidas (usado só na mensagem de aviso).
declare -A PORQUE=(
  [COB_CHAVE_PIX]="BC-021/022 e SMK-09 (Pix cob/cobv)"
  [COB_SICOOB_CLIENT_SECRET]="BC-030/059 (Pix Automático exige OAuth+mTLS)"
  [COB_SICOOB_PFX_BASE64]="BC-030/059 (certificado mTLS do Sicoob)"
  [COB_SICOOB_PFX_PASSWORD]="BC-030/059 (senha do certificado)"
  [COB_AGENCIA]="BC-009 -> destrava cobranca_id (SMK-07, BC-010..013)"
  [COB_CONTA]="BC-009 -> destrava cobranca_id (SMK-07, BC-010..013)"
  [COB_CONVENIO]="BC-009 -> destrava cobranca_id (SMK-07, BC-010..013)"
  [COB_WEBHOOK_TOKEN]="BC-066/067 exercitam a ENTREGA do webhook; sem ele so se afirma o 401 fail-closed"
)

ARGS=()
PREENCHIDAS=0
for shell_var in "${!MAPA[@]}"; do
  valor="${!shell_var:-}"
  if [[ -n "$valor" ]]; then
    ARGS+=(--env-var "${MAPA[$shell_var]}=$valor")
    PREENCHIDAS=$((PREENCHIDAS + 1))
  fi
done

echo "==> ${PREENCHIDAS}/${#MAPA[@]} variáveis injetadas"
FALTAM=()
for shell_var in "${!PORQUE[@]}"; do
  [[ -z "${!shell_var:-}" ]] && FALTAM+=("$shell_var")
done
if ((${#FALTAM[@]})); then
  echo "==> Não preenchidas (as falhas abaixo são esperadas):"
  for v in $(printf '%s\n' "${FALTAM[@]}" | sort); do
    printf '      %-28s %s\n' "$v" "${PORQUE[$v]}"
  done
fi

# Janela do sandbox C6: fora dela a auth devolve 403 e a API responde 424.
HORA_BR=$(TZ=America/Sao_Paulo date +%H)
DIA_BR=$(TZ=America/Sao_Paulo date +%u)
if ((DIA_BR > 5)) || ((10#$HORA_BR < 7)) || ((10#$HORA_BR >= 23)); then
  echo "==> AVISO: fora da janela do sandbox C6 (seg-sex, 7h-23h BRT)."
  echo "    Agora: $(TZ=America/Sao_Paulo date '+%a %d/%m %H:%M') BRT — os requests online do C6 devolverão 424."
fi

PASTA=()
if [[ "${1:-}" == "--smoke" ]]; then
  PASTA=(--folder "SMK · Smoke (pre-deploy, < 5 min)")
  echo "==> Modo SMOKE"
fi

mkdir -p "$SAIDA"
echo "==> newman: $AMBIENTE"
newman run "$COLECAO" -e "$AMBIENTE" \
  "${ARGS[@]}" "${PASTA[@]}" \
  --timeout-request 120000 \
  -r cli,htmlextra,junit,json \
  --reporter-htmlextra-export "$SAIDA/regressao.html" \
  --reporter-junit-export "$SAIDA/regressao.xml" \
  --reporter-json-export "$SAIDA/regressao.json"
CODIGO=$?

echo
echo "==> Evidências em $SAIDA/ (fora do git)"
if [[ -f "$SAIDA/regressao.json" ]]; then
  python3 - "$SAIDA/regressao.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
r = d["run"]
falhas = {}
for f in r["failures"]:
    n = f["source"]["name"] if f.get("source") else "?"
    falhas.setdefault(n, 0)
    falhas[n] += 1
print(f"==> {len(r['executions'])} requests executados, "
      f"{len(r['failures'])} assertions falharam em {len(falhas)} requests")
for n, q in falhas.items():
    print(f"      {n}  ({q})")
PY
fi
exit $CODIGO
