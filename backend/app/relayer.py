from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from celery import Celery, Task
from eth_typing import HexStr
from kombu import Queue
from sqlalchemy.orm import Session
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.exceptions import ContractLogicError, TimeExhausted, TransactionNotFound
from web3.types import TxParams

from app.blockchain.web3_client import Chain
from app.config import settings
from app.deps import SessionLocal, get_chain, rds  # type: ignore[attr-defined]
from app.models.meta_tx_requests import MetaTxRequest

log = logging.getLogger(__name__)

# Queue names (env-overridable)
HIGH_Q = getattr(settings, "relayer_high_queue", None) or "relayer.high"
DEFAULT_Q = getattr(settings, "relayer_default_queue", None) or "relayer.default"
ANCHOR_Q = "anchor"

celery = Celery("relayer", broker=settings.redis_dsn, backend=settings.redis_dsn)
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
celery.conf.task_queues = (
    Queue(HIGH_Q),
    Queue(DEFAULT_Q),
    Queue(ANCHOR_Q),
)
# Ensure tasks from app.tasks.anchor are registered (handle tuple/list gracefully)
_existing_imports = celery.conf.get("imports", ())
if isinstance(_existing_imports, list):
    _existing_imports = tuple(_existing_imports)
celery.conf.imports = (*tuple(_existing_imports), "app.tasks.anchor")

# route by task name + payload (useOnce/revoke → high)


def _route_for_task(
    name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    options: dict[str, object],
    task: Task | None = None,
) -> dict[str, str]:
    """Route tasks by name + payload. Typed args/kwargs to satisfy static checks."""
    if name == "relayer.submit_forward":
        typed: dict[str, object] | None = None
        # args may be positional: (request_id, typed_data, signature)
        if isinstance(args, tuple) and len(args) >= 2 and isinstance(args[1], dict):
            typed = cast(dict[str, object], args[1])
        else:
            typed = cast(dict[str, object] | None, kwargs.get("typed_data")) or None
        if typed:
            q = _decide_queue(typed)
            return {"queue": q}
    return {"queue": DEFAULT_Q}


celery.conf.task_routes = (_route_for_task,)

# simple metrics in Redis
METRICS_KEY_PREFIX = "metrics:relayer"


def _metrics_incr(counter: str, by: int = 1) -> None:
    rds.incrby(f"{METRICS_KEY_PREFIX}:{counter}", by)


def _metrics_add_duration(task_type: str, ms: float) -> None:
    key = f"{METRICS_KEY_PREFIX}:durations:{task_type}"
    # push and trim last 200 values
    pipe = rds.pipeline()
    pipe.lpush(key, int(ms))
    pipe.ltrim(key, 0, 199)
    pipe.execute()


def _build_req_tuple(msg: dict[str, Any]) -> tuple[str, str, int, int, int, bytes]:
    """
    Приводим message из typedData к tuple ForwardRequest:
    (from, to, value, gas, nonce, data)
    """
    return (
        Web3.to_checksum_address(msg["from"]),
        Web3.to_checksum_address(msg["to"]),
        int(msg.get("value", 0)),
        int(msg.get("gas", 0)),
        int(msg["nonce"]),
        Web3.to_bytes(hexstr=cast(HexStr, msg["data"])),
    )


def _series_key(msg: dict[str, Any]) -> str:
    # per-grantor ordering by forwarder.from (EOA)
    from_addr = str(msg.get("from", "")).lower()
    return f"relayer:series:{from_addr}"


