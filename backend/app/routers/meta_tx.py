from __future__ import annotations

# NEW: optional sync execution in dev
import logging
import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..deps import get_db, rds
from ..models.meta_tx_requests import MetaTxRequest
from ..relayer import enqueue_forward_request
from ..relayer import submit_forward as _submit_forward_task
from ..schemas.auth import MetaTxSubmitIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meta-tx", tags=["meta-tx"])


def _validate_typed_data(td: dict) -> None:
    if not isinstance(td, dict):
        raise HTTPException(400, "typed_data_invalid")
    if not all(k in td for k in ("domain", "types", "primaryType", "message")):
        raise HTTPException(400, "typed_data_invalid")
    if not isinstance(td["message"], dict):
        raise HTTPException(400, "typed_data_invalid")


@router.post("/submit")
def submit(req: MetaTxSubmitIn, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    """
    Accept signed ForwardRequest and enqueue it in the relayer.
    Return a deterministic JSON response with status.
    In DEV mode (RELAYER_SYNC_DEV=1), also execute the task synchronously in-process.
    Idempotency behavior: we allow re-enqueue with the same request_id,
    relying on DB/relayer de-duplication to avoid sticking on an old NX flag.
    """
    # Basic validation of typedData shape (avoid .get errors)
    _validate_typed_data(req.typed_data)

    # Soft mark in Redis (without NX) to avoid blocking re-enqueue
    key = f"mtx:req:{req.request_id}"
    try:
        rds.set(key, "queued", ex=3600)
    except Exception:
        # best-effort, log for diagnostics
        logger.debug("submit_meta_tx: failed to set redis key %s", key, exc_info=True)

    # Upsert MetaTxRequest in DB (for internal de-duplication and monitoring)
    try:
        rid = uuid.UUID(str(req.request_id))
    except Exception as e:
        raise HTTPException(400, "bad_request_id") from e
    try:
        m = db.get(MetaTxRequest, rid)
        if m is None:
            m = MetaTxRequest(request_id=rid, type="forward", status="queued")
            db.add(m)
        else:
            if m.status not in ("sent", "mined"):
                m.status = "queued"
                db.add(m)
        db.commit()
    except Exception:
        db.rollback()
        # non-critical for enqueueing the task


    # Enqueue task in Celery (de-duplication and serialization happen in the task itself)
    task_id = enqueue_forward_request(req.request_id, req.typed_data, req.signature)

    # Optional DEV path: execute synchronously (without worker)
    if os.getenv("RELAYER_SYNC_DEV", "0") == "1":
        try:
            result = _submit_forward_task.apply(args=[req.request_id, req.typed_data, req.signature]).get(timeout=60)
            response.status_code = 200
            return {"status": "executed", "task_id": task_id, "result": result}
        except Exception as e:
            response.status_code = 202
            return {"status": "queued", "task_id": task_id, "error": str(e)}

    # 202 — accepted for processing
    response.status_code = 202
    return {"status": "queued", "task_id": task_id}
