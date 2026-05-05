from __future__ import annotations

import json
from typing import Any


class OpenAIResponsesAdapter:
    """Thin adapter over OpenAI Responses API.

    This adapter only attempts generation. Fallback decisions live one layer above.
    """

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _extract_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        try:
            parts = []
            for item in getattr(response, "output", []) or []:
                for content in getattr(item, "content", []) or []:
                    text = getattr(content, "text", "")
                    if text:
                        parts.append(text)
            return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
        except Exception:
            return ""

    def render(self, instructions: str, payload: dict[str, Any], max_output_tokens: int = 500) -> str:
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
                max_output_tokens=max_output_tokens,
            )
        except Exception:
            return ""

        return self._extract_text(response)
