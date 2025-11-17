from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.grants import Grant


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("checksum", "owner_id", name="uq_files_checksum_owner"),
        Index("ix_files_owner", "owner_id"),
        Index("ix_files_owner_created", "owner_id", "created_at"),
    )

    # PK = bytes32 (on-chain fileId)
    id: Mapped[bytes] = mapped_column(sa.LargeBinary(32), primary_key=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    mime: Mapped[str | None] = mapped_column(nullable=True)
    cid: Mapped[str] = mapped_column(nullable=False)

    checksum: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    grants: Mapped[list[Grant]] = relationship(
        "Grant", back_populates="file", cascade="all, delete-orphan"
    )


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_id", "version", name="uq_file_versions_file_version"),
        Index("ix_file_versions_file", "file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # FK → files.id (bytes32)
    file_id: Mapped[bytes] = mapped_column(
        sa.LargeBinary(32), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )

    version: Mapped[int] = mapped_column(nullable=False)
    cid: Mapped[str] = mapped_column(nullable=False)

    checksum: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)
    size: Mapped[int] = mapped_column(nullable=False)
    mime: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
