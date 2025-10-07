from __future__ import annotations

import json
from web3 import Web3
from web3.types import TxParams

class Chain:
    def __init__(self, rpc_url: str, chain_id: int, deploy_json_path: str, contract_name: str, tx_from: str | None = None):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.chain_id = chain_id
        d = json.load(open(deploy_json_path, "r", encoding="utf-8"))
        c = d["contracts"][contract_name]
        self.address = Web3.to_checksum_address(c["address"])
        self.abi = c["abi"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        self.tx_from = Web3.to_checksum_address(tx_from) if tx_from else self.w3.eth.accounts[0]
        self._fn = {f["name"]: f for f in self.abi if f.get("type") == "function"}
        self._events = {e["name"]: e for e in self.abi if e.get("type") == "event"}

    def _tx(self) -> TxParams:
        return {"from": self.tx_from, "chainId": self.chain_id, "gas": 2_000_000}

    def register_or_update(self, item_id: bytes, cid: str, checksum32: bytes, size: int, mime: str = "") -> str:

        """
        Универсальная запись: если есть register — зовём его (2 или 5 аргументов).
        Если revert/конфликт — пробуем updateCid (2 или 5 аргументов).
        """
        def _arity(name: str) -> int:
            f = self._fn.get(name)
            return len(f["inputs"]) if f else -1

        # primary: register OR store
        primary_name = "register" if "register" in self._fn else ("store" if "store" in self._fn else None)
        if not primary_name:
            raise RuntimeError("Registry has no register/store")

        # try primary
        try:
            n = _arity(primary_name)
            if n == 2:
                txh = getattr(self.contract.functions, primary_name)(item_id, cid).transact(self._tx())
            elif n == 5:
                txh = getattr(self.contract.functions, primary_name)(
                    item_id,
                    cid,
                    checksum32 or (b"\x00" * 32),
                    int(size) & ((1 << 64) - 1),  # ← размер файла
                    mime or "",  # ← mime
                ).transact(self._tx())
            else:
                raise RuntimeError(f"{primary_name} has unsupported arity: {n}")
            rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
            return rcpt.transactionHash.hex()
        except Exception:
            # fallback: updateCid
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
        # прямой путь
        if "cidOf" in self._fn:
            return self.contract.functions.cidOf(item_id).call() or ""

        # metaOf(bytes32) returns tuple(...). Найдём индекс поля 'cid' по ABI.
        if "metaOf" in self._fn:
            fn = self._fn["metaOf"]
            outs = (fn.get("outputs") or [{}])[0]
            comps = outs.get("components") or []
            # попробуем найти явно 'cid'; если нет — возьмём первую string-компоненту; запасной дефолт = 1
            idx = next((i for i, c in enumerate(comps) if (c.get("name") or "").lower() == "cid"), None)
            if idx is None:
                idx = next((i for i, c in enumerate(comps) if c.get("type") == "string"), 1)

            res = self.contract.functions.metaOf(item_id).call()
            if isinstance(res, dict):
                return res.get("cid") or ""
            if isinstance(res, (list, tuple)) and len(res) > idx:
                return res[idx] or ""
            return ""

        # versionsOf(bytes32) → string[]
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

        # сопоставляем имена полей с значениями
        def to_dict(vals):
            if isinstance(vals, dict):
                return vals
            if isinstance(vals, (list, tuple)):
                return { (c.get("name") or f"f{i}"): vals[i] for i, c in enumerate(comps) if i < len(vals) }
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
            # web3.py v6: get_logs(from_block, to_block)
            try:
                return list(evt.get_logs(from_block=0, to_block="latest", argument_filters=arg_filters))
            except TypeError:
                pass
            # иногда в старых версиях есть get_logs с camelCase
            try:
                return list(evt.get_logs(fromBlock=0, toBlock="latest", argument_filters=arg_filters))  # type: ignore
            except Exception:
                pass
            # v6: create_filter(from_block, to_block)
            try:
                flt = evt.create_filter(from_block=0, to_block="latest", argument_filters=arg_filters)
                return flt.get_all_entries()
            except TypeError:
                pass
            # v5: createFilter(fromBlock, toBlock)
            flt = evt.createFilter(fromBlock=0, toBlock="latest", argument_filters=arg_filters)  # type: ignore
            return flt.get_all_entries()

        def _collect(evt_name: str):
            if evt_name not in self._events:
                return
            evt = getattr(self.contract.events, evt_name)

            arg_filters = {"fileId": item_id}
            # owner есть только у FileRegistered и он indexed — фильтруем, если передан
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
                    "timestamp": int(block["timestamp"]),
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

