#!/bin/bash
# Incrementa a versão do SERVIÇO (Cobranca-API) seguindo Semantic Versioning.
# Uso: ./scripts/bump-version.sh [patch|minor|major]   (padrão: patch)
#
# Escopo — o repositório abriga dois artefatos com versionamentos
# INDEPENDENTES (docs/development/separacao-3-produtos.md):
#
#   1. o serviço FastAPI  -> VERSION, app.version, info.version da spec
#   2. o cliente pip      -> cobranca_api.__version__, versionado à parte
#
# Este script mexe SÓ no serviço. O cliente se publica no PyPI no ritmo dele;
# sincronizar os dois criaria releases falsas de um SDK que não mudou.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd "$(dirname "$0")/.."

BUMP_TYPE=${1:-patch}

[ -f VERSION ] || { echo -e "${RED}❌ Arquivo VERSION não encontrado!${NC}"; exit 1; }

CURRENT_VERSION=$(tr -d '[:space:]' < VERSION)
echo -e "${BLUE}📦 Versão atual: ${CURRENT_VERSION}${NC}"

[[ "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo -e "${RED}❌ VERSION não está em MAJOR.MINOR.PATCH: '${CURRENT_VERSION}'${NC}"; exit 1; }

IFS='.' read -ra VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}
PATCH=${VERSION_PARTS[2]}

case $BUMP_TYPE in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0; CHANGE_TYPE="MAJOR" ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0;          CHANGE_TYPE="MINOR" ;;
    patch) PATCH=$((PATCH + 1));                   CHANGE_TYPE="PATCH" ;;
    *) echo -e "${RED}❌ Tipo inválido: $BUMP_TYPE (use: patch, minor, ou major)${NC}"; exit 1 ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo -e "${GREEN}✨ Nova versão: ${NEW_VERSION} (${CHANGE_TYPE})${NC}"

# Cada substituição é conferida: uma versão que sobra num arquivo é pior que um
# erro, porque só aparece depois, em produção, no /api/metadata ou no Swagger.
substituir() {
    local arquivo="$1" expressao="$2" confirmacao="$3"
    [ -f "$arquivo" ] || { echo -e "${RED}❌ $arquivo não encontrado${NC}"; exit 1; }
    sed -i "$expressao" "$arquivo"
    grep -q "$confirmacao" "$arquivo" || {
        echo -e "${RED}❌ $arquivo continuou na versão antiga — o padrão do sed não casou.${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ ${arquivo}${NC}"
}

echo "$NEW_VERSION" > VERSION
echo -e "${GREEN}✅ VERSION${NC}"

# app.version — é o que GET /api/metadata devolve
substituir gateway/app/main.py \
    "s/^    version=\"${CURRENT_VERSION}\",$/    version=\"${NEW_VERSION}\",/" \
    "version=\"${NEW_VERSION}\","

# info.version da spec OpenAPI da superfície offline
substituir docs/openapi.yaml \
    "s/^  version: ${CURRENT_VERSION}$/  version: ${NEW_VERSION}/" \
    "^  version: ${NEW_VERSION}$"

# example do campo `version` em /api/metadata — é o que aparece no Swagger.
# Ficava para trás a cada release: exatamente a versão sobrando num arquivo
# que o comentário de `substituir` acima descreve.
substituir docs/openapi.yaml \
    "s/^              example: '${CURRENT_VERSION}'$/              example: '${NEW_VERSION}'/" \
    "^              example: '${NEW_VERSION}'$"

# CHANGELOG: abre a seção da versão logo abaixo de [Não lançado], que segue
# existindo, vazia, para o próximo ciclo.
if [ -f CHANGELOG.md ]; then
    grep -q '^## \[Não lançado\]' CHANGELOG.md || {
        echo -e "${RED}❌ CHANGELOG.md sem a seção '## [Não lançado]'${NC}"; exit 1; }

    TODAY=$(date +%Y-%m-%d)
    awk -v version="$NEW_VERSION" -v date="$TODAY" '
    /^## \[Não lançado\]/ && !feito {
        print $0; print ""
        print "## [" version "] - " date
        feito = 1
        next
    }
    { print }
    ' CHANGELOG.md > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md
    echo -e "${GREEN}✅ CHANGELOG.md${NC}"
fi

echo ""
echo -e "${YELLOW}📝 Próximos passos:${NC}"
echo "1. Mova as entradas de [Não lançado] para a seção [${NEW_VERSION}] no CHANGELOG.md"
echo "2. Rode a suíte:"
echo -e "   ${BLUE}cd gateway && PYTHONPATH=. pytest && cd ..${NC}"
echo "3. Commit:"
echo -e "   ${BLUE}git add VERSION CHANGELOG.md gateway/app/main.py docs/openapi.yaml${NC}"
echo -e "   ${BLUE}git commit -m \"[RELEASE] Versão ${NEW_VERSION}\"${NC}"
echo "4. Tag (só depois do merge em main):"
echo -e "   ${BLUE}git tag -a v${NEW_VERSION} -m \"Versão ${NEW_VERSION}\"${NC}"
echo -e "   ${BLUE}git push origin main --tags${NC}"
echo ""
echo -e "${GREEN}🎉 Versão ${NEW_VERSION} pronta!${NC}"
