"""Format notification messages for Telegram."""
# ruff: noqa: RUF001

from typing import Any

from ..message_store import get_message
from .models import CoalescedNotification, NotificationEvent


def format_address(address: str, max_len: int = 10) -> str:
    """Format Ethereum address for display."""
    if not address:
        return "Unknown"
    addr = address.lower()
    if addr.startswith("0x"):
        addr = addr[2:]
    if len(addr) > max_len * 2:
        return f"0x{addr[:max_len]}...{addr[-max_len:]}"
    return f"0x{addr}"


def format_file_id(file_id: str) -> str:
    """Format file ID for display."""
    if not file_id:
        return "Unknown"
    if file_id.startswith("0x"):
        file_id = file_id[2:]
    if len(file_id) > 12:
        return f"0x{file_id[:6]}...{file_id[-6:]}"
    return f"0x{file_id}"


DOWNLOAD_DENIED_REASONS: dict[str, str] = {
    "not_grantee": "notifications.download_denied.reason.not_grantee",
    "not_grantee_onchain": "notifications.download_denied.reason.not_grantee_onchain",
    "revoked": "notifications.download_denied.reason.revoked",
    "expired": "notifications.download_denied.reason.expired",
    "exhausted": "notifications.download_denied.reason.exhausted",
    "quota_exceeded": "notifications.download_denied.reason.quota_exceeded",
    "pow_required": "notifications.download_denied.reason.pow_required",
}

EVENT_TYPE_NAME_KEYS: dict[str, str] = {
    "grant_created": "notifications.type_name.grant_created",
    "grant_received": "notifications.type_name.grant_received",
    "grant_revoked": "notifications.type_name.grant_revoked",
    "download_allowed": "notifications.type_name.download_allowed",
    "download_denied": "notifications.type_name.download_denied",
    "anchor_ok": "notifications.type_name.anchor_ok",
    "relayer_warn": "notifications.type_name.relayer_warn",
}


async def format_grant_created(event: NotificationEvent) -> str:
    """Format grant_created notification."""
    payload = event.payload or {}

    grantee = format_address(payload.get("grantee", ""))
    file_id = format_file_id(payload.get("fileId") or payload.get("capId", ""))

    ttl_days = payload.get("ttlDays", payload.get("ttl_days", "?"))
    max_dl = payload.get("maxDownloads", payload.get("max_downloads", "?"))

    return await get_message(
        "notifications.grant_created",
        variables={
            "file_id": file_id,
            "grantee": grantee,
            "ttl_days": ttl_days,
            "max_downloads": max_dl,
        },
    )


async def format_grant_received(event: NotificationEvent) -> str:
    """Format grant_received notification (same as grant_created for grantee)."""
    payload = event.payload or {}

    grantor = format_address(payload.get("grantor", ""))
    file_id = format_file_id(payload.get("fileId") or payload.get("capId", ""))

    ttl_days = payload.get("ttlDays", payload.get("ttl_days", "?"))
    max_dl = payload.get("maxDownloads", payload.get("max_downloads", "?"))

    return await get_message(
        "notifications.grant_received",
        variables={
            "file_id": file_id,
            "grantor": grantor,
            "ttl_days": ttl_days,
            "max_downloads": max_dl,
        },
    )


async def format_grant_revoked(event: NotificationEvent) -> str:
    """Format grant_revoked notification."""
    payload = event.payload or {}
    file_id = format_file_id(payload.get("fileId") or payload.get("capId", ""))

    return await get_message("notifications.grant_revoked", variables={"file_id": file_id})


async def format_download_allowed(event: NotificationEvent) -> str:
    """Format download_allowed notification."""
    payload = event.payload or {}
    file_id = format_file_id(payload.get("fileId") or payload.get("capId", ""))

    return await get_message("notifications.download_allowed", variables={"file_id": file_id})


async def format_download_denied(event: NotificationEvent) -> str:
    """Format download_denied notification."""
    payload = event.payload or {}
    file_id = format_file_id(payload.get("fileId") or payload.get("capId", ""))
    reason = payload.get("reason", "unknown")

    reason_key = DOWNLOAD_DENIED_REASONS.get(reason)
    reason_text = await get_message(reason_key) if reason_key else reason

    return await get_message(
        "notifications.download_denied",
        variables={
            "file_id": file_id,
            "reason": reason_text,
        },
    )


async def format_anchor_ok(event: NotificationEvent) -> str:
    """Format anchor_ok notification."""
    payload = event.payload or {}

    period_id = payload.get("periodId", "?")
    tx_hash = payload.get("txHash")

    tx_display = format_address(tx_hash, max_len=8) if tx_hash else "pending"

    return await get_message(
        "notifications.anchor_ok",
        variables={
            "period_id": period_id,
            "tx_display": tx_display,
        },
    )


async def format_relayer_warn(event: NotificationEvent) -> str:
    """Format relayer_warn notification."""
    payload = event.payload or {}

    request_id = payload.get("requestId", "?")
    reason = payload.get("reason", "unknown")
    error = payload.get("error", "")

    return await get_message(
        "notifications.relayer_warn",
        variables={
            "request_id": request_id,
            "reason": reason,
            "error": error[:100] if error else "N/A",
        },
    )


async def format_notification(event: NotificationEvent) -> str:
    """Format single notification event."""
    event_type = event.type

    formatters: dict[str, Any] = {
        "grant_created": format_grant_created,
        "grant_received": format_grant_received,
        "grant_revoked": format_grant_revoked,
        "download_allowed": format_download_allowed,
        "download_denied": format_download_denied,
        "anchor_ok": format_anchor_ok,
        "relayer_warn": format_relayer_warn,
    }

    formatter = formatters.get(event_type)
    if formatter:
        return await formatter(event)

    # Fallback for unknown event types
    return await get_message(
        "notifications.unknown",
        variables={"event_type": event_type, "data": event.payload or {}},
    )


async def format_coalesced(notification: CoalescedNotification) -> str:
    """Format coalesced notification (multiple events grouped)."""
    event_type = notification.event_type
    count = len(notification.events)

    if count == 1:
        return await format_notification(notification.events[0])

    type_name_key = EVENT_TYPE_NAME_KEYS.get(event_type, "notifications.type_name.default")
    type_name = await get_message(type_name_key, variables={"event_type": event_type})
    seconds = int((notification.last_ts - notification.first_ts).total_seconds())

    return await get_message(
        "notifications.coalesced_summary",
        variables={
            "count": count,
            "type_name": type_name,
            "seconds": seconds,
        },
    )