def _sync_grant_events_from_receipt(receipt: AttributeDict, chain: Chain, db: Session | None) -> None:
    """
    Parse events from receipt and update grants table in DB.
    Handles: Used, Revoked, Granted events.
    Also invalidates Redis caches: can_dl and grant_nonce.
    """
    if db is None:
        return

    try:
        from app.models.grants import Grant
        from app.models.users import User

        ac = chain.get_access_control()

        def _invalidate_for_grant(gr: Grant) -> None:
            try:
                file_hex = "0x" + bytes(gr.file_id).hex()
                # Invalidate can_dl for grantee
                rds.delete(f"can_dl:{gr.grantee_id}:{file_hex}")
                # Invalidate can_dl for grantor too (defensive)
                rds.delete(f"can_dl:{gr.grantor_id}:{file_hex}")
                # Invalidate grant_nonce for grantor (need address)
                grantor_user = db.get(User, gr.grantor_id)
                if grantor_user and getattr(grantor_user, "eth_address", None):
                    from eth_utils.address import to_checksum_address as _to_cs

                    addr = _to_cs(str(grantor_user.eth_address))
                    key = f"grant_nonce:{addr.lower()}"
                    rds.delete(key)
            except Exception as e:
                # keep message compact to satisfy line-length rule
                log.debug(
                    "_invalidate_for_grant: cache invalidation failed for grant %s: %s",
                    getattr(gr, "cap_id", None),
                    e,
                    exc_info=True,
                )

        # Process Used events
        try:
            used_events = ac.events.Used().process_receipt(receipt)
            log.info("_sync_grant_events: found %d Used events", len(used_events))
            for evt in used_events:
                cap_id = evt.args.capId if hasattr(evt.args, "capId") else evt.get("args", {}).get("capId")
                used_count = evt.args.used if hasattr(evt.args, "used") else evt.get("args", {}).get("used")
                if cap_id and used_count is not None:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.used = int(used_count)
                        db.add(cast(Any, grant))
                        _invalidate_for_grant(grant)
        except Exception as e:
            log.debug("_sync_grant_events: Used processing failed: %s", e, exc_info=True)

        # Process Revoked events
        try:
            revoked_events = ac.events.Revoked().process_receipt(receipt)
            log.info("_sync_grant_events: found %d Revoked events", len(revoked_events))
            for evt in revoked_events:
                cap_id = evt.args.capId if hasattr(evt.args, "capId") else evt.get("args", {}).get("capId")
                if cap_id:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.revoked_at = datetime.now(UTC)
                        grant.status = "revoked"
                        db.add(cast(Any, grant))
                        _invalidate_for_grant(grant)
        except Exception as e:
            log.debug("_sync_grant_events: Revoked processing failed: %s", e, exc_info=True)

        # Process Granted events (update status to confirmed)
        try:
            granted_events = ac.events.Granted().process_receipt(receipt)
            log.info("_sync_grant_events: found %d Granted events", len(granted_events))
            for evt in granted_events:
                cap_id = evt.args.capId if hasattr(evt.args, "capId") else evt.get("args", {}).get("capId")
                if cap_id:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.status = "confirmed"
                        grant.confirmed_at = datetime.now(UTC)
                        grant.tx_hash = (
                            receipt.get("transactionHash", b"").hex() if receipt.get("transactionHash") else None
                        )
                        db.add(cast(Any, grant))
                        _invalidate_for_grant(grant)
        except Exception as e:
            log.debug("_sync_grant_events: Granted processing failed: %s", e, exc_info=True)

        db.commit()
    except Exception as e:
        log.warning("_sync_grant_events: unexpected failure: %s", e, exc_info=True)
        if db:
            db.rollback()


