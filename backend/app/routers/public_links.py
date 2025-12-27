from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

import redis
from eth_typing import HexStr
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from web3 import Web3

from app.blockchain.web3_client import Chain
from app.config import settings
from app.deps import get_chain, get_db, get_ipfs, get_redis
from app.ipfs.client import IpfsClient
from app.models.files import File
from app.models.public_links import PublicLink
from app.models.users import User
from app.schemas.public_links import (
    OkOut,
    PowIn,
    PublicLinkCreateIn,
    PublicLinkCreateOut,
    PublicLinkItemOut,
    PublicLinkPolicyOut,
    PublicLinksListOut,
    PublicMetaOut,
    RevokeOut,
)
from app.security import get_current_user

router = APIRouter(prefix="", tags=["public_links"])
logger = logging.getLogger(__name__)


@router.post("/files/{file_id_hex}/public-links", response_model=PublicLinkCreateOut, status_code=201)
def create_public_link(
    file_id_hex: str,
    body: PublicLinkCreateIn,
    creds: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    rds: Annotated[redis.Redis, Depends(get_redis)],
) -> PublicLinkCreateOut:
    # Validate file id (hex 0x...)
    if not (isinstance(file_id_hex, str) and file_id_hex.startswith("0x") and len(file_id_hex) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id = Web3.to_bytes(hexstr=cast(HexStr, file_id_hex))
    except Exception as err:
        raise HTTPException(400, "bad_file_id") from err
    file_row: File | None = db.get(File, file_id)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    # Owner check
    if file_row.owner_id != creds.id:
        raise HTTPException(403, "not_owner")

    # Build snapshot
    name = body.name_override or file_row.name or "Unnamed"
    mime = body.mime_override or file_row.mime
    size = file_row.size
    cid = file_row.cid or None

    # TTL
    expires_at = None
    if body.ttl_sec:
        expires_at = datetime.now(UTC) + timedelta(seconds=int(body.ttl_sec))

    # policy
    pow_difficulty = None
    if isinstance(body.pow, dict) and body.pow.get("enabled"):
        try:
            pow_difficulty = int(body.pow.get("difficulty") or settings.pow_difficulty_base)
        except Exception:
            pow_difficulty = int(settings.pow_difficulty_base)

    policy = PublicLinkPolicyOut(max_downloads=body.max_downloads, pow_difficulty=pow_difficulty, one_time=False)

    # generate token
    token = secrets.token_urlsafe(48)[:64]

    pl = PublicLink(
        file_id=file_id,
        version=body.version,
        token=token,
        expires_at=expires_at,
        max_downloads=body.max_downloads,
        downloads_count=0,
        pow_difficulty=pow_difficulty,
        bandwidth_mb_per_day=None,
        one_time=False,
        snapshot_name=name,
        snapshot_mime=mime,
        snapshot_size=size,
        snapshot_cid=cid,
        created_by=creds.id,
    )
    db.add(pl)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(500, "token_generation_failed") from err

    return PublicLinkCreateOut(token=token, expires_at=expires_at, policy=policy)


@router.get("/public/{token}/meta", response_model=PublicMetaOut)
def public_meta(token: str, db: Annotated[Session, Depends(get_db)]) -> PublicMetaOut:
    pl: PublicLink | None = db.scalar(select(PublicLink).where(PublicLink.token == token))
    if pl is None:
        raise HTTPException(404, "not_found")
    now = datetime.now(UTC)
    if pl.revoked_at is not None or (pl.expires_at is not None and now > pl.expires_at):
        raise HTTPException(410, "expired|revoked")

    policy = PublicLinkPolicyOut(max_downloads=pl.max_downloads, pow_difficulty=pl.pow_difficulty, one_time=pl.one_time)

    return PublicMetaOut(
        name=pl.snapshot_name,
        size=pl.snapshot_size,
        mime=pl.snapshot_mime,
        cid=pl.snapshot_cid,
        fileId="0x" + pl.file_id.hex(),
        version=pl.version,
        expires_at=pl.expires_at,
        policy=policy,
    )


@router.post("/public/{token}/pow", response_model=OkOut)
def public_pow(
    token: str, body: PowIn, rds: Annotated[redis.Redis, Depends(get_redis)], db: Annotated[Session, Depends(get_db)]
) -> OkOut:
    pl: PublicLink | None = db.scalar(select(PublicLink).where(PublicLink.token == token))
    if pl is None:
        raise HTTPException(404, "not_found")
    key = f"pow:challenge:{body.nonce}"
    if rds.get(key) is None:
        raise HTTPException(400, "bad_solution")
    # choose difficulty: per-link if set and >0, else global
    try:
        diff = int(pl.pow_difficulty or 0)
    except Exception:
        diff = 0
    if diff <= 0:
        diff = int(settings.pow_difficulty_base)
    nibbles = int((diff + 3) // 4)
    prefix = "0" * nibbles
    h = hashlib.sha256((body.nonce + body.solution).encode("utf-8")).hexdigest()
    logger.info(
        "public_pow: token=%s, diff=%s, prefix=%s, computed_hash=%s..., valid=%s",
        token,
        diff,
        prefix,
        h[:16],
        h.startswith(prefix),
    )
    if not h.startswith(prefix):
        raise HTTPException(400, "bad_solution")
    # consume challenge
    try:
        deleted = rds.delete(key)
        logger.info(f"public_pow: deleted challenge key={key}, result={deleted}")
    except Exception as e:
        logger.debug("Failed to delete pow challenge %s: %s", key, e, exc_info=True)
    # grant short-lived access token for content retrieval
    access_key = f"public:access:{token}"
    try:
        set_result = rds.set(access_key, "1", ex=60)
        logger.info(f"public_pow: set access_key={access_key}, ex=60, result={set_result}")
    except Exception as e:
        logger.warning("Failed to set access key %s: %s", access_key, e, exc_info=True)
    try:
        rds.incr("metrics:public_pow_ok")
    except Exception:
        logger.debug("Failed to increment metrics:public_pow_ok", exc_info=True)
    return OkOut(ok=True)


@router.get("/public/{token}/content")
def public_content(
    token: str,
    db: Annotated[Session, Depends(get_db)],
    rds: Annotated[redis.Redis, Depends(get_redis)],
    chain: Annotated[Chain, Depends(get_chain)],
    ipfs: Annotated[IpfsClient, Depends(get_ipfs)],
) -> StreamingResponse:
    pl: PublicLink | None = db.scalar(select(PublicLink).where(PublicLink.token == token))
    if pl is None:
        raise HTTPException(404, "not_found")
    now = datetime.now(UTC)
    if pl.revoked_at is not None or (pl.expires_at is not None and now > pl.expires_at):
        raise HTTPException(410, "expired|revoked")

    # PoW check: require access only when difficulty > 0
    try:
        diff_val = int(pl.pow_difficulty or 0)
    except Exception:
        diff_val = 0
    logger.info(f"public_content: token={token}, pow_difficulty={pl.pow_difficulty}, computed_diff={diff_val}")
    if diff_val > 0:
        access_key = f"public:access:{token}"
        access_exists = rds.get(access_key)
        logger.info(f"public_content: checking access_key={access_key}, exists={access_exists is not None}")
        if access_exists is None:
            raise HTTPException(403, "denied")

    # check downloads limit (0 means unlimited)
    if pl.max_downloads is not None and pl.max_downloads > 0 and pl.downloads_count >= pl.max_downloads:
        logger.info(f"public_content: downloads limit exceeded: {pl.downloads_count} >= {pl.max_downloads}")
        raise HTTPException(403, "limit")

    # get cid from chain first
    cid = None
    try:
        cid = chain.cid_of(pl.file_id) or None
    except Exception:
        cid = None
    if not cid:
        cid = pl.snapshot_cid
    if not cid:
        logger.warning(f"public_content: no CID found for token={token}, file_id={pl.file_id.hex()}")
        raise HTTPException(502, "registry_unavailable")

    logger.info(f"public_content: proceeding to fetch from IPFS, cid={cid}")

    # increment downloads_count
    try:
        pl.downloads_count = (pl.downloads_count or 0) + 1
        db.add(pl)
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("Failed to increment downloads_count for %s", token, exc_info=True)

    # fetch bytes from IPFS and stream
    try:
        data = ipfs.cat(cid)
    except Exception as err:
        logger.debug("ipfs cat failed for %s: %s", cid, err, exc_info=True)
        raise HTTPException(502, "ipfs_unavailable") from err

    filename = pl.snapshot_name or "file"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([data]), media_type="application/octet-stream", headers=headers)


@router.delete("/public-links/{token}", response_model=RevokeOut)
def revoke_public_link(
    token: str,
    creds: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RevokeOut:
    pl: PublicLink | None = db.scalar(select(PublicLink).where(PublicLink.token == token))
    if pl is None:
        raise HTTPException(404, "not_found")
    # Only owner can revoke
    try:
        file_row: File | None = db.get(File, pl.file_id)
        if file_row is None or file_row.owner_id != creds.id:
            raise HTTPException(403, "not_owner")
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(403, "not_owner") from err

    pl.revoked_at = datetime.now(UTC)
    db.add(pl)
    db.commit()
    return RevokeOut(revoked=True)


@router.get("/files/{file_id_hex}/public-links", response_model=PublicLinksListOut)
def list_public_links(
    file_id_hex: str,
    creds: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PublicLinksListOut:
    if not (isinstance(file_id_hex, str) and file_id_hex.startswith("0x") and len(file_id_hex) == 66):
        raise HTTPException(400, "bad_file_id")
    try:
        file_id = Web3.to_bytes(hexstr=cast(HexStr, file_id_hex))
    except Exception as err:
        raise HTTPException(400, "bad_file_id") from err
    file_row: File | None = db.get(File, file_id)
    if file_row is None:
        raise HTTPException(404, "file_not_found")
    if file_row.owner_id != creds.id:
        raise HTTPException(403, "not_owner")

    rows = db.scalars(select(PublicLink).where(PublicLink.file_id == file_id)).all()
    items: list[PublicLinkItemOut] = []
    for pl in rows:
        items.append(
            PublicLinkItemOut(
                token=pl.token,
                expires_at=pl.expires_at,
                policy=PublicLinkPolicyOut(
                    max_downloads=pl.max_downloads,
                    pow_difficulty=pl.pow_difficulty,
                    one_time=pl.one_time,
                ),
                downloads_count=pl.downloads_count or 0,
            )
        )
    return PublicLinksListOut(items=items)
