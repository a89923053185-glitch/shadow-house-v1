from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.fallback_llm import FallbackLLMService
from app.services.openai_adapter import OpenAIResponsesAdapter


METHOD_KEYS = (
    "short_reaction",
    "prediction",
    "depth_summary",
    "contradiction_reflection",
    "passport",
    "offer",
)

V_REACTION_QUESTION_MARKERS = (
    "чтобы точнее понять",
    "хочется уточнить",
    "интересно",
    "что помогает тебе",
    "что тебе помогает",
    "как тебе лучше",
    "в какие моменты",
    "что чаще всего",
)


class ScenarioLLMService:
    def __init__(self, adapter: OpenAIResponsesAdapter | None = None) -> None:
        self.adapter = adapter
        self.fallback = FallbackLLMService()
        self.usage = {
            key: {"openai": 0, "fallback": 0}
            for key in METHOD_KEYS
        }

    def _record(self, method: str, source: str) -> None:
        if method in self.usage and source in self.usage[method]:
            self.usage[method][source] += 1

    def _render(self, method: str, instructions: str, payload: dict[str, Any], max_output_tokens: int = 500) -> str:
        if not self.adapter:
            self._record(method, "fallback")
            return ""

        text = self.adapter.render(instructions=instructions, payload=payload, max_output_tokens=max_output_tokens)
        if text:
            self._record(method, "openai")
            return text

        self._record(method, "fallback")
        return ""

    def _looks_like_reply_request(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        if "?" in lowered:
            return True
        return any(marker in lowered for marker in V_REACTION_QUESTION_MARKERS)

    def short_reaction(self, shadow: dict[str, Any], choice: str, dream: str | None = None) -> str:
        fallback_text = self.fallback.short_reaction(shadow, choice, dream)
        if choice == "V":
            self._record("short_reaction", "fallback")
            return fallback_text
        if not self.adapter:
            self._record("short_reaction", "fallback")
            return fallback_text

        text = self.adapter.render(
            instructions=(
                "Ты усиливаешь сценарный ответ, а не заменяешь сценарий. "
                "Ты пишешь как КЭТ — тёплый, внимательный и инженерно-точный проводник диагностики. "
                "Напиши короткую живую реакцию на ответ пользователя. "
                "2-3 коротких предложения, без диагноза, без стыда, без психологической теории, без списков. "
                "Сохрани тон бережный, наблюдательный, человечный и чуть более живой, чем у шаблонной реплики. "
                "Если это реакция, не задавай в ней вопрос."
            ),
            payload={"shadow": shadow, "choice": choice, "dream": dream},
            max_output_tokens=180,
        )
        if not text or (choice == "V" and self._looks_like_reply_request(text)):
            self._record("short_reaction", "fallback")
            return fallback_text

        self._record("short_reaction", "openai")
        return text

    def prediction(self, dream: str | None, shadow_names: list[str]) -> str:
        text = self._render(
            "prediction",
            (
                "Сформулируй мягкое предсказание внутреннего паттерна. "
                "Это не анализ всей личности и не чат, а один сценарный блок модуля 'Тень дома' внутри большой системы 'Дом'. "
                "2-4 предложения, язык простой, эффект 'меня увидели', без категоричности. "
                "Пусть звучит тепло, точно и с небольшим чувством надежды. "
                "Используй слова вроде 'похоже', 'как будто', 'скорее всего'."
            ),
            {"dream": dream, "shadow_names": shadow_names},
            max_output_tokens=220,
        )
        return text or self.fallback.prediction(dream, shadow_names)

    def depth_summary(self, responses: dict[str, str]) -> str:
        text = self._render(
            "depth_summary",
            (
                "Сделай короткий человеческий вывод после блока глубины. "
                "Держи в фоне, что речь идет об одной скрытой трещине перед дальнейшей стройкой Дома. "
                "2-3 коротких абзаца. Не делай обзор всех 10 теней и не превращай текст в лекцию. "
                "Покажи один конкретный живой узел: где он проявляется, что он пытается защитить и почему уже мешает. "
                "Не используй мужской или женский род, не вставляй конструкции вроде 'ты увидел(а)' или 'ты отметил'. "
                "Если опираешься на формулировки пользователя, бери их в русские кавычки «...». "
                "Без стыда, без длинной теории, без советов. Пусть это звучит тепло, ясно и по-человечески."
            ),
            responses,
            max_output_tokens=220,
        )
        return text or self.fallback.depth_summary(responses)

    def contradiction_reflection(self, contradiction_labels: list[str]) -> str:
        text = self._render(
            "contradiction_reflection",
            (
                "Сформулируй мягкий текст о противоречии в ответах. "
                "Это должно звучать как внимательное наблюдение, а не разоблачение. "
                "Пусть чувствуется, что КЭТ замечает трещину, а не оценивает человека. "
                "2-3 предложения, спокойно, без давления и обвинения. Добавь человеческое тепло, но не расплывайся."
            ),
            {"contradictions": contradiction_labels},
            max_output_tokens=220,
        )
        return text or self.fallback.contradiction_text(contradiction_labels)

    def passport(self, dream: str | None, result: dict[str, Any]) -> str:
        text = self._render(
            "passport",
            (
                "Собери итоговый текст 'Паспорт тени' строго как структурированный сценарный блок, а не свободный чат. "
                "Помни, что 'Тень дома' — это не весь путь, а первый замер скрытой трещины перед следующими модулями Дома. "
                "Сохрани markdown-структуру с заголовком '### Паспорт тени', затем дай короткий вводный абзац с ощущением точного узнавания и только потом структурные разделы. "
                "Если тень одна, используй подпись '**Ключевая тень:**'. Если теней две, используй '**Ключевые тени:**'. "
                "Дальше используй разделы: "
                "'**Формула механизма:**', '**Как это проявляется:**', '**Цена:**', "
                "'**Объяснение без стыда:**', '**Скрытый ресурс:**', '**Фраза для скрина:**', '**Микро-разрешение:**'. "
                "Каждый раздел начинай с новой строки, подпись отделяй от содержания. "
                "Если используешь мысль пользователя, встраивай её аккуратно и грамотно, оформляй её в русские кавычки «...», не вставляй сырой кусок ответа механически. "
                "Избегай сломанных конструкций вроде 'Похоже, в я ...' и избегай гендерно окрашенных форм. "
                "Язык должен быть сильным, ясным, человечным, тёплым и компактным. "
                "Финал должен давать не только понимание, но и ощущение опоры и облегчения: со мной не что-то не так, это защитный механизм, который наконец стал видимым."
            ),
            {"dream": dream, "result": result},
            max_output_tokens=700,
        )
        return text or self.fallback.passport(dream, result)

    def offer(self, dream: str | None = None, result: dict[str, Any] | None = None) -> str:
        text = self._render(
            "offer",
            (
                "Сделай мягкий, но убедительный переход в следующий продуктовый шаг 'Чертеж дома'. "
                "2-4 предложения. Не продавай агрессивно. "
                "Покажи, что текущий результат уже важен, но это только часть всей системы Дома. "
                "Тон должен быть спокойным, уважительным и чуть вдохновляющим."
            ),
            {"dream": dream, "result": result or {}},
            max_output_tokens=220,
        )
        return text or self.fallback.offer()

    def get_usage_snapshot(self) -> dict[str, Any]:
        has_openai_calls = any(item["openai"] > 0 for item in self.usage.values())
        return {
            "configured_provider": "openai" if self.adapter else "fallback",
            "active_provider": "openai" if has_openai_calls else "fallback",
            "model": self.adapter.model if self.adapter else None,
            "calls": deepcopy(self.usage),
        }
