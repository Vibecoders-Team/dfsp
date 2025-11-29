from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.telegram_link import TelegramLink
from app.models.users import User

logger = logging.getLogger(__name__)


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
        instance.is_active = True
    else:
        instance = TelegramLink(
            wallet_address=normalized_address,
            chat_id=chat_id,
            revoked_at=None,
            is_active=True,
        )
        db.add(instance)

    # Ensure only one active per chat
    db.query(TelegramLink).filter(
        TelegramLink.chat_id == chat_id, TelegramLink.wallet_address != normalized_address
    ).update({"is_active": False})

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


def get_active_chat_ids_for_addresses(db: Session, addresses: list[str]) -> dict[str, int]:
    """
    Возвращает mapping address(lower) -> chat_id для активных привязок.
    Берём последний по created_at для каждого адреса.
    """
    if not addresses:
        return {}
    normalized = [addr.lower() for addr in addresses if addr]
    if not normalized:
        return {}
    rows = (
        db.query(TelegramLink.wallet_address, TelegramLink.chat_id, TelegramLink.created_at)
        .filter(
            TelegramLink.wallet_address.in_(normalized),
            TelegramLink.revoked_at.is_(None),
            TelegramLink.is_active.is_(True),
        )
        .order_by(TelegramLink.wallet_address, TelegramLink.created_at.desc())
        .all()
    )
    out: dict[str, int] = {}
    for addr, chat_id, _created_at in rows:
        if addr and addr.lower() not in out:
            out[addr.lower()] = int(chat_id)
    return out


def get_active_chat_id_for_user(db: Session, user: User) -> int | None:
    """Возвращает chat_id по eth_address пользователя, если есть активная привязка."""
    if not user or not user.eth_address:
        return None
    mapping = get_active_chat_ids_for_addresses(db, [user.eth_address])
    return mapping.get(user.eth_address.lower())


def get_wallet_by_chat_id(db: Session, chat_id: int) -> str | None:
    """
    Возвращает wallet_address по Telegram chat_id
    для *активной* привязки (revoked_at IS NULL),
    либо None, если привязки нет.
    """
    wallet = (
        db.query(TelegramLink.wallet_address)
        .filter(
            TelegramLink.chat_id == chat_id,
            TelegramLink.revoked_at.is_(None),
        )
        .order_by(TelegramLink.is_active.desc(), TelegramLink.created_at.desc())
        .limit(1)
        .scalar()
    )

    return wallet


def list_links_by_chat(db: Session, chat_id: int) -> list[TelegramLink]:
    return (
        db.query(TelegramLink)
        .filter(TelegramLink.chat_id == chat_id, TelegramLink.revoked_at.is_(None))
        .order_by(TelegramLink.created_at.desc())
        .all()
    )


def upsert_link(db: Session, chat_id: int, wallet_address: str, make_active: bool) -> TelegramLink:
    normalized = (wallet_address or "").lower()
    link = (
        db.query(TelegramLink)
        .filter(TelegramLink.chat_id == chat_id, TelegramLink.wallet_address == normalized)
        .one_or_none()
    )
    has_active = (
        db.query(TelegramLink)
        .filter(
            TelegramLink.chat_id == chat_id,
            TelegramLink.revoked_at.is_(None),
            TelegramLink.is_active.is_(True),
        )
        .count()
        > 0
    )

    if link:
        link.revoked_at = None
        if make_active or not has_active:
            link.is_active = True
    else:
        link = TelegramLink(
            chat_id=chat_id,
            wallet_address=normalized,
            revoked_at=None,
            is_active=make_active or not has_active,
        )
        db.add(link)

    if make_active or not has_active:
        db.query(TelegramLink).filter(
            TelegramLink.chat_id == chat_id,
            TelegramLink.wallet_address != normalized,
        ).update({"is_active": False})

    db.commit()
    db.refresh(link)
    return link


def set_active_link(db: Session, chat_id: int, wallet_address: str) -> TelegramLink:
    normalized = (wallet_address or "").lower()
    link = (
        db.query(TelegramLink)
        .filter(
            TelegramLink.chat_id == chat_id,
            TelegramLink.wallet_address == normalized,
            TelegramLink.revoked_at.is_(None),
        )
        .one_or_none()
    )
    if link is None:
        raise LookupError("link_not_found")

    db.query(TelegramLink).filter(TelegramLink.chat_id == chat_id).update({"is_active": False})
    link.is_active = True
    db.commit()
    db.refresh(link)
    return link


def revoke_link(db: Session, chat_id: int, wallet_address: str) -> None:
    normalized = (wallet_address or "").lower()
    link = (
        db.query(TelegramLink)
        .filter(TelegramLink.chat_id == chat_id, TelegramLink.wallet_address == normalized)
        .one_or_none()
    )
    if link is None:
        return
    link.revoked_at = datetime.now(UTC)
    link.is_active = False
    db.add(link)
    db.commit()

    remaining = (
        db.query(TelegramLink)
        .filter(
            TelegramLink.chat_id == chat_id,
            TelegramLink.revoked_at.is_(None),
        )
        .order_by(TelegramLink.created_at.desc())
        .all()
    )
    if remaining:
        for idx, item in enumerate(remaining):
            item.is_active = idx == 0
            db.add(item)
        db.commit()
