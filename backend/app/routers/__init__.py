from fastapi import APIRouter
from .system import router as system_router
# позже: auth, files, grants, download, verify, anchors, metatx, pow

api_router = APIRouter()
api_router.include_router(system_router)
