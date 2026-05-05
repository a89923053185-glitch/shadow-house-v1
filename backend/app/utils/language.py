from __future__ import annotations

import re


def normalize_user_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def parse_user_age(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text.isdigit():
        return None
    age = int(text)
    if 8 <= age <= 120:
        return age
    return None


def dream_focus(dream: str | None) -> str:
    text = (dream or "").strip().strip(" .,!?:;")
    lowered = text.lower()
    prefixes = (
        "я хочу ",
        "хочу ",
        "мне хочется ",
        "мне нужен ",
        "мне нужна ",
        "мне нужно ",
        "нужен ",
        "нужна ",
        "нужно ",
        "хочется ",
        "к ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            lowered = text.lower()
            break

    if lowered.startswith("жизнь без "):
        return text[10:].strip()
    if lowered.startswith("жизнь с "):
        return text[7:].strip()
    if lowered.startswith("жизнь, где есть "):
        return text[16:].strip()
    if lowered.startswith("жизнь где есть "):
        return text[15:].strip()
    if lowered.startswith("жизнь "):
        return text[5:].strip()
    return text or "больше своей жизни"


def dream_life_clause(dream: str | None) -> str:
    focus = dream_focus(dream)
    lowered = focus.lower()

    if lowered.startswith("без "):
        return f"где нет {focus[4:].strip()}"
    if lowered.startswith("больше ") or lowered.startswith("меньше "):
        return f"где есть {focus}"
    return f"где есть {focus}"


def dream_step_phrase(dream: str | None) -> str:
    focus = dream_focus(dream)
    lowered = focus.lower()

    if "жизн" in lowered:
        return f"к {focus}"

    return f"к жизни, {dream_life_clause(dream)}"
