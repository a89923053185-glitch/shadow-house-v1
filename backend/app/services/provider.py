from app.core.config import get_settings
from app.services.llm_service import ScenarioLLMService
from app.services.openai_adapter import OpenAIResponsesAdapter


def get_llm_service():
    settings = get_settings()
    adapter = None
    if settings.openai_enabled and settings.openai_api_key:
        try:
            adapter = OpenAIResponsesAdapter(api_key=settings.openai_api_key, model=settings.openai_model)
        except Exception:
            adapter = None
    return ScenarioLLMService(adapter=adapter)
