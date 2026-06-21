#!/usr/bin/env bash
# Refresh del dashboard Tech AI News.
#   1. Baja el histórico JSONL desde EC2 (fuente de verdad; el cron corre allá).
#   2. Reconstruye index.html con build_dashboard.py.
#   3. Muestra el diff de git para revisión ANTES de commitear.
# Uso:  bash analysis/refresh.sh
set -euo pipefail

ROOT="/c/Users/supip/OneDrive/Documentos/Alejandria/Tech AI News"
cd "$ROOT"

echo "==> 1/3  Bajando history/ desde EC2 (starlan)..."
scp -q -r starlan:~/tech-ai-news/history/ ./

echo "==> 2/3  Reconstruyendo index.html..."
.venv/Scripts/python.exe analysis/build_dashboard.py || .venv/bin/python analysis/build_dashboard.py

echo "==> 3/3  Estado git (revisa antes de commitear):"
git status -s
echo
echo "Días nuevos en history/:"
git status -s history/ | grep -E '\.jsonl$' || echo "  (ninguno nuevo)"
echo
echo "Listo. Para publicar:"
echo "  git add history/*.jsonl index.html"
echo "  git commit -m 'refresh dashboard 2026-06-21 (semanas 07-20 jun)'"
echo "  git push"
