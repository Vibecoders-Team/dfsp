import json
import logging
from pathlib import Path
from typing import Dict

from web3 import Web3
from web3.types import TxParams

# Импортируем наш объект settings
from app.config import settings

log = logging.getLogger(__name__)

# Папка с ABI-файлами, которую мы создали
ABI_DIR = Path(__file__).parent / "abi"


class Chain:
    def __init__(self, contract_name: str):
        # 1. Подключаемся к блокчейну, используя URL из настроек
        self.w3 = Web3(Web3.HTTPProvider(settings.CHAIN_RPC_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Web3 provider at {settings.CHAIN_RPC_URL}")

        # 2. Загружаем конфигурацию с адресами, используя путь из настроек
        deploy_json_path = settings.DEPLOYMENT_JSON_PATH
        try:
            with open(deploy_json_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Deployment config not found at {deploy_json_path}")

        self.chain_id = int(config_data.get("chainId", 0))

        # 3. Получаем АДРЕС контракта из "verifyingContracts"
        contract_address_str = config_data.get("verifyingContracts", {}).get(contract_name)
        if not contract_address_str:
            raise ValueError(f"Address for '{contract_name}' not found in {deploy_json_path}")
        self.address = Web3.to_checksum_address(contract_address_str)

        # 4. Загружаем ABI из файла в папке /abi
        abi_path = ABI_DIR / f"{contract_name}.json"
        if not abi_path.exists():
            raise FileNotFoundError(f"ABI file not found for '{contract_name}' at {abi_path}")

        with open(abi_path, "r", encoding="utf-8") as f:
            abi_data = json.load(f)
            self.abi = abi_data.get("abi") if isinstance(abi_data, dict) else abi_data
            if not self.abi:
                raise ValueError(f"Invalid ABI format in {abi_path}")

        # 5. Инициализируем остальные атрибуты
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        # Для локальной разработки предполагаем, что первый аккаунт доступен для отправки транзакций
        self.tx_from = self.w3.eth.accounts[0] if self.w3.eth.accounts else None
        if not self.tx_from:
            log.warning("Could not determine default 'from' address for transactions.")

        self._fn = {f["name"]: f for f in self.abi if f.get("type") == "function"}
        self._events = {e["name"]: e for e in self.abi if e.get("type") == "event"}

    def _tx(self) -> TxParams:
        if not self.tx_from:
            raise RuntimeError("Cannot send transaction: 'from' address is not set.")
        return {"from": self.tx_from, "chainId": self.chain_id, "gas": 2_000_000}

    # --- ВАША ЛОГИКА МЕТОДОВ (СКОПИРОВАНА БЕЗ ИЗМЕНЕНИЙ) ---

    def register_or_update(
        self, item_id: bytes, cid: str, checksum32: bytes, size: int, mime: str = ""
    ) -> str:
        def _arity(name: str) -> int:
            f = self._fn.get(name)
            return len(f["inputs"]) if f else -1

        primary_name = (
            "register" if "register" in self._fn else ("store" if "store" in self._fn else None)
        )
        if not primary_name:
            raise RuntimeError("Registry has no register/store")
        try:
            n = _arity(primary_name)
            if n == 2:
                txh = getattr(self.contract.functions, primary_name)(item_id, cid).transact(
                    self._tx()
                )
            elif n == 5:
                txh = getattr(self.contract.functions, primary_name)(
                    item_id,
                    cid,
                    checksum32 or (b"\x00" * 32),
                    int(size) & ((1 << 64) - 1),
                    mime or "",
                ).transact(self._tx())
            else:
                raise RuntimeError(f"{primary_name} has unsupported arity: {n}")
            rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
            return rcpt.transactionHash.hex()
        except Exception:
            if "updateCid" not in self._fn:
                raise
            n = _arity("updateCid")
            if n == 2:
                txh = self.contract.functions.updateCid(item_id, cid).transact(self._tx())
            elif n == 5:
                txh = self.contract.functions.updateCid(
                    item_id,
                    cid,
                    checksum32 or (b"\x00" * 32),
                    int(size) & ((1 << 64) - 1),
                    mime or "",
                ).transact(self._tx())
            else:
                raise RuntimeError(f"updateCid has unsupported arity: {n}")
            rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
            return rcpt.transactionHash.hex()

    def cid_of(self, item_id: bytes) -> str:
        if "cidOf" in self._fn:
            return self.contract.functions.cidOf(item_id).call() or ""
        if "metaOf" in self._fn:
            fn = self._fn["metaOf"]
            outs = (fn.get("outputs") or [{}])[0]
            comps = outs.get("components") or []
            idx = next(
                (i for i, c in enumerate(comps) if (c.get("name") or "").lower() == "cid"), None
            )
            if idx is None:
                idx = next((i for i, c in enumerate(comps) if c.get("type") == "string"), 1)
            res = self.contract.functions.metaOf(item_id).call()
            if isinstance(res, dict):
                return res.get("cid") or ""
            if isinstance(res, (list, tuple)) and len(res) > idx:
                return res[idx] or ""
            return ""
        if "versionsOf" in self._fn:
            arr = self.contract.functions.versionsOf(item_id).call()
            return (arr[-1] if isinstance(arr, (list, tuple)) and arr else "") or ""
        return ""

    def meta_of_full(self, item_id: bytes) -> dict:
        if "metaOf" not in self._fn:
            raise RuntimeError("Registry has no metaOf")
        fn = self._fn["metaOf"]
        outs = (fn.get("outputs") or [{}])[0]
        comps = outs.get("components") or []
        res = self.contract.functions.metaOf(item_id).call()

        def to_dict(vals):
            if isinstance(vals, dict):
                return vals
            if isinstance(vals, (list, tuple)):
                return {
                    (c.get("name") or f"f{i}"): vals[i]
                    for i, c in enumerate(comps)
                    if i < len(vals)
                }
            return {}

        return to_dict(res)

    def versions_of(self, item_id: bytes) -> list[dict]:
        if "versionsOf" not in self._fn:
            return []
        fn = self._fn["versionsOf"]
        outs = (fn.get("outputs") or [{}])[0]
        comps = outs.get("components") or []
        res = self.contract.functions.versionsOf(item_id).call()
        out: list[dict] = []
        if isinstance(res, (list, tuple)):
            for el in res:
                if isinstance(el, dict):
                    out.append(el)
                elif isinstance(el, (list, tuple)) and comps:
                    d = {}
                    for i, c in enumerate(comps):
                        name = c.get("name") or f"f{i}"
                        val = el[i] if i < len(el) else None
                        d[name] = val
                    out.append(d)
                elif isinstance(el, str):
                    out.append({"cid": el})
                else:
                    out.append({"value": el})
        return out

    def history(self, item_id: bytes, owner: str | None = None) -> list[dict]:
        events: list[dict] = []

        def _evt_logs(evt, arg_filters):
            try:
                return list(
                    evt.get_logs(from_block=0, to_block="latest", argument_filters=arg_filters)
                )
            except TypeError:
                pass
            try:
                return list(
                    evt.get_logs(fromBlock=0, toBlock="latest", argument_filters=arg_filters)
                )
            except Exception:
                pass
            try:
                flt = evt.create_filter(
                    from_block=0, to_block="latest", argument_filters=arg_filters
                )
                return flt.get_all_entries()
            except TypeError:
                pass
            flt = evt.createFilter(fromBlock=0, toBlock="latest", argument_filters=arg_filters)
            return flt.get_all_entries()

        def _collect(evt_name: str):
            if evt_name not in self._events:
                return
            evt = getattr(self.contract.events, evt_name)
            arg_filters = {"fileId": item_id}
            if owner and any(
                i.get("name") == "owner" and i.get("indexed")
                for i in self._events[evt_name]["inputs"]
            ):
                arg_filters["owner"] = Web3.to_checksum_address(owner)
            logs = _evt_logs(evt, arg_filters)
            for lg in logs:
                args = dict(lg["args"]) if isinstance(lg.get("args"), dict) else lg.get("args", {})
                block = self.w3.eth.get_block(lg["blockNumber"])
                checksum = args.get("checksum")
                if isinstance(checksum, (bytes, bytearray)):
                    checksum = checksum.hex()
                events.append(
                    {
                        "type": evt_name,
                        "blockNumber": lg["blockNumber"],
                        "txHash": lg["transactionHash"].hex(),
                        "timestamp": int(block["timestamp"]),
                        "owner": args.get("owner"),
                        "cid": args.get("cid"),
                        "checksum": checksum,
                        "size": int(args.get("size") or 0),
                        "mime": args.get("mime"),
                    }
                )
        _collect("FileRegistered")
        _collect("FileVersioned")
        events.sort(key=lambda x: (x["blockNumber"], x["timestamp"]))
        return events