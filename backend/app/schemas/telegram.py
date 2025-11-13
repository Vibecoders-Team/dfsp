from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

# Схема для тела запроса к /tg/link-start
class TgLinkStartRequest(BaseModel):
    chat_id: int = Field(..., gt=0, description="Telegram User Chat ID")


# Схема для ответа от /tg/link-start
class TgLinkStartResponse(BaseModel):
    link_token: str
    expires_at: datetime
    
# Схема для тела запроса к /tg/link-complete
class TgLinkCompleteRequest(BaseModel):
    link_token: str

# Стандартный успешный ответ
class OkResponse(BaseModel):
    ok: bool = True