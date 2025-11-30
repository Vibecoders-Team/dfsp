from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class InitData:
    data: dict[str, Any]
    auth_date: datetime
    user_id: int | None


def _build_check_string(pairs: list[tuple[str, str]]) -> str:
    filtered = [(k, v) for k, v in pairs if k != "hash"]
    filtered.sort(key=lambda kv: kv[0])
    return "\n".join(f"{k}={v}" for k, v in filtered)


def verify_init_data(init_data: str, bot_token: str) -> InitData | None:
    """
    Verify Telegram initData according to https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    Returns parsed InitData on success, None otherwise.
    """
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        hash_hex = data.get("hash") or ""
        check_str = _build_check_string(pairs)
        # Telegram WebApp requires secret = HMAC_SHA256("WebAppData", bot_token)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret_key, check_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, hash_hex):
            return None

        auth_ts = int(data.get("auth_date", "0") or 0)
        auth_dt = datetime.fromtimestamp(auth_ts, tz=UTC) if auth_ts else datetime.now(UTC)

        user_payload = data.get("user")
        user_id: int | None = None
        if user_payload:
            try:
                user_dict = json.loads(user_payload)
                user_id = int(user_dict.get("id"))
            except Exception:
                user_id = None

        return InitData(data=data, auth_date=auth_dt, user_id=user_id)
    except Exception:
        return None
