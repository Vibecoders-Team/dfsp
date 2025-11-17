from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from typing import Any, cast

from eth_abi.abi import encode as abi_encode
from eth_utils.address import to_checksum_address
from web3 import HTTPProvider, Web3
from web3.types import TxParams

from app.cache import Cache

log = logging.getLogger(__name__)


def _hex32(b: bytes | bytearray) -> str:
    return "0x" + bytes(b).hex()


class Chain:
    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        deploy_json_path: str,
        contract_name: str,
        tx_from: str | None = None,
        relayer_private_key: str | None = None,
    ):
        self.rpc_url = rpc_url or os.getenv("CHAIN_RPC_URL", "http://chain:8545")
        self.w3 = Web3(HTTPProvider(self.rpc_url))
        self.chain_id = chain_id
        self._acct = None  # eth_account.Account instance if relayer key provided
        self._relayer_pk = relayer_private_key
        if relayer_private_key:
            try:
                from eth_account import Account  # type: ignore

                self._acct = Account.from_key(relayer_private_key)
                if not tx_from:
                    tx_from = self._acct.address
                # default_account используется web3 для газ-оценки и т.п.
                self.w3.eth.default_account = self._acct.address  # type: ignore[assignment]
                log.info("Relayer signing enabled (direct mode): %s", self._acct.address)
            except Exception as e:
                log.warning("Failed to init relayer account: %s", e)
        # основной целевой контракт
        with open(deploy_json_path, encoding="utf-8") as _f:
            d = json.load(_f)
        c = d["contracts"][contract_name]
        self.address = Web3.to_checksum_address(c["address"])
        self.abi = c["abi"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        self.tx_from = (
            Web3.to_checksum_address(tx_from)
            if tx_from
            else (self.w3.eth.accounts[0] if self.w3.eth.accounts else None)
        )
        self.deployment_json = deploy_json_path or os.getenv(
            "CONTRACTS_DEPLOYMENT_JSON", "/app/shared/deployment.localhost.json"
        )
        self._fn = {f["name"]: f for f in self.abi if f.get("type") == "function"}
        self._events = {e["name"]: e for e in self.abi if e.get("type") == "event"}
        self.contracts: dict[str, Any] = {}
        self._load_contracts()

        # Авто-пополнение релейера в dev/anvil, если баланс нулевой и есть unlocked аккаунты
        try:
            if self._acct is not None:
                bal = int(self.w3.eth.get_balance(self._acct.address))
                if bal == 0:
                    accounts = list(getattr(self.w3.eth, "accounts", []) or [])
                    if accounts:
                        funder = Web3.to_checksum_address(accounts[0])
                        if funder.lower() != self._acct.address.lower():
                            log.info("Top up relayer %s from %s", self._acct.address, funder)
                            tx = {
                                "from": funder,
                                "to": self._acct.address,
                                "value": Web3.to_wei(
                                    10, "ether"
                                ),  # Увеличиваем до 10 ETH для покрытия высоких gas
                                "gas": 21_000,
                                "chainId": self.chain_id,
                            }
                            try:
                                # Без комиссий при baseFee=0
                                latest = self.w3.eth.get_block("latest")
                                base_fee = int(latest.get("baseFeePerGas") or 0)
                                if base_fee == 0:
                                    tx["maxFeePerGas"] = 0
                                    tx["maxPriorityFeePerGas"] = 0
                                else:
                                    tx["gasPrice"] = int(self.w3.eth.gas_price)
                            except Exception as e:
                                # Non-fatal: gas price may be unavailable in some providers
                                log.debug("failed to determine gas pricing info: %s", e, exc_info=True)
                            try:
                                h = self.w3.eth.send_transaction(tx)  # type: ignore[arg-type]
                                _ = self.w3.eth.wait_for_transaction_receipt(h, timeout=10)
                                new_bal = int(self.w3.eth.get_balance(self._acct.address))
                                log.info(
                                    "Top up successful, new balance: %s wei (%s ETH)",
                                    new_bal,
                                    Web3.from_wei(new_bal, "ether"),
                                )
                            except Exception as e:
                                log.warning("Top up failed (non-fatal): %s", e)
        except Exception as e:
            log.debug("Relayer auto-fund check failed: %s", e, exc_info=True)

    # ----------------- базовое -----------------

    def _tx(self) -> TxParams:
        tx: TxParams = {"chainId": self.chain_id, "gas": 2_000_000, "value": 0}
        if self.tx_from:
            tx["from"] = self.tx_from
        return tx

    def _fill_tx_defaults(self, tx: dict[str, Any]) -> dict[str, Any]:
        # Заполняем nonce, gas и gasPrice / maxFeePerGas если нужно, аккуратно приводя к TxParams
        try:
            if "from" not in tx and self.tx_from:
                tx["from"] = self.tx_from
            if "chainId" not in tx:
                tx["chainId"] = self.chain_id
            if "nonce" not in tx and tx.get("from"):
                try:
                    tx["nonce"] = self.w3.eth.get_transaction_count(
                        Web3.to_checksum_address(tx["from"])
                    )
                except Exception as e:
                    log.debug("failed to read transaction nonce: %s", e, exc_info=True)
            if "gas" not in tx:
                try:
                    # Словарь для оценки газа: только разрешенные ключи и без None
                    allowed = {
                        k: v
                        for k, v in tx.items()
                        if v is not None
                        and k in {"from", "to", "data", "value", "nonce", "chainId"}
                    }
                    gas_est = self.w3.eth.estimate_gas(cast(TxParams, allowed))
                    tx["gas"] = min(
                        int(gas_est), 2_000_000
                    )  # Ограничиваем gas, чтобы не превысить баланс
                except Exception:
                    tx["gas"] = 2_000_000
            if (
                ("gasPrice" not in tx)
                and ("maxFeePerGas" not in tx)
                and ("maxPriorityFeePerGas" not in tx)
            ):
                try:
                    tx["gasPrice"] = int(self.w3.eth.gas_price)
                except Exception as e:
                    log.debug("failed to fetch gas price: %s", e, exc_info=True)
        except Exception as e:
            log.debug("_fill_tx_defaults failed: %s", e)
        return tx

    def _send_tx(self, built_tx: dict[str, Any]) -> str:
        tx = self._fill_tx_defaults(dict(built_tx))
        # Убеждаемся, что from, chainId, nonce установлены для send_transaction fallback
        tx["from"] = tx.get("from", self.tx_from)
        tx["chainId"] = tx.get("chainId", self.chain_id)
        if "nonce" not in tx and tx.get("from"):
            try:
                tx["nonce"] = self.w3.eth.get_transaction_count(tx["from"])
            except Exception as e:
                log.debug("failed to get transaction nonce (fallback): %s", e, exc_info=True)
        # Если есть приватный ключ — подписываем вручную
        if self._acct and self._relayer_pk:
            try:
                from eth_account import Account  # type: ignore

                signed = Account.sign_transaction(tx, private_key=self._relayer_pk)
                # Совместимость разных версий eth-account: пытаемся получить raw-транзакцию из разных атрибутов
                raw = getattr(signed, "rawTransaction", None)
                if raw is None:
                    raw = getattr(signed, "raw_transaction", None)
                if raw is None:
                    raw = getattr(signed, "raw", None)
                if raw is None and hasattr(signed, "__bytes__"):
                    try:
                        raw = bytes(signed)  # type: ignore[arg-type]
                    except Exception:
                        raw = None
                if raw is None:
                    raise RuntimeError("signed_tx_has_no_raw_bytes")
                tx_hash = self.w3.eth.send_raw_transaction(raw)
                hexh = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
                log.info("Sent raw transaction: %s", hexh)
                return hexh
            except Exception as e:
                log.error("Raw sign/send failed, fallback to send_transaction: %s", e)
        # Fallback: используем unlocked аккаунт (Anvil / dev chain)
        try:
            tx_hash = self.w3.eth.send_transaction(tx)  # type: ignore[arg-type]
            return tx_hash.hex()
        except Exception as e:
            log.error("send_transaction failed (fallback): %s", e)
            raise

    def _load_contracts(self) -> None:
        self.contracts = {}
        try:
            with open(self.deployment_json, encoding="utf-8") as f:
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

    def get_contract(self, name: str) -> Any:
        c = self.contracts.get(name)
        if not c:
            raise RuntimeError(f"contract {name} not loaded")
        return c

    # ----------------- registry helpers -----------------

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
                fn = getattr(self.contract.functions, primary_name)(item_id, cid)
            elif n == 5:
                fn = getattr(self.contract.functions, primary_name)(
                    item_id,
                    cid,
                    checksum32 or (b"\x00" * 32),
                    int(size) & ((1 << 64) - 1),
                    mime or "",
                )
            else:
                raise RuntimeError(f"unsupported arity {n} for {primary_name}")
            built = fn.build_transaction(self._tx())
            txh = self._send_tx(built)
            return txh
        except Exception as e:
            log.error("register_or_update failed: %s", e, exc_info=True)
            raise

    def cid_of(self, item_id: bytes) -> str:
        key = f"file_meta:{_hex32(item_id)}"
        meta = Cache.get_json(key)
        if isinstance(meta, dict) and meta.get("cid"):
            return cast(str, meta.get("cid"))
        # Fallback to direct call then cache
        cid = ""
        if "cidOf" in self._fn:
            cid = self.contract.functions.cidOf(item_id).call() or ""
        elif "metaOf" in self._fn:
            meta = self.meta_of_full(item_id)
            cid = str(meta.get("cid") or "")
        elif "versionsOf" in self._fn:
            arr_val = self.contract.functions.versionsOf(item_id).call()
            if isinstance(arr_val, (list, tuple)) and arr_val:
                seq: Sequence[Any] = cast(Sequence[Any], arr_val)
                last = seq[-1]
                cid = last or ""
        # store minimal meta if available
        if cid:
            Cache.set_json(key, {"cid": cid}, ttl=300)
        return cid

    def meta_of_full(self, item_id: bytes) -> dict:
        key = f"file_meta:{_hex32(item_id)}"
        cached = Cache.get_json(key)
        if isinstance(cached, dict) and cached:
            return cached
        if "metaOf" not in self._fn:
            raise RuntimeError("Registry has no metaOf")
        fn = self._fn["metaOf"]
        outs = (fn.get("outputs") or [{}])[0]
        comps = outs.get("components") or []
        res = self.contract.functions.metaOf(item_id).call()

        def to_dict(vals: object) -> dict:
            if isinstance(vals, dict):
                return vals
            if isinstance(vals, (list, tuple)):
                return {
                    (c.get("name") or f"f{i}"): vals[i]
                    for i, c in enumerate(comps)
                    if i < len(vals)
                }
            return {}

        out = to_dict(res)
        if out:
            Cache.set_json(key, out, ttl=300)  # 5 minutes
        return out

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

        def _evt_logs(evt: object, arg_filters: dict[str, object]) -> list[object]:
            try:
                return list(
                    evt.get_logs(from_block=0, to_block="latest", argument_filters=arg_filters)
                )
            except TypeError:
                log.debug("evt.get_logs with from_block failed (TypeError), trying camelCase API")
            try:
                return list(
                    evt.get_logs(fromBlock=0, toBlock="latest", argument_filters=arg_filters)
                )  # type: ignore
            except Exception as e:
                log.debug("evt.get_logs camelCase failed: %s", e, exc_info=True)
            try:
                flt = evt.create_filter(
                    from_block=0, to_block="latest", argument_filters=arg_filters
                )
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
            arg_filters: dict[str, Any] = {"fileId": item_id}
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
                        # ✅ .get с дефолтом, чтобы TypedDict нас не пугал
                        "timestamp": int(block.get("timestamp", 0)),
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

    # ----------------- НОВОЕ: encode + EIP-712 для форвардера -----------------

    def get_forwarder(self) -> Any:
        return self.get_contract("MinimalForwarder")

    def get_access_control(self) -> Any:
        return self.get_contract("AccessControlDFSP")

    def encode_register_call(
        self, item_id: bytes, cid: str, checksum32: bytes, size: int, mime: str
    ) -> str:
        try:
            fn = self.contract.get_function_by_name("register")
        except ValueError as e:
            raise RuntimeError("FileRegistry has no 'register'") from e
        tx = fn(
            item_id, cid, checksum32, int(size) & ((1 << 64) - 1), mime or ""
        ).build_transaction(self._tx())
        return tx["data"]  # 0x...

    def encode_grant_call(
        self, file_id: bytes, grantee: str, ttl_sec: int, max_downloads: int
    ) -> str:
        """Build call data for AccessControlDFSP.grant."""
        ac = self.get_access_control()
        grantee = to_checksum_address(grantee)
        # ttl fits uint64, max_downloads fits uint32
        tx = ac.functions.grant(
            file_id, grantee, int(ttl_sec) & ((1 << 64) - 1), int(max_downloads) & ((1 << 32) - 1)
        ).build_transaction(self._tx())
        return tx["data"]

    def build_forward_typed_data(
        self, from_addr: str, to_addr: str, data: bytes | str, gas: int = 120_000
    ) -> dict:
        fwd = self.get_forwarder()
        from_addr = to_checksum_address(from_addr)
        to_addr = to_checksum_address(to_addr)
        verifying = (
            fwd.address if hasattr(fwd, "address") else fwd.functions.eip712Domain().call()[3]
        )

        # getNonce is per-signer; leave uncached (it changes frequently on use)
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
        return {
            "domain": domain,
            "types": types,
            "primaryType": "ForwardRequest",
            "message": message,
        }

    def read_grant_nonce(self, grantor: str) -> int:
        """Read AccessControlDFSP.grantNonces(grantor) as int.
        Safe checksum normalization is applied.
        """
        grantor_cs = to_checksum_address(grantor)
        return int(self.get_access_control().functions.grantNonces(grantor_cs).call())

    def read_grant_nonce_cached(self, grantor: str) -> int:
        grantor_cs = to_checksum_address(grantor)
        key = f"grant_nonce:{grantor_cs.lower()}"
        val = Cache.get_text(key)
        if val is not None:
            try:
                return int(val)
            except Exception as e:
                log.debug("read_grant_nonce_cached: failed to parse cached value %r: %s", val, e, exc_info=True)
        n = self.read_grant_nonce(grantor_cs)
        Cache.set_text(key, str(int(n)), ttl=30)
        return int(n)

    def predict_cap_id(
        self, grantor: str, grantee: str, file_id: bytes, nonce: int | None = None, offset: int = 0
    ) -> bytes:
        """Compute keccak256(grantor, grantee, fileId, (nonce or grantNonces[grantor]) + offset) → bytes32.
        Matches Solidity: keccak256(abi.encode(address,address,bytes32,uint256)).
        - grantor, grantee: EVM addresses (0x-hex), case-insensitive.
        - file_id: bytes32 or 0x-hex32.
        - nonce: if None, read on-chain via read_grant_nonce().
        - offset: to predict a batch item, add 0,1,2,... to the starting nonce.
        """
        grantor_cs = to_checksum_address(grantor)
        grantee_cs = to_checksum_address(grantee)
        if nonce is None:
            nonce_val = self.read_grant_nonce_cached(grantor_cs)
        else:
            nonce_val = int(nonce)
        n = nonce_val + int(offset)
        # Ensure file_id is 32 bytes
        if isinstance(file_id, (bytes, bytearray)):
            fid = bytes(file_id)
        elif isinstance(file_id, str) and file_id.startswith("0x") and len(file_id) == 66:
            fid = Web3.to_bytes(hexstr=cast("HexStr", file_id))  # type: ignore[name-defined]
        else:
            raise ValueError("file_id must be bytes32 or 0x-hex32")
        encoded = abi_encode(
            ["address", "address", "bytes32", "uint256"], [grantor_cs, grantee_cs, fid, n]
        )
        return Web3.keccak(encoded)

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

    # -------- New helpers for AccessControlDFSP actions --------
    def encode_use_once_call(self, cap_id: bytes | str) -> str:
        """Build call data for AccessControlDFSP.useOnce(capId). cap_id can be bytes32 or hex string."""
        ac = self.get_access_control()
        if isinstance(cap_id, (bytes, bytearray)):
            cap_b = bytes(cap_id)
        elif isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66:
            cap_b = Web3.to_bytes(hexstr=cast("HexStr", cap_id))  # type: ignore[name-defined]
        else:
            raise ValueError("cap_id must be bytes32 or 0x-hex32")
        tx = ac.functions.useOnce(cap_b).build_transaction(self._tx())
        return tx["data"]

    def encode_revoke_call(self, cap_id: bytes | str) -> str:
        """Build call data for AccessControlDFSP.revoke(capId)."""
        ac = self.get_access_control()
        if isinstance(cap_id, (bytes, bytearray)):
            cap_b = bytes(cap_id)
        elif isinstance(cap_id, str) and cap_id.startswith("0x") and len(cap_id) == 66:
            cap_b = Web3.to_bytes(hexstr=cast("HexStr", cap_id))  # type: ignore[name-defined]
        else:
            raise ValueError("cap_id must be bytes32 or 0x-hex32")
        tx = ac.functions.revoke(cap_b).build_transaction(self._tx())
        return tx["data"]
