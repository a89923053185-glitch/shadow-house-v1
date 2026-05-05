from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.session import SessionEvent, UserSession
from app.services.v1_2_logic import (
    DEPTH_ORDER,
    DEPTH_QUESTIONS,
    STAGES,
    assemble_passport,
    base_root_for,
    calculate_shadow_score,
    choose_root,
    default_state,
    expression_template,
    load_question_bank,
    next_root_candidate,
    normalize_depth_answer,
    route_level_2,
    select_level_1_main,
    shadow_map,
)
from app.utils.language import normalize_user_name, parse_user_age


@dataclass
class EngineResponse:
    session_id: str
    status: str
    assistant_message: str
    input_mode: str
    choices: list[dict[str, str]]
    progress: dict[str, Any]
    meta: dict[str, Any]


class ScenarioEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.shadows = load_question_bank()
        self.shadow_map = shadow_map()

    def create_session(self) -> EngineResponse:
        session = UserSession(status="active", current_stage="intro", state={}, result={}, current_shadow_id=None)
        self.db.add(session)
        self.db.flush()
        session.state = default_state(session.id, self._now())
        self._sync_system_state(session)
        self.db.add(session)
        self._log(session.id, "session_created", {"mode": "v1_2", "stage": "intro"})
        self.db.commit()
        self.db.refresh(session)
        return self._response(session, self._intro_message(), "text", meta={"mode": "v1_2"})

    def get_session_state(self, session: UserSession) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "status": session.status,
            "current_stage": session.current_stage,
            "dream": session.dream,
            "user_name": (session.state or {}).get("session_meta", {}).get("user_name") or None,
            "user_age": (session.state or {}).get("session_meta", {}).get("user_age"),
            "contact_name": session.contact_name,
            "phone_number": session.phone_number,
            "phone_verified": bool(session.phone_verified_at),
            "result_unlocked": bool(session.result_released_at),
            "progress": self._progress(session.current_stage, session.current_shadow_id),
            "state": session.state or {},
            "result": session.result or {},
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def get_result(self, session: UserSession) -> dict[str, Any]:
        if not session.result_released_at:
            raise ValueError("Result is locked until phone verification is completed")
        return {"session_id": session.id, "status": session.status, "result": session.result}

    def handle_message(self, session: UserSession, text: str | None = None, choice: str | None = None) -> EngineResponse:
        state = deepcopy(session.state) if session.state else default_state(session.id, self._now())
        stage = session.current_stage
        if stage not in STAGES and stage != "completed":
            raise ValueError(f"Unknown stage: {stage}")
        if stage == "completed":
            return self._response(session, "Сессия уже завершена. Паспорт тени и оффер уже собраны.", "done", meta={"result_unlocked": True})
        if stage == "intro":
            return self._handle_intro(session, state, text)
        if stage == "legend":
            return self._enter_level_1(session, state)
        if stage in {"level_1", "level_2", "level_3"}:
            return self._handle_shadow_answer(session, state, choice)
        if stage == "checkpoint_1":
            return self._enter_level_2(session, state)
        if stage == "checkpoint_2":
            return self._enter_depth(session, state)
        if stage == "depth_short":
            return self._handle_depth(session, state, choice, text)
        if stage == "passport":
            return self._show_passport_and_offer(session, state)
        if stage == "offer":
            return self._complete(session, state)
        raise ValueError(f"Unknown stage: {stage}")

    def complete_contact_gate(self, session: UserSession) -> EngineResponse:
        state = deepcopy(session.state) if session.state else default_state(session.id, self._now())
        return self._complete(session, state)

    def _handle_intro(self, session: UserSession, state: dict[str, Any], text: str | None) -> EngineResponse:
        substage = state["system_state"].get("current_question_type") or "ask_name"

        if substage == "ask_name":
            user_name = normalize_user_name(text)
            if len(user_name) < 2:
                return self._response(session, self._intro_message(), "text", meta={"intro_substage": "ask_name"})
            state["session_meta"]["user_name"] = user_name
            state["system_state"]["current_question_type"] = "ask_age"
            session.message_count += 1
            session.state = state
            self._sync_system_state(session)
            self.db.add(session)
            self._log(session.id, "name_captured", {"user_name": user_name})
            self.db.commit()
            return self._response(session, self._age_prompt(user_name), "text", meta={"intro_substage": "ask_age"})

        if substage == "ask_age":
            age = parse_user_age(text)
            user_name = state["session_meta"].get("user_name") or "тебя"
            if age is None:
                return self._response(session, self._age_prompt(user_name), "text", meta={"intro_substage": "ask_age"})
            state["session_meta"]["user_age"] = age
            state["system_state"]["current_question_type"] = "ask_goal"
            session.message_count += 1
            session.state = state
            self._sync_system_state(session)
            self.db.add(session)
            self._log(session.id, "age_captured", {"user_age": age})
            self.db.commit()
            return self._response(session, self._first_measure_message(user_name), "text", meta={"intro_substage": "ask_goal"})

        goal = (text or "").strip()
        if len(goal) < 3:
            user_name = state["session_meta"].get("user_name") or "тебя"
            return self._response(session, self._first_measure_message(user_name), "text", meta={"intro_substage": "ask_goal"})
        state["session_meta"]["user_goal_text"] = goal
        state["system_state"]["current_question_type"] = None
        session.dream = goal
        session.message_count += 1
        session.current_stage = "legend"
        session.state = state
        self._sync_system_state(session)
        self.db.add(session)
        self._log(session.id, "goal_captured", {"goal": goal})
        self.db.commit()
        return self._response(session, self._legend_message(), "choices", choices=[{"key": "go", "label": "Готов(а), поехали"}])

    def _enter_level_1(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        session.current_stage = "level_1"
        return self._ask_shadow_question(session, state, 1, "main_answer", self._level_1_intro())

    def _handle_shadow_answer(self, session: UserSession, state: dict[str, Any], choice: str | None) -> EngineResponse:
        question_type = state["system_state"]["current_question_type"]
        shadow_id = state["system_state"]["current_shadow_id"]
        if not choice:
            return self._ask_shadow_question(session, state, shadow_id, question_type, "Выбери вариант ниже.")
        question = self._question_for(shadow_id, question_type, state["system_state"].get("current_branch"))
        if choice not in question["answers"]:
            return self._ask_shadow_question(session, state, shadow_id, question_type, "Выбери один из вариантов ниже.")

        if question_type == "main_answer":
            branch = choice
            self._write_shadow_answer(state, session.current_stage, shadow_id, "main_answer", choice)
            self._write_shadow_answer(state, session.current_stage, shadow_id, "branch", branch)
            state["system_state"]["current_branch"] = branch
            next_type = "fact_check" if branch == "В" else "emotion_answer"
            return self._ask_shadow_question(session, state, shadow_id, next_type)

        self._write_shadow_answer(state, session.current_stage, shadow_id, question_type, choice)
        next_type = self._next_question_type(shadow_id, state["system_state"]["current_branch"], question_type)
        if next_type:
            return self._ask_shadow_question(session, state, shadow_id, next_type)
        return self._finish_shadow(session, state, shadow_id)

    def _finish_shadow(self, session: UserSession, state: dict[str, Any], shadow_id: int) -> EngineResponse:
        stage = session.current_stage
        level = self.shadow_map[shadow_id]["level"]
        shadow_state = self._shadow_state(state, stage, shadow_id)
        score, score_type, expr = calculate_shadow_score(shadow_state)
        shadow_state["score"] = score
        shadow_state["score_type"] = score_type
        shadow_state["expression_level"] = expr
        shadow_state["route_context"]["hypothesis_answer"] = shadow_state.get("hypothesis_answer")

        if stage == "level_1":
            next_id = shadow_id + 1
            if next_id <= 3:
                return self._ask_shadow_question(session, state, next_id, "main_answer", self._transition_to_shadow(next_id))
            main_id, low = select_level_1_main(state["level_1"])
            state["session_meta"]["low_confidence"] = state["session_meta"]["low_confidence"] or low
            target, route_fallback = route_level_2(state["level_1"])
            state["level_2"]["checked_shadow_id"] = target
            state["level_2"]["main_shadow_id"] = target
            if route_fallback:
                state["session_meta"]["route_fallback"] = True
            session.current_stage = "checkpoint_1"
            session.current_shadow_id = None
            session.state = state
            self._sync_system_state(session)
            self.db.add(session)
            self.db.commit()
            main_shadow = self.shadow_map[main_id]
            return self._response(
                session,
                self._checkpoint_1_message(main_shadow["shadow_name"], expression_template(main_id, 1, state["level_1"][f"shadow_{main_id}"]["expression_level"])),
                "choices",
                choices=[{"key": "go", "label": "Перейти к уровню 2"}],
                meta={"main_shadow_id": main_id, "route_to": target},
            )

        if stage == "level_2":
            state["level_2"]["score"] = score
            state["level_2"]["expression_level"] = expr
            state["level_3"]["checked_shadow_id"] = base_root_for(shadow_id)
            state["level_3"]["main_shadow_id"] = base_root_for(shadow_id)
            session.current_stage = "level_3"
            return self._ask_shadow_question(session, state, base_root_for(shadow_id), "main_answer", self._level_3_checkpoint_message(shadow_id, expr))

        checked = state.setdefault("level_3_checks", {})
        checked[shadow_id] = deepcopy(shadow_state)
        root_id, low, done = choose_root(state["level_2"]["main_shadow_id"], checked)
        if done:
            state["level_3"]["checked_shadow_id"] = shadow_id
            state["level_3"]["main_shadow_id"] = root_id
            selected = checked[root_id]
            state["level_3"]["score"] = selected["score"]
            state["level_3"]["expression_level"] = selected["expression_level"]
            state["level_3"]["answers"] = {key: selected.get(key) for key in state["level_3"]["answers"]}
            state["session_meta"]["low_confidence"] = state["session_meta"]["low_confidence"] or low
            self._build_final_link(state)
            session.current_stage = "checkpoint_2"
            session.current_shadow_id = None
            session.state = state
            self._sync_system_state(session)
            self.db.add(session)
            self.db.commit()
            return self._response(session, self._checkpoint_2_message(state), "choices", choices=[{"key": "go", "label": "Перейти к глубине"}])

        next_root = next_root_candidate(state["level_2"]["main_shadow_id"], checked)
        state["level_3"]["answers"] = {key: None for key in state["level_3"]["answers"]}
        state["level_3"]["score"] = None
        state["level_3"]["expression_level"] = None
        return self._ask_shadow_question(session, state, next_root, "main_answer", "Сигнал корня слабый, поэтому КЭТ проверит альтернативный корневой слой по матрице ТЗ.")

    def _enter_level_2(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        target = state["level_2"]["checked_shadow_id"]
        session.current_stage = "level_2"
        return self._ask_shadow_question(session, state, target, "main_answer", self._level_2_intro())

    def _enter_depth(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        session.current_stage = "depth_short"
        state["depth_idx"] = 0
        return self._ask_depth_question(session, state, prelude=self._depth_intro())

    def _handle_depth(self, session: UserSession, state: dict[str, Any], choice: str | None, text: str | None) -> EngineResponse:
        idx = state.get("depth_idx", 0)
        if idx >= len(DEPTH_ORDER):
            return self._enter_passport(session, state)
        key = DEPTH_ORDER[idx]
        state["depth_block"][key] = normalize_depth_answer(choice, text, DEPTH_QUESTIONS[key]["answers"])
        state["depth_idx"] = idx + 1
        if state["depth_idx"] < len(DEPTH_ORDER):
            return self._ask_depth_question(session, state)
        return self._enter_passport_ready(session, state)

    def _enter_passport_ready(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        assemble_passport(state)
        session.current_stage = "passport"
        session.state = state
        self._sync_system_state(session)
        self.db.add(session)
        self.db.commit()
        return self._response(
            session,
            "Результат готов.",
            "choices",
            choices=[{"key": "collect_passport", "label": "Забрать Паспорт"}],
            meta={"result_ready": True, "link_key": state["final_link"]["link_key"]},
        )

    def _show_passport_and_offer(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        if not state["passport"]["title"]:
            assemble_passport(state)
        session.current_stage = "offer"
        session.state = state
        self._sync_system_state(session)
        self.db.add(session)
        self.db.commit()
        return self._response(
            session,
            f"{self._passport_message(state)}\n\n---\n\n{self._offer_message()}",
            "choices",
            choices=[],
            meta={"passport": state["passport"], "link_key": state["final_link"]["link_key"], "final_offer": True},
        )

    def _complete(self, session: UserSession, state: dict[str, Any]) -> EngineResponse:
        if not state["passport"]["title"]:
            assemble_passport(state)
        state["session_meta"]["completed_at"] = self._now()
        full_text = f"{self._passport_message(state)}\n\n---\n\n{self._offer_message()}"
        result = {
            "mode": "v1_2",
            "passport": state["passport"],
            "final_link": state["final_link"],
            "top_shadow_names": [state["passport"]["title"]],
            "passport_text": self._passport_message(state),
            "offer_text": self._offer_message(),
            "full_text": full_text,
            "mechanism_formula": state["passport"]["formula_mechanism"],
            "manifestation": state["passport"]["inner_mechanism"],
            "price": state["passport"]["main_price"],
            "hidden_resource": state["passport"]["hidden_resource"],
            "screen_phrase": state["passport"]["save_phrase"],
            "micro_permission": state["passport"]["micro_permission"],
        }
        session.result = result
        session.status = "completed"
        session.current_stage = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.result_released_at = session.result_released_at or datetime.now(timezone.utc)
        session.state = state
        self._sync_system_state(session)
        self.db.add(session)
        self._log(session.id, "session_completed", {"mode": "v1_2", "link_key": state["final_link"]["link_key"]})
        self.db.commit()
        return self._response(session, full_text, "done", meta={"result_ready": True, "result_unlocked": True, "link_key": state["final_link"]["link_key"]})

    def _ask_shadow_question(self, session: UserSession, state: dict[str, Any], shadow_id: int, question_type: str, prelude: str = "") -> EngineResponse:
        question = self._question_for(shadow_id, question_type, state["system_state"].get("current_branch"))
        session.current_shadow_id = shadow_id
        state["system_state"]["current_stage"] = session.current_stage
        state["system_state"]["current_shadow_id"] = shadow_id
        state["system_state"]["current_question_type"] = question_type
        if question_type == "main_answer":
            state["system_state"]["current_branch"] = None
        session.state = state
        self._sync_answers_to_level(state, session.current_stage, shadow_id)
        self.db.add(session)
        self.db.commit()
        heading = f"Тень. {self.shadow_map[shadow_id]['shadow_name']}." if self.shadow_map[shadow_id]["level"] == 1 else ""
        body = f"**{heading}**\n\n{question['text']}" if heading else question["text"]
        message = f"{prelude}\n\n{body}\n\nВыбери вариант ниже." if prelude else f"{body}\n\nВыбери вариант ниже."
        return self._response(session, message, "choices", choices=self._choices(question), meta={"shadow_id": shadow_id, "shadow_name": self.shadow_map[shadow_id]["shadow_name"], "question_type": question_type})

    def _ask_depth_question(self, session: UserSession, state: dict[str, Any], prelude: str = "") -> EngineResponse:
        idx = state.get("depth_idx", 0)
        key = DEPTH_ORDER[idx]
        question = DEPTH_QUESTIONS[key]
        session.current_stage = "depth_short"
        session.current_shadow_id = None
        state["system_state"]["current_stage"] = "depth_short"
        state["system_state"]["current_shadow_id"] = None
        state["system_state"]["current_branch"] = None
        state["system_state"]["current_question_type"] = key
        session.state = state
        self.db.add(session)
        self.db.commit()
        message = f"{prelude}\n\n{question['text']}\n\nМожно выбрать вариант ниже или написать свой ответ." if prelude else f"{question['text']}\n\nМожно выбрать вариант ниже или написать свой ответ."
        return self._response(session, message, "choices", choices=[{"key": key, "label": label} for key, label in question["answers"].items()], meta={"depth_key": key, "depth_index": idx + 1})

    def _question_for(self, shadow_id: int, question_type: str, branch: str | None) -> dict[str, Any]:
        shadow = self.shadow_map[shadow_id]
        if question_type == "main_answer":
            return shadow["main_question"]
        for item in shadow["branches"][branch or "A"]:
            if item["question_type"] == question_type:
                return item
        raise ValueError(f"No question {question_type} for shadow {shadow_id}")

    def _next_question_type(self, shadow_id: int, branch: str, current: str) -> str | None:
        order = [item["question_type"] for item in self.shadow_map[shadow_id]["branches"][branch]]
        idx = order.index(current)
        return order[idx + 1] if idx + 1 < len(order) else None

    def _write_shadow_answer(self, state: dict[str, Any], stage: str, shadow_id: int, key: str, value: str) -> None:
        if stage == "level_1":
            self._shadow_state(state, stage, shadow_id)[key] = value
            return
        if key == "branch":
            return
        state[stage]["checked_shadow_id"] = shadow_id
        if key == "main_answer":
            state[stage]["main_shadow_id"] = state[stage]["main_shadow_id"] or shadow_id
        state[stage]["answers"][key] = value

    def _shadow_state(self, state: dict[str, Any], stage: str, shadow_id: int) -> dict[str, Any]:
        if stage == "level_1":
            return state["level_1"][f"shadow_{shadow_id}"]
        bucket = state[stage]
        if bucket["checked_shadow_id"] in {None, shadow_id}:
            bucket["checked_shadow_id"] = shadow_id
        bucket["main_shadow_id"] = bucket["main_shadow_id"] or shadow_id
        answers = bucket["answers"]
        return {
            "shadow_id": shadow_id,
            "level": self.shadow_map[shadow_id]["level"],
            "main_answer": answers.get("main_answer"),
            "branch": answers.get("main_answer"),
            "emotion_answer": answers.get("emotion_answer"),
            "hypothesis_answer": None,
            "body_answer": answers.get("body_answer"),
            "reality_answer": answers.get("reality_answer"),
            "fact_check": answers.get("fact_check"),
            "inner_check": answers.get("inner_check"),
            "score": bucket.get("score") or 0,
            "score_type": None,
            "expression_level": bucket.get("expression_level"),
            "is_main": True,
            "route_context": {"hypothesis_answer": None},
        }

    def _sync_answers_to_level(self, state: dict[str, Any], stage: str, shadow_id: int) -> None:
        if stage not in {"level_2", "level_3"}:
            return
        target = state[stage]
        target["checked_shadow_id"] = shadow_id
        target["main_shadow_id"] = target["main_shadow_id"] or shadow_id

    def _build_final_link(self, state: dict[str, Any]) -> None:
        behavior = state["level_1"]["main_shadow_id"]
        personality = state["level_2"]["main_shadow_id"]
        root = state["level_3"]["main_shadow_id"]
        state["final_link"] = {
            "behavior_shadow_id": behavior,
            "personality_shadow_id": personality,
            "root_shadow_id": root,
            "link_key": f"{behavior}_{personality}_{root}",
        }

    def _choices(self, question: dict[str, Any]) -> list[dict[str, str]]:
        return [{"key": key, "label": label} for key, label in question["answers"].items()]

    def _response(self, session: UserSession, assistant_message: str, input_mode: str, choices: list[dict[str, str]] | None = None, progress: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> EngineResponse:
        return EngineResponse(
            session_id=session.id,
            status=session.status,
            assistant_message=assistant_message.strip(),
            input_mode=input_mode,
            choices=choices or [],
            progress=progress or self._progress(session.current_stage, session.current_shadow_id),
            meta=meta or {},
        )

    def _progress(self, stage: str, shadow_id: int | None = None) -> dict[str, Any]:
        labels = {
            "intro": ("Вход", 1),
            "legend": ("Легенда", 2),
            "level_1": ("Уровень 1 из 3", 2 + (shadow_id or 1)),
            "checkpoint_1": ("Уровень 2 из 3", 6),
            "level_2": ("Уровень 2 из 3", 7),
            "level_3": ("Уровень 3 из 3", 8),
            "checkpoint_2": ("Диагностика пройдена", 9),
            "depth_short": ("Персонализация", 10),
            "passport": ("Паспорт тени", 11),
            "offer": ("Паспорт тени", 12),
            "completed": ("Готово", 12),
        }
        label, current = labels.get(stage, (stage, 1))
        return {"label": label, "current": min(current, 12), "total": 12}

    def _sync_system_state(self, session: UserSession) -> None:
        state = session.state or {}
        if "system_state" in state:
            state["system_state"]["current_stage"] = session.current_stage if session.current_stage != "completed" else "offer"
            state["system_state"]["current_shadow_id"] = session.current_shadow_id
        session.state = state

    def _log(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.db.add(SessionEvent(session_id=session_id, event_type=event_type, payload=payload))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _intro_message(self) -> str:
        return (
            "Привет. Меня зовут КЭТ.\n\n"
            "Я помогу увидеть одну точку, в которой может ломаться движение.\n\n"
            "Но сначала давай познакомимся.\n\n"
            "Как я могу к тебе обращаться?"
        )

    def _age_prompt(self, user_name: str) -> str:
        return (
            f"Приятно познакомиться, {user_name}.\n\n"
            "Скажи, пожалуйста, сколько тебе лет?"
        )

    def _first_measure_message(self, user_name: str) -> str:
        return (
            f"Спасибо, {user_name}.\n\n"
            "Теперь можно перейти к первому замеру.\n\n"
            f"{self._diagnostic_intro_message()}"
        )

    def _diagnostic_intro_message(self) -> str:
        return (
            "Я помогаю увидеть одну точку, в которой у человека ломается движение.\n\n"
            "Не «почему ты не делаешь».\n\n"
            "А где именно внутри ты останавливаешься — даже когда понимаешь, что хочешь большего.\n\n"
            "Важно: это не тест и не оценка. Мы не будем искать «что с тобой не так».\n\n"
            f"{self._goal_prompt()}"
        )

    def _legend_message(self) -> str:
        return (
            "Замечательно. \n"
            "Теперь коротко о том, как устроен механизм, который чаще всего тормозит движение на пути к жизни твоей мечты.\n\n"
            "У стоп—механизма есть 3 слоя:\n\n"
            "1. Как ты останавливаешься (поведение)\n"
            "2. Что это запускает внутри (личность)\n"
            "3. Что держит это годами (корень)\n\n"
            "Мы пройдем все три. Каждый слой приближает к ответу.\n\n"
            "Готов(а)? Поехали."
        )

    def _level_1_intro(self) -> str:
        return (
            "Сначала посмотрим, как ты чаще всего себя останавливаешь на пути к «большему, лучшему, другому, твоему» — потому что без этого мы не поймем, где искать причину. \n"
            "3 минуты.\n"
            "Если ни один вариант не подходит идеально — выбери самый близкий. Узнавание придет в процессе."
        )

    def _level_2_intro(self) -> str:
        return "Теперь мы посмотрим не только на поведение, а на возможную внутреннюю причину, из которой такое поведение запускается."

    def _goal_prompt(self) -> str:
        return (
            "Перед тем, как начнем, напиши коротко: к какой жизни ты сейчас хочешь приблизиться?\n\n"
            "Например:\n"
            "— жизнь,  в которой меньше сжатия и больше живого движения\n"
            "— спокойная и своя жизнь без постоянного внутреннего напряжения \n"
            "— больше свободы в деньгах и перемещении\n"
            "— свое дело, свой ритм, больше здоровья и внутренней гармонии\n"
            "И тд"
        )

    def _level_3_checkpoint_message(self, personality_id: int, expression: str) -> str:
        name = self.shadow_map[personality_id]["shadow_name"]
        return (
            f"Сейчас уже видно не только, как у тебя ломается движение, но и что внутри чаще всего запускает этот сценарий.\n\n"
            f"Главная внутренняя причина: {name}\n\n"
            f"Это проявляется так: {expression_template(personality_id, 2, expression)}\n\n"
            "Сейчас уровень 3 — самый глубокий. Здесь часто откликается то, что обычно не видно."
        )

    def _transition_to_shadow(self, shadow_id: int) -> str:
        return {
            2: "Мы посмотрели точку старта. Теперь проверим, не уходит ли движение в подготовку.",
            3: "Теперь посмотрим, что происходит не только в старте, но и в самом процессе.",
        }.get(shadow_id, "")

    def _checkpoint_1_message(self, shadow_name: str, expression: str) -> str:
        return (
            "Сейчас уже видно, как именно у тебя ломается движение.\n\n"
            f"Главный способ торможения: {shadow_name}\n\n"
            f"Это проявляется так: {expression}\n\n"
            "Ты не «не делаешь» — ты останавливаешься в конкретной точке.\n\n"
            "Дальше мы будем смотреть не на поведение, а на то, что его запускает."
        )

    def _checkpoint_2_message(self, state: dict[str, Any]) -> str:
        behavior = self.shadow_map[state["final_link"]["behavior_shadow_id"]]["shadow_name"]
        personality = self.shadow_map[state["final_link"]["personality_shadow_id"]]["shadow_name"]
        root = self.shadow_map[state["final_link"]["root_shadow_id"]]["shadow_name"]
        return (
            "Сейчас становится видно самый глубокий слой.\n\n"
            f"Основной корневой механизм: {root}\n\n"
            f"Глубинная связка = {behavior} → {personality} → {root}\n\n"
            "Это одна и та же конструкция. И это одновременно сложно и освобождает: если это одна конструкция, её можно разобрать."
        )

    def _depth_intro(self) -> str:
        return (
            "Сейчас у нас уже есть главная линия.\n\n"
            "Теперь важно сделать ее по-настоящему твоей: понять, где именно это проявляется сильнее всего, от чего защищает и какую цену уже берет.\n\n"
            "Не умом. А телом. Если честно — какую плату ты уже чувствуешь? Не «понимаю», а «ощущаю»."
        )

    def _passport_message(self, state: dict[str, Any]) -> str:
        passport = state["passport"]
        warning = ""
        if state["session_meta"].get("low_confidence"):
            warning = (
                "\n\nВажно: сигналы слабые.\n"
                "Это может значить, что механизм не проявлен ярко или ты сейчас в сопротивлении.\n\n"
                "Но даже слабый сигнал — это сигнал. Если внутри шевельнулось — доверься.\n"
                "Если нет — возможно, стоит пройти диагностику в другой день, когда будешь спокойнее."
            )
        return (
            f"### Паспорт тени\n\n"
            f"Твоя главная тень сейчас — {passport['title']}.\n\n"
            "Важно сразу: дело не в том, что ты «не стараешься» или «не делаешь».\n\n"
            "У тебя есть конкретная точка, в которой движение ломается.\n\n"
            "Формула механизма:\n\n"
            f"{passport['formula_mechanism']}\n\n"
            "Архитектура:\n\n"
            f"{passport['architecture']}\n\n"
            "Что происходит внутри:\n\n"
            f"{passport['inner_mechanism']}\n\n"
            "Где это проявляется сильнее всего:\n\n"
            f"{passport['main_sphere']}\n\n"
            "Скорее всего, этот механизм защищает тебя от:\n\n"
            f"{passport['main_protection']}\n\n"
            "Но цена этой защиты уже становится заметной:\n\n"
            f"{passport['main_price']}\n\n"
            "Твой скрытый ресурс:\n\n"
            f"{passport['hidden_resource']}\n\n"
            "Фраза, которую можно сохранить:\n\n"
            f"{passport['save_phrase']}\n\n"
            "Микро-разрешение:\n\n"
            f"{passport['micro_permission']}\n\n"
            "Вопрос на вырост: если бы этот механизм ослаб на 20% — что бы изменилось в твоей жизни завтра?"
            f"{warning}"
        )

    def _offer_message(self) -> str:
        return (
            "Сейчас ты увидел(а) важную вещь.\n\n"
            "Не «проблему». А механизм.\n\n"
            "И он уже не будет развидеться.\n\n"
            "Дальше можно разобрать не только «где ломается», а всю конструкцию: где ты сейчас, куда на самом деле хочешь, на что можешь опереться и как из этого собирается путь.\n\n"
            "Это и есть:\n\n"
            "«Чертеж дома»\n\n"
            "Персональная карта с личным проектом твоего ДОМА."
        )
