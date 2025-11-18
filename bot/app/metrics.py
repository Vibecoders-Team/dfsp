from prometheus_client import Counter, Histogram, start_http_server

from .config import settings

bot_updates_total = Counter(
    "bot_updates_total",
    "Total number of updates processed by bot",
)

bot_errors_total = Counter(
    "bot_errors_total",
    "Total number of errors in bot handlers",
)

bot_update_latency_seconds = Histogram(
    "bot_update_latency_seconds",
    "Latency of update processing in seconds",
)

# Notification metrics
tg_notify_sent_total = Counter(
    "tg_notify_sent_total",
    "Total number of notifications sent to Telegram",
    labelnames=["type"],
)

tg_notify_dropped_total = Counter(
    "tg_notify_dropped_total",
    "Total number of notifications dropped",
    labelnames=["reason"],
)

tg_webhook_errors_total = Counter(
    "tg_webhook_errors_total",
    "Total number of webhook errors",
    labelnames=["code"],
)

tg_outbound_rate_limited_total = Counter(
    "tg_outbound_rate_limited_total",
    "Total number of rate limit hits from Telegram API",
)

tg_notify_send_latency_seconds = Histogram(
    "tg_notify_send_latency_seconds",
    "Latency of sending notifications to Telegram in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


def setup_metrics_server() -> None:
    # просто запускаем HTTP-сервер в отдельном потоке
    start_http_server(settings.PROM_PORT)
