from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from contextvars import ContextVar
from urllib.parse import urlparse, urlunparse

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Текущий язык запроса (устанавливается middleware'ом)
_current_language: ContextVar[str | None] = ContextVar("current_language", default=None)


class _SafeFormatDict(dict[str, Any]):
    """Сохраняет неизвестные плейсхолдеры нетронутыми при форматировании."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _build_admin_dsn(dsn: str) -> tuple[str, str]:
    """
    Возвращает (admin_dsn, db_name), где admin_dsn указывает на системную БД postgres
    c теми же логином/паролем/хостом/портом.
    """
    parsed = urlparse(dsn)
    db_name = (parsed.path or "").lstrip("/")
    admin_path = "/postgres"  # системная БД по умолчанию
    admin_dsn = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            admin_path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return admin_dsn, db_name


class MessageStore:
    """Postgres-хранилище шаблонов сообщений."""

    def __init__(self, db_dsn: str, seed_path: Path, default_language: str = "ru") -> None:
        self.db_dsn = db_dsn
        self.seed_path = seed_path
        self.default_language = default_language
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._pool: asyncpg.Pool | None = None
        self._cache: dict[tuple[str, str], str] = {}

    async def init(self) -> None:
        """Создаёт БД/таблицу при необходимости, заливает seed и греет кэш."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            await self._ensure_database_exists()
            self._pool = await asyncpg.create_pool(self.db_dsn, command_timeout=10)

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_messages (
                        key TEXT NOT NULL,
                        language TEXT NOT NULL,
                        content TEXT NOT NULL,
                        PRIMARY KEY (key, language)
                    )
                    """
                )

                await self._seed_from_json(conn)
                await self._warm_cache(conn)

            self._initialized = True
            logger.info("Message store initialised in Postgres (%d records cached)", len(self._cache))

    async def _ensure_database_exists(self) -> None:
        """Проверяет наличие базы из DSN; создаёт её через системную БД postgres при отсутствии."""
        admin_dsn, db_name = _build_admin_dsn(self.db_dsn)

        last_error: Exception | None = None

        # несколько попыток: база может ещё не поднялась, даём немного времени
        for attempt in range(1, 6):
            try:
                conn = await asyncpg.connect(self.db_dsn, timeout=5)
            except asyncpg.InvalidCatalogNameError:
                logger.info("Database %s not found (attempt %s); will try to create", db_name, attempt)
                try:
                    await self._create_database(admin_dsn, db_name)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.warning("Attempt %s: failed to create DB %s: %s", attempt, db_name, exc)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Attempt %s: failed to connect to %s: %s", attempt, self.db_dsn, exc)
            else:
                await conn.close()
                return

            await asyncio.sleep(min(2 * attempt, 5))

        raise RuntimeError(f"Could not ensure database {db_name} exists after {attempt} attempts: {last_error}")

    async def _create_database(self, admin_dsn: str, db_name: str) -> None:
        """Создаёт базу через административные подключения."""
        # fallback: сначала postgres, затем template1 (если postgres отключён)
        admin_candidates = (admin_dsn, admin_dsn.replace("/postgres", "/template1"))
        last_error: Exception | None = None

        for candidate in admin_candidates:
            try:
                admin_conn = await asyncpg.connect(candidate, timeout=5)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Failed to connect to admin DSN %s: %s", candidate, exc)
                continue

            try:
                exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
                if not exists:
                    await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
                    logger.info("Database %s created via %s", db_name, candidate)
            finally:
                await admin_conn.close()
            return

        raise RuntimeError(f"Could not create database {db_name}: {last_error}")

    async def _seed_from_json(self, conn: asyncpg.Connection) -> None:
        """Загружает сообщения из JSON и делает upsert в БД."""
        if not self.seed_path.exists():
            logger.warning("Seed file %s not found; skipping message seeding", self.seed_path)
            return

        try:
            with self.seed_path.open("r", encoding="utf-8") as fp:
                seed_data = json.load(fp)
        except Exception as exc:
            logger.error("Failed to read seed file %s: %s", self.seed_path, exc)
            return

        rows: list[tuple[str, str, str]] = []
        for item in seed_data:
            key = item.get("key")
            language = item.get("language", self.default_language)
            content = item.get("content")

            if not key or content is None:
                logger.warning("Skipping invalid seed row: %s", item)
                continue

            rows.append((key, language, content))

        if not rows:
            logger.warning("No valid messages found in seed file %s", self.seed_path)
            return

        await conn.executemany(
            """
            INSERT INTO bot_messages (key, language, content)
            VALUES ($1, $2, $3)
            ON CONFLICT (key, language) DO UPDATE SET content=EXCLUDED.content
            """,
            rows,
        )
        logger.info("Seeded %d messages into bot_messages", len(rows))

    async def _warm_cache(self, conn: asyncpg.Connection) -> None:
        """Греет in-memory кэш всех сообщений."""
        self._cache.clear()
        rows = await conn.fetch("SELECT key, language, content FROM bot_messages")
        for row in rows:
            self._cache[(row["key"], row["language"])] = row["content"]

    async def get_message(self, key: str, *, language: str | None = None, variables: dict[str, Any] | None = None) -> str:
        """Достаёт сообщение по ключу/языку и форматирует плейсхолдеры."""
        await self.init()

        lang = language or _current_language.get() or self.default_language
        content = self._cache.get((key, lang))

        if content is None and lang != self.default_language:
            content = self._cache.get((key, self.default_language))

        if content is None:
            logger.warning("Message '%s' not found for language '%s'", key, lang)
            return f"[{key}]"

        if variables:
            return content.format_map(_SafeFormatDict(variables))

        return content

    def get_cached(self, key: str, language: str | None = None) -> str | None:
        """Синхронный просмотр кэша (после init)."""
        if not self._initialized:
            return None
        lang = language or _current_language.get() or self.default_language
        content = self._cache.get((key, lang))
        if content is None and lang != self.default_language:
            content = self._cache.get((key, self.default_language))
        return content


def set_current_language(lang: str | None) -> Any:
    """Устанавливает язык в контекст текущей обработки и возвращает token для reset."""
    return _current_language.set(lang)


def reset_current_language(token: Any) -> None:
    """Сбрасывает язык в контекстной переменной."""
    try:
        _current_language.reset(token)
    except Exception:
        # безопасно игнорируем, если токен невалиден/уже сброшен
        logger.debug("Failed to reset current language context")


SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "messages.json"
message_store = MessageStore(
    db_dsn=settings.BOT_DB_DSN,
    seed_path=SEED_PATH,
    default_language=settings.BOT_DEFAULT_LANGUAGE,
)


async def get_message(key: str, *, language: str | None = None, variables: dict[str, Any] | None = None) -> str:
    """Шорткат для получения сообщения из глобального стора."""
    return await message_store.get_message(key, language=language, variables=variables)
