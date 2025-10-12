from .config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis
import os
from .config import settings
from app.blockchain.web3_client import Chain
from app.ipfs.client import IpfsClient

def get_settings():
    return settings


engine = create_engine(settings.postgres_dsn, future=True)
SessionLocal = sessionmaker(engine, autoflush=False, autocommit=False, future=True)

rds = redis.from_url(settings.redis_dsn, decode_responses=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

_chain_instance: Chain | None = None


def get_chain() -> Chain:
    """
    Dependency function to get a cached instance of the Chain client,
    configured for the FileRegistry contract.
    """
    global _chain_instance

    if _chain_instance is None:
        # Мы явно указываем, что по умолчанию нам нужен "FileRegistry"
        _chain_instance = Chain(contract_name="FileRegistry")

    if not _chain_instance.contract and os.path.exists(settings.DEPLOYMENT_JSON_PATH):
        # Если что-то пошло не так, можно попробовать "перезагрузить" объект
        _chain_instance = Chain(contract_name="FileRegistry")

    return _chain_instance

def get_ipfs() -> IpfsClient:
    return IpfsClient(
        api_url=os.getenv("IPFS_API_URL", "http://ipfs:5001/api/v0"),
        gateway_url=os.getenv("IPFS_GATEWAY_URL", "http://ipfs:8080"),
        public_gateway_url=os.getenv("IPFS_PUBLIC_GATEWAY_URL", "http://localhost:8080"),
    )