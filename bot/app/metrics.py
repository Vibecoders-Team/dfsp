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


def setup_metrics_server() -> None:
    # просто запускаем HTTP-сервер в отдельном потоке
    start_http_server(settings.PROM_PORT)
