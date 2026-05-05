from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


STAGES = {
    "intro",
    "legend",
    "level_1",
    "checkpoint_1",
    "level_2",
    "level_3",
    "checkpoint_2",
    "depth_short",
    "passport",
    "offer",
}

AB_SCORE = {
    "main_answer": {"A": 6, "Б": 4},
    "emotion_answer": {"A": 3, "Б": 6, "В": 9, "Г": 12},
    "body_answer": {"A": 3, "Б": 6, "В": 9, "Г": 12},
    "reality_answer": {"A": 16, "Б": 12, "В": 8, "Г": 0},
}
V_SCORE = {
    "fact_check": {"A": 16, "Б": 8, "В": 0},
    "inner_check": {"A": 9, "Б": 3, "В": 0},
}

LEVEL_1_PRIORITY = {2: 0, 1: 1, 3: 2}
LEVEL_2_ROUTE = {"A": 4, "Б": 5, "В": 6, "Г": 4}
ROOT_MATRIX = {4: 8, 5: 7, 6: 9}
ROOT_PRIORITIES = {4: [8, 7, 9], 5: [7, 8, 9], 6: [9, 8, 7]}
WEAK_LEVELS = {"низкий", "неактуальная"}

DEPTH_QUESTIONS = {
    "sphere": {
        "text": "В каких сферах жизни этот механизм проявляется чаще всего? Можно выбрать до двух вариантов.",
        "answers": {
            "работа": "работа",
            "деньги": "деньги",
            "отношения": "отношения",
            "проявленность": "проявленность",
            "выбор пути": "выбор пути",
            "личные границы": "личные границы",
            "образ жизни": "образ жизни",
            "другое": "другое",
        },
    },
    "protection": {
        "text": "Как тебе кажется, от чего именно этот механизм может тебя защищать?",
        "answers": {
            "от боли ошибки": "от боли ошибки",
            "от осуждения и оценки": "от осуждения и оценки",
            "от провала и потери контроля": "от провала и потери контроля",
            "от слишком больших перемен": "от слишком больших перемен",
            "от разочарования в себе": "от разочарования в себе",
            "от потери одобрения, поддержки или близости": "от потери одобрения, поддержки или близости",
            "от неизвестности и небезопасности нового": "от неизвестности и небезопасности нового",
            "от собственной силы и масштаба": "от собственной силы и масштаба",
            "другое": "другое",
        },
    },
    "price": {
        "text": (
            "Какую цену ты уже платишь за этот механизм?\n\n"
            "Если честно — не «что я теряю», а что я уже заплатил(а). Ощущениями, временем, энергией, верой в себя."
        ),
        "answers": {
            "потерянное время": "потерянное время",
            "упущенные возможности": "упущенные возможности",
            "жизнь меньшего масштаба": "жизнь меньшего масштаба",
            "ослабление веры в себя": "ослабление веры в себя",
            "хроническое внутреннее напряжение": "хроническое внутреннее напряжение",
            "нереализованные желания и идеи": "нереализованные желания и идеи",
            "чужой сценарий жизни": "чужой сценарий жизни",
            "снижение энергии и вкуса к жизни": "снижение энергии и вкуса к жизни",
            "другое": "другое",
        },
    },
}
DEPTH_ORDER = ["sphere", "protection", "price"]


@lru_cache
def load_question_bank() -> list[dict[str, Any]]:
    return _read_json("question_bank_v1_2.json")


@lru_cache
def load_shadow_links() -> dict[str, Any]:
    return _read_json("shadow_links_v1_2.json")


@lru_cache
def load_expression_templates() -> dict[str, Any]:
    return _read_json("expression_templates_v1_2.json")


def _read_json(name: str) -> Any:
    path = Path(__file__).resolve().parent.parent / "data" / name
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def shadow_map() -> dict[int, dict[str, Any]]:
    return {item["shadow_id"]: item for item in load_question_bank()}


def empty_shadow(shadow_id: int) -> dict[str, Any]:
    return {
        "shadow_id": shadow_id,
        "level": shadow_map()[shadow_id]["level"],
        "main_answer": None,
        "branch": None,
        "emotion_answer": None,
        "hypothesis_answer": None,
        "body_answer": None,
        "reality_answer": None,
        "fact_check": None,
        "inner_check": None,
        "score": 0,
        "score_type": None,
        "expression_level": None,
        "is_main": False,
        "route_context": {"hypothesis_answer": None},
    }


