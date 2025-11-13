from __future__ import annotations
from sqlalchemy.orm import Session
from app.models.telegram_link import TelegramLink
from sqlalchemy import func


def link_user_to_chat(db: Session, wallet_address: str, chat_id: int) -> TelegramLink:
    """
    Создает или обновляет (UPSERT) связь между wallet_address и chat_id.
    Работает в синхронном стиле, совместимом с psycopg.
    """
    normalized_address = wallet_address.lower()

    # Сначала пытаемся найти существующую запись
    instance: TelegramLink | None = (
        db.query(TelegramLink)
        .filter_by(wallet_address=normalized_address, chat_id=chat_id)
        .one_or_none()
    )

    if instance:
        # Если нашли - обновляем
        instance.revoked_at = None
    else:
        # Если не нашли - создаем новую
        instance = TelegramLink(wallet_address=normalized_address, chat_id=chat_id, revoked_at=None)
        db.add(instance)

    # Коммитим изменения (обновление или создание)
    db.commit()
    db.refresh(instance)

    return instance

def revoke_links_by_address(db: Session, wallet_address: str) -> int:
    """
    Деактивирует (soft-delete) все активные привязки для указанного wallet_address.
    Устанавливает revoked_at = NOW() для всех записей, где оно IS NULL.

    Возвращает количество обновленных записей.
    Идемпотентна: при повторном вызове обновит 0 записей и не вызовет ошибки.
    """
    normalized_address = wallet_address.lower()

    # Находим все активные привязки для этого адреса
    query = db.query(TelegramLink).filter(
        TelegramLink.wallet_address == normalized_address,
        TelegramLink.revoked_at.is_(None)
    )

    # Обновляем у них поле revoked_at на текущее время
    # .update() возвращает количество затронутых строк
    updated_rows = query.update({"revoked_at": func.now()})

    db.commit()

    return updated_rows