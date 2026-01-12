# backend/app/repos/grant_repo.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.models.files import File
from app.models.grants import Grant
from app.models.users import User  # Important: import User model
from app.schemas.bot import GrantDirection


def get_grants_for_user(
    db: Session,
    user_id: str,
    direction: GrantDirection,
    limit: int,
    cursor: datetime | None,
) -> list[tuple[Grant, str]]:
    """
    Get list of grants for user_id with cursor pagination.

    Returns list of tuples (Grant object, file name).
    """
    # Create aliases for User to distinguish grantor and grantee in the query
    GrantorUser = aliased(User)
    GranteeUser = aliased(User)

    # Base query with JOINs to file and both users
    query = (
        select(Grant, File.name)
        .join(File, Grant.file_id == File.id)
        .join(GrantorUser, Grant.grantor_id == GrantorUser.id)
        .join(GranteeUser, Grant.grantee_id == GranteeUser.id)
    )

    # Apply direction filter using user_id
    if direction == GrantDirection.IN:
        query = query.where(Grant.grantee_id == user_id)
    else:  # direction == GrantDirection.OUT
        query = query.where(Grant.grantor_id == user_id)

    # Additionally filter to show only confirmed grants
    query = query.where(Grant.status == "confirmed")

    # Apply cursor by created_at
    if cursor:
        query = query.where(Grant.created_at < cursor)

    # Sort, limit, and execute
    query = query.order_by(Grant.created_at.desc()).limit(limit)

    results = db.execute(query).all()
    return results
