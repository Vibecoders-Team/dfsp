from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Предполагаем, что ваш settings находится в app/config.py
from app.config import settings
from fastapi.middleware.cors import CORSMiddleware

from .routers.health import router as health_router
from .routers.auth import router as auth_router
from .routers.storage import router as storage_router
#from .routers.meta_tx import router as mtx_router
#from .routers.verify import router as verify_router

app = FastAPI(title="DFSP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5170"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(storage_router)
#app.include_router(mtx_router)
#app.include_router(verify_router)