from __future__ import annotations

from dataclasses import asdict
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO, StringIO
import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_session_or_404
from app.db.session import get_db
from app.models.session import PhoneVerification, SessionEvent, User, UserSession
from app.schemas.session import (
    AdminSessionDetailResponse,
    AdminSessionListResponse,
    AdminSessionSummary,
    AnalyticsOverview,
    ContactCodeRequest,
    ContactCodeResponse,
    ContactCodeVerify,
    ContactVerifyResponse,
    ResultResponse,
    SessionCreateResponse,
    SessionMessageResponse,
    SessionStateResponse,
    UserMessageCreate,
)
from app.services.phone_verification import PhoneVerificationService
from app.services.scenario_engine import ScenarioEngine

router = APIRouter()
PDF_TITLES = {
    "blueprint_sample": "Пример полного Чертежа дома",
    "shadow_tools": "10 главных инструментов борьбы с Тенями",
}
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BONUS_DOWNLOAD_EVENT = "bonus_file_downloaded"
BLUEPRINT_OPEN_EVENT = "blueprint_offer_opened"
NO_DATA = "нет данных"
ADMIN_TIMEZONE = timezone(timedelta(hours=5))
ADMIN_EXPORT_FIELDNAMES = [
    "Дата старта",
    "Последняя активность",
    "Имя",
    "Возраст",
    "Телефон",
    "Подтверждение номера",
    "Скачивал бонусный файл",
    "Скачивал чертеж",
    "Статус прохождения",
    "Где остановился",
    "Желаемая жизнь",
    "Паспорт / результат",
    "session_id",
]

ADMIN_FILTERS = {
    "all",
    "with_phone",
    "verified",
    "unlocked",
    "with_phone_unverified",
    "verified_locked",
}
PERIOD_FILTERS = {"today", "7d", "30d", "custom"}


def _admin_result_payload(session: UserSession) -> dict:
    result = session.result or {}
    pending = result.get("pending_result")
    if isinstance(pending, dict):
        return pending
    return result


def _load_json_data(filename: str):
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def _question_bank() -> list[dict]:
    return _load_json_data("question_bank_v1_2.json")


def _shadow_links() -> dict:
    return _load_json_data("shadow_links_v1_2.json")


def _expression_templates() -> dict:
    return _load_json_data("expression_templates_v1_2.json")


def _shadow_name_map() -> dict[int, str]:
    return {int(item["shadow_id"]): item["shadow_name"] for item in _question_bank()}


def _shadow_name(shadow_id: int | None) -> Optional[str]:
    if shadow_id is None:
        return None
    return _shadow_name_map().get(int(shadow_id))


def _admin_full_state(session: UserSession) -> dict:
    return session.state or {}


def _admin_session_meta(session: UserSession) -> dict:
    return _admin_full_state(session).get("session_meta", {}) or {}


def _admin_final_link(session: UserSession) -> dict:
    return _admin_full_state(session).get("final_link", {}) or {}


def _admin_passport(session: UserSession) -> dict:
    result = _admin_result_payload(session)
    state = _admin_full_state(session)
    return result.get("passport") or state.get("passport", {}) or {}


def _admin_link_key(session: UserSession) -> Optional[str]:
    final_link = _admin_final_link(session)
    return final_link.get("link_key") or (_admin_result_payload(session).get("link_key"))


def _has_passport(session: UserSession) -> bool:
    passport = _admin_passport(session)
    return bool(passport.get("title") or session.result_released_at or session.current_stage in {"passport", "offer", "completed"})


def _admin_v1_2_payload(session: UserSession) -> dict:
    state = _admin_full_state(session)
    meta = _admin_session_meta(session)
    final_link = _admin_final_link(session)
    behavior_id = final_link.get("behavior_shadow_id")
    personality_id = final_link.get("personality_shadow_id")
    root_id = final_link.get("root_shadow_id")
    link_key = _admin_link_key(session)
    links = _shadow_links()
    return {
        "mode": meta.get("mode") or "v1_2",
        "user_name": meta.get("user_name"),
        "user_age": meta.get("user_age"),
        "user_goal_text": meta.get("user_goal_text") or session.dream,
        "low_confidence": bool(meta.get("low_confidence")),
        "route_fallback": bool(meta.get("route_fallback")),
        "current_stage": session.current_stage,
        "level_1": state.get("level_1", {}),
        "level_2": state.get("level_2", {}),
        "level_3": state.get("level_3", {}),
        "depth_block": state.get("depth_block", {}),
        "final_link": {
            **final_link,
            "behavior_shadow_name": _shadow_name(behavior_id),
            "personality_shadow_name": _shadow_name(personality_id),
            "root_shadow_name": _shadow_name(root_id),
        },
        "link_key": link_key,
        "passport": _admin_passport(session),
        "shadow_link_template_found": bool(link_key and link_key in links),
        "question_bank_count": len(_question_bank()),
        "shadow_links_count": len(links),
        "expression_template_levels": list(_expression_templates().keys()),
    }


