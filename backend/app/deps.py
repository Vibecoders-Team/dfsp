from __future__ import annotations

import os

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator
from sqlalchemy.orm import Session

from app.blockchain.web3_client import Chain
from app.ipfs.client import IpfsClient
from app.config import settings


def get_settings():
    return settings


engine = create_engine(settings.postgres_dsn, future=True)
SessionLocal = sessionmaker(engine, autoflush=False, autocommit=False, future=True)

rds = redis.from_url(settings.redis_dsn, decode_responses=True)


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
            deploy_json_path=os.getenv("CONTRACTS_DEPLOYMENT_JSON", "/app/shared/deployment.localhost.json"),
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
