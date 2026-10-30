#!/usr/bin/env bash
# Sincroniza con AWS (si está configurado en data/aws.json).
#   down: trae el estado que cambia en AWS (plan, memoria del coach, gasto de IA de Lambda)
#   up:   sube la web y el estado del PC
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f data/aws.json ] || exit 0
cfg() { python3 -c "import json; print(json.load(open('data/aws.json'))['$1'])"; }
export AWS_PROFILE=$(cfg profile) AWS_REGION=$(cfg region) AWS_PAGER=""
B=$(cfg bucket)
case "${1:-}" in
  down)
    for f in coach.json ai_usage_lambda.log; do
      aws s3 cp "s3://$B/state/$f" "data/$f" --only-show-errors 2>/dev/null || true
    done ;;
  up)
    aws s3 sync site/ "s3://$B/site/" --delete --only-show-errors --cache-control no-store
    for f in coach.json settings.json ai_usage.log ai_cache.json; do
      [ -f "data/$f" ] && aws s3 cp "data/$f" "s3://$B/state/$f" --only-show-errors
    done ;;
  *) echo "uso: $0 down|up" >&2; exit 2 ;;
esac
