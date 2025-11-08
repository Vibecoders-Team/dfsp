#!/usr/bin/env bash
# NOTE: expects official ngrok image output; if tunnels array empty, retry a few times.
set -euo pipefail
MODE="sync"
SKIP_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) SKIP_RESTART=1 ;;
    --env-only) MODE="env" ; SKIP_RESTART=1 ;;
  esac
done
API_HOSTS=("localhost" "127.0.0.1")
NGROK_API_PATH="api/tunnels"
ENV_LOCAL="deploy/.env.local"
RETRY=30

find_api_host() {
  for h in "${API_HOSTS[@]}"; do
    if curl -sf "http://$h:4040/$NGROK_API_PATH" >/dev/null 2>&1; then echo "$h"; return 0; fi
  done
  return 1
}

echo "[ngrok-sync] Locating ngrok API..."
api_host=""
for i in $(seq 1 $RETRY); do
  if api_host=$(find_api_host); then break; fi
  sleep 1
done
if [ -z "$api_host" ]; then
  echo "[ngrok-sync] ERROR: ngrok API not reachable on 4040." >&2
  exit 1
fi

echo "[ngrok-sync] Using API host: $api_host"
URL=""
for i in $(seq 1 $RETRY); do
  RAW_JSON=$(curl -sf "http://$api_host:4040/$NGROK_API_PATH") || RAW_JSON=""
  URL=$(echo "$RAW_JSON" | sed -n 's/.*"public_url"[[:space:]]*:[[:space:]]*"\(https:[^"]*\)".*/\1/p' | head -n1 || true)
  if [ -n "$URL" ]; then break; fi
  echo "[ngrok-sync] Waiting for tunnel to initialize ($i/$RETRY)..."
  sleep 1
done
if [ -z "$URL" ]; then
  echo "[ngrok-sync] ERROR: tunnel not established. Raw JSON:" >&2
  echo "$RAW_JSON" | sed 's/.*/[ngrok-sync] &/' >&2
  exit 1
fi

echo "[ngrok-sync] Detected public RPC URL: $URL"
if [ "$MODE" = "env" ]; then echo "$URL"; exit 0; fi
mkdir -p deploy
if grep -q '^CHAIN_PUBLIC_RPC_URL=' "$ENV_LOCAL" 2>/dev/null; then
  sed -i "s#^CHAIN_PUBLIC_RPC_URL=.*#CHAIN_PUBLIC_RPC_URL=$URL#" "$ENV_LOCAL"
else
  echo "CHAIN_PUBLIC_RPC_URL=$URL" >> "$ENV_LOCAL"
fi
if grep -q '^VITE_CHAIN_RPC_URL=' "$ENV_LOCAL" 2>/dev/null; then
  sed -i '/^VITE_CHAIN_RPC_URL=/d' "$ENV_LOCAL"
fi

echo "[ngrok-sync] Updated $ENV_LOCAL"

echo "[ngrok-sync] Probing RPC via eth_chainId..."
health=$(curl -sf -X POST -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' "$URL" || true)
[ -n "$health" ] && echo "[ngrok-sync] RPC response: $health" || echo "[ngrok-sync] WARNING: no RPC response yet"

if [ $SKIP_RESTART -eq 0 ]; then
  echo "[ngrok-sync] Starting stack with updated env..."
  docker compose --env-file ./deploy/.env.local -f compose.dev.yml up -d api web
fi

echo "[ngrok-sync] Done."
