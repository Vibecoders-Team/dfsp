from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from typing_extensions import Annotated
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import File, Grant, User
from app.models.action_intent import ActionIntent
from app.repos import telegram_repo
from app.repos.user_repo import get_by_eth_address
from app.security import parse_token
from app.schemas.action_intent import (
    ActionIntentCreateIn,
    ActionIntentCreateOut,
    ActionIntentConsumeIn,
    ActionIntentConsumeOut,
)

router = APIRouter(prefix="/bot", tags=["Bot"])

ACTION_INTENT_TTL_SECONDS = 15 * 60  # 10–15 min as per task; we pick 15

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]


# =========================
# JWT helper for bot endpoints (action-intents)
# =========================

def _require_jwt_user(
    authorization: AuthorizationHeader,
    db: Session = Depends(get_db),
) -> User:
    """
    Extract current User from Bearer JWT.
    Shared between /bot/action-intents endpoints.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="auth_required")
    try:
        payload = parse_token(token)
        sub = getattr(payload, "sub", None) or payload.get("sub")
        user_id = uuid.UUID(str(sub))
    except Exception:
        raise HTTPException(status_code=401, detail="bad_token")
    user_obj: Optional[User] = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user_obj


# =========================
# Helpers for Telegram-based auth (files/grants)
# =========================

def _parse_chat_id(x_tg_chat_id: str) -> int:
    try:
        return int(x_tg_chat_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid X-TG-Chat-Id")


def _resolve_user_by_chat_id_value(chat_id: int, db: Session) -> User:
    """
    Общая логика: chat_id -> wallet -> User.
    Используется и как зависимость, и внутри хендлеров.
    """
    wallet_address = telegram_repo.get_wallet_by_chat_id(db, chat_id)
    if not wallet_address:
        raise HTTPException(status_code=404, detail="Chat is not linked")

    user = get_by_eth_address(db, wallet_address)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def _get_user_by_chat_id(
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
    db: Session = Depends(get_db),
) -> User:
    chat_id = _parse_chat_id(x_tg_chat_id)
    return _resolve_user_by_chat_id_value(chat_id, db)


def _parse_cursor(cursor: Optional[str]) -> Optional[datetime]:
    """
    Курсор — строка. Сначала пробуем трактовать как timestamp (float),
    затем как ISO 8601. Это даёт:
      - стабильный URL-safe формат, когда мы сами генерим курсор;
      - обратную совместимость, если кто-то шлёт ISO-дату.

    При неудаче кидаем 400 с сообщением из логов теста.
    """
    if cursor is None:
        return None

    # variant 1: POSIX timestamp
    try:
        ts = float(cursor)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        pass

    # variant 2: ISO-строка
    try:
        return datetime.fromisoformat(cursor)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid cursor format. Use ISO 8601.",
        )


def _datetime_to_cursor(dt: Optional[datetime]) -> Optional[str]:
    """
    Превращаем datetime в строковый курсор.
    Чтобы избежать проблем с '+' в таймзоне в query-параметре,
    используем timestamp (float) как строку.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(dt.timestamp())


# =========================
# GET /bot/files
# =========================

@router.get("/files")
def bot_list_files(
    user: User = Depends(_get_user_by_chat_id),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = Query(None),
):
    """
    Bot-friendly список файлов по Telegram chat_id.

    Вход:
      - X-TG-Chat-Id (header)
      - limit, cursor (строковый курсор)

    Ответ:
    {
      "files": [
        {
          "id_hex": "...",   # без 0x
          "name": "...",
          "size": 123,
          "mime": "...",
          "cid": "...",
          "updatedAt": "ISO8601"
        },
        ...
      ],
      "cursor": "<строковый курсор или null>"
    }
    """
    cursor_dt = _parse_cursor(cursor)

    q = (
        select(File)
        .where(File.owner_id == user.id)
        .order_by(File.created_at.desc())
    )
    if cursor_dt is not None:
        q = q.where(File.created_at < cursor_dt)

    rows: List[File] = db.scalars(q.limit(limit + 1)).all()
    page_items = rows[:limit]

    next_cursor: Optional[str] = None
    if len(rows) > limit and page_items:
        last = page_items[-1]
        next_cursor = _datetime_to_cursor(last.created_at)

    files_out = []
    for f in page_items:
        updated_at = f.created_at or datetime.now(timezone.utc)
        files_out.append(
            {
                "id_hex": f.id.hex(),  # без '0x'
                "name": f.name,
                "size": f.size,
                "mime": f.mime or "application/octet-stream",
                "cid": f.cid,
                "updatedAt": updated_at.isoformat(),
            }
        )

    return {"files": files_out, "cursor": next_cursor}


# =========================
# GET /bot/grants
# =========================

