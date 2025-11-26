import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
from redis import asyncio as aioredis

from .config import settings
from .handlers import files as files_handlers
from .handlers import link as link_handlers
from .handlers import link_callback as link_callback_handlers
from .handlers import me as me_handlers
from .handlers import menu as menu_handlers
from .handlers import start as start_handlers
from .handlers import unlink as unlink_handlers
from .handlers import verify as verify_handlers
from .metrics import setup_metrics_server, tg_webhook_errors_total
from .middlewares.error_handler import ErrorHandlerMiddleware
from .middlewares.logging import LoggingMiddleware
from .middlewares.rate_limit import RateLimitMiddleware
from .services.notifications.consumer import NotificationConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# --- Bot & dispatcher (общие для обоих режимов) ---------------------------------


async def setup_bot_commands(bot_: Bot) -> None:
    """Устанавливает меню команд бота."""
    from aiogram.exceptions import TelegramNetworkError
    from aiogram.types import BotCommand

    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="me", description="Мой профиль"),
        BotCommand(command="files", description="Мои файлы"),
        BotCommand(command="link", description="Привязать аккаунт"),
        BotCommand(command="unlink", description="Отвязать аккаунт"),
        BotCommand(command="help", description="Справка"),
    ]

    try:
        await bot_.set_my_commands(commands)
        logger.info("Bot commands menu set")
    except TelegramNetworkError as e:
        logger.warning("Failed to set bot commands (network error): %s. Bot will continue without menu.", e)
    except Exception as e:
        logger.warning("Failed to set bot commands: %s. Bot will continue without menu.", e)


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot_ = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp_ = Dispatcher()

    dp_.update.middleware(ErrorHandlerMiddleware())
    dp_.update.middleware(LoggingMiddleware())
    dp_.update.middleware(RateLimitMiddleware())

    dp_.include_router(start_handlers.router)
    dp_.include_router(menu_handlers.router)
    dp_.include_router(link_handlers.router)
    dp_.include_router(link_callback_handlers.router)
    dp_.include_router(unlink_handlers.router)
    dp_.include_router(me_handlers.router)
    dp_.include_router(files_handlers.router)
    dp_.include_router(verify_handlers.router)
    # остальные роутеры: grants, callbacks

    return bot_, dp_


bot, dp = create_bot_and_dispatcher()


# --- DEV: long polling ---------------------------------------------------------


async def run_polling() -> None:
    logger.info("Starting polling (dev mode)...")

    # Setup bot commands menu
    await setup_bot_commands(bot)

    # Start notification consumer in background
    consumer_task = None
    redis_client = None
    try:
        redis_client = aioredis.from_url(settings.REDIS_DSN, decode_responses=False)
        consumer = NotificationConsumer(bot, redis_client)
        consumer_task = asyncio.create_task(consumer.start())
        logger.info("Notification consumer started")
    except Exception as e:
        logger.warning("Failed to start notification consumer: %s", e)

    try:
        await dp.start_polling(bot)
    finally:
        # Cleanup
        if consumer_task:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
        if redis_client:
            await redis_client.close()


# --- PROD: webhook + healthz ---------------------------------------------------


async def healthz_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def webhook_handler(request: web.Request) -> web.Response:
    secret = request.match_info.get("secret")
    if secret != settings.WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret: %s", secret)
        tg_webhook_errors_total.labels(code="403").inc()
        return web.Response(status=403, text="forbidden")

    try:
        data = await request.json()
    except Exception:
        logger.exception("Failed to read JSON body for webhook")
        tg_webhook_errors_total.labels(code="400").inc()
        return web.Response(status=400, text="invalid json")

    logger.info("Webhook update received: %s", data)

    try:
        # скармливаем апдейт aiogram как сырой dict
        await dp.feed_raw_update(bot, data)
    except Exception:
        # для продакшена важно залогировать, но Телеге лучше вернуть 200,
        # чтобы она не спамила ретраями
        tg_webhook_errors_total.labels(code="500").inc()
        logger.exception("Failed to process update")

    return web.Response(text="ok")


def create_web_app() -> web.Application:
    app = web.Application()

    app.router.add_get("/healthz", healthz_handler)
    app.router.add_post("/tg/webhook/{secret}", webhook_handler)

    async def on_startup(app_: web.Application) -> None:
        logger.info("Webhook app startup")

        # Setup bot commands menu
        await setup_bot_commands(bot)

        # Start notification consumer in background
        redis_client = aioredis.from_url(settings.REDIS_DSN, decode_responses=False)
        consumer = NotificationConsumer(bot, redis_client)
        consumer_task = asyncio.create_task(consumer.start())
        app_["consumer_task"] = consumer_task
        app_["redis_client"] = redis_client
        logger.info("Notification consumer started")

    async def on_shutdown(app_: web.Application) -> None:
        logger.info("Webhook app shutdown: closing bot session")

        # Stop consumer
        consumer_task = app_.get("consumer_task")
        if consumer_task:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        # Close Redis
        redis_client = app_.get("redis_client")
        if redis_client:
            await redis_client.close()

        await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


# --- Entry point ---------------------------------------------------------------


def main() -> None:
    setup_metrics_server()
    logger.info("Prometheus metrics server started on port %s", settings.PROM_PORT)

    # Диагностика конфигурации
    from .utils.diagnostics import print_config_diagnostics

    print_config_diagnostics()

    if settings.BOT_MODE == "dev":
        asyncio.run(run_polling())
    else:
        logger.info(
            "Starting webhook server (prod mode) on %s:%s",
            settings.APP_HOST,
            settings.APP_PORT,
        )
        app = create_web_app()
        web.run_app(app, host=settings.APP_HOST, port=settings.APP_PORT)


if __name__ == "__main__":
    main()
