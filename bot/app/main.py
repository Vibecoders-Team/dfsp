import asyncio
import logging

from aiohttp import web
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


# --- Bot & dispatcher (общие для обоих режимов) ---------------------------------


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot_ = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp_ = Dispatcher()

    dp_.update.middleware(LoggingMiddleware())
    dp_.update.middleware(ErrorHandlerMiddleware())

    dp_.include_router(start_handlers.router)
    # остальные роутеры: link, unlink, me, files, grants, verify, callbacks

    return bot_, dp_


bot, dp = create_bot_and_dispatcher()


# --- DEV: long polling ---------------------------------------------------------


async def run_polling() -> None:
    logger.info("Starting polling (dev mode)...")
    await dp.start_polling(bot)


# --- PROD: webhook + healthz ---------------------------------------------------


async def healthz_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def webhook_handler(request: web.Request) -> web.Response:
    secret = request.match_info.get("secret")
    if secret != settings.WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret: %s", secret)
        return web.Response(status=403, text="forbidden")

    try:
        data = await request.json()
    except Exception:
        logger.exception("Failed to read JSON body for webhook")
        return web.Response(status=400, text="invalid json")

    logger.info("Webhook update received: %s", data)

    try:
        # скармливаем апдейт aiogram как сырой dict
        await dp.feed_raw_update(bot, data)
    except Exception:
        # для продакшена важно залогировать, но Телеге лучше вернуть 200,
        # чтобы она не спамила ретраями
        logger.exception("Failed to process update")

    return web.Response(text="ok")


def create_web_app() -> web.Application:
    app = web.Application()

    app.router.add_get("/healthz", healthz_handler)
    app.router.add_post("/tg/webhook/{secret}", webhook_handler)

    async def on_startup(app_: web.Application) -> None:
        logger.info("Webhook app startup")

    async def on_shutdown(app_: web.Application) -> None:
        logger.info("Webhook app shutdown: closing bot session")
        await bot.session.close()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app


# --- Entry point ---------------------------------------------------------------


def main() -> None:
    setup_metrics_server()
    logger.info("Prometheus metrics server started on port %s", settings.PROM_PORT)

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
