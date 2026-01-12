#!/usr/bin/env bash
set -Eeuo pipefail

# --- Settings (can be overridden via env) ---
HARDHAT_NETWORK="${HARDHAT_NETWORK:-docker}"  # default network from hardhat.config.ts
DO_DEPLOY="${DO_DEPLOY:-1}"                   # 1 — perform local deployment if a script exists
DO_TESTS="${DO_TESTS:-0}"                     # 1 — run tests
DO_ABI_EXPORT="${DO_ABI_EXPORT:-1}"           # 1 — run npm run abi:export if it exists
NODE_OPTIONS="${NODE_OPTIONS:-}"              # in case of memory shortage: --max-old-space-size=4096

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

echo "▶ contracts bootstrap @ $PWD"

# 1) Check Node/npm
if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js not found. Node 18+/20+ is required."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "❌ npm not found."
  exit 1
fi

echo "• Node: $(node -v)"
echo "• npm : $(npm -v)"

# 2) Clean installation of dependencies from lock file
if [[ -f "package-lock.json" ]]; then
  echo "• Installing deps via npm ci (lockfile)"
  npm ci
else
  echo "• package-lock.json not found — npm install"
  npm install
fi

# 3) Compile contracts
echo "• Compiling contracts (hardhat compile)…"
npx hardhat compile

# 4) (optional) Export ABI if defined in package.json
if [[ "$DO_ABI_EXPORT" == "1" ]]; then
  if node -e "const s=require('./package.json').scripts||{}; process.exit(s['abi:export']?0:1)" ; then
    echo "• Exporting ABI (npm run abi:export)…"
    npm run -s abi:export
  else
    echo "• abi:export script not found — skipping"
  fi
fi

echo "✅ Done: contracts are built."
