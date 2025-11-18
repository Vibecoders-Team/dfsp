from __future__ import annotations

# NEW: optional sync execution in dev
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
    Принимаем подписанный ForwardRequest и кладем задачу в релейер.
    Гарантируем детерминированный JSON-ответ со статусом.
    В DEV-режиме (RELAYER_SYNC_DEV=1) дополнительно выполняем задачу синхронно в текущем процессе.
    Поведение идемпотентности: мы допускаем повторную постановку в очередь с тем же request_id,
    опираясь на БД/релейер для дедупликации, чтобы не залипать из-за прежнего NX-флага.
    """
    # базовая валидация формы typedData (чтобы не падали на .get)
    _validate_typed_data(req.typed_data)

    # мягкая пометка в Redis (без NX) — не блокирует повторную постановку
    key = f"mtx:req:{req.request_id}"
    try:
        rds.set(key, "queued", ex=3600)
    except Exception:
        # best-effort, log for diagnostics
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("submit_meta_tx: failed to set redis key %s", key, exc_info=True)

    # upsert в БД запись MetaTxRequest (для внутренних дедупов и мониторинга)
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
        # не критично для постановки задачи

    # ставим задачу в Celery (дедупликация и сериализация произойдут в самой задаче)
    task_id = enqueue_forward_request(req.request_id, req.typed_data, req.signature)

    # опциональный DEV path: выполнить синхронно (без воркера)
    if os.getenv("RELAYER_SYNC_DEV", "0") == "1":
        try:
            result = _submit_forward_task.apply(args=[req.request_id, req.typed_data, req.signature]).get(timeout=60)
            response.status_code = 200
            return {"status": "executed", "task_id": task_id, "result": result}
        except Exception as e:
            response.status_code = 202
            return {"status": "queued", "task_id": task_id, "error": str(e)}

    # 202 — принято в обработку
    response.status_code = 202
    return {"status": "queued", "task_id": task_id}