@celery.task(
    name="relayer.submit_forward",
    bind=True,
    max_retries=5,
    default_retry_delay=2,
    retry_backoff=True,
    retry_jitter=True,
)
def submit_forward(self: Task, request_id: str, typed_data: dict[str, Any], signature: str) -> dict[str, Any]:
    """
    Отправка meta-тx в OZ MinimalForwarder c пер-Grantor блокировкой, ретраями, метриками и структурированными логами.
    """
    t0 = time.perf_counter()

    # DB session for idempotency/metrics persistence
    db: Session | None = None
    try:
        db = SessionLocal()
    except Exception:
        db = None

    # Reinforce idempotency: skip if MetaTxRequest already mined/sent
    try:
        if db is not None:
            existing = db.get(MetaTxRequest, uuid.UUID(request_id))
            if existing and existing.status in ("mined", "sent"):
                return {"status": "duplicate"}
    except Exception as e:
        log.debug("submit_forward: idempotency check failed: %s", e, exc_info=True)
        pass


    # Standard EVM signature processing
    chain = get_chain()
    fwd = chain.get_forwarder()

    msg = (typed_data or {}).get("message") or {}
    try:
        req_tuple = _build_req_tuple(msg)
        sig_bytes = Web3.to_bytes(hexstr=cast(HexStr, signature))
    except Exception as e:
        _metrics_incr("error_total")
        return {"status": "bad_request", "error": str(e)}

    series = _series_key(msg)
    lock = rds.lock(series, timeout=60, blocking_timeout=30)

    with lock:
        # verify signature and nonce
        try:
            ok = bool(fwd.functions.verify(req_tuple, sig_bytes).call())
            if not ok:
                _metrics_incr("error_total")
                return {"status": "bad_signature"}
        except Exception as e:
            _metrics_incr("error_total")
            return {"status": "verify_failed", "error": str(e)}

        # gas params with bumping per retry
        tx_params: dict[str, Any] = {}
        tx_from = chain.tx_from or getattr(settings, "chain_tx_from", None)
        if tx_from:
            tx_params["from"] = Web3.to_checksum_address(tx_from)
        # simple gasPrice bumping strategy for legacy tx replacement
        try:
            base_gp = int(chain.w3.eth.gas_price)
        except Exception:
            base_gp = 0
        # each retry add 10%
        bump_factor = 1.0 + 0.1 * int(getattr(self.request, "retries", 0) or 0)
        if base_gp > 0:
            tx_params["gasPrice"] = int(base_gp * bump_factor)
        # add margin to requested gas
        msg_gas = int(msg.get("gas", 0))
        if msg_gas > 0:
            tx_params["gas"] = msg_gas + 50_000

        try:
            # Build transaction and send as raw (signed) tx to avoid requiring a signer on the node
            fn = fwd.functions.execute(req_tuple, sig_bytes)
            # If tx_params is empty, use chain defaults
            # build_transaction expects TxParams | None; cast chain._tx() result appropriately
            built = fn.build_transaction(cast(TxParams, cast(object, tx_params or chain._tx())))
            # chain._send_tx expects dict[str, Any]
            tx_hash = chain._send_tx(cast(dict[str, Any], built))
            log.info("submit_forward: sent tx_hash=%s", tx_hash)
            # Ensure tx_hash is 0x-prefixed hex and cast to HexStr for wait_for_transaction_receipt
            tx_hash_hex = tx_hash if isinstance(tx_hash, str) and tx_hash.startswith("0x") else ("0x" + str(tx_hash))
            receipt = cast(
                AttributeDict,
                chain.w3.eth.wait_for_transaction_receipt(cast(HexStr, tx_hash_hex), timeout=120),
            )
            # Log receipt summary and logs for debugging
            try:
                logs_len = len(receipt.get("logs") or [])
            except Exception:
                logs_len = -1
            log.info(
                "submit_forward: receipt obtained tx=%s status=%s logs=%s",
                tx_hash_hex,
                receipt.get("status"),
                logs_len,
            )
            try:
                for i, lg in enumerate((receipt.get("logs") or [])[:10]):
                    addr = lg.get("address") if isinstance(lg, dict) else getattr(lg, "address", None)
                    topics = lg.get("topics") if isinstance(lg, dict) else getattr(lg, "topics", None)
                    log.info(
                        "submit_forward: receipt.log[%d] address=%s topics_count=%s",
                        i,
                        addr,
                        (len(topics) if topics is not None else None),
                    )
            except Exception as e:
                log.debug("submit_forward: failed iterating receipt logs: %s", e, exc_info=True)
            # metrics + DB update
            dt_ms = (time.perf_counter() - t0) * 1000.0
            _metrics_incr("success_total")
            _metrics_add_duration("submit_forward", dt_ms)
            if db is not None:
                try:
                    m = db.get(MetaTxRequest, uuid.UUID(request_id))
                    if m:
                        # receipt.get('transactionHash') may be bytes/HexBytes or hexstring
                        txh_raw = receipt.get("transactionHash") or receipt.get("transactionHash", b"")
                        try:
                            m.tx_hash = txh_raw.hex() if hasattr(txh_raw, "hex") else str(txh_raw)
                        except Exception:
                            m.tx_hash = str(tx_hash)
                        m.status = "mined"
                        m.gas_used = int(receipt.get("gasUsed", 0) or 0)
                        db.add(m)
                        db.commit()
                except Exception as e:
                    log.warning("submit_forward: DB update failed while saving MetaTxRequest: %s", e, exc_info=True)
                    db.rollback()

            # Sync grant events from receipt to DB
            _sync_grant_events_from_receipt(receipt, chain, db)

            # Fallback: reconcile pending grants for grantor by on-chain lookup
            try:
                grantor_src = msg.get("from") if isinstance(msg, dict) else None
                if grantor_src:
                    grantor_addr = Web3.to_checksum_address(grantor_src)
                    _reconcile_pending_for_grantor(grantor_addr, chain, db)
                else:
                    log.debug("submit_forward: no grantor address present in message, skipping reconciliation")
            except Exception as e:
                log.debug("submit_forward: reconcile pending grants failed: %s", e, exc_info=True)

            # structured log
            txh = (receipt.get("transactionHash") or b"").hex()
            return {"status": "sent", "txHash": txh}
        except (ContractLogicError, TransactionNotFound, TimeExhausted) as e:
            # Common replace/nonce errors → retry with backoff and gas bump
            msg_str = str(e)
            if any(s in msg_str for s in ("nonce too low", "replacement transaction underpriced", "underpriced")):
                raise self.retry(exc=e) from e
            raise self.retry(exc=e) from e
        except Exception as e:
            raise self.retry(exc=e) from e
    # end with lock


