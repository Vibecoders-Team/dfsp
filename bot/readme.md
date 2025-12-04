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
- redis (async очередь для нотификаций)
- asyncpg (Postgres для шаблонов сообщений)

## Шаблоны сообщений

- Типовые ответы бота лежат в Postgres по `BOT_DB_DSN` (отдельная БД `dfsp-bot`).
- При старте сервис сам создаёт БД (если нет) и таблицу `bot_messages`, заливает seed из `app/data/messages.json`.
- Добавлять новые шаблоны нужно в `app/data/messages.json`; язык по умолчанию задаётся `BOT_DEFAULT_LANGUAGE`, поле `language` поддерживает локализации.

## Команды бота

- `/start` — приветствие, описание приватности и кнопка **«Привязать аккаунт»**, которая запускает flow привязки.
- `/help` — краткая справка по доступным командам.
- `/link` — начало привязки Telegram-аккаунта к пользователю DFSP.
- `/me` - профиль аккаунта

## Метрики Prometheus

Бот экспортирует метрики на эндпоинте `/metrics` на порту `PROM_PORT` (по умолчанию `8001`).

### Доступные метрики

- `tg_notify_sent_total{type}` - количество отправленных уведомлений по типам
- `tg_notify_dropped_total{reason}` - количество отброшенных уведомлений по причинам
- `tg_webhook_errors_total{code}` - количество ошибок webhook по кодам
- `tg_outbound_rate_limited_total` - количество rate limit от Telegram API
- `tg_notify_send_latency_seconds` - гистограмма латентности отправки уведомлений

### Настройка Prometheus

1. **Где находится `prometheus.yml`?**

   Файл `prometheus.yml` должен находиться на сервере, где запущен Prometheus, а не в проекте бота.

   - **Локально**: обычно в `/etc/prometheus/prometheus.yml` или в директории где запускается Prometheus
   - **Docker**: монтируется как volume, путь указывается в `docker-compose.yml`
   - **Kubernetes**: хранится в ConfigMap

2. **Пример конфигурации**

   См. файл `prometheus.example.yml` в корне проекта бота. Скопируйте его содержимое в ваш `prometheus.yml` и настройте под вашу инфраструктуру:

   ```yaml
   scrape_configs:
     - job_name: 'telegram-bot'
       static_configs:
         - targets: ['localhost:8001']  # или IP:PORT вашего бота
   ```

3. **Проверка метрик**

   ```bash
   # Проверить что метрики доступны
   curl http://localhost:8001/metrics
   
   # Или открыть в браузере
   # http://localhost:8001/metrics
   ```

## Диагностика проблем

### ERR_CONNECTION_REFUSED на ссылке для линка

Если при нажатии на ссылку для привязки аккаунта (`/link`) вы получаете `ERR_CONNECTION_REFUSED`, проверьте:

1. **Проверьте значение `PUBLIC_WEB_ORIGIN` в `.env`:**
   ```bash
   # Неправильно (недоступно извне):
   PUBLIC_WEB_ORIGIN=http://localhost:3000
   PUBLIC_WEB_ORIGIN=http://127.0.0.1:3000
   
   # Правильно (используйте публичный IP или домен):
   PUBLIC_WEB_ORIGIN=http://192.168.1.100:3000  # ваш локальный IP
   PUBLIC_WEB_ORIGIN=https://dfsp.example.com   # или домен
   ```

2. **Убедитесь что фронтенд запущен и доступен:**
   ```bash
   # Проверьте что фронтенд отвечает
   curl http://your-public-ip:3000
   # или
   curl https://dfsp.example.com
   ```

3. **Проверьте логи бота при запуске:**
   Бот автоматически выводит диагностику конфигурации при старте:
   ```
   === Диагностика конфигурации ===
   PUBLIC_WEB_ORIGIN: http://localhost:3000
   ❌ PUBLIC_WEB_ORIGIN указывает на localhost - это может быть недоступно для пользователей
   ```

4. **Если используете локальную разработку:**
   - Используйте ваш локальный IP вместо `localhost`
   - Убедитесь что фронтенд слушает на `0.0.0.0`, а не только `127.0.0.1`
   - Проверьте firewall/антивирус - они могут блокировать входящие соединения

## Уведомления

- Бот слушает очередь `tg.notifications` (Redis Streams, либо RabbitMQ если `QUEUE_DSN` начинается с `amqp://`).
- Идемпотентность и антиспам:
  - `tg:subscribed:<chat_id>` — `1/0`, управляется командой `/notify`.
  - `tg:event:seen:<chat_id>` — set event_id с TTL 1 день (дедупликация).
  - Дневной лимит на чат: 500 событий, коалесинг в окно `NOTIFY_COALESCE_WINDOW_SEC` (60 c).
  - Тихие часы сохраняются в `tg:quiet_hours:<chat_id>` в формате `HH:MM-HH:MM` (UTC).
- Команда `/notify` в боте включает/выключает подписку и даёт быстрый пресет тихих часов 23:00–07:00 (UTC).

## Локальный запуск (dev, polling)

1. Установите зависимости:

   ```bash
   cd bot
   uv sync