def default_state(session_id: str, started_at: str) -> dict[str, Any]:
    return {
        "session_meta": {
            "session_id": session_id,
            "user_name": "",
            "user_age": None,
            "user_goal_text": "",
            "mode": "v1_2",
            "low_confidence": False,
            "started_at": started_at,
            "completed_at": None,
        },
        "system_state": {
            "current_stage": "intro",
            "current_shadow_id": None,
            "current_branch": None,
            "current_question_type": "ask_name",
        },
        "level_1": {
            "shadow_1": empty_shadow(1),
            "shadow_2": empty_shadow(2),
            "shadow_3": empty_shadow(3),
            "main_shadow_id": None,
            "route_4": 0,
            "route_5": 0,
            "route_6": 0,
        },
        "level_2": _empty_level_state(),
        "level_3": _empty_level_state(),
        "depth_block": {
            "sphere": {"selected": [], "free_text": "", "main_value": ""},
            "protection": {"selected": [], "free_text": "", "main_value": ""},
            "price": {"selected": [], "free_text": "", "main_value": ""},
        },
        "final_link": {
            "behavior_shadow_id": None,
            "personality_shadow_id": None,
            "root_shadow_id": None,
            "link_key": "",
        },
        "passport": {
            "title": "",
            "formula_mechanism": "",
            "architecture": "",
            "inner_mechanism": "",
            "main_sphere": "",
            "main_protection": "",
            "main_price": "",
            "hidden_resource": "",
            "save_phrase": "",
            "micro_permission": "",
        },
    }


def _empty_level_state() -> dict[str, Any]:
    return {
        "checked_shadow_id": None,
        "main_shadow_id": None,
        "score": None,
        "expression_level": None,
        "answers": {
            "main_answer": None,
            "emotion_answer": None,
            "body_answer": None,
            "reality_answer": None,
            "fact_check": None,
            "inner_check": None,
        },
    }


def calculate_shadow_score(answers: dict[str, Any]) -> tuple[int, str, str]:
    branch = answers.get("branch") or answers.get("main_answer")
    if branch in {"A", "Б"}:
        score = (
            AB_SCORE["main_answer"].get(branch, 0)
            + AB_SCORE["emotion_answer"].get(answers.get("emotion_answer"), 0)
            + AB_SCORE["body_answer"].get(answers.get("body_answer"), 0)
            + AB_SCORE["reality_answer"].get(answers.get("reality_answer"), 0)
        )
        return score, "AB", expression_level(score, "AB")

    score = V_SCORE["fact_check"].get(answers.get("fact_check"), 0) + V_SCORE["inner_check"].get(answers.get("inner_check"), 0)
    return score, "V", expression_level(score, "V")


def expression_level(score: int, score_type: str) -> str:
    if score_type == "AB":
        if 32 <= score <= 46:
            return "высокий"
        if 24 <= score <= 31:
            return "средне-высокий"
        if 16 <= score <= 23:
            return "средний"
        return "низкий"
    if 16 <= score <= 25:
        return "скрытая, но выраженная"
    if 9 <= score <= 15:
        return "скрытая фоновая"
    return "неактуальная"


def select_level_1_main(level_1: dict[str, Any]) -> tuple[int, bool]:
    candidates = []
    for shadow_id in (1, 2, 3):
        item = level_1[f"shadow_{shadow_id}"]
        threshold = 16 if item.get("score_type") == "AB" else 9
        if item.get("score", 0) >= threshold and item.get("reality_answer") != "Г":
            candidates.append(item)

    for shadow_id in (1, 2, 3):
        level_1[f"shadow_{shadow_id}"]["is_main"] = False

    if not candidates:
        level_1["shadow_2"]["is_main"] = True
        level_1["main_shadow_id"] = 2
        return 2, True

    candidates.sort(key=lambda item: (-item["score"], LEVEL_1_PRIORITY[item["shadow_id"]]))
    selected = candidates[0]["shadow_id"]
    level_1[f"shadow_{selected}"]["is_main"] = True
    level_1["main_shadow_id"] = selected
    return selected, False


def route_level_2(level_1: dict[str, Any]) -> tuple[int, bool]:
    main_id = level_1["main_shadow_id"]
    hypothesis = (level_1.get(f"shadow_{main_id}") or {}).get("hypothesis_answer")
    route_fallback = hypothesis in {None, "Г"}
    target = LEVEL_2_ROUTE.get(hypothesis, 4)
    level_1["route_4"] = main_id if target == 4 and not route_fallback else 0
    level_1["route_5"] = main_id if target == 5 and not route_fallback else 0
    level_1["route_6"] = main_id if target == 6 and not route_fallback else 0
    if route_fallback:
        level_1["route_fallback"] = True
    return target, route_fallback


