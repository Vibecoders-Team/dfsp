from datetime import datetime
from sqlalchemy import Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
import uuid

class MetaTxRequest(Base):
    __tablename__ = "meta_tx_requests"
    __table_args__ = (
        Index("ix_mtx_status_created", "status", "created_at"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[str]
    tx_hash: Mapped[str | None]
    status: Mapped[str]            # queued/sent/mined/failed
    gas_used: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
