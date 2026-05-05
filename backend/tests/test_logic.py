from pathlib import Path

import pytest

from app.services.fallback_llm import FallbackLLMService
from app.services.llm_service import ScenarioLLMService
from app.utils.phone import normalize_phone_number
from app.utils.language import dream_step_phrase


def project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current.parent, *current.parents]:
        if (candidate / "docker-compose.yml").exists():
            return candidate
    for candidate in [current.parent, *current.parents]:
        if (candidate / "app").is_dir() and (candidate / "tests").is_dir() and (candidate / "pytest.ini").exists():
            return candidate
    raise RuntimeError("Project root not found")


ROOT = project_root()


def project_file(relative: str) -> Path:
    path = ROOT / relative
    if path.exists():
        return path
    if relative.startswith("backend/"):
        backend_path = ROOT / relative.removeprefix("backend/")
        if backend_path.exists():
            return backend_path
    pytest.skip(f"Project file is not available in this test image: {relative}")


def test_fallback_prediction():
    service = FallbackLLMService()
    text = service.prediction("более своей жизни", ["Замирание перед шагом", "Жизнь с оглядкой"])
    assert "более своей жизни" in text
    assert "Замирание" in text


class FakeAdapter:
    model = "fake-model"

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    def render(self, instructions, payload, max_output_tokens=500):  # noqa: ANN001, ANN201
        return self.response_text


def test_scenario_llm_service_uses_fallback_without_adapter():
    service = ScenarioLLMService()
    text = service.prediction("более своей жизни", ["Замирание перед шагом"])

    assert "более своей жизни" in text
    snapshot = service.get_usage_snapshot()
    assert snapshot["configured_provider"] == "fallback"
    assert snapshot["active_provider"] == "fallback"
    assert snapshot["calls"]["prediction"]["fallback"] == 1


def test_scenario_llm_service_uses_openai_when_adapter_returns_text():
    service = ScenarioLLMService(adapter=FakeAdapter("Живой ответ от OpenAI"))
    text = service.depth_summary({"situations": "в работе", "avoiding": "стыд"})

    assert text == "Живой ответ от OpenAI"
    snapshot = service.get_usage_snapshot()
    assert snapshot["configured_provider"] == "openai"
    assert snapshot["active_provider"] == "openai"
    assert snapshot["calls"]["depth_summary"]["openai"] == 1


def test_short_reaction_for_v_falls_back_when_openai_returns_question():
    service = ScenarioLLMService(adapter=FakeAdapter("Чтобы точнее понять, как тебе лучше стартовать?"))
    shadow = {"micro_reaction": "Похоже, старт сам по себе для тебя не выглядит опасным."}

    text = service.short_reaction(shadow, "V", "к спокойной жизни")

    assert "?" not in text
    assert "Чтобы точнее понять" not in text
    snapshot = service.get_usage_snapshot()
    assert snapshot["configured_provider"] == "openai"
    assert snapshot["calls"]["short_reaction"]["fallback"] == 1
    assert snapshot["calls"]["short_reaction"]["openai"] == 0


def test_short_reaction_for_v_always_uses_stable_non_contradictory_fallback():
    service = ScenarioLLMService(adapter=FakeAdapter("Похоже, тебе трудно удерживаться в процессе без подтверждения."))
    shadow = {
        "micro_reaction": "Похоже, тебе сложно находиться в процессе, если нет быстрого подтверждения, что все работает.",
        "options": {"V": "Могу продолжать долго"},
        "v_reaction": "Похоже, тема длинного пути без быстрых подтверждений для тебя здесь выдерживается довольно устойчиво. Значит, сам процесс, скорее всего, не главный узел — дальше важнее посмотреть, что происходит в более личном слое.",
    }

    text = service.short_reaction(shadow, "V", "к спокойной жизни")

    assert shadow["v_reaction"] == text
    assert "сложно находиться в процессе" not in text


def test_frontend_message_rendering_splits_question_from_reaction_and_next_step():
    source = project_file("frontend/app/page.tsx").read_text()

    assert "function splitAssistantMessage" in source
    assert 'const shadowSeparator = "\\n\\n**Тень "' in source
    assert "lastPart.endsWith(\"?\")" in source
    assert source.count("assistantMessagesFromResponse(") >= 3


def test_frontend_css_keeps_warm_input_palette_and_readable_text():
    css = project_file("frontend/app/globals.css").read_text()

    assert "--bg: #402b20;" in css
    assert "--assistant: #f4e2ce;" in css
    assert "--input-bg: #d4b08e;" in css
    assert "--input-text: #4b3324;" in css
    assert "--input-placeholder: #85644d;" in css
    assert ".textInput {" in css
    assert "background: var(--input-bg);" in css
    assert "color: var(--input-text);" in css
    assert ".textInput::placeholder" in css
    assert ".bubbleAssistant {" in css
    assert ".bubbleUser {" in css
    assert "@media (max-width: 720px)" in css
    assert ".contactGateCard {" in css
    assert ".chatFooter {" in css
    assert "position: sticky;" in css