def _admin_display_name(session: UserSession) -> Optional[str]:
    meta = _admin_session_meta(session)
    return session.contact_name or (session.user.display_name if session.user else None) or meta.get("user_name")


def _admin_phone_number(session: UserSession) -> Optional[str]:
    return session.phone_number or (session.user.phone_number if session.user else None)


def _admin_phone_verified(session: UserSession) -> bool:
    return bool(session.phone_verified_at or (session.user and session.user.phone_verified))


def _admin_phone_verified_at(session: UserSession):
    return session.phone_verified_at or (session.user.phone_verified_at if session.user else None)


def _admin_bonus_downloaded(session: UserSession) -> bool:
    return any(event.event_type == BONUS_DOWNLOAD_EVENT for event in (session.events or []))


def _admin_blueprint_opened(session: UserSession) -> bool:
    return any(event.event_type == BLUEPRINT_OPEN_EVENT for event in (session.events or []))


def _format_admin_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return NO_DATA
    display_value = value.astimezone(ADMIN_TIMEZONE) if value.tzinfo else value.replace(tzinfo=timezone.utc).astimezone(ADMIN_TIMEZONE)
    return display_value.strftime("%d.%m.%Y %H:%M")


def _admin_session_state(session: UserSession) -> dict:
    return _admin_full_state(session)


def _admin_last_activity(session: UserSession) -> datetime:
    return session.updated_at or session.created_at


def _coerce_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _admin_status_label(session: UserSession) -> str:
    if session.current_stage in {"offer", "completed"} or session.result_released_at:
        return "Дошел до паспорта"
    if session.current_stage == "passport":
        return "Паспорт готов"
    if session.result_released_at:
        return "Завершил модуль"
    if session.phone_verified_at:
        return "Подтвердил номер"
    if session.phone_number and not session.phone_verified_at:
        return "Получил код, но не подтвердил"
    if session.current_stage == "contact_gate":
        return "Дошел до сохранения результата"
    v1_2_labels = {
        "intro": "Знакомство",
        "legend": "Легенда v1.2",
        "level_1": "Уровень 1: поведенческие тени",
        "checkpoint_1": "Переход к уровню 2",
        "level_2": "Уровень 2: личностная тень",
        "level_3": "Уровень 3: корневая тень",
        "checkpoint_2": "Переход к глубине",
        "depth_short": "Короткая глубина",
    }
    if session.current_stage in v1_2_labels:
        return v1_2_labels[session.current_stage]
    if session.current_stage == "intro_name":
        return "Остановился на имени"
    if session.current_stage == "intro_age":
        return "Остановился на возрасте"
    if session.current_stage == "dream":
        return "Остановился на желаемой жизни"
    if session.current_stage in {"shadow_choice", "shadow_followup", "shadow_bridge"}:
        shadow_id = session.current_shadow_id or (session.state or {}).get("current_shadow_idx", 0) + 1
        return f"Остановился на тени {shadow_id}"
    if session.current_stage == "reality_check":
        return "Остановился на проверке реальности"
    if session.current_stage == "body_block":
        return "Остановился на телесном блоке"
    if session.current_stage == "depth_block":
        return "Остановился на глубинном блоке"
    if session.current_stage == "contradiction_reflection":
        return "Остановился на выявлении противоречий"
    if session.current_stage == "completed":
        return "Открыл результат"
    return "Прохождение в работе"


