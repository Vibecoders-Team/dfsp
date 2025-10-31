from __future__ import annotations

import os
import re
from typing import Iterable

from eth_utils import is_address
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.exceptions import UnsupportedAlgorithm

HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# Basic whitelist for MIME types
_ALLOWED_MIME_PREFIXES = (
    "text/",
    "image/",
)
_ALLOWED_MIME_EXACT = {
    "application/pdf",
    "application/json",
}

MAX_FILE_NAME_LEN = 255
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


def validate_eth_address(addr: str) -> bool:
    try:
        return bool(is_address(addr))
    except Exception:
        return False


def validate_hex32(s: str) -> bool:
    return isinstance(s, str) and HEX32_RE.fullmatch(s or "") is not None


def validate_mime(m: str) -> bool:
    if not isinstance(m, str) or not m:
        return False
    if m in _ALLOWED_MIME_EXACT:
        return True
    return any(m.startswith(p) for p in _ALLOWED_MIME_PREFIXES)


def sanitize_filename(name: str) -> str:
    # Keep only basename, strip path components
    base = os.path.basename(name or "")
    # Remove traversal remnants and control chars
    base = base.replace("..", "").replace("\\", "").replace("/", "")
    base = "".join(ch for ch in base if 31 < ord(ch) < 127)
    if not base:
        base = "file"
    if len(base) > MAX_FILE_NAME_LEN:
        base = base[:MAX_FILE_NAME_LEN]
    return base


def validate_rsa_spki_pem(pem: str) -> bool:
    if not isinstance(pem, str) or "BEGIN PUBLIC KEY" not in pem:
        return False
    try:
        key = load_pem_public_key(pem.encode("utf-8"))
        return isinstance(key, RSAPublicKey)
    except (ValueError, UnsupportedAlgorithm):
        return False
    except Exception:
        return False

