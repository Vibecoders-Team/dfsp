# backend/app/schemas/bot.py
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BotFile(BaseModel):
    """Компактное представление файла для ответа боту."""

    id_hex: str = Field(..., description="File ID в виде hex-строки (32 байта)")
    name: str
    size: int
    mime: str | None
    cid: str
    created_at: datetime = Field(..., alias="updatedAt")

    class Config:
        populate_by_name = True


class BotFileListResponse(BaseModel):
    """Ответ со списком файлов и курсором для следующей страницы."""

    files: list[BotFile]
    cursor: str | None = Field(
        None,
        description="Курсор для следующей страницы (ISO timestamp)",
    )


class GrantDirection(str, Enum):
    """Направление грантов для фильтрации."""

    IN = "in"
    OUT = "out"


class BotGrant(BaseModel):
    """Компактное представление гранта для ответа боту."""

    capId: str = Field(..., description="Capability ID гранта в hex-формате")
    fileName: str
    used: int
    max_dl: int = Field(..., alias="max")  # используем max_dl из модели и отдаём как max
    expiresAt: datetime
    status: str  # "active", "expired", "revoked", "used_up"

    class Config:
        populate_by_name = True


class BotGrantListResponse(BaseModel):
    """Ответ со списком грантов и курсором для следующей страницы."""

    grants: list[BotGrant]
    cursor: str | None = Field(
        None,
        description="Курсор для следующей страницы (ISO timestamp)",
    )


class BotProfileResponse(BaseModel):
    """Профиль пользователя для бота (/bot/me)."""

    address: str = Field(..., description="Связанный wallet-адрес пользователя")
    display_name: str | None = Field(
        None,
        description="Отображаемое имя пользователя, если задано",
    )
