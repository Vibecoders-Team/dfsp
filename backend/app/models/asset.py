from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

from .users import User


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # file id (bytes32) in hex (0x + 64)
    file_id_hex: Mapped[str] = mapped_column(String(66), index=True)

    # CID from IPFS
    cid: Mapped[str] = mapped_column(String(120), index=True)

    # chain
    tx_hash: Mapped[str] = mapped_column(String(66), index=True)  # 0x + 64
    owner: Mapped[str | None] = mapped_column(String(42), index=True)  # eth address
    chain_block: Mapped[int | None] = mapped_column(Integer, index=True)
    chain_timestamp: Mapped[int | None] = mapped_column(Integer)  # unix sec

    # file
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str | None] = mapped_column(String(128))

    # owner in our system (from JWT), can be null
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped[User] = relationship("User", backref="assets")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
