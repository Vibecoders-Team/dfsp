from datetime import datetime
from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Anchor(Base):
    __tablename__ = "anchors"
    __table_args__ = (UniqueConstraint("period_id", name="uq_anchors_period"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int]
    root: Mapped[bytes]            # merkle root (32 bytes)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
