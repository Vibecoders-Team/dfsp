import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .config import settings
from .metrics import setup_metrics_server
from .middlewares.logging import LoggingMiddleware
from .middlewares.error_handler import ErrorHandlerMiddleware
from .handlers import start as start_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    setup_metrics_server()
    logger.info("Prometheus metrics server started on port %s", settings.PROM_PORT)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(ErrorHandlerMiddleware())

    dp.include_router(start_handlers.router)

    logger.info("Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
