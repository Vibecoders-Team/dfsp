from __future__ import annotations

import os
from collections.abc import Generator

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.blockchain.web3_client import Chain
from app.config import Settings, settings
from app.ipfs.client import IpfsClient


def get_settings() -> Settings:
    return settings


engine = create_engine(
    settings.postgres_dsn,
    future=True,
    pool_size=int(getattr(settings, "postgres_pool_size", 20)),
    max_overflow=int(getattr(settings, "postgres_max_overflow", 10)),
)
SessionLocal = sessionmaker(engine, autoflush=False, autocommit=False, future=True)

# Redis connection with pool
_pool = redis.ConnectionPool.from_url(
    settings.redis_dsn, max_connections=int(getattr(settings, "redis_max_connections", 100))
)
rds = redis.Redis(connection_pool=_pool, decode_responses=True)


def get_redis() -> redis.Redis:
    """Dependency to get the Redis client instance."""
    return rds


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_chain_instance: Chain | None = None


def get_chain() -> Chain:
    global _chain_instance
    if _chain_instance is None:
        _chain_instance = Chain(
            rpc_url=os.getenv("CHAIN_RPC_URL", "http://chain:8545"),
            chain_id=int(os.getenv("CHAIN_ID", "31337")),
            contract_name=os.getenv("REGISTRY_CONTRACT_NAME", "FileRegistry"),
            tx_from=os.getenv("CHAIN_TX_FROM") or None,
            deploy_json_path=os.getenv("CONTRACTS_DEPLOYMENT_JSON", "/app/shared/deployment.json"),
            relayer_private_key=os.getenv("RELAYER_PRIVATE_KEY") or settings.relayer_private_key,
        )
    # если инстанс уже жив, но контрактов нет — попробуем перечитать файл
    if not _chain_instance.contracts and os.path.exists(_chain_instance.deployment_json):
        _chain_instance.reload_contracts()
    return _chain_instance


def get_ipfs() -> IpfsClient:
    return IpfsClient(
        api_url=os.getenv("IPFS_API_URL", "http://ipfs:5001/api/v0"),
        gateway_url=os.getenv("IPFS_GATEWAY_URL", "http://ipfs:8080"),
        public_gateway_url=os.getenv("IPFS_PUBLIC_GATEWAY_URL", "http://localhost:8080"),
    )
