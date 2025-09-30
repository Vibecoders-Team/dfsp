from datetime import datetime
from sqlalchemy import func, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    eth_address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    display_name: Mapped[str | None]
    rsa_public_spki_pem: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
