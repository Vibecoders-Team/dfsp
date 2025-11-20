import argparse
import logging
import os
import sys
import time

import psycopg
import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _normalize_dsn(dsn: str) -> str:
    """
    Приводим DSN к формату понятному psycopg:
    - postgresql+psycopg:// -> postgresql://
    - postgresql+asyncpg:// -> postgresql://
    - убираем лишние кавычки, если попали из env
    """
    if not dsn:
        return dsn
    d = dsn.strip().strip('"').strip("'")
    if d.startswith("postgresql+psycopg://") or d.startswith("postgresql+asyncpg://"):
        d = "postgresql://" + d.split("://", 1)[1]
    return d


def wait_db(dsn: str, deadline: float) -> None:
    dsn = _normalize_dsn(dsn)
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            logger.info("[wait] DB OK")
            return
        except Exception as e:
            logger.warning(f"[wait] DB not ready: {e}")
            time.sleep(1)
    logger.error("[wait] DB timeout")
    sys.exit(1)


def wait_redis(url: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            r = redis.Redis.from_url(url, socket_connect_timeout=5)
            if r.ping():
                logger.info("[wait] Redis OK")
                return
        except Exception as e:
            logger.warning(f"[wait] Redis not ready: {e}")
            time.sleep(1)
    logger.error("[wait] Redis timeout")
    sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=int(os.getenv("WAIT_FOR_TIMEOUT", "60")))
    args = ap.parse_args()
    deadline = time.time() + args.timeout

    dsn = os.getenv("POSTGRES_DSN")
    redis_url = os.getenv("REDIS_URL")

    if dsn:
        wait_db(dsn, deadline)
    else:
        logger.info("[wait] POSTGRES_DSN not set -> skip DB wait")

    if redis_url:
        wait_redis(redis_url, deadline)
    else:
        logger.info("[wait] REDIS_URL not set -> skip Redis wait")
