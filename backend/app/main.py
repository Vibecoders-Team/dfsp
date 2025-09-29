from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .config import settings

log = logging.getLogger("dfsp.api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DFSP API", version="0.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- system routes ---
from .routers.system import router as system_router  # noqa: E402
app.include_router(system_router, prefix="/api", tags=["system"])


@app.on_event("startup")
async def _on_startup():
    log.info("Loaded settings: %s", settings.debug_dump())

