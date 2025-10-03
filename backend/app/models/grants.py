from __future__ import annotations

import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        Index("ix_grants_grantee", "grantee_id"),
        Index("ix_grants_file", "file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    grantee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    ttl_days: Mapped[int | None] = mapped_column(nullable=True)
    max_dl: Mapped[int | None] = mapped_column(nullable=True)
    used: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    # шифрованный ключ получателя (строка, может быть длинной)
    enc_k: Mapped[str | None] = mapped_column(nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
