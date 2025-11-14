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

## Команды бота

- `/start` — приветствие, описание приватности и кнопка **«Привязать аккаунт»**, которая запускает flow привязки.
- `/help` — краткая справка по доступным командам.
- `/link` — (пока заглушка) начало привязки Telegram-аккаунта к пользователю DFSP.

## Локальный запуск (dev, polling)

1. Установите зависимости:

   ```bash
   cd bot
   uv sync
