from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_chain
from app.deps import get_db, rds
from app.relayer import enqueue_forward_request
from app.schemas.auth import MetaTxSubmitIn

router = APIRouter(prefix="/meta-tx", tags=["meta-tx"])


@router.post("/submit")
def submit(req: MetaTxSubmitIn, db: Session = Depends(get_db), chain=Depends(get_chain)):
    # идемпотентность
    key = f"mtx:req:{req.request_id}"
    if rds.exists(key):
        return {"status": "duplicate"}
    # опциональная серверная проверка подписи (быстрый fail)
    if getattr(settings, "verify_forward_sig", False):
        try:
            if not chain.verify_forward(req.typed_data, req.signature):
                raise HTTPException(400, "signature_invalid")
        except Exception as e:
            raise HTTPException(400, f"signature_invalid: {e}")

    rds.setex(key, 3600, "queued")
    task_id = enqueue_forward_request(req.request_id, req.typed_data, req.signature)
    return {"status": "queued", "task_id": task_id}, status.HTTP_202_ACCEPTED
