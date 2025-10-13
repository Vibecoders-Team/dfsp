from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Anchor(Base):
    __tablename__ = "anchors"
    __table_args__ = (UniqueConstraint("period_id", name="uq_anchors_period"),)

    # для PG корректнее Identity, но autoincrement на PK int тоже ок
    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)

    period_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # 32 байта (bytea)
    root: Mapped[bytes] = mapped_column(sa.LargeBinary(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
