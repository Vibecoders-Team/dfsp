from __future__ import annotations


def mask_hex_id(value: int | str | None) -> str:
    """
    Convert number/hex string to 0x1234…abcd form.
    Used to mask chat_id and other identifiers.
    """
    if value is None:
        return "unknown"

    if isinstance(value, int):
        hex_str = f"{value:x}"  # in hex
    else:
        hex_str = value.lower().removeprefix("0x")

    if len(hex_str) <= 8:
        return f"0x{hex_str}"

    return f"0x{hex_str[:4]}…{hex_str[-4:]}"


def mask_chat_id(chat_id: int | None) -> str:
    return mask_hex_id(chat_id)
