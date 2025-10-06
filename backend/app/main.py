from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Предполагаем, что ваш settings находится в app/config.py
from app.config import settings

from .routers.auth import router as auth_router
#from .routers.files import router as files_router
#from .routers.meta_tx import router as mtx_router
#from .routers.verify import router as verify_router

app = FastAPI(title="DFSP API")

@app.get("/healthz")
def healthz():
    return {"ok": True}

app.include_router(auth_router)
#app.include_router(files_router)
#app.include_router(mtx_router)
#app.include_router(verify_router)