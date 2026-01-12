import os
from pathlib import Path

import asyncpg
import pytest

from app.services.message_store import MessageStore


def _get_test_dsn() -> str:
    dsn = os.getenv("BOT_DB_TEST_DSN")
    if not dsn:
        pytest.skip("BOT_DB_TEST_DSN is not set; skipping DB-dependent tests")
    return dsn


@pytest.mark.asyncio
async def test_message_store_seeds_and_reads() -> None:
    seed_path = Path(__file__).resolve().parents[1] / "app" / "data" / "messages.json"
    dsn = _get_test_dsn()

    # Use a separate DB if provided via DSN (can add ?dbname=test_x)
    store = MessageStore(db_dsn=dsn, seed_path=seed_path, default_language="ru")

    await store.init()

    start_text = await store.get_message("start.linked")
    assert "Welcome" in start_text

    summary = await store.get_message(
        "verify.summary",
        variables={
            "status_icon": "✅",
            "onchain_icon": "✅",
            "offchain_icon": "❌",
            "status_text": "ok",
        },
    )
    assert "File verification result" in summary

    # Cleanup test DB: delete records but keep the DB
    async with asyncpg.connect(dsn) as conn:
        await conn.execute("TRUNCATE bot_messages")
