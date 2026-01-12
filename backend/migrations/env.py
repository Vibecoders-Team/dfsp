# Alembic env (async, SQLAlchemy 2.x)
from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# --- PYTHONPATH: project root (/app) ---
HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))  # backend/
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- import Base and MODELS ---
# IMPORTANT: for autogenerate to "see" tables, import the models module here
import app.models as models_pkg
from app.db.base import Base  # your Declarative Base


def import_submodules(package):
    for _finder, name, ispkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(name)


import_submodules(models_pkg)  # import only, so tables are registered in metadata

# Alembic Config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_dsn() -> str:
    """
    Read DSN from env (POSTGRES_DSN) — you already configured .env,
    otherwise fall back to sqlalchemy.url from alembic.ini.
    """
    env_dsn = os.getenv("POSTGRES_DSN")
    if env_dsn:
        return env_dsn
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("POSTGRES_DSN env var or sqlalchemy.url in alembic.ini must be set")
    return url


def run_migrations_offline() -> None:
    url = get_dsn()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = get_dsn()
    connectable: AsyncEngine = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