@router.get("/grants")
def bot_list_grants(
    direction: str = Query(..., alias="direction"),
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = Query(None),
):
    """
    Bot-friendly список грантов.

    Вход:
      - X-TG-Chat-Id
      - direction = "in" | "out"
      - limit, cursor

    Ответ:
    {
      "grants": [
        {
          "capId": "0x...",
          "fileName": "...",
          "used": 0,
          "max": 3,
          "expiresAt": "ISO8601",
          "status": "pending|confirmed|expired|revoked|exhausted"
        },
        ...
      ],
      "cursor": "<строковый курсор или null>"
    }
    """
    # 1) Сначала валидируем direction — это важно для теста invalid_direction
    if direction not in ("in", "out"):
        raise HTTPException(status_code=400, detail="invalid_direction")

    # 2) Теперь уже разбираем chat_id и пользователя
    chat_id = _parse_chat_id(x_tg_chat_id)
    user = _resolve_user_by_chat_id_value(chat_id, db)

    cursor_dt = _parse_cursor(cursor)

    if direction == "out":
        cond = Grant.grantor_id == user.id
    else:
        cond = Grant.grantee_id == user.id

    q = (
        select(Grant, File.name)
        .join(File, File.id == Grant.file_id)
        .where(cond)
        .order_by(Grant.created_at.desc())
    )
    if cursor_dt is not None:
        q = q.where(Grant.created_at < cursor_dt)

    rows: List[Tuple[Grant, str]] = db.execute(q.limit(limit + 1)).all()
    page_items = rows[:limit]

    next_cursor: Optional[str] = None
    if len(rows) > limit and page_items:
        last_grant = page_items[-1][0]
        next_cursor = _datetime_to_cursor(last_grant.created_at)

    now = datetime.now(timezone.utc)
    grants_out = []
    for g, file_name in page_items:
        status = (g.status or "pending").lower()
        if g.revoked_at is not None:
            status = "revoked"
        elif now > g.expires_at:
            status = "expired"
        elif int(g.used or 0) >= int(g.max_dl or 0):
            status = "exhausted"

        grants_out.append(
            {
                "capId": "0x" + bytes(g.cap_id).hex(),
                "fileName": file_name,
                "used": int(g.used or 0),
                "max": int(g.max_dl or 0),
                "expiresAt": g.expires_at.isoformat(),
                "status": status,
            }
        )

    return {"grants": grants_out, "cursor": next_cursor}


# =========================
# GET /bot/verify/{file_id}
# =========================

@router.get("/verify/{file_id}")
def bot_verify_file(
    file_id: str,
    db: Session = Depends(get_db),
):
    """
    Bot-friendly верификация файла по fileId.

    Валидация:
      - формат 0x + 64 hex, иначе 400.
      - если файла нет в БД — 404.

    Возвращаем:
      {
        "onchain_ok": bool,
        "offchain_ok": bool,
        "match": bool,
        "lastAnchorTx": str | None
      }

    Сейчас реализуем простую версию:
      - offchain_ok = True, если файл существует.
      - onchain_ok = False (мы не трогаем цепь).
      - match = onchain_ok and offchain_ok.
      - lastAnchorTx = None.
    """
    # валидация формата
    if not (isinstance(file_id, str) and file_id.startswith("0x") and len(file_id) == 66):
        raise HTTPException(status_code=400, detail="bad_file_id")
    try:
        file_id_bytes = bytes.fromhex(file_id[2:])
    except ValueError:
        raise HTTPException(status_code=400, detail="bad_file_id")

    file_row = db.get(File, file_id_bytes)
    if file_row is None:
        raise HTTPException(status_code=404, detail="file_not_found")

    offchain_ok = True
    onchain_ok = False
    match = onchain_ok and offchain_ok
    last_anchor_tx: Optional[str] = None

    return {
        "onchain_ok": onchain_ok,
        "offchain_ok": offchain_ok,
        "match": match,
        "lastAnchorTx": last_anchor_tx,
    }


# =========================
# POST /bot/action-intents (JWT)
# =========================

@router.post("/action-intents", response_model=ActionIntentCreateOut)
def create_action_intent(
    body: ActionIntentCreateIn,
    user: User = Depends(_require_jwt_user),
    db: Session = Depends(get_db),
):
    """
    Создаёт одноразовый интент (handoff) для текущего пользователя.

    Вход: { type, params }
    Шаги:
      - генерим UUID (через PK id)
      - expires_at = now + 10–15 мин (здесь 15)
      - пишем в action_intents(owner_address, type, data, expires_at)
      - возвращаем { state, expires_at }, где state = str(id)
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ACTION_INTENT_TTL_SECONDS)

    owner_addr = (user.eth_address or "").lower()

    intent = ActionIntent(
        owner_address=owner_addr,
        type=body.type,
        data=body.params,
        expires_at=expires_at,
        used_at=None,
    )
    db.add(intent)
    db.commit()
    db.refresh(intent)

    return ActionIntentCreateOut(
        state=str(intent.id),
        expires_at=expires_at,
    )


# =========================
# POST /bot/action-intents/consume (JWT)
# =========================

@router.post("/action-intents/consume", response_model=ActionIntentConsumeOut)
def consume_action_intent(
    body: ActionIntentConsumeIn,
    user: User = Depends(_require_jwt_user),
    db: Session = Depends(get_db),
):
    """
    Потребляет одноразовый интент.

    Вход: { state }

    Шаги:
      - находим интент по state (PK id)
      - проверяем, что JWT.addr совпадает с owner_address
      - проверяем TTL (expires_at > now)
      - проверяем, что not used (used_at is NULL)
      - помечаем used_at = now
      - возвращаем { type, params }
    """
    owner_addr = (user.eth_address or "").lower()

    # state — это просто string(UUID), который мы вернули ранее = PK id
    try:
        state_uuid = uuid.UUID(body.state)
    except Exception:
        raise HTTPException(status_code=400, detail="bad_state")

    intent: Optional[ActionIntent] = db.get(ActionIntent, state_uuid)
    if intent is None:
        raise HTTPException(status_code=404, detail="intent_not_found")

    if (intent.owner_address or "").lower() != owner_addr:
        raise HTTPException(status_code=403, detail="not_owner")

    now = datetime.now(timezone.utc)

    if intent.expires_at is not None and now > intent.expires_at:
        raise HTTPException(status_code=400, detail="intent_expired")

    if intent.used_at is not None:
        raise HTTPException(status_code=400, detail="intent_already_used")

    intent.used_at = now
    db.commit()

    return ActionIntentConsumeOut(
        type=intent.type,
        params=intent.data or {},
    )
