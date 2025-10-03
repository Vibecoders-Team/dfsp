from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from ..deps import get_db, rds
from ..models import File, User
from ..schemas.auth import MetaTxSubmitIn
from ..security import parse_token
from ..relayer import enqueue_forward_request

router = APIRouter(prefix="/meta-tx", tags=["meta-tx"])

@router.post("/submit")
def submit(req: MetaTxSubmitIn, db: Session = Depends(get_db)):
    # идемпотентность
    key = f"mtx:req:{req.request_id}"
    if rds.exists(key):
        return {"status":"duplicate"}
    # опциональная серверная проверка подписи (быстрый fail)
    try:
        ok = True  # можно вызвать verify_forward_signature(req.typed_data, req.signature)
    except Exception:
        raise HTTPException(400, "signature_invalid")

    rds.setex(key, 3600, "queued")
    task_id = enqueue_forward_request(req.request_id, req.typed_data, req.signature)
    return {"status":"queued", "task_id": task_id}
