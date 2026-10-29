#!/usr/bin/env bash
# Sincroniza Garmin y regenera site/data.js. Lo lanza cron cada hora.
# flock evita dos ejecuciones a la vez; el log se recorta a las últimas 2000 líneas.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=data/update.log
exec 9>data/.update.lock
flock -n 9 || { echo "$(date '+%F %T') ya hay una actualización en marcha" >> "$LOG"; exit 0; }
{
  echo "=== $(date '+%F %T')"
  /home/garrigas/.local/bin/uv run --quiet garmin-stats all
} >> "$LOG" 2>&1 || echo "$(date '+%F %T') ERROR (ver arriba)" >> "$LOG"
tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
