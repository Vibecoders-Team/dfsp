from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from typing_extensions import Annotated
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, get_chain
from app.blockchain.web3_client import Chain
from app.models import File, Grant, User
from app.models.action_intent import ActionIntent
from app.models.anchors import Anchor
from app.repos import telegram_repo
from app.repos.user_repo import get_by_eth_address
from app.security import parse_token
import logging
from app.schemas.action_intent import (
    ActionIntentCreateIn,
    ActionIntentCreateOut,
    ActionIntentConsumeIn,
    ActionIntentConsumeOut,
)
from app.schemas.bot import BotProfileResponse  # 👈 вот этого не хватало

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

    При неудаче кидаем 400.
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
# GET /bot/me
# =========================


@router.get("/me", response_model=BotProfileResponse)
def bot_get_me(
    user: User = Depends(_get_user_by_chat_id),
) -> BotProfileResponse:
    """
    Bot-friendly профиль пользователя по Telegram chat_id.

    Вход:
      - X-TG-Chat-Id (header)

    Выход:
      - address: связанный wallet-адрес
      - display_name: имя пользователя, если задано
    """
    return BotProfileResponse(
        address=(user.eth_address or "").lower(),
        display_name=getattr(user, "display_name", None),
    )


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


def _normalize_checksum(value: Any) -> str | None:
    """Приводит чек-сумму в байтах к hex-строке '0x...'."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    return None


@router.get("/verify/{file_id}")
def bot_verify_file(
    file_id: str,
    db: Session = Depends(get_db),
    chain: Chain = Depends(get_chain),
):
    """
    Bot-friendly верификация файла по fileId.

    Валидация:
      - формат 0x + 64 hex, иначе 400.
      - если файла нет в БД — 404.

    Возвращает:
      - onchain_ok: есть ли файл в блокчейне
      - offchain_ok: есть ли файл в БД
      - match: совпадают ли checksum on-chain и off-chain
      - lastAnchorTx: последняя транзакция анкора (если есть)
    """
    log = logging.getLogger(__name__)
    
    # валидация формата
    if not (isinstance(file_id, str) and file_id.startswith("0x") and len(file_id) == 66):
        raise HTTPException(status_code=400, detail="bad_file_id")
    try:
        file_id_bytes = bytes.fromhex(file_id[2:])
    except ValueError:
        raise HTTPException(status_code=400, detail="bad_file_id")

    # 1. Проверяем off-chain (БД)
    file_row = db.get(File, file_id_bytes)
    offchain_ok = file_row is not None
    
    if not offchain_ok:
        raise HTTPException(status_code=404, detail="file_not_found")

    # 2. Проверяем on-chain (блокчейн)
    onchain_ok = False
    match = False
    
    try:
        raw_onchain_meta = chain.meta_of_full(file_id_bytes)
        
        # Проверяем, что смарт-контракт вернул непустые данные
        # (обычно возвращает нули для несуществующего id)
        if raw_onchain_meta and any(raw_onchain_meta.values()):
            onchain_ok = True
            
            # Сравниваем checksum если есть данные в обеих системах
            if file_row.checksum:
                onchain_checksum = _normalize_checksum(raw_onchain_meta.get("checksum"))
                offchain_checksum = _normalize_checksum(file_row.checksum)
                
                if onchain_checksum and offchain_checksum:
                    match = onchain_checksum.lower() == offchain_checksum.lower()
    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение
        log.warning(f"Failed to fetch on-chain meta for {file_id}: {e}")
        onchain_ok = False

    # 3. Получаем последнюю транзакцию анкора (если есть)
    last_anchor_tx: Optional[str] = None
    try:
        latest_anchor = db.scalar(
            select(Anchor)
            .where(Anchor.tx_hash.isnot(None))
            .order_by(Anchor.created_at.desc())
            .limit(1)
        )
        if latest_anchor and latest_anchor.tx_hash:
            last_anchor_tx = latest_anchor.tx_hash
    except Exception as e:
        log.warning(f"Failed to fetch latest anchor tx: {e}")

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
    """
    owner_addr = (user.eth_address or "").lower()

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