def _decide_queue(typed_data: dict[str, Any]) -> str:
    """Basic router: use high queue for AccessControlDFSP.useOnce/revoke; default otherwise."""
    try:
        chain = get_chain()
        ac_addr = getattr(chain.get_access_control(), "address", None)
        to = str(((typed_data or {}).get("message") or {}).get("to", ""))
        if ac_addr and to and Web3.to_checksum_address(ac_addr) == Web3.to_checksum_address(to):
            data = str(((typed_data or {}).get("message") or {}).get("data", ""))
            sel = data[2:10].lower() if data.startswith("0x") and len(data) >= 10 else ""
            # first 4 bytes (8 hex chars) of keccak("sig")
            use_sel = Web3.keccak(text="useOnce(bytes32)")[:4].hex()[2:].lower()
            rev_sel = Web3.keccak(text="revoke(bytes32)")[:4].hex()[2:].lower()
            if sel in (use_sel, rev_sel):
                return HIGH_Q
    except Exception as e:
        log.debug("_decide_queue failed to determine queue: %s", e, exc_info=True)
    return DEFAULT_Q


def enqueue_forward_request(
    request_id: str, typed_data: dict[str, Any], signature: str, queue: str | None = None
) -> str:
    q = queue or _decide_queue(typed_data)
    # record a best-effort queue metric
    _metrics_incr(f"enqueue_total:{q}")
    async_result = cast(Any, submit_forward).apply_async(args=[request_id, typed_data, signature], queue=q)
    return async_result.id


def _reconcile_pending_for_grantor(grantor_addr: str, chain: Chain, db: Session | None) -> None:
    """
    Fallback reconciliation: for pending grants with this grantor,
    call grantOf(capId) and mark confirmed if present on-chain.
    """
    if db is None:
        return
    try:
        from app.models.grants import Grant
        from app.models.users import User

        ac = chain.get_access_control()
        # find grantor user id
        gu = db.query(User).filter(User.eth_address == grantor_addr).one_or_none()
        if gu is None:
            return
        pending = db.query(Grant).filter(Grant.grantor_id == gu.id, Grant.status == "pending").all()
        if not pending:
            return
        log.info(
            "_reconcile_pending_for_grantor: checking %d pending grants for %s",
            len(pending),
            grantor_addr,
        )
        for gr in pending:
            try:
                res = ac.functions.grantOf(gr.cap_id).call()
                # grantOf returns tuple: [grantor, grantee, fileId, expiresAt, maxDownloads, used, createdAt, revoked]
                created_at = None
                if isinstance(res, (list, tuple)) and len(res) > 6:
                    try:
                        created_at = int(res[6] or 0)
                    except Exception:
                        created_at = None
                if created_at and created_at > 0:
                    gr.status = "confirmed"
                    gr.confirmed_at = datetime.now(UTC)
                    db.add(cast(Any, gr))
            except Exception as e:
                log.debug(
                    "_reconcile_pending_for_grantor: grantOf call failed for cap %s: %s",
                    gr.cap_id.hex() if isinstance(gr.cap_id, (bytes, bytearray)) else str(gr.cap_id),
                    e,
                )
        db.commit()
    except Exception:
        if db:
            db.rollback()
