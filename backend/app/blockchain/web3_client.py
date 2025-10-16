from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Sequence, cast

from eth_utils.address import to_checksum_address  # ✅ правильный импорт
from web3 import Web3, HTTPProvider
from web3.types import TxParams

log = logging.getLogger(__name__)


class Chain:
    def __init__(
            self,
            rpc_url: str,
            chain_id: int,
            deploy_json_path: str,
            contract_name: str,
            tx_from: str | None = None,
    ):
        self.rpc_url = rpc_url or os.getenv("CHAIN_RPC_URL", "http://chain:8545")
        self.w3 = Web3(HTTPProvider(self.rpc_url))
        self.chain_id = chain_id

        # основной целевой контракт (обычно FileRegistry)
        with open(deploy_json_path, "r", encoding="utf-8") as _f:
            d = json.load(_f)
        c = d["contracts"][contract_name]
        self.address = Web3.to_checksum_address(c["address"])
        self.abi = c["abi"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        self.tx_from = Web3.to_checksum_address(tx_from) if tx_from else (
            self.w3.eth.accounts[0] if self.w3.eth.accounts else None
        )

        self.deployment_json = deploy_json_path or os.getenv(
            "CONTRACTS_DEPLOYMENT_JSON", "/app/shared/deployment.localhost.json"
        )

        # индексы функций/событий для основного контракта
        self._fn = {f["name"]: f for f in self.abi if f.get("type") == "function"}
        self._events = {e["name"]: e for e in self.abi if e.get("type") == "event"}

        # загрузка всех контрактов из deployment.json (в т.ч. MinimalForwarder)
        self.contracts: Dict[str, Any] = {}
        self._load_contracts()

    # ----------------- базовое -----------------

    def _tx(self) -> TxParams:
        tx: TxParams = {"chainId": self.chain_id, "gas": 2_000_000}
        if self.tx_from:
            tx["from"] = self.tx_from
        return tx

    def _load_contracts(self) -> None:
        self.contracts = {}
        try:
            with open(self.deployment_json, "r", encoding="utf-8") as f:
                j = json.load(f)
            for name, info in j.get("contracts", {}).items():
                addr = Web3.to_checksum_address(info["address"])
                abi = info["abi"]
                self.contracts[name] = self.w3.eth.contract(address=addr, abi=abi)
            log.info("Loaded %d contracts from %s", len(self.contracts), self.deployment_json)
        except Exception as e:
            log.warning("Contracts load failed (%s): %s", self.deployment_json, e)

    def reload_contracts(self) -> None:
        self._load_contracts()

    def get_contract(self, name: str):
        c = self.contracts.get(name)
        if not c:
            raise RuntimeError(f"contract {name} not loaded")
        return c

    # ----------------- registry helpers -----------------

    def register_or_update(self, item_id: bytes, cid: str, checksum32: bytes, size: int, mime: str = "") -> str:
        def _arity(name: str) -> int:
            f = self._fn.get(name)
            return len(f["inputs"]) if f else -1

        primary_name = "register" if "register" in self._fn else ("store" if "store" in self._fn else None)
        if not primary_name:
            raise RuntimeError("Registry has no register/store")
        try:
            n = _arity(primary_name)
            if n == 2:
                txh = getattr(self.contract.functions, primary_name)(item_id, cid).transact(self._tx())
            elif n == 5:
                txh = getattr(self.contract.functions, primary_name)(
                    item_id, cid, checksum32 or (b"\x00" * 32), int(size) & ((1 << 64) - 1), mime or ""
                ).transact(self._tx())
            else:
                raise RuntimeError(f"{primary_name} has unsupported arity: {n}")
            rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
            return rcpt["transactionHash"].hex()  # ✅ dict-доступ вместо атрибута
        except Exception:
            if "updateCid" not in self._fn:
                raise
            n = _arity("updateCid")
            if n == 2:
                txh = self.contract.functions.updateCid(item_id, cid).transact(self._tx())
            elif n == 5:
                txh = self.contract.functions.updateCid(
                    item_id, cid, checksum32 or (b"\x00" * 32), int(size) & ((1 << 64) - 1), mime or ""
                ).transact(self._tx())
            else:
                raise RuntimeError(f"updateCid has unsupported arity: {n}")
            rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
            return rcpt["transactionHash"].hex()  # ✅

    def cid_of(self, item_id: bytes) -> str:
        if "cidOf" in self._fn:
            return self.contract.functions.cidOf(item_id).call() or ""
        if "metaOf" in self._fn:
            fn = self._fn["metaOf"]
            outs = (fn.get("outputs") or [{}])[0]
            comps = outs.get("components") or []
            idx = next((i for i, c in enumerate(comps) if (c.get("name") or "").lower() == "cid"), None)
            if idx is None:
                idx = next((i for i, c in enumerate(comps) if c.get("type") == "string"), 1)
            res = self.contract.functions.metaOf(item_id).call()
            if isinstance(res, dict):
                return res.get("cid") or ""
            if isinstance(res, (list, tuple)) and len(res) > cast(int, idx):
                # ✅ явно работаем с последовательностью
                seq: Sequence[Any] = cast(Sequence[Any], res)
                val = seq[cast(int, idx)]
                return val or ""
            return ""
        if "versionsOf" in self._fn:
            arr_val = self.contract.functions.versionsOf(item_id).call()
            if isinstance(arr_val, (list, tuple)) and arr_val:
                seq: Sequence[Any] = cast(Sequence[Any], arr_val)
                last = seq[-1]  # ✅ индекс по Sequence
                return last or ""
            return ""
        return ""

    def meta_of_full(self, item_id: bytes) -> dict:
        if "metaOf" not in self._fn:
            raise RuntimeError("Registry has no metaOf")
        fn = self._fn["metaOf"]
        outs = (fn.get("outputs") or [{}])[0]
        comps = outs.get("components") or []
        res = self.contract.functions.metaOf(item_id).call()

        def to_dict(vals: Any) -> dict:
            if isinstance(vals, dict):
                return vals
            if isinstance(vals, (list, tuple)):
                return {(c.get("name") or f"f{i}"): vals[i] for i, c in enumerate(comps) if i < len(vals)}
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
                    d: dict[str, Any] = {}
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

        def _evt_logs(evt: Any, arg_filters: Dict[str, Any]) -> list[Any]:
            try:
                return list(evt.get_logs(from_block=0, to_block="latest", argument_filters=arg_filters))
            except TypeError:
                pass
            try:
                return list(evt.get_logs(fromBlock=0, toBlock="latest", argument_filters=arg_filters))  # type: ignore
            except Exception:
                pass
            try:
                flt = evt.create_filter(from_block=0, to_block="latest", argument_filters=arg_filters)
                return flt.get_all_entries()
            except TypeError:
                pass
            flt = evt.createFilter(fromBlock=0, toBlock="latest", argument_filters=arg_filters)  # type: ignore
            return flt.get_all_entries()

        def _collect(evt_name: str) -> None:
            if evt_name not in self._events:
                return
            evt = getattr(self.contract.events, evt_name)
            # ✅ аннотация значения как Any, чтобы не застрять на bytes vs str
            arg_filters: Dict[str, Any] = {"fileId": item_id}
            if owner and any(i.get("name") == "owner" and i.get("indexed") for i in self._events[evt_name]["inputs"]):
                arg_filters["owner"] = Web3.to_checksum_address(owner)
            logs = _evt_logs(evt, arg_filters)
            for lg in logs:
                args = dict(lg["args"]) if isinstance(lg.get("args"), dict) else lg.get("args", {})
                block = self.w3.eth.get_block(lg["blockNumber"])
                checksum = args.get("checksum")
                if isinstance(checksum, (bytes, bytearray)):
                    checksum = checksum.hex()
                events.append({
                    "type": evt_name,
                    "blockNumber": lg["blockNumber"],
                    "txHash": lg["transactionHash"].hex(),
                    # ✅ .get с дефолтом, чтобы TypedDict нас не пугал
                    "timestamp": int(block.get("timestamp", 0)),
                    "owner": args.get("owner"),
                    "cid": args.get("cid"),
                    "checksum": checksum,
                    "size": int(args.get("size") or 0),
                    "mime": args.get("mime"),
                })

        _collect("FileRegistered")
        _collect("FileVersioned")
        events.sort(key=lambda x: (x["blockNumber"], x["timestamp"]))
        return events

    # ----------------- НОВОЕ: encode + EIP-712 для форвардера -----------------

    def get_forwarder(self):
        return self.get_contract("MinimalForwarder")

    def encode_register_call(self, item_id: bytes, cid: str, checksum32: bytes, size: int, mime: str) -> str:
        try:
            fn = self.contract.get_function_by_name("register")
        except ValueError as e:
            raise RuntimeError("FileRegistry has no 'register'") from e
        tx = fn(item_id, cid, checksum32, int(size) & ((1 << 64) - 1), mime or "").build_transaction(self._tx())
        return tx["data"]  # 0x...

    def build_forward_typed_data(self, from_addr: str, to_addr: str, data: bytes | str, gas: int = 120_000) -> dict:
        fwd = self.get_forwarder()
        from_addr = to_checksum_address(from_addr)
        to_addr = to_checksum_address(to_addr)
        verifying = fwd.address if hasattr(fwd, "address") else fwd.functions.eip712Domain().call()[3]

        nonce = int(fwd.functions.getNonce(from_addr).call())

        # ✅ нормализация data → hex без использования hexstr= на str
        if isinstance(data, (bytes, bytearray)):
            data_hex = "0x" + bytes(data).hex()
        elif isinstance(data, str):
            data_hex = data if data.startswith("0x") else ("0x" + data)
        else:
            raise TypeError("data must be bytes or hex string")

        domain = {
            "name": "MinimalForwarder",
            "version": "0.0.1",
            "chainId": int(self.chain_id),
            "verifyingContract": verifying,
        }
        types = {
            "ForwardRequest": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "gas", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "data", "type": "bytes"},
            ]
        }
        message = {
            "from": from_addr,
            "to": to_addr,
            "value": 0,
            "gas": int(gas),
            "nonce": nonce,
            "data": data_hex,
        }
        return {"domain": domain, "types": types, "primaryType": "ForwardRequest", "message": message}

    def verify_forward(self, typed: dict, signature: str) -> bool:
        fwd = self.get_forwarder()
        msg = (typed or {}).get("message") or {}
        try:
            req = (
                to_checksum_address(msg["from"]),
                to_checksum_address(msg["to"]),
                int(msg.get("value", 0)),
                int(msg.get("gas", 0)),
                int(msg["nonce"]),
                # ✅ подсказываем типизатору, что это hex-строка
                Web3.to_bytes(hexstr=cast("HexStr", msg["data"])),  # type: ignore[name-defined]
            )
        except Exception as e:
            raise RuntimeError(f"bad_forward_request: {e}")

        try:
            ok = bool(fwd.functions.verify(req, signature).call())
            return ok
        except Exception as e:
            log.warning("forwarder.verify failed: %s", e)
            return False
