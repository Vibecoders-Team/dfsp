from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.grants import Grant


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # '0x' + 40 hex
    eth_address: Mapped[str] = mapped_column(String(42), unique=True, index=True, nullable=False)

    rsa_public: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str | None] = mapped_column(nullable=True)
    ton_pubkey: Mapped[bytes | None] = mapped_column(sa.LargeBinary(), unique=True)

    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    given_grants: Mapped[list[Grant]] = relationship(
        "Grant",
        foreign_keys="Grant.grantor_id",
        back_populates="grantor",
        cascade="all, delete-orphan",
    )
    received_grants: Mapped[list[Grant]] = relationship(
        "Grant",
        foreign_keys="Grant.grantee_id",
        back_populates="grantee",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, eth_address='{self.eth_address}')>"
