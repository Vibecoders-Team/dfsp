# DFSP Telegram Bot

Telegram-бот для платформы DFSP. Позволяет линковать Telegram-аккаунт с DFSP-пользователем,
просматривать файлы и гранты, проверять доступ и т.д.

## Стек

- Python 3.11+
- aiogram v3
- pydantic / pydantic-settings
- httpx
- aiohttp (webhook, позже)
- prometheus_client
- aioredis (очередь, позже)

## Локальный запуск (dev, polling)

1. Установите зависимости:

   ```bash
   cd bot
   uv sync
