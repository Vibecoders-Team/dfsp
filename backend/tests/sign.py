# sign_login_manual.py
# Подпись EIP-712 (LoginChallenge) вручную: digest = keccak(0x1901 || domainSep || structHash)
# Требуется: eth-account, eth-keys, eth-utils
import argparse, json, sys
from eth_account import Account
from eth_utils import keccak, to_bytes, to_canonical_address
from eth_keys import keys

DOMAIN_NAME = "DFSP-Login"
DOMAIN_VERSION = "1"

def keccak_text(s: str) -> bytes:
    return keccak(text=s)  # эквивалент keccak(bytes(s, 'utf-8'))

def hexstr_to_32(hx: str) -> bytes:
    if not (isinstance(hx, str) and hx.startswith("0x") and len(hx) == 66):
        print("ERROR: nonce должен быть 0x + 64 hex", file=sys.stderr); sys.exit(2)
    return bytes.fromhex(hx[2:])

def left_pad_32(b: bytes) -> bytes:
    if len(b) > 32: b = b[-32:]
    return b.rjust(32, b"\x00")

def build_typed(address: str, nonce_hex: str) -> dict:
    return {
        "domain": {"name": DOMAIN_NAME, "version": DOMAIN_VERSION},
        "types": {
            "LoginChallenge": [
                {"name": "address", "type": "address"},
                {"name": "nonce",   "type": "bytes32"},
            ]
        },
        "primaryType": "LoginChallenge",
        "message": {"address": address, "nonce": nonce_hex},
    }

def main():
    ap = argparse.ArgumentParser(description="Sign DFSP Login EIP-712 manually (no encode_typed_data)")
    ap.add_argument("--pk", required=True, help="0x + 64 hex приватный ключ")
    ap.add_argument("--nonce", required=True, help="bytes32 nonce из /auth/challenge (0x + 64 hex)")
    args = ap.parse_args()

    pk = args.pk.strip()
    if not (pk.startswith("0x") and len(pk) == 66):
        print("ERROR: --pk формат 0x + 64 hex", file=sys.stderr); sys.exit(2)

    acct = Account.from_key(pk)
    nonce32 = hexstr_to_32(args.nonce)

    # --- 1) type hashes ---
    # EIP712Domain(string name,string version)
    typehash_domain = keccak_text("EIP712Domain(string name,string version)")
    name_hash       = keccak_text(DOMAIN_NAME)
    version_hash    = keccak_text(DOMAIN_VERSION)
    domain_sep      = keccak(typehash_domain + name_hash + version_hash)

    # LoginChallenge(address address,bytes32 nonce)
    typehash_login  = keccak_text("LoginChallenge(address address,bytes32 nonce)")
    addr32          = left_pad_32(to_canonical_address(acct.address))  # 20 -> 32
    struct_hash     = keccak(typehash_login + addr32 + nonce32)

    # --- 2) EIP-712 digest ---
    digest = keccak(b"\x19\x01" + domain_sep + struct_hash)

    # --- 3) Подпись secp256k1 ---
    priv = keys.PrivateKey(bytes.fromhex(pk[2:]))
    sig  = priv.sign_msg_hash(digest)  # v в {27,28}
    sig_hex = "0x" + sig.to_bytes().hex()

    # --- 4) Готовый typedData (ровно то, что ждёт сервер) ---
    typed = build_typed(acct.address, args.nonce)

    print(f"ETH_ADDRESS={acct.address}")
    print(f"AUTH_SIGNATURE={sig_hex}")
    print("AUTH_TYPED_DATA=" + json.dumps(typed, separators=(',', ':')))

if __name__ == "__main__":
    main()