def test_frontend_env_keeps_only_public_api_base_and_no_openai_secret():
    env_example = project_file(".env.example").read_text()
    frontend_api = project_file("frontend/lib/api.ts").read_text()

    assert "NEXT_PUBLIC_API_BASE_URL" in env_example
    assert "NEXT_PUBLIC_OPENAI" not in env_example
    assert "NEXT_PUBLIC_API_BASE_URL" in frontend_api
    assert "OPENAI_API_KEY" not in frontend_api


def test_otp_dev_mode_is_explicit_in_config_and_provider():
    config_source = project_file("backend/app/core/config.py").read_text()
    provider_source = project_file("backend/app/services/phone_verification.py").read_text()

    assert 'alias="OTP_DEV_MODE"' in config_source
    assert 'alias="OTP_PROVIDER"' in config_source
    assert "if settings.otp_provider == \"dev\"" in provider_source
    assert "self.settings.otp_dev_mode and sent.provider == \"dev\"" in provider_source


def test_frontend_shows_done_only_when_server_explicitly_unlocks_result():
    source = project_file("frontend/app/page.tsx").read_text()

    assert 'apiState?.input_mode === "done" && apiState?.meta?.result_unlocked === true' in source
    assert "canShowUnlockedResult ? (" in source
    assert "function sanitizeAssistantMessage" in source
    assert "LOCKED_RESULT_MARKERS" in source
    assert "hasLockedResultLeak(response.assistant_message)" in source
    assert "Ваш результат уже собран." not in source
    assert 'const CONTACT_GATE_LOCKED_MESSAGE =\n  "Результат готов.";' in source


def test_frontend_contact_gate_card_uses_russian_copy_without_technical_marker():
    source = project_file("frontend/components/ContactGateCard.tsx").read_text()
    css = project_file("frontend/app/globals.css").read_text()

    assert "Результат готов" in source
    assert "Введите код из сообщения" in source
    assert "Получить код" in source
    assert "Подтвердить код" in source
    assert "CONTACT GATE ACTIVE 001" not in source
    assert "Паспорт тени готов" not in source
    assert 'onChange={(e) => onPhoneChange(e.target.value)}' in source
    assert "onBlur={onPhoneBlur}" in source
    assert ".contactCodeHint {" in css
    assert ".contactGateDiagnostic {" not in css


def test_mobile_css_prioritizes_chat_flow_and_touch_targets():
    css = project_file("frontend/app/globals.css").read_text()
    source = project_file("frontend/app/page.tsx").read_text()
    phone_source = project_file("frontend/lib/phone.ts").read_text()
    message_bubble = project_file("frontend/components/MessageBubble.tsx").read_text()

    assert 'const [isMobileFlow, setIsMobileFlow] = useState(false);' in source
    assert 'const [mobileFlowStarted, setMobileFlowStarted] = useState(false);' in source
    assert 'window.matchMedia("(max-width: 820px)")' in source
    assert 'const showMobileIntro = !mobileFlowStarted && Boolean(apiState) && isInteractiveStep(apiState);' in source
    assert 'className={`mobileShell${showMobileIntro ? " mobileShellIntro" : ""}`}' in source
    assert "Первый замер скрытой трещины" in source
    assert "примерно 7–10 минут" in source
    assert "В конце вы получите короткий и понятный результат." in source
    assert "Диагностика проходит пошагово, спокойно и без" in source
    assert 'className="mobileIntroCard"' in source
    assert 'className="mobileStepScreen"' in source
    assert 'className="mobileActionDock"' in source
    assert 'compact' in source
    assert ".mobileIntroCard {" in css
    assert ".mobileShellIntro {" in css
    assert ".mobileProgressHeader {" in css
    assert ".mobileStepCard {" in css
    assert ".mobileActionDock {" in css
    assert ".mobileBulletList {" in css
    assert ".mobileSectionLabel {" in css
    assert ".mobileSectionBlock {" in css
    assert "renderStructuredSection" in source
    assert "mobileStructuredBlock" in source
    assert "quoteForScreen" in source
    assert 'if (options?.resultMode)' in source
    assert "renderAssistantText" in message_bubble
    assert ".bubbleSectionBlock {" in css
    assert ".bubbleSectionLabel {" in css
    assert "formatRussianPhone" in source
    assert "validateRussianPhone" in source
    assert "normalizeRussianPhone" in phone_source
    assert "Укажи номер в формате +7 (999) 123-45-67" in phone_source
    assert ".sidebar {\n    position: static;\n    order: 2;" in css
    assert ".chatCard {\n    min-height: calc(100vh - 36px);\n    order: 1;" in css
    assert "scroll-padding-bottom: 140px;" in css
    assert "min-height: 72px;" in css
    assert "max-height: 34vh;" in css
    assert "padding: 12px 12px calc(12px + env(safe-area-inset-bottom));" in css


