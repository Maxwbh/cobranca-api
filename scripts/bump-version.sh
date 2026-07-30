#!/bin/bash
# Script para incrementar versão automaticamente
# Uso: ./scripts/bump-version.sh [patch|minor|major]
# Padrão: patch (1.0.0 -> 1.0.1)

set -e

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Tipo de bump (patch por padrão)
BUMP_TYPE=${1:-patch}

# Ler versão atual
if [ ! -f "VERSION" ]; then
    echo "❌ Arquivo VERSION não encontrado!"
    exit 1
fi

CURRENT_VERSION=$(cat VERSION)
echo -e "${BLUE}📦 Versão atual: ${CURRENT_VERSION}${NC}"

# Separar major.minor.patch
IFS='.' read -ra VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}
PATCH=${VERSION_PARTS[2]}

# Incrementar versão
case $BUMP_TYPE in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        CHANGE_TYPE="MAJOR"
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        CHANGE_TYPE="MINOR"
        ;;
    patch)
        PATCH=$((PATCH + 1))
        CHANGE_TYPE="PATCH"
        ;;
    *)
        echo "❌ Tipo inválido: $BUMP_TYPE (use: patch, minor, ou major)"
        exit 1
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo -e "${GREEN}✨ Nova versão: ${NEW_VERSION} (${CHANGE_TYPE})${NC}"

# Atualizar arquivo VERSION
echo "$NEW_VERSION" > VERSION
echo -e "${GREEN}✅ VERSION atualizado${NC}"

# Atualizar __init__.py do cliente Python
if [ -f "python-client/boleto_cnab_client/__init__.py" ]; then
    sed -i "s/__version__ = '.*'/__version__ = '${NEW_VERSION}'/" python-client/boleto_cnab_client/__init__.py
    echo -e "${GREEN}✅ Cliente Python atualizado${NC}"
fi

# Data atual
TODAY=$(date +%Y-%m-%d)

# Adicionar entrada no CHANGELOG
if [ -f "CHANGELOG.md" ]; then
    # Criar backup
    cp CHANGELOG.md CHANGELOG.md.bak

    # Inserir nova versão após o cabeçalho
    awk -v version="$NEW_VERSION" -v date="$TODAY" '
    /^## \[Unreleased\]/ {
        print $0
        print ""
        print "## [" version "] - " date
        print ""
        print "### Alterado"
        print "- Atualização de versão"
        print ""
        next
    }
    { print }
    ' CHANGELOG.md.bak > CHANGELOG.md

    rm CHANGELOG.md.bak
    echo -e "${GREEN}✅ CHANGELOG.md atualizado${NC}"
fi

echo ""
echo -e "${YELLOW}📝 Próximos passos:${NC}"
echo "1. Edite CHANGELOG.md e adicione as mudanças desta versão"
echo "2. Commit as alterações:"
echo -e "   ${BLUE}git add VERSION CHANGELOG.md python-client/boleto_cnab_client/__init__.py${NC}"
echo -e "   ${BLUE}git commit -m \"[RELEASE] Versão ${NEW_VERSION}\"${NC}"
echo "3. Crie uma tag:"
echo -e "   ${BLUE}git tag -a v${NEW_VERSION} -m \"Versão ${NEW_VERSION}\"${NC}"
echo "4. Push com tags:"
echo -e "   ${BLUE}git push origin $(git branch --show-current) --tags${NC}"
echo ""
echo -e "${GREEN}🎉 Versão ${NEW_VERSION} pronta!${NC}"
