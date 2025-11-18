from __future__ import annotations


def mask_hex_id(value: int | str | None) -> str:
    """
    Превращает число/hex-строку в вид 0x1234…abcd.
    Используем для маскировки chat_id и прочих идентификаторов.
    """
    if value is None:
        return "unknown"

    if isinstance(value, int):
        hex_str = f"{value:x}"  # в hex
    else:
        hex_str = value.lower().removeprefix("0x")

    if len(hex_str) <= 8:
        return f"0x{hex_str}"

    return f"0x{hex_str[:4]}…{hex_str[-4:]}"


def mask_chat_id(chat_id: int | None) -> str:
    return mask_hex_id(chat_id)
