#!/usr/bin/env bash
# Build/push dev images and restart dev compose stack remotely.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ROOT_DIR}/deploy/.env.dev"
FRONT_DIR="${ROOT_DIR}/frontend"
COMPOSE_FILE="deploy/compose.dev.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[deploy-dev] Missing ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC2046
export $(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')

: "${REGISTRY_HOST:?set REGISTRY_HOST in deploy/.env.dev}"
: "${SERVICE_BACKEND:?set SERVICE_BACKEND in deploy/.env.dev}"
: "${BRANCH_NAME_LOWER:?set BRANCH_NAME_LOWER in deploy/.env.dev}"
: "${DEV_SSH_USER:?set DEV_SSH_USER in deploy/.env.dev}"
: "${DEV_SSH_HOST:?set DEV_SSH_HOST in deploy/.env.dev}"
: "${DEV_REMOTE_DIR:?set DEV_REMOTE_DIR in deploy/.env.dev}"
: "${DEV_STATIC_DIR:?set DEV_STATIC_DIR in deploy/.env.dev}"

IMAGE_TAG="${REGISTRY_HOST}/${SERVICE_BACKEND}:${BRANCH_NAME_LOWER}"

log(){ printf "\033[32m[deploy-dev]\033[0m %s\n" "$*"; }
warn(){ printf "\033[33m[deploy-dev]\033[0m %s\n" "$*"; }
err(){ printf "\033[31m[deploy-dev]\033[0m %s\n" "$*"; }

command -v docker >/dev/null || { err "docker not installed"; exit 1; }
command -v ssh >/dev/null || { err "ssh not installed"; exit 1; }
command -v rsync >/dev/null || { err "rsync not installed"; exit 1; }

log "Building backend image: ${IMAGE_TAG}"
DOCKER_BUILDKIT=1 docker build -t "${IMAGE_TAG}" "${ROOT_DIR}/backend"

log "Pushing image to ${REGISTRY_HOST}"
docker push "${IMAGE_TAG}"

if [[ -d "${FRONT_DIR}" ]]; then
  if command -v pnpm >/dev/null 2>&1; then
    log "Building frontend artifacts"
    VITE_OUT_DIR=build-dev
    if [[ -f "${ENV_FILE}" ]]; then
      while IFS='=' read -r key value; do
        [[ -z "${key}" ]] && continue
        [[ "${key}" != VITE_* ]] && continue
        export "${key}"="${value}"
      done < <(grep '^VITE_' "${ENV_FILE}")
    fi
    export VITE_OUT_DIR
    (cd "${FRONT_DIR}" && pnpm install --frozen-lockfile && pnpm run build)
  else
    warn "pnpm not found; skipping frontend build"
  fi
else
  warn "frontend directory missing; skipping build"
fi

REMOTE="${DEV_SSH_USER}@${DEV_SSH_HOST}"
log "Syncing repo to ${REMOTE}:${DEV_REMOTE_DIR}"
ssh -t "${REMOTE}" "mkdir -p '${DEV_REMOTE_DIR}' && sudo rm -rf '${DEV_REMOTE_DIR}/contracts/deploy'"
rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  "${ROOT_DIR}/" "${REMOTE}:${DEV_REMOTE_DIR}/"

log "Restarting dev stack on remote host"
ssh "${REMOTE}" <<EOF
set -euo pipefail
cd "${DEV_REMOTE_DIR}"
docker login "${REGISTRY_HOST}" >/dev/null 2>&1 || true
docker compose -f ${COMPOSE_FILE} --env-file deploy/.env.dev pull api celery-worker celery-beat migrator || true
docker compose -f ${COMPOSE_FILE} --env-file deploy/.env.dev up -d
EOF

if [[ -d "${FRONT_DIR}/build-dev" ]]; then
  log "Syncing frontend/build-dev to ${DEV_STATIC_DIR}"
  rsync -az --delete \
    "${FRONT_DIR}/build-dev/" "${REMOTE}:${DEV_STATIC_DIR}/"
else
  warn "frontend/build-dev missing; dev static assets not synced"
fi

log "Done."
