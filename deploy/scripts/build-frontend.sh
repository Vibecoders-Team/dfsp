#!/usr/bin/env bash
# Rebuild frontend with production environment variables
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
FRONT_DIR="$ROOT_DIR/frontend"
ENV_FILE="$ROOT_DIR/deploy/.env.prod"

cd "$FRONT_DIR"

echo "[build-frontend] Loading production ENV from $ENV_FILE"
export $(grep "^VITE_" "$ENV_FILE" | xargs)

echo "[build-frontend] Building frontend with production variables:"
echo "  VITE_API_BASE=$VITE_API_BASE"
echo "  VITE_CHAIN_RPC_URL=$VITE_CHAIN_RPC_URL"
echo "  VITE_IPFS_PUBLIC_GATEWAY=$VITE_IPFS_PUBLIC_GATEWAY"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "[build-frontend] pnpm not found, enabling corepack"
  corepack enable || echo "[build-frontend] Warning: corepack enable failed"
fi

echo "[build-frontend] Installing dependencies"
pnpm install --frozen-lockfile

echo "[build-frontend] Building"
pnpm build

echo "[build-frontend] Done! Build output in: $FRONT_DIR/build"

