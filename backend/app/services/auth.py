# backend/app/services/auth.py

import base64
import uuid
from datetime import datetime, timezone

import redis
from eth_account.messages import encode_structured_data
from sqlalchemy.orm import Session
from web3 import Web3

from app.repos import user_repo
from app.schemas.auth import RegisterRequest
from ..config import settings
from ..db import models as db_models

redis_client = redis.from_url(settings.redis_dsn, decode_responses=True)


def create_auth_challenge(eth_address: str) -> tuple[str, datetime]:
    """Генерирует nonce, сохраняет в Redis и возвращает его."""
    nonce_bytes = uuid.uuid4().bytes
    nonce = base64.urlsafe_b64encode(nonce_bytes).decode().rstrip("=")
    exp_time = datetime.now(timezone.utc) + settings.auth_nonce_ttl

    redis_key = f"auth:nonce:{eth_address.lower()}"
    redis_client.set(redis_key, nonce, ex=settings.auth_nonce_ttl)

    return nonce, exp_time


def verify_signature_and_consume_nonce(eth_address: str, nonce: str, signature: str) -> bool:
    """Проверяет подпись EIP-712 и удаляет nonce из Redis."""
    redis_key = f"auth:nonce:{eth_address.lower()}"
    stored_nonce = redis_client.get(redis_key)
    if not stored_nonce or stored_nonce != nonce:
        return False

    redis_client.delete(redis_key)

    try:
        domain = {"name": "DFSP Auth", "version": "1", "chainId": 1}
        types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "AuthChallenge": [
                {"name": "message", "type": "string"},
                {"name": "nonce", "type": "string"},
            ],
        }
        message = {"message": "Sign this message to authenticate with DFSP.", "nonce": nonce}

        encoded_data = encode_structured_data(
            domain=domain, types=types, message=message, primary_type="AuthChallenge"
        )
        signer_address = Web3.eth.account.recover_message(encoded_data, signature=signature)
        return signer_address.lower() == eth_address.lower()
    except Exception:
        return False


def register_new_user(db: Session, request: RegisterRequest) -> db_models.User:
    """
    Координирует создание нового пользователя, вызывая репозиторий.
    """
    # Здесь можно добавить дополнительную бизнес-логику перед созданием, если потребуется
    return user_repo.create(db, request)