# backend/app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Предполагаем, что ваш settings находится в app/config.py
from app.config import settings

# --- Импорт роутеров ---
# Группируем импорты роутеров для порядка
from .routers.system import router as system_router
from app.routers.auth import router as auth_router

# --- Настройка логирования ---
log = logging.getLogger("dfsp.api")
logging.basicConfig(level=logging.INFO)

# --- Инициализация приложения ---
app = FastAPI(title="DFSP API", version="0.1.0")

# --- Middleware ---
# CORS (используем ваш вариант, он полностью корректен)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins, # Убедитесь, что в config.py переменная называется cors_origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Подключение роутеров ---
# Системный роутер уже был
app.include_router(system_router, prefix="/api", tags=["system"])
# Добавляем новый роутер аутентификации
app.include_router(auth_router, prefix="/api", tags=["Authentication"]) # <--- 2. ДОБАВЛЕНО: Подключаем роутер auth

# --- События жизненного цикла ---
@app.on_event("startup")
async def _on_startup():
    log.info("Loaded settings: %s", settings.debug_dump())

# <--- 3. ДОБАВЛЕНО (опционально): Корневой эндпоинт для проверки, что API жив ---
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Welcome to DFSP API"}