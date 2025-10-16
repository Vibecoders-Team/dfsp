from __future__ import annotations

from typing import Any, cast, Dict, Tuple
from celery import Celery
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.exceptions import ContractLogicError, TransactionNotFound, TimeExhausted
from eth_typing import HexStr

from app.config import settings
from app.deps import get_chain  # берём Chain (w3 + все контракты)

celery = Celery("relayer", broker=settings.redis_dsn, backend=settings.redis_dsn)
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]


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
    Отправка meta-tx в OZ MinimalForwarder:
    1) verify(req, sig) — дешёвый on-chain вызов
    2) execute(req, sig) — транзакция от имени релейера
    """
    chain = get_chain()
    fwd = chain.get_forwarder()

    # извлекаем message и нормализуем
    msg = (typed_data or {}).get("message") or {}
    try:
        req_tuple = _build_req_tuple(msg)
        # здесь cast нужен, чтобы удовлетворить статическому анализатору
        sig_bytes = Web3.to_bytes(hexstr=cast(HexStr, signature))  # 0x… → bytes
    except Exception as e:
        # невалидный typed_data — не ретраим
        return {"status": "bad_request", "error": str(e)}

    # проверяем подпись и nonce
    try:
        ok = bool(fwd.functions.verify(req_tuple, sig_bytes).call())
        if not ok:
            return {"status": "bad_signature"}
    except Exception as e:
        # verify сам может упасть — считаем это невалидным
        return {"status": "verify_failed", "error": str(e)}

    # кто платит газ: используем конфиг/Chain.tx_from (разлоченный аккаунт у ноды)
    tx_from = chain.tx_from or getattr(settings, "chain_tx_from", None)
    tx_params: Dict[str, Any] = {}
    if tx_from:
        tx_params["from"] = Web3.to_checksum_address(tx_from)

    # добавим небольшой запас газа относительно msg.gas
    msg_gas = int(msg.get("gas", 0))
    if msg_gas > 0:
        tx_params["gas"] = msg_gas + 50_000

    try:
        tx_hash = fwd.functions.execute(req_tuple, sig_bytes).transact(tx_params)
        receipt = cast(AttributeDict, chain.w3.eth.wait_for_transaction_receipt(tx_hash))
        return {"status": "sent", "txHash": receipt.transactionHash.hex()}
    except (ContractLogicError, TransactionNotFound, TimeExhausted) as e:
        raise self.retry(exc=e)
    except Exception as e:
        raise self.retry(exc=e)


def enqueue_forward_request(request_id: str, typed_data: Dict[str, Any], signature: str) -> str:
    async_result = cast(Any, submit_forward).delay(request_id, typed_data, signature)
    return async_result.id
