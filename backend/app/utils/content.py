from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def get_shadows() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "data" / "shadows.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def get_shadow_map() -> dict[int, dict]:
    return {shadow["id"]: shadow for shadow in get_shadows()}


REALITY_CHECK_STEPS = [
    ("started_recently", "Если опереться не на ощущение, а на факты: что из важного для себя реально сдвинулось за последние 3 месяца?"),
    ("completed_to_result", "А что из этого уже дошло до результата, а не осталось только на старте?"),
    ("still_delaying", "И где всё ещё остается откладывание, хотя внутри ясно, что это важно?"),
]

REALITY_CHECK_QUESTIONS = [question for _, question in REALITY_CHECK_STEPS]

DEPTH_QUESTIONS = [
    ("strongest_trigger", "Если сейчас оглянуться на весь путь, где был самый сильный неприятный отклик? Можно назвать одну тень, связку из двух или описать место своими словами."),
    ("situations", "В каких реальных ситуациях в жизни это проявляется чаще всего?"),
    ("avoiding", "С чем этот механизм помогает тебе не сталкиваться? Например: с риском ошибиться, с чужой оценкой, с потерей опоры — или с чем-то еще."),
    ("protects_from", "От чего именно он пытается тебя защищать? Например: от стыда, от боли, от перегруза, от ощущения, что почва уходит из-под ног — или от чего-то другого."),
    ("price_paid", "И какую цену ты уже платишь за такую защиту? Например: время, силы, упущенные возможности, жизнь не в своем уровне — или что-то еще."),
]

BODY_CHOICES = [
    {"key": "сжатие", "label": "Сжатие"},
    {"key": "напряжение", "label": "Напряжение"},
    {"key": "тяжесть", "label": "Тяжесть"},
    {"key": "хочется закрыться", "label": "Хочется закрыться"},
    {"key": "хочется отступить", "label": "Хочется отступить"},
    {"key": "другое", "label": "Другое"},
]