def _admin_stopped_at_label(session: UserSession) -> str:
    if session.current_stage in {"offer", "completed"} or session.result_released_at:
        return "Паспорт тени"
    if session.current_stage == "passport":
        return "Кнопка «Забрать Паспорт»"
    if session.phone_verified_at:
        return "Результат подтвержден"
    if session.phone_number and not session.phone_verified_at:
        return "Подтверждение кода"
    if session.current_stage == "contact_gate":
        return "Сохранение результата"
    v1_2_labels = {
        "intro": "Имя / возраст / желаемая жизнь",
        "legend": "Объяснение 3 слоев",
        "level_1": f"Тень {session.current_shadow_id or '1-3'}",
        "checkpoint_1": "Выбор главной поведенческой тени",
        "level_2": "Одна личностная тень",
        "level_3": "Одна корневая тень",
        "checkpoint_2": "Связка теней",
        "depth_short": "3 вопроса глубины",
    }
    if session.current_stage in v1_2_labels:
        return v1_2_labels[session.current_stage]
    if session.current_stage == "intro_name":
        return "Шаг имени"
    if session.current_stage == "intro_age":
        return "Шаг возраста"
    if session.current_stage == "dream":
        return "Контур желаемой жизни"
    if session.current_stage in {"shadow_choice", "shadow_followup", "shadow_bridge"}:
        shadow_id = session.current_shadow_id or (session.state or {}).get("current_shadow_idx", 0) + 1
        return f"Тень {shadow_id}"
    if session.current_stage == "reality_check":
        return "Проверка реальности"
    if session.current_stage == "body_block":
        return "Телесный блок"
    if session.current_stage == "depth_block":
        return "Блок глубины"
    if session.current_stage == "contradiction_reflection":
        return "Выявление противоречий"
    return session.current_stage


def _client_text(result: dict) -> Optional[str]:
    return result.get("full_text") or result.get("passport_text")


def _internal_addendum(result: dict) -> Optional[str]:
    offer_text = result.get("offer_text")
    client_text = _client_text(result) or ""
    if offer_text and offer_text.strip() and offer_text.strip() not in client_text:
        return offer_text
    return None


