#!/usr/bin/env bash
# Mantiene el servidor de la web en marcha (http://localhost:8765). Cron lo lanza al arrancar
# y cada 5 minutos; si ya está corriendo, flock hace que salga sin hacer nada.
set -uo pipefail
cd "$(dirname "$0")/.."
exec 8>data/.serve.lock
flock -n 8 || exit 0
echo "=== $(date '+%F %T') arranca el servidor" >> data/serve.log
exec /home/garrigas/.local/bin/uv run --quiet garmin-stats serve >> data/serve.log 2>&1
