from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.deps import get_chain

router = APIRouter(prefix="/chain", tags=["chain"])


@router.get("/info")
async def chain_info() -> dict[str, Any]:
    chain = get_chain()
    forwarder = chain.contracts.get("MinimalForwarder")
    fwd_addr = getattr(forwarder, "address", None) if forwarder else None
    return {
        "chain_id": int(getattr(chain, "chain_id", 0)),
        "forwarder": fwd_addr,
        "public_rpc_url": settings.chain_public_rpc_url,
    }
