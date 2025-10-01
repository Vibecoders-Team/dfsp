#!/usr/bin/env bash
set -euo pipefail

mode="${1:-api}"
api_host="${API_HOST:-0.0.0.0}"
api_port="${API_PORT:-8000}"
api_reload="${API_RELOAD:-true}"
api_log_level="${API_LOG_LEVEL:-info}"
wait_timeout="${WAIT_FOR_TIMEOUT:-60}"

echo "[entrypoint] mode=${mode}"

uv run python docker/wait_for.py --timeout "${wait_timeout}"

if [[ "${mode}" == "migrate" ]]; then
  echo "[entrypoint] alembic upgrade head"
  uv run alembic upgrade head
  echo "[entrypoint] migrations done."
  exit 0
fi

if [[ "${API_AUTO_MIGRATE:-false}" == "true" ]]; then
  echo "[entrypoint] API_AUTO_MIGRATE=true -> alembic upgrade head"
  uv run alembic upgrade head
fi

exec uv run uvicorn app.main:app \
  --host "${api_host}" \
  --port "${api_port}" \
  --log-level "${api_log_level}" \
  $( [[ "${api_reload}" == "true" ]] && echo --reload )