def base_root_for(personality_shadow_id: int) -> int:
    return ROOT_MATRIX[personality_shadow_id]


def next_root_candidate(personality_shadow_id: int, checked_roots: dict[int, dict[str, Any]]) -> int | None:
    for root_id in ROOT_PRIORITIES[personality_shadow_id]:
        if root_id not in checked_roots:
            return root_id
    return None


def choose_root(personality_shadow_id: int, checked_roots: dict[int, dict[str, Any]]) -> tuple[int, bool, bool]:
    base_root = base_root_for(personality_shadow_id)
    normalized_roots = {int(root_id): data for root_id, data in checked_roots.items()}
    strong = [
        data for _, data in sorted(normalized_roots.items(), key=lambda item: ROOT_PRIORITIES[personality_shadow_id].index(item[0]))
        if data.get("expression_level") not in WEAK_LEVELS
    ]
    if strong:
        return strong[0]["shadow_id"], False, True
    if len(normalized_roots) >= len(ROOT_PRIORITIES[personality_shadow_id]):
        return base_root, True, True
    return base_root, False, False


def normalize_depth_answer(choice: str | None, text: str | None, options: dict[str, str]) -> dict[str, Any]:
    raw_text = (text or "").strip()
    if raw_text:
        parts = [part.strip() for part in raw_text.replace("\n", ",").split(",") if part.strip()]
        selected = [part for part in parts if part in options and part != "другое"]
        free_parts = [part for part in parts if part not in options or part == "другое"]
        free_text = free_parts[0] if free_parts else ""
        if free_text:
            main_value = trim_free_text(free_text)
            return {"selected": selected[:2], "free_text": main_value, "main_value": main_value}
        if selected:
            return {"selected": selected[:2], "free_text": "", "main_value": selected[0]}
        return {"selected": [], "free_text": trim_free_text(raw_text), "main_value": trim_free_text(raw_text)}

    selected = []
    if choice:
        selected = [choice] if choice in options and choice != "другое" else []
    main_value = selected[0] if selected else "другое"
    return {"selected": selected[:2], "free_text": "", "main_value": main_value}


def trim_free_text(value: str) -> str:
    value = value.strip()
    if len(value) > 60:
        return value[:60] + "..."
    return value


def assemble_passport(state: dict[str, Any]) -> dict[str, str]:
    final = state["final_link"]
    link_key = final["link_key"]
    links = load_shadow_links()
    link = deepcopy(links.get(link_key))
    if link is None:
        link = _fallback_link(final)

    passport = {
        "title": link["title"],
        "formula_mechanism": link["formula_mechanism"],
        "architecture": link["architecture"],
        "inner_mechanism": link["inner_mechanism"],
        "main_sphere": state["depth_block"]["sphere"]["main_value"],
        "main_protection": state["depth_block"]["protection"]["main_value"],
        "main_price": state["depth_block"]["price"]["main_value"],
        "hidden_resource": link["hidden_resource"],
        "save_phrase": link["save_phrase"],
        "micro_permission": link["micro_permission"],
    }
    state["passport"] = passport
    return passport


def _fallback_link(final: dict[str, Any]) -> dict[str, str]:
    names = {
        1: "Замирание перед шагом",
        2: "Вечная подготовка",
        3: "Разрыв с процессом",
        4: "Жизнь с оглядкой",
        5: "Запрет занимать место",
        6: "Чужой чертеж",
        7: "Страх большего",
        8: "Нет внутренней опоры",
        9: "Жизнь в привычном",
    }
    fallback = deepcopy(load_shadow_links()["fallback"])
    values = {
        "behavior_name": names.get(final["behavior_shadow_id"], ""),
        "personality_name": names.get(final["personality_shadow_id"], ""),
        "root_name": names.get(final["root_shadow_id"], ""),
    }
    return {key: value.format(**values) for key, value in fallback.items()}


def expression_template(shadow_id: int, level: int, expression: str) -> str:
    level_key = f"level_{level}"
    expression_key = {
        "высокий": "high",
        "средне-высокий": "medium_high",
        "средний": "medium",
        "низкий": "low",
        "скрытая, но выраженная": "hidden_expressed",
        "скрытая фоновая": "hidden_background",
        "неактуальная": "inactive",
    }[expression]
    return load_expression_templates()[level_key][str(shadow_id)][expression_key]
