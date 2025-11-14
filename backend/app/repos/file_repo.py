# backend/app/repos/file_repo.py
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.files import File

def get_files_by_owner_id(
    db: Session, owner_id: uuid.UUID, limit: int, cursor: datetime | None
) -> list[File]:
    """
    Получает список файлов для пользователя с курсорной пагинацией по created_at.
    """
    query = db.query(File).filter(File.owner_id == owner_id)

    if cursor:
        # Если есть курсор, ищем записи, которые были созданы раньше
        query = query.filter(File.created_at < cursor)

    # Сортируем по убыванию даты, чтобы новые были первыми
    return query.order_by(File.created_at.desc()).limit(limit).all()