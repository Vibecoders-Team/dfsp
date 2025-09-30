from typing import Annotated
import uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, BigInteger, Text, LargeBinary, Index, CheckConstraint, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# Базовый класс
class Base(DeclarativeBase):
    pass

# Общие типы
UUID_PK = Annotated[uuid.UUID, mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)]
BYTES32 = Annotated[bytes, mapped_column(LargeBinary(32))]
TS_NOW = Annotated[str, mapped_column(server_default=text("now()"))]
