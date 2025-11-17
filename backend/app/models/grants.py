from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        # unique cap_id and useful lookups
        UniqueConstraint("cap_id", name="uq_grants_cap_id"),
        Index("ix_grants_grantee", "grantee_id"),
        Index("ix_grants_file", "file_id"),
        Index("ix_grants_grantee_expires", "grantee_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # capId bytes32 (on-chain)
    cap_id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)

    # FK → files.id (bytes32)
    file_id: Mapped[bytes] = mapped_column(
        sa.LargeBinary(32), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )

    grantor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    grantee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    max_dl: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    used: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String, nullable=False, server_default="pending"
    )  # pending|confirmed|revoked
    tx_hash: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    # зашифрованный ключ (encK), bytea
    enc_key: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Отношения для ORM
    file = relationship("File", back_populates="grants")
    grantor = relationship("User", foreign_keys=[grantor_id], back_populates="given_grants")
    grantee = relationship("User", foreign_keys=[grantee_id], back_populates="received_grants")
