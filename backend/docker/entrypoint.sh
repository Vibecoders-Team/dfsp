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

auto_rev="${ALEMBIC_AUTO_REVISION:-false}"

gen_auto_revision() {
  if [[ "${auto_rev}" == "true" ]]; then
    echo "[entrypoint] alembic revision --autogenerate (dev)"
    uv run alembic revision --autogenerate -m "auto $(date -u +%Y%m%d%H%M%S)" || true

    latest=$(ls -t migrations/versions/*.py 2>/dev/null | head -n1 || true)
    if [[ -n "${latest}" ]]; then
      if ! grep -q "from sqlalchemy.dialects import postgresql" "${latest}"; then
        echo "[entrypoint] patching: add PG dialect import to ${latest}"
        # вставим сразу после 'import sqlalchemy as sa'
        sed -i '/^import sqlalchemy as sa$/a from sqlalchemy.dialects import postgresql' "${latest}"
      fi
      echo "[entrypoint] generated revision head:"
      head -n 25 "${latest}"
      chmod -R 0777 /app/migrations
    fi
  fi
}


if [[ "${mode}" == "migrate" ]]; then
  echo "[entrypoint] alembic upgrade head"
  uv run alembic upgrade head
  echo "[entrypoint] migrations done."
  gen_auto_revision
  exit 0
fi

if [[ "${API_AUTO_MIGRATE:-false}" == "true" ]]; then
  echo "[entrypoint] API_AUTO_MIGRATE=true -> alembic upgrade head"
  uv run alembic upgrade head
  gen_auto_revision
fi

exec uv run uvicorn app.main:app \
  --host "${api_host}" \
  --port "${api_port}" \
  --log-level "${api_log_level}" \
  $( [[ "${api_reload}" == "true" ]] && echo --reload )