def _period_bounds(period: str, start_date: Optional[str], end_date: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    if period not in PERIOD_FILTERS:
        raise HTTPException(status_code=400, detail="Unknown period filter")

    def local_bound_to_utc_naive(local_value: datetime) -> datetime:
        return local_value.replace(tzinfo=ADMIN_TIMEZONE).astimezone(timezone.utc).replace(tzinfo=None)

    now_local = datetime.now(ADMIN_TIMEZONE)
    if period == "today":
        start = local_bound_to_utc_naive(datetime.combine(now_local.date(), time.min))
        end = local_bound_to_utc_naive(datetime.combine(now_local.date(), time.max))
        return start, end
    if period == "7d":
        return local_bound_to_utc_naive(now_local - timedelta(days=7)), local_bound_to_utc_naive(now_local)
    if period == "30d":
        return local_bound_to_utc_naive(now_local - timedelta(days=30)), local_bound_to_utc_naive(now_local)
    if not start_date and not end_date:
        return None, None

    start = None
    end = None
    if start_date:
        parsed_start = date.fromisoformat(start_date)
        start = local_bound_to_utc_naive(datetime.combine(parsed_start, time.min))
    if end_date:
        parsed_end = date.fromisoformat(end_date)
        end = local_bound_to_utc_naive(datetime.combine(parsed_end, time.max))
    return start, end


def _load_admin_sessions(
    db: Session,
    filter_by: str,
    period: str,
    search: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> list[UserSession]:
    if filter_by not in ADMIN_FILTERS:
        raise HTTPException(status_code=400, detail="Unknown admin filter")

    query = (
        select(UserSession)
        .options(joinedload(UserSession.user), selectinload(UserSession.events))
        .order_by(UserSession.created_at.desc())
    )
    sessions = list(db.scalars(query).all())

    start_bound, end_bound = _period_bounds(period, start_date, end_date)
    if start_bound:
        sessions = [session for session in sessions if _coerce_naive(session.created_at) and _coerce_naive(session.created_at) >= start_bound]
    if end_bound:
        sessions = [session for session in sessions if _coerce_naive(session.created_at) and _coerce_naive(session.created_at) <= end_bound]

    if filter_by == "with_phone":
        sessions = [session for session in sessions if _admin_phone_number(session)]
    elif filter_by == "verified":
        sessions = [session for session in sessions if _admin_phone_verified(session)]
    elif filter_by == "unlocked":
        sessions = [session for session in sessions if session.result_released_at is not None]
    elif filter_by == "with_phone_unverified":
        sessions = [session for session in sessions if _admin_phone_number(session) and not _admin_phone_verified(session)]
    elif filter_by == "verified_locked":
        sessions = [session for session in sessions if _admin_phone_verified(session) and session.result_released_at is None]

    if search:
        needle = search.lower().strip()
        sessions = [
            session for session in sessions
            if needle in (session.id or "").lower()
            or needle in (_admin_display_name(session) or "").lower()
            or needle in (_admin_phone_number(session) or "").lower()
        ]

    return sessions


def _summary_metrics(sessions: list[UserSession]) -> dict:
    passport_counter: Counter[str] = Counter()
    behavior_counter: Counter[str] = Counter()
    personality_counter: Counter[str] = Counter()
    root_counter: Counter[str] = Counter()
    route_counter: Counter[str] = Counter()
    for session in sessions:
        passport = _admin_passport(session)
        if passport.get("title"):
            passport_counter.update([passport["title"]])
        final_link = _admin_final_link(session)
        behavior = _shadow_name(final_link.get("behavior_shadow_id"))
        personality = _shadow_name(final_link.get("personality_shadow_id"))
        root = _shadow_name(final_link.get("root_shadow_id"))
        if behavior:
            behavior_counter.update([behavior])
        if personality:
            personality_counter.update([personality])
        if root:
            root_counter.update([root])
        link_key = _admin_link_key(session)
        if link_key:
            route_counter.update([link_key])
    total = len(sessions)
    reached_passport = sum(1 for session in sessions if _has_passport(session))
    # Паспорт является финалом сценария, поэтому "завершено" считаем
    # тем же набором сессий, что и "дошли до паспорта".
    completed = reached_passport
    conversion = round((reached_passport / total) * 100, 1) if total else 0.0
    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "reached_passport": reached_passport,
        "passport_conversion_percent": conversion,
        "top_passports": passport_counter.most_common(5),
        "top_behavior_shadows": behavior_counter.most_common(5),
        "top_personality_shadows": personality_counter.most_common(5),
        "top_root_shadows": root_counter.most_common(5),
        "top_routes": route_counter.most_common(5),
    }


def _admin_summary(session: UserSession) -> AdminSessionSummary:
    result = _admin_result_payload(session)
    meta = _admin_session_meta(session)
    final_link = _admin_final_link(session)
    passport = _admin_passport(session)
    return AdminSessionSummary(
        session_id=session.id,
        created_at=session.created_at,
        last_activity_at=_admin_last_activity(session),
        display_name=_admin_display_name(session),
        phone_number=_admin_phone_number(session),
        current_stage=session.current_stage,
        status_label=_admin_status_label(session),
        stopped_at_label=_admin_stopped_at_label(session),
        status=session.status,
        phone_verified=_admin_phone_verified(session),
        result_unlocked=session.result_released_at is not None,
        bonus_downloaded=_admin_bonus_downloaded(session),
        blueprint_downloaded=_admin_blueprint_opened(session),
        top_shadow_names=result.get("top_shadow_names", []) or ([passport.get("title")] if passport.get("title") else []),
        user_age=meta.get("user_age"),
        dream=meta.get("user_goal_text") or session.dream,
        passport_title=passport.get("title"),
        behavior_shadow_name=_shadow_name(final_link.get("behavior_shadow_id")),
        personality_shadow_name=_shadow_name(final_link.get("personality_shadow_id")),
        root_shadow_name=_shadow_name(final_link.get("root_shadow_id")),
        link_key=_admin_link_key(session),
    )


def _admin_detail(session: UserSession) -> AdminSessionDetailResponse:
    result = _admin_result_payload(session)
    meta = _admin_session_meta(session)
    passport = _admin_passport(session)
    return AdminSessionDetailResponse(
        session_id=session.id,
        created_at=session.created_at,
        last_activity_at=_admin_last_activity(session),
        updated_at=session.updated_at,
        completed_at=session.completed_at,
        display_name=_admin_display_name(session),
        phone_number=_admin_phone_number(session),
        current_stage=session.current_stage,
        status_label=_admin_status_label(session),
        stopped_at_label=_admin_stopped_at_label(session),
        status=session.status,
        dream=meta.get("user_goal_text") or session.dream,
        user_age=meta.get("user_age"),
        user_goal_text=meta.get("user_goal_text") or session.dream,
        phone_verified=_admin_phone_verified(session),
        phone_verified_at=_admin_phone_verified_at(session),
        result_unlocked=session.result_released_at is not None,
        result_released_at=session.result_released_at,
        bonus_downloaded=_admin_bonus_downloaded(session),
        blueprint_downloaded=_admin_blueprint_opened(session),
        top_shadow_names=result.get("top_shadow_names", []) or ([passport.get("title")] if passport.get("title") else []),
        client_text=_client_text(result),
        internal_addendum=_internal_addendum(result),
        result_summary=result.get("screen_phrase") or result.get("manifestation"),
        mechanism_formula=result.get("mechanism_formula"),
        manifestation=result.get("manifestation"),
        price=result.get("price"),
        hidden_resource=result.get("hidden_resource"),
        screen_phrase=result.get("screen_phrase"),
        micro_permission=result.get("micro_permission"),
        session_state=_admin_session_state(session),
        v1_2=_admin_v1_2_payload(session),
    )


def _text_or_no_data(value: object) -> str:
    if value is None:
        return NO_DATA
    if isinstance(value, str):
        return value.strip() or NO_DATA
    if isinstance(value, (int, float)):
        return str(value)
    return NO_DATA


def _admin_passport_rows(session: UserSession) -> list[tuple[str, str]]:
    result = _admin_result_payload(session)
    passport = _admin_passport(session)
    final_link = _admin_final_link(session)
    meta = _admin_session_meta(session)
    top_shadow_names = result.get("top_shadow_names", []) or ([passport.get("title")] if passport.get("title") else [])
    main_shadow = passport.get("title") or (top_shadow_names[0] if top_shadow_names else None)

    return [
        ("Паспорт тени", _text_or_no_data(_client_text(result))),
        ("Твоя главная тень сейчас", _text_or_no_data(main_shadow)),
        ("Итоговая тень", _text_or_no_data(passport.get("title") or main_shadow)),
        ("Вторая тень", _text_or_no_data(final_link.get("personality_shadow_name") or _shadow_name(final_link.get("personality_shadow_id")))),
        ("Формула механизма", _text_or_no_data(passport.get("formula_mechanism") or result.get("mechanism_formula"))),
        ("Архитектура", _text_or_no_data(passport.get("architecture"))),
        ("Что происходит внутри", _text_or_no_data(passport.get("inner_mechanism") or result.get("manifestation"))),
        ("Где это проявляется сильнее всего", _text_or_no_data(passport.get("main_sphere") or meta.get("user_goal_text") or session.dream)),
        ("От чего защищает", _text_or_no_data(passport.get("main_protection"))),
        ("Цена защиты", _text_or_no_data(passport.get("main_price") or result.get("price"))),
        ("Твой скрытый ресурс", _text_or_no_data(passport.get("hidden_resource") or result.get("hidden_resource"))),
        ("Фраза, которую можно сохранить", _text_or_no_data(passport.get("save_phrase") or result.get("screen_phrase"))),
        ("Микро-разрешение", _text_or_no_data(passport.get("micro_permission") or result.get("micro_permission"))),
        ("Вопрос на вырост", _text_or_no_data(result.get("screen_phrase") or result.get("manifestation"))),
        ("Финальный текст про Чертеж дома", "Сейчас ты увидел(а) важную вещь.\nНе «проблему». А механизм.\nИ он уже не будет развидеться.\n\nДальше можно разобрать не только «где ломается», а всю конструкцию: где ты сейчас, куда на самом деле хочешь, на что можешь опереться и как из этого собирается путь.\n\nЭто и есть:\n«Чертеж дома»\n\nПерсональная карта с личным проектом твоего ДОМА."),
    ]


def _admin_passport_text(session: UserSession) -> str:
    return "\n\n".join(f"{label}:\n{value}" for label, value in _admin_passport_rows(session))


def _admin_result_print_html(session: UserSession) -> str:
    display_name = _admin_display_name(session) or "Клиент"
    fields = [
        ("Дата старта", _format_admin_datetime(session.created_at)),
        ("Последняя активность", _format_admin_datetime(_admin_last_activity(session))),
        ("session_id", session.id),
        ("Имя", display_name),
        ("Возраст", _text_or_no_data(_admin_session_meta(session).get("user_age"))),
        ("Телефон", _admin_phone_number(session) or NO_DATA),
        ("Подтвержден ли номер", "Да" if _admin_phone_verified(session) else "Нет"),
        ("Скачивал ли бонусный файл", "Да" if _admin_bonus_downloaded(session) else "Нет"),
        ("Скачивал ли чертеж", "Да" if _admin_blueprint_opened(session) else "Нет"),
        ("Статус прохождения", _admin_status_label(session)),
        ("Где остановился", _admin_stopped_at_label(session)),
        ("Желаемая жизнь", _admin_session_meta(session).get("user_goal_text") or session.dream or NO_DATA),
    ]
    passport_rows = _admin_passport_rows(session)
    fields_html = "".join(
        f"<div class='item'><dt>{escape(label)}</dt><dd>{escape(str(value)).replace(chr(10), '<br>')}</dd></div>"
        for label, value in fields
    )
    passport_html = "".join(
        f"<div class='item'><dt>{escape(label)}</dt><dd>{escape(value).replace(chr(10), '<br>')}</dd></div>"
        for label, value in passport_rows
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Результат клиента — {escape(display_name)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin: 0; font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; color: #202124; background: #f6f7f9; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
    .panel {{ background: #fff; border: 1px solid #d8dee6; border-radius: 14px; padding: 18px; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 4px; font-size: 26px; }}
    h2 {{ margin: 0 0 12px; font-size: 22px; }}
    .meta {{ color: #5f6368; margin-bottom: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px 14px; }}
    .item {{ border: 1px solid #eceff3; border-radius: 10px; padding: 10px 12px; }}
    dt {{ font-weight: 600; color: #3c4043; }}
    dd {{ margin: 4px 0 0; white-space: pre-wrap; }}
    .actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }}
    .btn {{ border: 1px solid #b6bec8; border-radius: 999px; padding: 10px 14px; background: #fff; color: #1f2937; text-decoration: none; cursor: pointer; font-size: 14px; }}
    @media print {{
      body {{ background: #fff; }}
      .wrap {{ max-width: 100%; padding: 0; }}
      .actions {{ display: none; }}
      .panel {{ border: 0; padding: 0; margin: 0 0 18px; }}
      .item {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="actions">
      <button class="btn" type="button" onclick="window.print()">Сохранить как PDF</button>
    </div>
    <section class="panel">
      <h1>Карточка клиента</h1>
      <div class="meta">Результат без технических полей и JSON.</div>
      <dl class="grid">{fields_html}</dl>
    </section>
    <section class="panel">
      <h2>Паспорт тени</h2>
      <dl class="grid">{passport_html}</dl>
    </section>
  </div>
</body>
</html>"""


def _export_rows(sessions: list[UserSession]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for session in sessions:
        meta = _admin_session_meta(session)
        rows.append({
            "Дата старта": _format_admin_datetime(session.created_at),
            "Последняя активность": _format_admin_datetime(_admin_last_activity(session)),
            "Имя": _admin_display_name(session) or NO_DATA,
            "Возраст": _text_or_no_data(meta.get("user_age")),
            "Телефон": _admin_phone_number(session) or NO_DATA,
            "Подтверждение номера": "Да" if _admin_phone_verified(session) else "Нет",
            "Скачивал бонусный файл": "Да" if _admin_bonus_downloaded(session) else "Нет",
            "Скачивал чертеж": "Да" if _admin_blueprint_opened(session) else "Нет",
            "Статус прохождения": _admin_status_label(session),
            "Где остановился": _admin_stopped_at_label(session),
            "Желаемая жизнь": meta.get("user_goal_text") or session.dream or NO_DATA,
            "Паспорт / результат": _admin_passport_text(session),
            "session_id": session.id,
        })
    return rows


def _export_explanations() -> list[tuple[str, str]]:
    return [
        ("Статус прохождения", "Человеческий статус: на каком уровне пользователь завершил или остановил путь."),
        ("Результат открыт", "Да — пользователь подтвердил номер и дошел до финального экрана результата."),
        ("Итоговая тень", "Тень с самым сильным вкладом в итоговую картину по текущей сессии."),
        ("Формула механизма", "Короткая формула, как желание, защита и торможение связываются между собой."),
        ("Текст, который увидел клиент", "Финальный текст, который реально был показан пользователю после подтверждения."),
        ("Внутреннее дополнение", "Дополнительный хвост для владельца, если в данных есть текст вне клиентского финального блока."),
    ]


def _xlsx_column_name(index: int) -> str:
    name = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=0):
            cell_ref = f"{_xlsx_column_name(col_index)}{row_index}"
            safe_value = escape(str(value or ""))
            cells.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{safe_value}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def _build_xlsx(sheet_map: list[tuple[str, list[list[str]]]]) -> bytes:
    workbook_rels = []
    workbook_sheets = []
    content_overrides = []
    worksheet_xml = {}

    for index, (sheet_name, rows) in enumerate(sheet_map, start=1):
        workbook_rels.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        workbook_sheets.append(
            f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        content_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        worksheet_xml[f"xl/worksheets/sheet{index}.xml"] = _xlsx_sheet_xml(rows)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f'{"".join(content_overrides)}'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets>'
        "</workbook>"
    )
    workbook_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(workbook_rels)}'
        "</Relationships>"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        for path, xml in worksheet_xml.items():
            archive.writestr(path, xml)
    return buffer.getvalue()


def _pdf_text_document(title: str, text: str) -> bytes:
    lines: list[str] = [title, ""]
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            next_value = f"{current} {word}".strip()
            if len(next_value) > 74 and current:
                lines.append(current)
                current = word
            else:
                current = next_value
        if current:
            lines.append(current)

    pages = [lines[index:index + 34] for index in range(0, len(lines), 34)] or [[title]]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{3 + index * 2} 0 R' for index in range(len(pages)))}] /Count {len(pages)} >>".encode("ascii"),
    ]
    for page_index, page_lines in enumerate(pages):
        page_object_id = 3 + page_index * 2
        content_object_id = page_object_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> /Contents {content_object_id} 0 R >>".encode("ascii")
        )
        content_parts = ["BT /F1 11 Tf 52 760 Td 14 TL"]
        for line_index, line in enumerate(page_lines):
            safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            hex_text = ("FEFF" + safe_line.encode("utf-16-be").hex()).upper()
            if line_index:
                content_parts.append("T*")
            content_parts.append(f"<{hex_text}> Tj")
        content_parts.append("ET")
        content = "\n".join(content_parts)
        objects.append(f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


@router.get("/health")
def healthcheck():
    return {"ok": True}


def _pdf_placeholder(title: str) -> bytes:
    text = f"{title}\n\nВременная PDF-заглушка. Полноценный дизайнерский файл можно заменить позже."
    hex_text = ("FEFF" + text.encode("utf-16-be").hex()).upper()
    content = f"BT /F1 22 Tf 72 720 Td <{hex_text}> Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream".encode("latin-1"),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


@router.get("/pdf/{pdf_type}")
def download_pdf(pdf_type: str):
    title = PDF_TITLES.get(pdf_type)
    if not title:
        raise HTTPException(status_code=404, detail="Unknown PDF type")

    pdf_path = Path(__file__).resolve().parents[2] / "data" / "pdfs" / f"{pdf_type}.pdf"
    if pdf_path.exists():
        data = pdf_path.read_bytes()
    else:
        data = _pdf_placeholder(title)

    filename = f"{pdf_type}.pdf"
    return StreamingResponse(
        BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(db: Session = Depends(get_db)):
    engine = ScenarioEngine(db)
    return engine.create_session()


@router.post("/sessions/{session_id}/reset", response_model=SessionCreateResponse)
def reset_session(session: UserSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    session.status = "reset"
    session.current_stage = "completed"
    session.current_shadow_id = None
    session.result_released_at = None
    session.access_token_hash = None
    session.phone_verified_at = None
    db.add(session)
    engine = ScenarioEngine(db)
    return engine.create_session()


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session_state(session: UserSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    engine = ScenarioEngine(db)
    return engine.get_session_state(session)


@router.post("/sessions/{session_id}/messages", response_model=SessionMessageResponse)
def create_message(
    payload: UserMessageCreate,
    session: UserSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
):
    engine = ScenarioEngine(db)
    return engine.handle_message(session=session, text=payload.text, choice=payload.choice)


@router.post("/sessions/{session_id}/bonus-download")
def record_bonus_download(session: UserSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    already_recorded = any(event.event_type == BONUS_DOWNLOAD_EVENT for event in (session.events or []))
    if not already_recorded:
        db.add(SessionEvent(session_id=session.id, event_type=BONUS_DOWNLOAD_EVENT, payload={"file": "checklist-shadow.pdf"}))
        db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/blueprint-open")
def record_blueprint_open(session: UserSession = Depends(get_session_or_404), db: Session = Depends(get_db)):
    already_recorded = any(event.event_type == BLUEPRINT_OPEN_EVENT for event in (session.events or []))
    if not already_recorded:
        db.add(SessionEvent(session_id=session.id, event_type=BLUEPRINT_OPEN_EVENT, payload={"file": "blueprint-offer.pdf"}))
        db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/result", response_model=ResultResponse)
def get_result_authorized(
    session: UserSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
    x_session_access_token: Optional[str] = Header(default=None),
):
    engine = ScenarioEngine(db)
    verification_service = PhoneVerificationService(db)
    verification_service.validate_result_access(session, x_session_access_token)
    try:
        return engine.get_result(session)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/contact/request-code", response_model=ContactCodeResponse)
def request_contact_code(
    payload: ContactCodeRequest,
    session: UserSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
):
    service = PhoneVerificationService(db)
    return service.request_code(session, payload.display_name, payload.phone_number)


@router.post("/sessions/{session_id}/contact/verify-code", response_model=ContactVerifyResponse)
def verify_contact_code(
    payload: ContactCodeVerify,
    session: UserSession = Depends(get_session_or_404),
    db: Session = Depends(get_db),
):
    service = PhoneVerificationService(db)
    verified_session, access_token = service.verify_code(session, payload.phone_number, payload.code)
    engine = ScenarioEngine(db)
    response = SessionMessageResponse.model_validate(asdict(engine.complete_contact_gate(verified_session)))
    return ContactVerifyResponse(session_id=verified_session.id, access_token=access_token, response=response)


@router.get("/admin/sessions", response_model=AdminSessionListResponse)
def admin_sessions(
    filter_by: str = Query(default="all", alias="filter"),
    period: str = Query(default="30d"),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    sessions = _load_admin_sessions(db, filter_by, period, search, start_date, end_date)
    return AdminSessionListResponse(
        filter=filter_by,
        total_count=len(sessions),
        items=[_admin_summary(session) for session in sessions],
        analytics=_summary_metrics(sessions),
    )


@router.get("/admin/sessions/{session_id}", response_model=AdminSessionDetailResponse)
def admin_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user), selectinload(UserSession.events))
        .where(UserSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _admin_detail(session)


@router.get("/admin/sessions/{session_id}/result.pdf")
def admin_session_result_pdf(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user), selectinload(UserSession.events))
        .where(UserSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    title = f"Паспорт клиента — {_admin_display_name(session) or session.id}"
    data = _pdf_text_document(title, _admin_passport_text(session))
    return StreamingResponse(
        BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="shadow-house-result-{session.id}.pdf"'},
    )


@router.get("/admin/sessions/{session_id}/result-print")
def admin_session_result_print(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user), selectinload(UserSession.events))
        .where(UserSession.id == session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    html = _admin_result_print_html(session)
    return StreamingResponse(
        iter([html.encode("utf-8")]),
        media_type="text/html; charset=utf-8",
    )


@router.get("/admin/export.csv")
def admin_export_csv(
    filter_by: str = Query(default="all", alias="filter"),
    period: str = Query(default="30d"),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    sessions = _load_admin_sessions(db, filter_by, period, search, start_date, end_date)
    rows = _export_rows(sessions)
    buffer = StringIO()
    fieldnames = ADMIN_EXPORT_FIELDNAMES
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="shadow-house-admin.csv"'},
    )


@router.get("/admin/export.xlsx")
def admin_export_xlsx(
    filter_by: str = Query(default="all", alias="filter"),
    period: str = Query(default="30d"),
    search: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    sessions = _load_admin_sessions(db, filter_by, period, search, start_date, end_date)
    rows = _export_rows(sessions)
    fieldnames = ADMIN_EXPORT_FIELDNAMES
    workbook_bytes = _build_xlsx([
        ("Прохождения", [fieldnames, *[[row.get(field, "") for field in fieldnames] for row in rows]]),
    ])
    return StreamingResponse(
        iter([workbook_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="shadow-house-admin.xlsx"'},
    )


@router.get("/analytics/overview", response_model=AnalyticsOverview)
def analytics_overview(db: Session = Depends(get_db)):
    total_sessions = db.scalar(select(func.count(UserSession.id))) or 0
    completed_sessions = db.scalar(select(func.count(UserSession.id)).where(UserSession.status == "completed")) or 0
    avg_messages_per_session = db.scalar(select(func.avg(UserSession.message_count))) or 0.0
    verified_users = db.scalar(select(func.count(User.id)).where(User.phone_verified.is_(True))) or 0
    pending_verifications = db.scalar(
        select(func.count(PhoneVerification.id)).where(PhoneVerification.status == "pending")
    ) or 0

    top_dropoff_stage = db.execute(
        select(UserSession.current_stage, func.count(UserSession.id))
        .where(UserSession.status != "completed")
        .group_by(UserSession.current_stage)
        .order_by(func.count(UserSession.id).desc())
        .limit(1)
    ).first()

    return AnalyticsOverview(
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        completion_rate=(completed_sessions / total_sessions) if total_sessions else 0.0,
        avg_messages_per_session=float(avg_messages_per_session or 0.0),
        top_dropoff_stage=top_dropoff_stage[0] if top_dropoff_stage else None,
        verified_users=int(verified_users),
        pending_verifications=int(pending_verifications),
    )
