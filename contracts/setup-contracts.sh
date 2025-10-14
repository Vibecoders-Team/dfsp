#!/usr/bin/env bash
set -Eeuo pipefail

# --- Settings (можно переопределить через env) ---
HARDHAT_NETWORK="${HARDHAT_NETWORK:-docker}"  # default сеть из hardhat.config.ts
DO_DEPLOY="${DO_DEPLOY:-1}"                   # 1 — выполнить локальный деплой, если есть скрипт
DO_TESTS="${DO_TESTS:-0}"                     # 1 — прогнать тесты
DO_ABI_EXPORT="${DO_ABI_EXPORT:-1}"           # 1 — запустить npm run abi:export, если есть
NODE_OPTIONS="${NODE_OPTIONS:-}"              # на случай нехватки памяти: --max-old-space-size=4096

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

echo "▶ contracts bootstrap @ $PWD"

# 1) Проверим Node/npm
if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js не найден. Нужен Node 18+/20+."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "❌ npm не найден."
  exit 1
fi

echo "• Node: $(node -v)"
echo "• npm : $(npm -v)"

# 2) Чистая установка зависимостей по lock-файлу
if [[ -f "package-lock.json" ]]; then
  echo "• Installing deps via npm ci (lockfile)"
  npm ci
else
  echo "• package-lock.json не найден — npm install"
  npm install
fi

# 3) Компиляция контрактов
echo "• Compiling contracts (hardhat compile)…"
npx hardhat compile

# 4) (опционально) Экспорт ABI, если определён в package.json
if [[ "$DO_ABI_EXPORT" == "1" ]]; then
  if node -e "const s=require('./package.json').scripts||{}; process.exit(s['abi:export']?0:1)" ; then
    echo "• Exporting ABI (npm run abi:export)…"
    npm run -s abi:export
  else
    echo "• Скрипт abi:export не найден — пропускаю"
  fi
fi

echo "✅ Готово: контракты собраны."
