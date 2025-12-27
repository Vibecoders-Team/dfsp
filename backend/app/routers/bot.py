from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.deps import get_chain, get_db, rds
from app.models import File, Grant, User
from app.models.action_intent import ActionIntent
from app.models.anchors import Anchor
from app.repos import telegram_repo
from app.repos.user_repo import get_by_eth_address
from app.routers.download import _build_download_payload
from app.schemas.action_intent import (
    ActionIntentConsumeIn,
    ActionIntentConsumeOut,
    ActionIntentCreateIn,
    ActionIntentCreateOut,
)
from app.schemas.bot import BotProfileResponse  # 👈 вот этого не хватало
from app.security import parse_token

router = APIRouter(prefix="/bot", tags=["Bot"])

ACTION_INTENT_TTL_SECONDS = 15 * 60  # 10–15 min as per task; we pick 15
DL_ONCE_TTL = int(os.getenv("DL_ONCE_TTL", "300"))
PUBLIC_WEB_ORIGIN = os.getenv("PUBLIC_WEB_ORIGIN", "http://localhost:3000").rstrip("/")

AuthorizationHeader = Annotated[str, Header(..., alias="Authorization")]
DbSessionDep = Annotated[Session, Depends(get_db)]


# =========================
# JWT helper for bot endpoints (action-intents)
# =========================


