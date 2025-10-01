from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse
from app.dependencies import get_db
from app.repos import user_repo

# Создаем роутер
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

# Временный тестовый роут, чтобы убедиться, что импорт работает
@router.get("/status")
async def get_auth_status():
    return {"status": "Auth router is ready, but endpoints are not implemented yet."}

# ВНИМАНИЕ: Здесь будут добавлены эндпоинты для:
# 1. /auth/nonce (генерация nonce для Web3)
# 2. /auth/verify (проверка подписи и выдача JWT)
# 3. /auth/register (регистрация классического пользователя)
# 4. /auth/login (логин классического пользователя)
