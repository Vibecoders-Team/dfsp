from fastapi import FastAPI

from app.config import settings
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers import pow as pow_router
from app.routers.auth import router as auth_router
from app.routers.storage import router as storage_router

from .routers.files import router as files_router
from .routers.meta_tx import router as mtx_router
from .routers.verify import router as verify_router
from .routers.download import router as download_router
from .routers.grants import router as grants_router

app = FastAPI(title="DFSP API")

app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=[settings.cors_origin or "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(storage_router)
app.include_router(mtx_router)
app.include_router(verify_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(grants_router)
app.include_router(pow_router.router)
