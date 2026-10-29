#!/usr/bin/env bash
# Copia semanal de los datos al OneDrive personal (no al de la empresa: son datos de salud).
# Guarda la base de datos (copia en caliente con la API de backup de SQLite), el plan y la memoria
# del coach, la caché de la IA y el registro de gasto. Conserva las 8 copias más recientes.
# Los archivos FIT no se copian: se vuelven a descargar de Garmin con `garmin-stats sync`.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="/mnt/c/Users/garrigas/OneDrive/Backups/garmin_stats"
mkdir -p "$DEST"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
/home/garrigas/.local/bin/uv run --quiet python - "$TMP/garmin.sqlite" <<'PY'
import sqlite3, sys
src = sqlite3.connect("data/garmin.sqlite")
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
dst.close(); src.close()
PY
for f in coach.json ai_cache.json ai_usage.log crontab.backup; do [ -f "data/$f" ] && cp "data/$f" "$TMP/"; done
NAME="garmin-stats-$(date +%F).tar.gz"
tar -czf "$DEST/$NAME" -C "$TMP" .
ls -1t "$DEST"/garmin-stats-*.tar.gz | tail -n +9 | xargs -r rm -f
echo "$(date '+%F %T') copia $NAME ($(du -h "$DEST/$NAME" | cut -f1))" >> data/backup.log