def _require_jwt_user(
    authorization: AuthorizationHeader,
    db: DbSessionDep,
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
    except Exception as exc:
        raise HTTPException(status_code=401, detail="bad_token") from exc
    user_obj: User | None = db.get(User, user_id)
    if user_obj is None:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user_obj


# =========================
# Helpers for Telegram-based auth (files/grants)
# =========================


def _parse_chat_id(x_tg_chat_id: str) -> int:
    try:
        return int(x_tg_chat_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid X-TG-Chat-Id") from exc


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
    db: DbSessionDep,
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> User:
    chat_id = _parse_chat_id(x_tg_chat_id)
    return _resolve_user_by_chat_id_value(chat_id, db)


def _parse_cursor(cursor: str | None) -> datetime | None:
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
        cursor_ts = float(cursor)
    except (TypeError, ValueError):
        cursor_ts = None
    if cursor_ts is not None:
        return datetime.fromtimestamp(cursor_ts, tz=UTC)

    # variant 2: ISO-строка
    try:
        return datetime.fromisoformat(cursor)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid cursor format. Use ISO 8601.",
        ) from exc


def _datetime_to_cursor(dt: datetime | None) -> str | None:
    """
    Превращаем datetime в строковый курсор.
    Чтобы избежать проблем с '+' в таймзоне в query-параметре,
    используем timestamp (float) как строку.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return str(dt.timestamp())


# =========================
# Models for links
# =========================


class BotLinkItem(BaseModel):
    address: str
    is_active: bool


class BotLinksResponse(BaseModel):
    links: list[BotLinkItem]


class BotLinkCreateIn(BaseModel):
    address: str
    make_active: bool | None = False


class BotLinkSwitchIn(BaseModel):
    address: str


class BotPrepareDownloadIn(BaseModel):
    capId: str | None = None
    fileId: str | None = None


class BotPrepareDownloadOut(BaseModel):
    url: str
    ttl: int
    fileName: str | None = None


# =========================
# /bot/links CRUD
# =========================


def _links_response(db: Session, chat_id: int) -> BotLinksResponse:
    links = telegram_repo.list_links_by_chat(db, chat_id)
    items = [BotLinkItem(address=link.wallet_address.lower(), is_active=bool(link.is_active)) for link in links or []]
    return BotLinksResponse(links=items)


@router.get("/links", response_model=BotLinksResponse)
def bot_list_links(
    db: DbSessionDep,
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> BotLinksResponse:
    chat_id = _parse_chat_id(x_tg_chat_id)
    return _links_response(db, chat_id)


@router.post("/links", response_model=BotLinksResponse, status_code=201)
def bot_add_link(
    body: BotLinkCreateIn,
    db: DbSessionDep,
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> BotLinksResponse:
    chat_id = _parse_chat_id(x_tg_chat_id)
    try:
        addr = Web3.to_checksum_address(body.address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad_address") from exc

    user = get_by_eth_address(db, addr)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    telegram_repo.upsert_link(db, chat_id, addr, bool(body.make_active))
    return _links_response(db, chat_id)


@router.post("/links/switch", response_model=BotLinksResponse)
def bot_switch_active_link(
    body: BotLinkSwitchIn,
    db: DbSessionDep,
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> BotLinksResponse:
    chat_id = _parse_chat_id(x_tg_chat_id)
    try:
        addr = Web3.to_checksum_address(body.address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad_address") from exc

    try:
        telegram_repo.set_active_link(db, chat_id, addr)
    except LookupError:
        raise HTTPException(status_code=404, detail="link_not_found") from None

    return _links_response(db, chat_id)


@router.delete("/links/{address}", response_model=BotLinksResponse)
def bot_delete_link(
    address: str,
    db: DbSessionDep,
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> BotLinksResponse:
    chat_id = _parse_chat_id(x_tg_chat_id)
    try:
        addr = Web3.to_checksum_address(address)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad_address") from exc

    telegram_repo.revoke_link(db, chat_id, addr)
    return _links_response(db, chat_id)


# =========================
# POST /bot/prepare-download
# =========================


@router.post("/prepare-download", response_model=BotPrepareDownloadOut)
def bot_prepare_download(
    body: BotPrepareDownloadIn,
    db: DbSessionDep,
    chain: Annotated[Chain, Depends(get_chain)],
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
) -> BotPrepareDownloadOut:
    chat_id = _parse_chat_id(x_tg_chat_id)
    user = _resolve_user_by_chat_id_value(chat_id, db)

    cap_id = body.capId
    file_id = body.fileId

    if not cap_id and not file_id:
        raise HTTPException(status_code=400, detail="capId_or_fileId_required")

    grant: Grant | None = None
    file_obj: File | None = None
    file_id_bytes: bytes | None = None

    if cap_id:
        if not (isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66):
            raise HTTPException(status_code=400, detail="bad_cap_id")
        try:
            cap_b = Web3.to_bytes(hexstr=cap_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="bad_cap_id") from exc

        grant = db.scalar(select(Grant).where(Grant.cap_id == cap_b))
        if grant is None:
            raise HTTPException(status_code=404, detail="grant_not_found")
        if grant.grantee_id != user.id:
            raise HTTPException(status_code=403, detail="not_grantee")
        payload = _build_download_payload(db, chain, user, grant, cap_id)
    else:
        # fileId путь: владелец файла или первый доступный грант для пользователя
        fid = file_id or ""
        if fid.startswith("0x"):
            fid_hex = fid
        else:
            fid_hex = f"0x{fid}"
        if len(fid_hex) != 66 or not fid_hex.startswith("0x"):
            raise HTTPException(status_code=400, detail="bad_file_id")
        try:
            file_id_bytes = Web3.to_bytes(hexstr=fid_hex)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="bad_file_id") from exc

        file_obj = db.get(File, file_id_bytes)
        if file_obj is None:
            raise HTTPException(status_code=404, detail="file_not_found")

        if file_obj.owner_id == user.id:
            # Владелец файла: готовим одноразовую ссылку без гранта
            try:
                cid = chain.cid_of(file_id_bytes) or file_obj.cid
            except Exception:
                cid = file_obj.cid
            if not cid:
                raise HTTPException(status_code=502, detail="registry_unavailable")
            payload = {
                "fileId": fid_hex,
                "ipfsPath": f"/ipfs/{cid}",
                "fileName": file_obj.name,
                "owner": user.eth_address,
            }
        else:
            grant = db.scalar(select(Grant).where(Grant.file_id == file_id_bytes, Grant.grantee_id == user.id).limit(1))
            if grant is None:
                raise HTTPException(status_code=403, detail="not_grantee")
            cap_hex = "0x" + bytes(grant.cap_id).hex()
            payload = _build_download_payload(db, chain, user, grant, cap_hex)
            cap_id = cap_hex

    token = secrets.token_urlsafe(20)
    key = f"dl:once:{token}"
    rds.setex(key, DL_ONCE_TTL, json.dumps(payload, separators=(",", ":")))

    url = f"{PUBLIC_WEB_ORIGIN}/dl/one-time/{token}"
    return BotPrepareDownloadOut(url=url, ttl=DL_ONCE_TTL, fileName=payload.get("fileName"))


# =========================
# GET /bot/me
# =========================


@router.get("/me", response_model=BotProfileResponse)
def bot_get_me(
    user: Annotated[User, Depends(_get_user_by_chat_id)],
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
    user: Annotated[User, Depends(_get_user_by_chat_id)],
    db: DbSessionDep,
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None),
) -> dict[str, object]:
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

    q = select(File).where(File.owner_id == user.id).order_by(File.created_at.desc())
    if cursor_dt is not None:
        q = q.where(File.created_at < cursor_dt)

    rows: list[File] = db.scalars(q.limit(limit + 1)).all()
    page_items = rows[:limit]

    next_cursor: str | None = None
    if len(rows) > limit and page_items:
        last = page_items[-1]
        next_cursor = _datetime_to_cursor(last.created_at)

    files_out = []
    for f in page_items:
        updated_at = f.created_at or datetime.now(UTC)
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
    db: DbSessionDep,
    direction: str = Query(..., alias="direction"),
    x_tg_chat_id: str = Header(..., alias="X-TG-Chat-Id"),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None),
) -> dict[str, object]:
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

    q = select(Grant, File.name).join(File, File.id == Grant.file_id).where(cond).order_by(Grant.created_at.desc())
    if cursor_dt is not None:
        q = q.where(Grant.created_at < cursor_dt)

    rows: list[tuple[Grant, str]] = db.execute(q.limit(limit + 1)).all()
    page_items = rows[:limit]

    next_cursor: str | None = None
    if len(rows) > limit and page_items:
        last_grant = page_items[-1][0]
        next_cursor = _datetime_to_cursor(last_grant.created_at)

    now = datetime.now(UTC)
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


def _normalize_checksum(value: object) -> str | None:
    """Приводит чек-сумму в байтах к hex-строке '0x...'."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    if isinstance(value, str):
        return value.lower()
    return None


@router.get("/verify/{file_id}")
def bot_verify_file(
    file_id: str,
    db: DbSessionDep,
    chain: Annotated[Chain, Depends(get_chain)],
) -> dict[str, bool | str | None]:
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_file_id") from exc

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
    last_anchor_tx: str | None = None
    try:
        latest_anchor = db.scalar(
            select(Anchor).where(Anchor.tx_hash.isnot(None)).order_by(Anchor.created_at.desc()).limit(1)
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
    user: Annotated[User, Depends(_require_jwt_user)],
    db: DbSessionDep,
) -> ActionIntentCreateOut:
    """
    Создаёт одноразовый интент (handoff) для текущего пользователя.
    """
    now = datetime.now(UTC)
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
    user: Annotated[User, Depends(_require_jwt_user)],
    db: DbSessionDep,
) -> ActionIntentConsumeOut:
    """
    Потребляет одноразовый интент.
    """
    owner_addr = (user.eth_address or "").lower()

    try:
        state_uuid = uuid.UUID(body.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_state") from exc

    intent: ActionIntent | None = db.get(ActionIntent, state_uuid)
    if intent is None:
        raise HTTPException(status_code=404, detail="intent_not_found")

    if (intent.owner_address or "").lower() != owner_addr:
        raise HTTPException(status_code=403, detail="not_owner")

    now = datetime.now(UTC)

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
