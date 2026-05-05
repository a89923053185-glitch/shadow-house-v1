from __future__ import annotations

import re


def normalize_phone_number(raw_phone: str) -> str:
    digits = re.sub(r"\D+", "", raw_phone or "")
    if not digits:
        raise ValueError("Укажи телефон, чтобы сохранить результат.")

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 11 and digits.startswith("7"):
        digits = digits
    elif len(digits) == 10:
        digits = "7" + digits

    if len(digits) != 11 or not digits.startswith("7"):
        raise ValueError("Укажи номер в формате +7 (999) 123-45-67, и я сразу отправлю код.")

    return f"+{digits}"


def mask_phone_number(raw_phone: str) -> str:
    normalized = normalize_phone_number(raw_phone)
    visible_tail = normalized[-2:]
    masked_digits = "*" * max(len(normalized) - len(visible_tail) - 1, 4)
    return f"+{masked_digits}{visible_tail}"
