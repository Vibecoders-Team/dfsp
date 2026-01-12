# backend/app/repos/file_repo.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.files import File


def get_files_by_owner_id(db: Session, owner_id: uuid.UUID, limit: int, cursor: datetime | None) -> list[File]:
    """
    Get list of files for a user with cursor pagination by created_at.
    """
    query = db.query(File).filter(File.owner_id == owner_id)

    if cursor:
        # If cursor is set, fetch records created earlier
        query = query.filter(File.created_at < cursor)

    # Sort descending by date so newest are first
    return query.order_by(File.created_at.desc()).limit(limit).all()
