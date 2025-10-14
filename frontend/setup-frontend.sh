#!/usr/bin/env bash
set -Eeuo pipefail

# --- Settings (можно переопределить через env) ---
PNPM_VERSION="${PNPM_VERSION:-latest}"   # фиксируй версию при желании, напр. "9.12.3"
RUN_LINT="${RUN_LINT:-0}"               # 1 — запускать eslint
RUN_TESTS="${RUN_TESTS:-0}"             # 1 — запускать vitest
CI="${CI:-false}"                        # true/false — влияет на install флаги

# --- Helpers ---
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

echo "▶ frontend bootstrap @ $PWD"

# 1) Проверим Node и включим pnpm через corepack
if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js не найден. Установи Node 18+/20+ (в Docker-образе node:20 уже есть)."
  exit 1
fi

echo "• Node version: $(node -v)"
if ! command -v corepack >/dev/null 2>&1; then
  echo "❌ Corepack не найден. Обнови Node.js (>=16.10) или установи corepack."
  exit 1
fi

echo "• Enabling pnpm via corepack (${PNPM_VERSION})"
corepack enable >/dev/null 2>&1 || true
corepack prepare "pnpm@${PNPM_VERSION}" --activate

echo "• pnpm: $(pnpm -v)"

# 2) Установка зависимостей (с учётом pnpm-lock.yaml)
if [[ -f "pnpm-lock.yaml" ]]; then
  if [[ "$CI" == "true" ]]; then
    echo "• Installing deps (frozen lockfile, CI)"
    pnpm install --frozen-lockfile --prefer-offline
  else
    echo "• Installing deps (respects lockfile)"
    pnpm install --frozen-lockfile
  fi
else
  echo "• pnpm-lock.yaml не найден — обычный install"
  pnpm install
fi

# 3) Опционально: линт
if [[ "$RUN_LINT" == "1" ]]; then
  if pnpm -s run | grep -qE '(^| )lint( |:)'; then
    echo "• Running eslint…"
    pnpm run lint
  else
    echo "• Скрипт lint не найден — пропускаю"
  fi
fi

# 4) Сборка (vite + tsc -b уже заложены в package.json->build)
if pnpm -s run | grep -qE '(^| )build( |:)'; then
  echo "• Building production bundle…"
  pnpm run build
else
  echo "• Скрипт build не найден — пропускаю"
fi

# 5) Короткая проверка наличия артефактов
if [[ -d "dist" ]]; then
  echo "✅ Готово: собранный фронт лежит в ./dist"
else
  echo "ℹ️  Сборочных артефактов нет (возможно, ты не запускал build)."
fi
