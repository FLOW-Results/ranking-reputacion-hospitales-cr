#!/usr/bin/env bash
# Publica el ranking por primera vez en GitHub (repositorio público + GitHub Pages + secreto + workflow).
# Requiere: gh autenticado con acceso a la organización FLOW-Results y FIRECRAWL_API_KEY en ~/.bash_profile.
set -euo pipefail
REPO="FLOW-Results/ranking-reputacion-hospitales-cr"
cd "$(dirname "$0")"

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" --public --description "Ranking mensual de reputación de los hospitales de Costa Rica según reseñas públicas de Google"
fi
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO.git"
git push -u origin main

KEY=$(grep -E '^export FIRECRAWL_API_KEY=' ~/.bash_profile | sed 's/^export FIRECRAWL_API_KEY=//; s/"//g')
printf '%s' "$KEY" | gh secret set FIRECRAWL_API_KEY --repo "$REPO"

# GitHub Pages desde la rama main, carpeta /docs
gh api "repos/$REPO/pages" -X POST -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 || \
gh api "repos/$REPO/pages" -X PUT -f "source[branch]=main" -f "source[path]=/docs" >/dev/null

echo "Sitio: https://flow-results.github.io/ranking-reputacion-hospitales-cr/ (tarda 1 a 2 minutos en aparecer)"
echo "Prueba del workflow: gh workflow run actualizacion-mensual.yml --repo $REPO -f periodo=$(date +%Y-%m)"
