# backend/app/blockchain.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from web3 import Web3
from web3.contract import Contract
from eth_account.messages import encode_typed_data
from eth_account import Account

from .config import settings

# RPC (по умолчанию попробуем localhost; в compose задавайте RPC_URL)
RPC_URL = settings.rpc_url or "http://127.0.0.1:8545"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

def _abi(name: str) -> list[dict[str, Any]]:
    # ABI_DIR можно передать через env; иначе ищем в стандартном пути монорепы
    abi_dir = settings.abi_dir or (Path(__file__).resolve().parents[2] / "contracts" / "artifacts-abi")
    return json.loads((abi_dir / f"{name}.abi.json").read_text())

def _chain():
    return settings.load_chain_config()

def _addr(name: str) -> str:
    chain = _chain()
    if not chain or name not in chain.verifyingContracts:
        raise RuntimeError(f"contract_address_missing: {name}")
    return Web3.to_checksum_address(chain.verifyingContracts[name])

def contract_at(address: str, abi_name: str) -> Contract:
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=_abi(abi_name))

def registry_contract() -> Contract:
    return contract_at(_addr("FileRegistry"), "FileRegistry")

def forwarder_contract() -> Contract:
    return contract_at(_addr("MinimalForwarder"), "MinimalForwarder")

FORWARD_TYPES = {
    "ForwardRequest": [
        {"name":"from","type":"address"},
        {"name":"to","type":"address"},
        {"name":"value","type":"uint256"},
        {"name":"gas","type":"uint256"},
        {"name":"nonce","type":"uint256"},
        {"name":"data","type":"bytes"},
    ]
}

def encode_register_call(file_id: bytes, cid: str, checksum: bytes, size: int, mime: str) -> str:
    reg = registry_contract()
    return reg.encode_abi("register", args=[file_id, cid, checksum, size, mime])

def build_forward_typed_data(from_addr: str, to_addr: str, data: str, gas: int = 1_000_000, value: int = 0) -> dict:
    fwd = forwarder_contract()
    nonce = fwd.functions.getNonce(Web3.to_checksum_address(from_addr)).call()
    chain = _chain()
    domain = {
        "name": (chain.domain.get("name") if chain else "MinimalForwarder"),
        "version": (chain.domain.get("version") if chain else "0.0.1"),
        "chainId": (chain.chainId if chain else 31337),
        "verifyingContract": Web3.to_checksum_address(_addr("MinimalForwarder")),
    }
    message = {
        "from": Web3.to_checksum_address(from_addr),
        "to": Web3.to_checksum_address(to_addr),
        "value": value,
        "gas": gas,
        "nonce": int(nonce),
        "data": data,
    }
    return {"domain": domain, "types": FORWARD_TYPES, "primaryType": "ForwardRequest", "message": message}
