from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.telegram_link import TelegramLink


def link_user_to_chat(db: Session, wallet_address: str, chat_id: int) -> TelegramLink:
    """
    Создает или обновляет (UPSERT) связь между wallet_address и chat_id.
    """
    normalized_address = (wallet_address or "").lower()

    instance: TelegramLink | None = (
        db.query(TelegramLink).filter_by(wallet_address=normalized_address, chat_id=chat_id).one_or_none()
    )

    if instance:
        instance.revoked_at = None
    else:
        instance = TelegramLink(
            wallet_address=normalized_address,
            chat_id=chat_id,
            revoked_at=None,
        )
        db.add(instance)

    db.commit()
    db.refresh(instance)
    return instance


def revoke_links_by_address(db: Session, wallet_address: str) -> int:
    """
    Деактивирует все активные привязки для указанного wallet_address
    (revoked_at = NOW() где revoked_at IS NULL).
    """
    normalized_address = (wallet_address or "").lower()

    query = db.query(TelegramLink).filter(
        TelegramLink.wallet_address == normalized_address,
        TelegramLink.revoked_at.is_(None),
    )

    updated_rows = query.update({"revoked_at": func.now()})
    db.commit()

    return updated_rows


def get_wallet_by_chat_id(db: Session, chat_id: int) -> str | None:
    """
    Возвращает wallet_address по Telegram chat_id
    для *активной* привязки (revoked_at IS NULL),
    либо None, если привязки нет.
    """
    wallet = db.execute(
        select(TelegramLink.wallet_address)
        .where(
            TelegramLink.chat_id == chat_id,
            TelegramLink.revoked_at.is_(None),
        )
        .order_by(TelegramLink.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return wallet
