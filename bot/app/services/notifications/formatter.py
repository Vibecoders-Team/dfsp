"""Format notification messages for Telegram."""
# ruff: noqa: RUF001

from typing import Any

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


def format_grant_created(event: NotificationEvent) -> str:
    """Format grant_created notification."""
    subject = event.subject or {}
    data = event.data or {}

    grantee = format_address(subject.get("grantee", ""))
    file_id = format_file_id(subject.get("fileId", ""))

    ttl_days = data.get("ttlDays", "?")
    max_dl = data.get("maxDownloads", "?")

    return (
        f"✅ <b>Grant создан</b>\n\n"
        f"📁 Файл: <code>{file_id}</code>\n"
        f"👤 Получатель: <code>{grantee}</code>\n"
        f"⏰ Срок: {ttl_days} дн.\n"
        f"📥 Лимит скачиваний: {max_dl}"
    )


def format_grant_received(event: NotificationEvent) -> str:
    """Format grant_received notification (same as grant_created for grantee)."""
    subject = event.subject or {}
    data = event.data or {}

    grantor = format_address(subject.get("grantor", ""))
    file_id = format_file_id(subject.get("fileId", ""))

    ttl_days = data.get("ttlDays", "?")
    max_dl = data.get("maxDownloads", "?")

    return (
        f"🎁 <b>Вы получили доступ</b>\n\n"
        f"📁 Файл: <code>{file_id}</code>\n"
        f"👤 От: <code>{grantor}</code>\n"
        f"⏰ Срок: {ttl_days} дн.\n"
        f"📥 Лимит скачиваний: {max_dl}"
    )


def format_grant_revoked(event: NotificationEvent) -> str:
    """Format grant_revoked notification."""
    subject = event.subject or {}
    file_id = format_file_id(subject.get("fileId", ""))

    return f"🚫 <b>Доступ отозван</b>\n\n📁 Файл: <code>{file_id}</code>\nДоступ к файлу был отозван."


def format_download_allowed(event: NotificationEvent) -> str:
    """Format download_allowed notification."""
    subject = event.subject or {}
    file_id = format_file_id(subject.get("fileId", ""))

    return f"✅ <b>Скачивание разрешено</b>\n\n📁 Файл: <code>{file_id}</code>\nВы можете скачать файл."


def format_download_denied(event: NotificationEvent) -> str:
    """Format download_denied notification."""
    subject = event.subject or {}
    data = event.data or {}
    file_id = format_file_id(subject.get("fileId", ""))
    reason = data.get("reason", "unknown")

    reason_map: dict[str, str] = {
        "not_grantee": "Вы не являетесь получателем доступа",
        "not_grantee_onchain": "Доступ не подтверждён в блокчейне",
        "revoked": "Доступ отозван",
        "expired": "Срок действия истёк",
        "exhausted": "Лимит скачиваний исчерпан",
        "quota_exceeded": "Превышен дневной лимит",
        "pow_required": "Требуется подтверждение PoW",
    }

    reason_text = reason_map.get(reason, reason)

    return f"❌ <b>Скачивание отклонено</b>\n\n📁 Файл: <code>{file_id}</code>\nПричина: {reason_text}"


def format_anchor_ok(event: NotificationEvent) -> str:
    """Format anchor_ok notification."""
    subject = event.subject or {}
    data = event.data or {}

    period_id = subject.get("periodId", "?")
    tx_hash = subject.get("txHash") or data.get("txHash")

    tx_display = format_address(tx_hash, max_len=8) if tx_hash else "pending"

    return f"🔗 <b>Анкер зафиксирован</b>\n\nПериод: {period_id}\nТранзакция: <code>{tx_display}</code>"


def format_relayer_warn(event: NotificationEvent) -> str:
    """Format relayer_warn notification."""
    subject = event.subject or {}
    data = event.data or {}

    request_id = subject.get("requestId", "?")
    reason = data.get("reason", "unknown")
    error = data.get("error", "")

    return (
        f"⚠️ <b>Предупреждение релейера</b>\n\n"
        f"Запрос: <code>{request_id}</code>\n"
        f"Причина: {reason}\n"
        f"Ошибка: {error[:100] if error else 'N/A'}"
    )


def format_notification(event: NotificationEvent) -> str:
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
        return formatter(event)

    # Fallback for unknown event types
    return f"📢 <b>{event_type}</b>\n\n{event.data or {}}"


def format_coalesced(notification: CoalescedNotification) -> str:
    """Format coalesced notification (multiple events grouped)."""
    event_type = notification.event_type
    count = len(notification.events)

    if count == 1:
        return format_notification(notification.events[0])

    # Multiple events - create summary
    event_type_names: dict[str, str] = {
        "grant_created": "созданий доступа",
        "grant_received": "получений доступа",
        "grant_revoked": "отзывов доступа",
        "download_allowed": "разрешённых скачиваний",
        "download_denied": "отклонённых скачиваний",
        "anchor_ok": "анкеров",
        "relayer_warn": "предупреждений релейера",
    }

    type_name = event_type_names.get(event_type, event_type)

    return (
        f"📊 <b>Сводка ({count} {type_name})</b>\n\n"
        f"За последние {int((notification.last_ts - notification.first_ts).total_seconds())} сек."
    )
