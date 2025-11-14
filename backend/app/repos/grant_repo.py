# backend/app/repos/grant_repo.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session, aliased
from sqlalchemy import select

from app.models.grants import Grant
from app.models.files import File
from app.models.users import User  # Важно: импортируем модель User
from app.schemas.bot import GrantDirection


def get_grants_for_user(
    db: Session,
    user_id: str,
    direction: GrantDirection,
    limit: int,
    cursor: datetime | None,
) -> list[tuple[Grant, str]]:
    """
    Получает список грантов для user_id с курсорной пагинацией.

    Возвращает список кортежей (объект Grant, имя файла).
    """
    # Создаем алиасы для User, чтобы различать grantor и grantee в запросе
    GrantorUser = aliased(User)
    GranteeUser = aliased(User)

    # Базовый запрос с JOIN'ами к файлу и обоим пользователям
    query = (
        select(Grant, File.name)
        .join(File, Grant.file_id == File.id)
        .join(GrantorUser, Grant.grantor_id == GrantorUser.id)
        .join(GranteeUser, Grant.grantee_id == GranteeUser.id)
    )

    # Применяем фильтр по направлению, используя user_id
    if direction == GrantDirection.IN:
        query = query.where(Grant.grantee_id == user_id)
    else:  # direction == GrantDirection.OUT
        query = query.where(Grant.grantor_id == user_id)

    # Дополнительно фильтруем, чтобы показывать только подтвержденные гранты
    query = query.where(Grant.status == "confirmed")

    # Применяем курсор по дате создания
    if cursor:
        query = query.where(Grant.created_at < cursor)

    # Сортировка, лимит и выполнение
    query = query.order_by(Grant.created_at.desc()).limit(limit)

    results = db.execute(query).all()
    return results