from datetime import datetime
from sqlalchemy import ForeignKey, Index, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
import uuid

class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_period", "period_id"),
        Index("ix_events_ts", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_id: Mapped[int]
    ts: Mapped[datetime] = mapped_column(server_default=func.now())
    type: Mapped[str]
    file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    payload_hash: Mapped[bytes] = mapped_column(LargeBinary)
