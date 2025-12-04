from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PublicLink(Base):
    __tablename__ = "public_links"
    __table_args__ = (
        UniqueConstraint("token", name="ux_public_links_token"),
        Index("ix_public_links_file_id", "file_id"),
        Index("ix_public_links_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK → files.id (bytes32)
    file_id: Mapped[bytes] = mapped_column(
        sa.LargeBinary(32), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )

    version: Mapped[int | None] = mapped_column(nullable=True)

    token: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)

    max_downloads: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    downloads_count: Mapped[int] = mapped_column(sa.Integer(), nullable=False, server_default=sa.text("0"))

    pow_difficulty: Mapped[int | None] = mapped_column(sa.SmallInteger(), nullable=True)
    bandwidth_mb_per_day: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)

    one_time: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, server_default=sa.text("false"))

    snapshot_name: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    snapshot_mime: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    snapshot_size: Mapped[int | None] = mapped_column(sa.BigInteger(), nullable=True)
    snapshot_cid: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # ORM relationships
    file = relationship("File")
    creator = relationship("User", foreign_keys=[created_by])
