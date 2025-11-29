#!/usr/bin/env bash
# One-shot prod startup (build + contracts + migrations + full stack)
# Usage: ./deploy/scripts/up-prod.sh [--verbose] [--skip-frontend] [--force-contracts]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/compose.prod.yml"
ENV_FILE="$ROOT_DIR/deploy/.env.prod"
DEPLOY_JSON="$ROOT_DIR/deploy/shared/deployment.json"
FRONT_DIR="$ROOT_DIR/frontend"
START_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
VERBOSE=false; SKIP_FRONTEND=false; FORCE_CONTRACTS=false
for arg in "$@"; do case "$arg" in --verbose) VERBOSE=true ;; --skip-frontend) SKIP_FRONTEND=true ;; --force-contracts) FORCE_CONTRACTS=true ;; esac; done
$VERBOSE && set -x || true
log(){ printf "\033[32m[up-prod]\033[0m %s\n" "$*"; };
warn(){ printf "\033[33m[up-prod]\033[0m %s\n" "$*"; };
err(){ printf "\033[31m[up-prod]\033[0m %s\n" "$*"; };
command -v docker >/dev/null || { err "docker missing"; exit 1; }
log "Start: $START_TS"; log "Compose: $COMPOSE_FILE"; log "Env: $ENV_FILE"
[ -f "$ENV_FILE" ] || { err "Env file not found"; exit 1; }
log "Building backend image"; DOCKER_BUILDKIT=1 docker build -t dfsp-backend:prod "$ROOT_DIR/backend"
if ! $SKIP_FRONTEND; then if [ -d "$FRONT_DIR" ]; then if [ -x "$ROOT_DIR/deploy/scripts/build-frontend.sh" ]; then "$ROOT_DIR/deploy/scripts/build-frontend.sh"; else command -v pnpm >/dev/null || (command -v corepack >/dev/null && corepack enable || true); (cd "$FRONT_DIR" && pnpm i --frozen-lockfile && pnpm build); fi; else warn "Frontend dir missing"; fi; fi
log "Pre-building compose images"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build api celery-worker celery-beat telegram-bot contracts explorer-indexer explorer-web || warn "Compose build issues"
log "Starting chain"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d chain || warn "chain start issue"; sleep 2
REDEPLOY_REASON=""; [ ! -s "$DEPLOY_JSON" ] && REDEPLOY_REASON="deployment.json missing"; $FORCE_CONTRACTS && REDEPLOY_REASON="--force-contracts flag"
log "Deploying contracts ($REDEPLOY_REASON)"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build contracts || err "contracts build failed"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" rm -f contracts >/dev/null 2>&1 || true; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run -T --rm contracts || err "contracts run failed"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" rm -f contracts >/dev/null 2>&1 || true;
log "Starting infra (db redis ipfs)"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d db redis ipfs || warn "infra up partial"
log "Starting api + celery + bot"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d api celery-worker celery-beat telegram-bot || warn "app layer issues"; sleep 5
log "Starting explorer stack"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d explorer-db explorer-indexer explorer-web || warn "explorer up issues"
log "Starting caddy"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d caddy || warn "caddy up issue"
log "Summary"; docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps || true
log "Done";
