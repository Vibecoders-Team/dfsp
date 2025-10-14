from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..deps import get_db, rds
from ..schemas.auth import MetaTxSubmitIn
from ..relayer import enqueue_forward_request

router = APIRouter(prefix="/meta-tx", tags=["meta-tx"])


def _validate_typed_data(td: dict):
    if not isinstance(td, dict):
        raise HTTPException(400, "typed_data_invalid")
    if not all(k in td for k in ("domain", "types", "primaryType", "message")):
        raise HTTPException(400, "typed_data_invalid")
    if not isinstance(td["message"], dict):
        raise HTTPException(400, "typed_data_invalid")


@router.post("/submit")
def submit(req: MetaTxSubmitIn, response: Response, db: Session = Depends(get_db)):
    """
    Принимаем подписанный ForwardRequest и кладем задачу в релейер.
    Гарантируем детерминированный JSON-ответ со статусом.
    """
    # идемпотентность: атомарный set NX
    key = f"mtx:req:{req.request_id}"
    created = rds.set(key, "queued", ex=3600, nx=True)
    if not created:
        # уже был поставлен в очередь ранее
        # возвращаем детерминированный dict
        response.status_code = 200
        return {"status": "duplicate"}

    # базовая валидация формы typedData (чтобы не падали на .get)
    _validate_typed_data(req.typed_data)

    # опциональная серверная проверка подписи — если включите, замените ok=True на реальную проверку
    try:
        ok = True
        if not ok:
            # снимаем флажок идемпотентности, чтобы можно было повторить
            rds.delete(key)
            raise HTTPException(400, "signature_invalid")
    except HTTPException:
        raise
    except Exception:
        rds.delete(key)
        raise HTTPException(400, "signature_invalid")

    # ставим задачу в Celery
    task_id = enqueue_forward_request(req.request_id, req.typed_data, req.signature)

    # 202 — принято в обработку
    response.status_code = 202
    return {"status": "queued", "task_id": task_id}
