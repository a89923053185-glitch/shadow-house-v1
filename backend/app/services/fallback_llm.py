from __future__ import annotations

import re
from typing import Any

from app.utils.language import dream_focus, dream_step_phrase


CHOICE_INTENSITY = {"A": "сильный", "B": "средний", "V": "низкий"}


class FallbackLLMService:
    def _dream_target(self, dream: str | None) -> str:
        return dream_focus(dream)

    def _stable_choice_label(self, shadow: dict[str, Any], choice: str) -> str:
        options = shadow.get("options") or {}
        return str(options.get(choice) or "").strip()

    def _contextual_v_reaction(self, shadow: dict[str, Any]) -> str:
        custom = str(shadow.get("v_reaction") or "").strip()
        if custom:
            return custom

        stable_label = self._stable_choice_label(shadow, "V")
        stable_prefix = (
            f"Ответ «{stable_label}» здесь звучит как более устойчивая опора. "
            if stable_label
            else "Здесь слышится более устойчивая опора, чем выраженная трещина. "
        )
        return (
            stable_prefix
            + "Похоже, в этой теме трещина выражена слабее и пока не держит тебя сильнее всего. Но давай спокойно посмотрим, что откликается глубже."
        )

    def short_reaction(self, shadow: dict[str, Any], choice: str, dream: str | None = None) -> str:
        if choice == "A":
            return (
                f"{shadow['micro_reaction']} "
                "Похоже, это не случайный эпизод, а живая точка, где внутри правда становится тесно и небезопасно."
            )
        if choice == "B":
            return (
                f"{shadow['micro_reaction']} "
                "Ты как будто не останавливаешься совсем, но и не можешь идти в это легко. Здесь уже чувствуется внутреннее трение, а не просто случайная заминка."
            )
        return self._contextual_v_reaction(shadow)

    def prediction(self, dream: str | None, shadow_names: list[str]) -> str:
        if not shadow_names:
            return ""
        joined = " и ".join(shadow_names[:2])
        dream_text = dream_step_phrase(dream)
        return (
            "Похоже, картина начинает собираться чуть яснее. "
            f"Ты правда хочешь двигаться {dream_text}, но рядом с этим быстро включаются {joined}. "
            "Из-за этого дело не просто в торможении: скорее всего, ты снова и снова попадаешь в один и тот же внутренний сценарий, даже если снаружи всё выглядит по-разному. И это уже не про слабость, а про важный узел, который становится видимым."
        )

    def depth_summary(self, responses: dict[str, str]) -> str:
        situations = self._clean_fragment(responses.get("situations"), "situations") or "в реальных важных шагах"
        avoiding = self._clean_fragment(responses.get("avoiding"), "avoiding") or "чего-то неприятного и небезопасного"
        protects_from = self._clean_fragment(responses.get("protects_from"), "protects_from")
        return (
            "Сейчас уже видно, что это не просто привычка и не случайная черта.\n\n"
            f"Этот узел особенно проявляется в таких ситуациях: «{situations}».\n\n"
            f"Похоже, так психика старается не сталкиваться с «{avoiding}»"
            + (f" и не подпускать слишком близко «{protects_from}»." if protects_from else ".")
            + " Когда-то это правда могло помогать держаться, но сейчас всё заметнее ограничивает движение."
        )

    def contradiction_text(self, contradiction_labels: list[str]) -> str:
        if not contradiction_labels:
            return ""
        labels = "; ".join(contradiction_labels)
        return (
            "Здесь видно важное и вполне человеческое расхождение.\n\n"
            f"Сейчас особенно проявляется вот что: {labels}.\n\n"
            "Это не обвинение и не попытка поймать на несостыковке, а место, где сам механизм становится особенно заметен."
        )

    def passport(self, dream: str | None, result: dict[str, Any]) -> str:
        top_names = result.get("top_shadow_names", [])
        top_title = " и ".join(top_names) if top_names else "Тень дома"
        top_label = "Ключевая тень" if len(top_names) <= 1 else "Ключевые тени"
        mechanism = result.get("mechanism_formula", "")
        manifestation = result.get("manifestation", "")
        price = result.get("price", "")
        resource = result.get("hidden_resource", "")
        screen_phrase = result.get("screen_phrase", "")
        micro_permission = result.get("micro_permission", "")
        normalisation = result.get("normalisation", "")
        thought = self._passport_thought(result)
        dream_step = dream_step_phrase(dream)

        return (
            f"### Паспорт тени\n\n"
            f"{thought}\n\n"
            f"**{top_label}:**\n{top_title}\n\n"
            f"**Формула механизма:**\n{mechanism}\n\n"
            f"**Как это проявляется:**\n{manifestation}\n\n"
            f"**Цена:**\n{price}\n\n"
            f"**Объяснение без стыда:**\n{normalisation}\n\n"
            f"**Скрытый ресурс:**\n{resource}\n\n"
            f"**Фраза для скрина:**\n«{screen_phrase}»\n\n"
            f"**Микро-разрешение:**\n{micro_permission}\n\n"
            "Главное: с тобой не что-то не так. Одна из скрытых трещин стала видимой, хотя раньше включалась почти автоматически и тихо влияла на движение. "
            f"Когда такой узел становится видимым, появляется не только ясность, но и опора. А значит, у тебя становится больше свободы действительно приблизиться {dream_step}."
        )

    def _passport_thought(self, result: dict[str, Any]) -> str:
        contradiction = (result.get("contradiction_explanation") or "").strip(" .")
        protects_from = self._clean_fragment(result.get("protects_from"), "protects_from")
        avoids = self._clean_fragment(result.get("avoiding"), "avoiding")
        situations = self._clean_fragment(result.get("situations"), "situations")
        if contradiction:
            return f"Похоже, в такие моменты внутри часто звучит мысль: «{contradiction}». Этот механизм не про слабость, а про способ удержать себя в безопасности."
        if protects_from:
            return f"Похоже, внутри здесь очень важно не сталкиваться с «{protects_from}». Этот механизм не про дефект, а про старую попытку сохранить безопасность."
        if avoids:
            return f"Похоже, в этой теме внутри всё время есть движение в сторону «не сталкиваться с {avoids}». Так обычно и собирается защитный механизм."
        if situations:
            return f"Этот механизм особенно заметен в таких ситуациях: «{situations}». Именно там скрытая трещина становится виднее всего."
        return "Сейчас уже можно увидеть не только внешнее поведение, но и тот внутренний механизм, который долго держал всё это на месте."

    def _clean_fragment(self, value: Any, kind: str) -> str:
        text = str(value or "").strip().strip(" .")
        lowered = text.lower()
        prefixes = {
            "situations": [
                "это чаще всего проявляется в ",
                "чаще всего проявляется в ",
                "это проявляется в ",
                "проявляется в ",
            ],
        }
        regex_prefixes = {
            "avoiding": r"^(этот механизм помогает|механизм помогает|помогает)?\s*не сталкиваться\s+с(?:о)?\s+",
            "protects_from": r"^(он как будто|это)?\s*защищает\s+от\s+",
        }
        pattern = regex_prefixes.get(kind)
        if pattern:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip(" .")
            lowered = text.lower()
        for prefix in prefixes.get(kind, []):
            if lowered.startswith(prefix):
                text = text[len(prefix):].strip(" .")
                break
        return re.sub(r"\s+", " ", text)

    def offer(self) -> str:
        return (
            "Сейчас стала видна не просто поверхность, а одна важная скрытая трещина перед дальнейшей стройкой Дома. "
            "И это уже немало: когда виден узел, перестаёт казаться, что всё буксует без причины. "
            "Но тень — это только часть всей конструкции. Следующий шаг — «Чертеж дома»: там мы собираем уже не один узел, а общую архитектуру, чтобы стало понятнее, на что можно опереться дальше при следующем этапе стройки."
        )
