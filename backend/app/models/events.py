from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_period", "period_id"),
        Index("ix_events_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)

    period_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    ts: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(nullable=False)

    # FK на files.id (UUID)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # FK на users.id (UUID)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # фиксированной длины 32 байта
    payload_hash: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
