from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.proxy_headers import ProxyHeadersMiddleware

from app.routers.health import router as health_router
from app.routers import pow as pow_router
from app.routers.auth import router as auth_router
from app.routers.storage import router as storage_router
from app.routers.admin import router as admin_router

from .routers.files import router as files_router
from .routers.meta_tx import router as mtx_router
from .routers.verify import router as verify_router
from .routers.download import router as download_router
from .routers.grants import router as grants_router
from .routers.users import router as users_router
from .routers.anchors import router as anchors_router
from .routers.chain_info import router as chain_info_router

# NEW: telemetry
from app.telemetry.logging import init_logging
from app.telemetry.metrics import router as metrics_router
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware import SecurityHeadersMiddleware

# Initialize structured logging
init_logging()

app = FastAPI(title="DFSP API")

# Trust X-Forwarded-For/Proto from reverse proxy (nginx)
app.add_middleware(ProxyHeadersMiddleware)

# Observability middleware (request metrics + structured logs)
app.add_middleware(ObservabilityMiddleware)

# Global rate limit for public endpoints (no Authorization header)
app.add_middleware(RateLimitMiddleware, limit_per_minute=100)

# CORS: используем список из настроек; поддерживаем '*'
_allowed_origins = settings.cors_origins
_allow_credentials = _allowed_origins != ["*"]
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=(["*"] if _allowed_origins == ["*"] else _allowed_origins),
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers for all responses
app.add_middleware(SecurityHeadersMiddleware)

# Convert 422 validation errors to 400 as per AC
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):  # type: ignore[no-redef]
    # Sanitize pydantic error objects so they are always JSON serializable
    sanitized: list[dict] = []
    try:
        for err in exc.errors():
            e = dict(err)
            # Coerce ctx values to strings
            ctx = e.get("ctx")
            if isinstance(ctx, dict):
                e["ctx"] = {str(k): str(v) for k, v in ctx.items()}
            elif ctx is not None:
                e["ctx"] = str(ctx)
            # Ensure 'input' is serializable (fallback to str for unknown types)
            if "input" in e:
                val = e["input"]
                if not isinstance(val, (str, int, float, bool, type(None), list, dict)):
                    e["input"] = str(val)
            sanitized.append(e)
    except Exception:
        sanitized = [{"type": "validation_error", "detail": "invalid input"}]
    return JSONResponse(status_code=400, content={"detail": sanitized})

app.include_router(health_router)
app.include_router(metrics_router)  # /metrics
app.include_router(auth_router)
app.include_router(storage_router)
app.include_router(mtx_router)
app.include_router(verify_router)
app.include_router(files_router)
app.include_router(download_router)
app.include_router(grants_router)
app.include_router(anchors_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(pow_router.router)
app.include_router(chain_info_router)
