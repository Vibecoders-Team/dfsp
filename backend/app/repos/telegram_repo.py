from __future__ import annotations
from sqlalchemy.orm import Session
from app.models.telegram_link import TelegramLink


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