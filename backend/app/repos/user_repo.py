from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User
from app.schemas.auth import RegisterIn


def get_by_eth_address(db: Session, eth_address: str) -> User | None:
    """Найти пользователя по EVM-адресу (нормализуем к lower())."""
    return db.query(User).filter(User.eth_address == (eth_address or "").lower()).one_or_none()


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
