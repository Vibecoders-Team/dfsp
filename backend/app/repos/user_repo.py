from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User
from app.schemas.auth import RegisterIn


def get_by_eth_address(db: Session, eth_address: str) -> Optional[User]:
    """Найти пользователя по EVM-адресу (нормализуем к lower())."""
    return (
        db.query(User)
        .filter(User.eth_address == (eth_address or "").lower())
        .one_or_none()
    )


def create(db: Session, payload: RegisterIn) -> User:
    """
    Создать пользователя из RegisterIn.
    Поля схемы и модели согласованы:
      - payload.eth_address -> User.eth_address (lower)
      - payload.rsa_public  -> User.rsa_public
      - payload.display_name -> User.display_name
    """
    user = User(
        eth_address=(payload.eth_address or "").lower(),
        rsa_public=payload.rsa_public,
        display_name=payload.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_user_id_by_wallet(db: Session, wallet_address: str) -> uuid.UUID | None:
    """
    Находит пользователя по eth_address и возвращает его UUID (id).
    Использует существующую функцию get_by_eth_address для поиска.
    """
    user = get_by_eth_address(db, wallet_address)
    return user.id if user else None