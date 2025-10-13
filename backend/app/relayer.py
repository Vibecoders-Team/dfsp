from celery import Celery
from web3 import Web3
from web3.exceptions import ContractLogicError

from app.blockchain import forwarder
from app.config import settings

celery = Celery("relayer", broker=settings.redis_dsn, backend=settings.redis_dsn)


@celery.task(name="relayer.submit_forward", bind=True, max_retries=5, default_retry_delay=2)
def submit_forward(self, request_id: str, typed_data: dict, signature: str):
    try:
        req = typed_data["message"]
        # дополнительная on-chain валидация сигнатуры (cheap call)
        ok = forwarder.functions.verify(
            (req["from"], req["to"], int(req["value"]), int(req["gas"]), int(req["nonce"]),
             bytes.fromhex(req["data"][2:])),
            signature
        ).call()
        if not ok:
            return {"status": "bad_signature"}

        tx = forwarder.functions.execute(
            (req["from"], req["to"], int(req["value"]), int(req["gas"]), int(req["nonce"]),
             bytes.fromhex(req["data"][2:])),
            signature
        ).transact({"from": Web3.to_checksum_address(req["from"])})
        receipt = forwarder.w3.eth.wait_for_transaction_receipt(tx)
        return {"status": "sent", "txHash": receipt.transactionHash.hex()}
    except ContractLogicError as e:
        raise self.retry(exc=e)
    except Exception as e:
        raise self.retry(exc=e)


def enqueue_forward_request(request_id: str, typed_data: dict, signature: str) -> str:
    async_result = submit_forward.delay(request_id, typed_data, signature)
    return async_result.id
