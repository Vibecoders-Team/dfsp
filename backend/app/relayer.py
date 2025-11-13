from __future__ import annotations

from typing import Any, cast, Dict, Tuple, Optional
import time
import uuid
from celery import Celery
from kombu import Queue
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.exceptions import ContractLogicError, TransactionNotFound, TimeExhausted
from eth_typing import HexStr

from app.config import settings
from app.deps import get_chain, rds, SessionLocal  # type: ignore[attr-defined]
from app.models.meta_tx_requests import MetaTxRequest
from sqlalchemy.orm import Session

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
# Ensure tasks from app.tasks.anchor are registered
celery.conf.imports = celery.conf.get("imports", []) + ["app.tasks.anchor"]

# route by task name + payload (useOnce/revoke → high)

def _route_for_task(name: str, args: tuple, kwargs: dict, options: dict, task=None, **kw):  # noqa: ANN001
    if name == "relayer.submit_forward":
        typed: Dict[str, Any] | None = None
        if args and isinstance(args, tuple) and len(args) >= 2 and isinstance(args[1], dict):
            typed = cast(Dict[str, Any], args[1])
        elif isinstance(kwargs, dict):
            typed = cast(Optional[Dict[str, Any]], kwargs.get("typed_data")) or None
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


def _build_req_tuple(msg: Dict[str, Any]) -> Tuple:
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


def _series_key(msg: Dict[str, Any]) -> str:
    # per-grantor ordering by forwarder.from (EOA)
    from_addr = str(msg.get("from", "")).lower()
    return f"relayer:series:{from_addr}"


def _sync_grant_events_from_receipt(receipt: AttributeDict, chain, db: Optional[Session]) -> None:
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
        from datetime import datetime, timezone

        ac = chain.get_access_control()

        def _invalidate_for_grant(gr: "Grant"):
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
            except Exception:
                pass

        # Process Used events
        try:
            used_events = ac.events.Used().process_receipt(receipt)
            for evt in used_events:
                cap_id = evt.args.capId if hasattr(evt.args, 'capId') else evt.get('args', {}).get('capId')
                used_count = evt.args.used if hasattr(evt.args, 'used') else evt.get('args', {}).get('used')
                if cap_id and used_count is not None:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.used = int(used_count)
                        db.add(grant)
                        _invalidate_for_grant(grant)
        except Exception:
            pass  # Event might not exist in receipt

        # Process Revoked events
        try:
            revoked_events = ac.events.Revoked().process_receipt(receipt)
            for evt in revoked_events:
                cap_id = evt.args.capId if hasattr(evt.args, 'capId') else evt.get('args', {}).get('capId')
                if cap_id:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.revoked_at = datetime.now(timezone.utc)
                        grant.status = "revoked"
                        db.add(grant)
                        _invalidate_for_grant(grant)
        except Exception:
            pass  # Event might not exist in receipt

        # Process Granted events (update status to confirmed)
        try:
            granted_events = ac.events.Granted().process_receipt(receipt)
            for evt in granted_events:
                cap_id = evt.args.capId if hasattr(evt.args, 'capId') else evt.get('args', {}).get('capId')
                if cap_id:
                    cap_b = bytes(cap_id) if isinstance(cap_id, (bytes, bytearray)) else Web3.to_bytes(hexstr=cap_id)
                    grant = db.query(Grant).filter(Grant.cap_id == cap_b).first()
                    if grant:
                        grant.status = "confirmed"
                        grant.confirmed_at = datetime.now(timezone.utc)
                        grant.tx_hash = receipt.get("transactionHash", b"").hex() if receipt.get("transactionHash") else None
                        db.add(grant)
                        _invalidate_for_grant(grant)
        except Exception:
            pass  # Event might not exist in receipt

        db.commit()
    except Exception:
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
def submit_forward(self, request_id: str, typed_data: Dict[str, Any], signature: str):
    """
    Отправка meta-тx в OZ MinimalForwarder c пер-Grantor блокировкой, ретраями, метриками и структурированными логами.
    """
    t0 = time.perf_counter()
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

    # DB session for idempotency/metrics persistence
    db: Optional[Session] = None
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
    except Exception:
        pass

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
        tx_params: Dict[str, Any] = {}
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
            tx_hash = fwd.functions.execute(req_tuple, sig_bytes).transact(tx_params)
            receipt = cast(AttributeDict, chain.w3.eth.wait_for_transaction_receipt(tx_hash))
            # metrics + DB update
            dt_ms = (time.perf_counter() - t0) * 1000.0
            _metrics_incr("success_total")
            _metrics_add_duration("submit_forward", dt_ms)
            if db is not None:
                try:
                    m = db.get(MetaTxRequest, uuid.UUID(request_id))
                    if m:
                        m.tx_hash = (receipt.get("transactionHash") or b"").hex()  # type: ignore[assignment]
                        m.status = "mined"
                        m.gas_used = int(receipt.get("gasUsed", 0) or 0)
                        db.add(m)
                        db.commit()
                except Exception:
                    db.rollback()

            # Sync grant events from receipt to DB
            _sync_grant_events_from_receipt(receipt, chain, db)

            # structured log
            txh = (receipt.get("transactionHash") or b"").hex()
            return {"status": "sent", "txHash": txh}
        except (ContractLogicError, TransactionNotFound, TimeExhausted) as e:
            # Common replace/nonce errors → retry with backoff and gas bump
            msg_str = str(e)
            if any(s in msg_str for s in ("nonce too low", "replacement transaction underpriced", "underpriced")):
                raise self.retry(exc=e)
            raise self.retry(exc=e)
        except Exception as e:
            raise self.retry(exc=e)
    # end with lock


def _decide_queue(typed_data: Dict[str, Any]) -> str:
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
    except Exception:
        pass
    return DEFAULT_Q


def enqueue_forward_request(request_id: str, typed_data: Dict[str, Any], signature: str, queue: Optional[str] = None) -> str:
    q = queue or _decide_queue(typed_data)
    # record a best-effort queue metric
    _metrics_incr(f"enqueue_total:{q}")
    async_result = cast(Any, submit_forward).apply_async(args=[request_id, typed_data, signature], queue=q)
    return async_result.id
