from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Anchor(Base):
    __tablename__ = "anchors"
    __table_args__ = (UniqueConstraint("period_id", name="uq_anchors_period"),)

    # Identity is more correct for PG, but autoincrement on int PK is OK
    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)

    period_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # 32 bytes (bytea)
    root: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)

    # Transaction hash on blockchain (optional, for future integration)
    tx_hash: Mapped[str | None] = mapped_column(sa.String(66), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
