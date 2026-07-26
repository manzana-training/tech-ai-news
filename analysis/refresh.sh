#!/usr/bin/env bash
# Refresh del dashboard Tech AI News.
#   1.   Baja el histórico JSONL desde EC2 (fuente de verdad; el cron corre allá).
#   2.   Genera el editorial semanal (tab 00 Brief) — idempotente por semana ISO,
#        NO fatal: si falla (sin red, sin key), el rebuild sigue sin brief nuevo.
#   3.   Reconstruye index.html con build_dashboard.py.
#   4.   Muestra el diff de git para revisión ANTES de commitear.
# Uso:  bash analysis/refresh.sh
set -euo pipefail

ROOT="/c/Users/supip/OneDrive/Documentos/Alejandria/Tech AI News"
cd "$ROOT"
PY() { if [ -x .venv/Scripts/python.exe ]; then .venv/Scripts/python.exe "$@"; else .venv/bin/python "$@"; fi; }

echo "==> 1/4  Bajando history/ desde EC2 (starlan)..."
scp -q -r starlan:~/tech-ai-news/history/ ./

echo "==> 2/4  Editorial semanal (tab 00 Brief)..."
PY analysis/build_editorial.py || echo "  WARN: build_editorial falló — sigo sin brief nuevo"

echo "==> 3/5  Reconstruyendo index.html..."
PY analysis/build_dashboard.py

echo "==> 4/5  Galeria de imagenes del brief (brief-gallery/)..."
PY analysis/sync_gallery.py || echo "  WARN: sync_gallery fallo — no fatal"

echo "==> 5/5  Estado git (revisa antes de commitear):"
git status -s
echo
echo "Días nuevos en history/:"
git status -s history/ | grep -E '\.jsonl$' || echo "  (ninguno nuevo)"
echo
echo "Listo. Para publicar:"
echo "  git add history/*.jsonl index.html analysis/editorial/ assets/editorial/ brief-gallery/"
echo "  git commit -m 'refresh dashboard + brief semanal'"
echo "  git push"