def test_phone_normalization_accepts_common_russian_formats_and_rejects_invalid():
    assert normalize_phone_number("+79991234567") == "+79991234567"
    assert normalize_phone_number("89991234567") == "+79991234567"
    assert normalize_phone_number("79991234567") == "+79991234567"
    assert normalize_phone_number("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone_number("8 (999) 123-45-67") == "+79991234567"

    try:
        normalize_phone_number("12345")
    except ValueError as exc:
        assert "Укажи номер в формате +7 (999) 123-45-67" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid phone")


def test_dream_step_phrase_handles_dative_life_answers_more_naturally():
    assert dream_step_phrase("К своей спокойной и видимой жизни") == "к своей спокойной и видимой жизни"


def test_frontend_phone_input_defers_formatting_until_blur():
    phone_source = project_file("frontend/lib/phone.ts").read_text()
    page_source = project_file("frontend/app/page.tsx").read_text()

    assert 'digits.length === 10' in phone_source
    assert 'return "";' in phone_source
    assert 'return (rawPhone || "").trim();' in phone_source
    assert "function handlePhoneBlur()" in page_source
    assert "setContactPhone((current) => formatRussianPhone(current));" in page_source


def test_frontend_restart_clears_old_session_token_and_creates_new_session():
    source = project_file("frontend/app/page.tsx").read_text()

    assert "function clearStoredAccessTokens()" in source
    assert "key?.startsWith(prefix)" in source
    assert "clearStoredAccessTokens();" in source
    assert "await initSession();" in source


def test_admin_frontend_pages_use_internal_session_list_and_detail_routes():
    list_page = project_file("frontend/app/admin/page.tsx").read_text()
    detail_page = project_file("frontend/app/admin/[sessionId]/page.tsx").read_text()
    api_source = project_file("frontend/lib/api.ts").read_text()
    types_source = project_file("frontend/lib/types.ts").read_text()

    assert "Прохождения «Тени дома»" in list_page
    assert "Статус прохождения" in list_page
    assert "Где остановился" in list_page
    assert "Выгрузить Excel" in list_page
    assert "Выгрузить CSV" in list_page
    assert "С телефоном, без подтверждения" in list_page
    assert "Подтвердил, но не открыл" in list_page
    assert "getAdminExportUrl" in list_page
    assert 'href={`/admin/${item.session_id}`}' in list_page
    assert "Детали записи" in detail_page
    assert "Текст, который увидел клиент" in detail_page
    assert "Технические детали" in detail_page
    assert "useParams" in detail_page
    assert "getAdminSessions" in api_source
    assert "getAdminSessionDetail" in api_source
    assert "AdminPeriod" in types_source
    assert "AdminSessionListResponse" in types_source
    assert "AdminSessionDetail" in types_source


def test_text_templates_are_neutral_and_mobile_friendly():
    shadows = project_file("backend/app/data/question_bank_v1_2.json").read_text()
    scenario_source = project_file("backend/app/services/scenario_engine.py").read_text()
    links_source = project_file("backend/app/data/shadow_links_v1_2.json").read_text()

    assert "Выбери вариант ниже." in scenario_source
    assert "Тень. {self.shadow_map[shadow_id]['shadow_name']}." in scenario_source
    assert "Паспорт тени" in scenario_source
    assert "ты отметил" not in scenario_source
    assert "Коротко оглянемся на все 10 теней" not in scenario_source
    assert "Мы прошли все 10 теней" not in scenario_source
    assert "secondary_note" not in links_source
    assert "Тень бесконечной подготовки" in links_source
    assert "Замирание перед шагом" in shadows
    assert "Жизнь в привычном" in shadows


def test_v1_2_question_bank_has_nine_route_shadows_and_no_shadow_10():
    import json

    shadows = json.loads(project_file("backend/app/data/question_bank_v1_2.json").read_text())
    ids = [shadow["shadow_id"] for shadow in shadows]

    assert ids == list(range(1, 10))
    assert 10 not in ids
    assert {shadow["level"] for shadow in shadows} == {1, 2, 3}
    assert all("main_question" in shadow and "branches" in shadow for shadow in shadows)


def test_env_keeps_local_cors_explicit_without_wildcard():
    env_example = project_file(".env.example").read_text()
    compose = project_file("docker-compose.yml").read_text()
    config = project_file("backend/app/core/config.py").read_text()

    assert "http://localhost:3000,http://127.0.0.1:3000" in env_example
    assert "http://localhost:3000,http://127.0.0.1:3000" in compose
    assert '"http://127.0.0.1:3000"' in config
    assert '"*"' not in compose
