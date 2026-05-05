from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import Base, get_db
from app.models.session import UserSession
from app.services.scenario_engine import ScenarioEngine
from app.services.v1_2_logic import (
    assemble_passport,
    calculate_shadow_score,
    choose_root,
    default_state,
    expression_level,
    normalize_depth_answer,
    route_level_2,
    select_level_1_main,
)

ROOT = Path(__file__).resolve().parents[2]


def project_file(relative: str) -> Path:
    path = ROOT / relative
    if path.exists():
        return path
    if relative.startswith("backend/"):
        backend_path = Path(__file__).resolve().parents[1] / relative.removeprefix("backend/")
        if backend_path.exists():
            return backend_path
    return path


def make_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return testing_session()


def get_session(db, session_id: str) -> UserSession:
    session = db.get(UserSession, session_id)
    assert session is not None
    return session


def send_choice(engine: ScenarioEngine, db, session_id: str, choice: str):
    return engine.handle_message(get_session(db, session_id), choice=choice)


def send_text(engine: ScenarioEngine, db, session_id: str, text: str):
    return engine.handle_message(get_session(db, session_id), text=text)


def answer_ab_shadow(engine: ScenarioEngine, db, session_id: str, main="A", emotion="В", body="В", reality="Б", hypothesis="A"):
    response = send_choice(engine, db, session_id, main)
    response = send_choice(engine, db, session_id, emotion)
    if response.meta.get("question_type") == "hypothesis_answer":
        response = send_choice(engine, db, session_id, hypothesis)
    response = send_choice(engine, db, session_id, body)
    return send_choice(engine, db, session_id, reality)


def answer_v_shadow(engine: ScenarioEngine, db, session_id: str, fact="В", inner="В"):
    response = send_choice(engine, db, session_id, "В")
    response = send_choice(engine, db, session_id, fact)
    return send_choice(engine, db, session_id, inner)


def start_level_1(engine: ScenarioEngine, db, session_id: str):
    send_text(engine, db, session_id, "Анна")
    send_text(engine, db, session_id, "34")
    send_text(engine, db, session_id, "Хочу больше свободы и свое дело")
    return send_choice(engine, db, session_id, "go")


def finish_depth_to_passport(engine: ScenarioEngine, db, session_id: str):
    response = send_choice(engine, db, session_id, "go")
    assert response.meta["depth_key"] == "sphere"
    response = send_text(engine, db, session_id, "проявленность, работа")
    assert response.meta["depth_key"] == "protection"
    response = send_choice(engine, db, session_id, "от осуждения и оценки")
    assert response.meta["depth_key"] == "price"
    response = send_choice(engine, db, session_id, "упущенные возможности")
    assert get_session(db, session_id).current_stage == "passport"
    assert response.assistant_message == "Результат готов."
    assert response.choices == [{"key": "collect_passport", "label": "Забрать Паспорт"}]
    return response


def run_route_to_passport(route_key: str):
    db = make_db()
    engine = ScenarioEngine(db)
    session_id = engine.create_session().session_id
    start_level_1(engine, db, session_id)

    if route_key == "1_4_8":
        answer_ab_shadow(engine, db, session_id, main="A", hypothesis="A")
        answer_v_shadow(engine, db, session_id)
        response = answer_v_shadow(engine, db, session_id)
    elif route_key == "2_5_7":
        answer_v_shadow(engine, db, session_id)
        answer_ab_shadow(engine, db, session_id, main="A", hypothesis="Б")
        response = answer_v_shadow(engine, db, session_id)
    elif route_key == "3_6_9":
        answer_v_shadow(engine, db, session_id)
        answer_v_shadow(engine, db, session_id)
        response = answer_ab_shadow(engine, db, session_id, main="A", hypothesis="В")
    else:
        raise AssertionError(f"Unknown route {route_key}")

    assert get_session(db, session_id).current_stage == "checkpoint_1"
    response = send_choice(engine, db, session_id, "go")
    personality_id = int(route_key.split("_")[1])
    assert response.meta["shadow_id"] == personality_id
    answer_ab_shadow(engine, db, session_id, main="A")
    root_id = int(route_key.split("_")[2])
    assert get_session(db, session_id).current_shadow_id == root_id
    response = answer_ab_shadow(engine, db, session_id, main="A")
    assert get_session(db, session_id).current_stage == "checkpoint_2"
    response = finish_depth_to_passport(engine, db, session_id)
    return db, engine, session_id, response


def test_state_machine_full_v1_2_path():
    db = make_db()
    engine = ScenarioEngine(db)
    created = engine.create_session()
    session_id = created.session_id
    assert get_session(db, session_id).current_stage == "intro"
    assert "Как я могу к тебе обращаться?" in created.assistant_message
    assert "Перед тем, как начнем" not in created.assistant_message

    response = send_text(engine, db, session_id, "Анна")
    state = get_session(db, session_id).state
    assert get_session(db, session_id).current_stage == "intro"
    assert state["session_meta"]["user_name"] == "Анна"
    assert state["system_state"]["current_question_type"] == "ask_age"
    assert "Приятно познакомиться, Анна." in response.assistant_message
    assert "сколько тебе лет" in response.assistant_message
    assert "Перед тем, как начнем" not in response.assistant_message

    response = send_text(engine, db, session_id, "34")
    state = get_session(db, session_id).state
    assert get_session(db, session_id).current_stage == "intro"
    assert state["session_meta"]["user_age"] == 34
    assert state["system_state"]["current_question_type"] == "ask_goal"
    assert "Спасибо, Анна." in response.assistant_message
    assert "Теперь можно перейти к первому замеру." in response.assistant_message
    assert "Перед тем, как начнем" in response.assistant_message

    response = send_text(engine, db, session_id, "Хочу больше свободы и свое дело")
    assert get_session(db, session_id).current_stage == "legend"
    assert "Замечательно." in response.assistant_message
    assert "У стоп—механизма есть 3 слоя" in response.assistant_message

    response = send_choice(engine, db, session_id, "go")
    assert get_session(db, session_id).current_stage == "level_1"
    assert response.meta["shadow_id"] == 1
    assert "Тень. Замирание перед шагом" in response.assistant_message
    assert "Тень 1." not in response.assistant_message

    response = answer_ab_shadow(engine, db, session_id, main="A", hypothesis="A")
    assert response.meta["shadow_id"] == 2
    response = answer_ab_shadow(engine, db, session_id, main="A", hypothesis="A")
    assert response.meta["shadow_id"] == 3
    response = answer_v_shadow(engine, db, session_id)
    assert get_session(db, session_id).current_stage == "checkpoint_1"

    response = send_choice(engine, db, session_id, "go")
    assert get_session(db, session_id).current_stage == "level_2"
    assert response.meta["shadow_id"] == 4
    assert "Тень 4." not in response.assistant_message
    assert "Жизнь с оглядкой" not in response.assistant_message

    response = answer_ab_shadow(engine, db, session_id, main="A")
    assert get_session(db, session_id).current_stage == "level_3"
    assert response.meta["shadow_id"] == 8
    assert "Тень 8." not in response.assistant_message
    assert "Нет внутренней опоры" not in response.assistant_message

    response = answer_ab_shadow(engine, db, session_id, main="A")
    assert get_session(db, session_id).current_stage == "checkpoint_2"

    response = send_choice(engine, db, session_id, "go")
    assert get_session(db, session_id).current_stage == "depth_short"
    assert response.meta["depth_key"] == "sphere"
    response = send_text(engine, db, session_id, "проявленность, работа")
    assert response.meta["depth_key"] == "protection"
    response = send_choice(engine, db, session_id, "от осуждения и оценки")
    assert response.meta["depth_key"] == "price"
    response = send_choice(engine, db, session_id, "упущенные возможности")
    assert get_session(db, session_id).current_stage == "passport"
    assert response.assistant_message == "Результат готов."

    response = send_choice(engine, db, session_id, "collect_passport")
    assert get_session(db, session_id).current_stage == "offer"
    assert "Паспорт тени" in response.assistant_message
    assert "Одной строкой" not in response.assistant_message
    assert "Чертеж дома" in response.assistant_message
    assert "PDF" not in response.assistant_message
    assert "pdf" not in response.assistant_message
    assert "Напиши «ДА»" not in response.assistant_message
    assert "Напиши «НЕТ»" not in response.assistant_message
    assert response.meta["final_offer"] is True
    assert "pdf_choices" not in response.meta
    assert response.choices == []


def test_scoring_and_expression_levels():
    assert calculate_shadow_score({"branch": "A", "emotion_answer": "В", "body_answer": "Б", "reality_answer": "A"}) == (37, "AB", "высокий")
    assert calculate_shadow_score({"branch": "В", "fact_check": "A", "inner_check": "Б"}) == (19, "V", "скрытая, но выраженная")
    assert expression_level(32, "AB") == "высокий"
    assert expression_level(24, "AB") == "средне-высокий"
    assert expression_level(16, "AB") == "средний"
    assert expression_level(15, "AB") == "низкий"
    assert expression_level(16, "V") == "скрытая, но выраженная"
    assert expression_level(9, "V") == "скрытая фоновая"
    assert expression_level(8, "V") == "неактуальная"


def test_level_1_main_shadow_rules():
    state = default_state("s", "now")
    l1 = state["level_1"]
    l1["shadow_1"].update({"score": 40, "score_type": "AB", "reality_answer": "Г"})
    l1["shadow_2"].update({"score": 30, "score_type": "AB", "reality_answer": "Б"})
    l1["shadow_3"].update({"score": 25, "score_type": "AB", "reality_answer": "Б"})
    assert select_level_1_main(l1) == (2, False)

    l1["shadow_1"].update({"score": 30, "score_type": "AB", "reality_answer": "Б"})
    l1["shadow_2"].update({"score": 30, "score_type": "AB", "reality_answer": "Б"})
    l1["shadow_3"].update({"score": 30, "score_type": "AB", "reality_answer": "Б"})
    assert select_level_1_main(l1) == (2, False)

    l1["shadow_1"].update({"score": 15, "score_type": "AB", "reality_answer": "Б"})
    l1["shadow_2"].update({"score": 8, "score_type": "V", "reality_answer": None})
    l1["shadow_3"].update({"score": 0, "score_type": "V", "reality_answer": None})
    assert select_level_1_main(l1) == (2, True)


def test_level_2_route_rules():
    state = default_state("s", "now")
    l1 = state["level_1"]
    l1["main_shadow_id"] = 1
    for hypothesis, expected, fallback in [("A", 4, False), ("Б", 5, False), ("В", 6, False), ("Г", 4, True), (None, 4, True)]:
        l1["shadow_1"]["hypothesis_answer"] = hypothesis
        assert route_level_2(l1) == (expected, fallback)


def test_root_correction_rules():
    assert choose_root(4, {8: {"shadow_id": 8, "expression_level": "высокий"}}) == (8, False, True)
    assert choose_root(5, {7: {"shadow_id": 7, "expression_level": "средний"}}) == (7, False, True)
    assert choose_root(6, {9: {"shadow_id": 9, "expression_level": "скрытая, но выраженная"}}) == (9, False, True)
    assert choose_root(4, {8: {"shadow_id": 8, "expression_level": "низкий"}}) == (8, False, False)
    weak_all = {
        8: {"shadow_id": 8, "expression_level": "низкий"},
        7: {"shadow_id": 7, "expression_level": "неактуальная"},
        9: {"shadow_id": 9, "expression_level": "низкий"},
    }
    assert choose_root(4, weak_all) == (8, True, True)


def test_depth_rules():
    options = {"работа": "работа", "деньги": "деньги", "другое": "другое"}
    assert normalize_depth_answer("работа", None, options)["main_value"] == "работа"
    assert normalize_depth_answer("работа", "своя очень точная сфера", options)["main_value"] == "своя очень точная сфера"
    long = "а" * 61
    assert normalize_depth_answer(None, long, options)["main_value"] == ("а" * 60 + "...")
    exact = "б" * 60
    assert normalize_depth_answer(None, exact, options)["main_value"] == exact
    result = normalize_depth_answer(None, "работа, деньги", options)
    assert result["selected"] == ["работа", "деньги"]
    assert result["main_value"] == "работа"


def test_passport_assembly_from_shadow_links_only_and_no_secondary_note():
    state = default_state("s", "now")
    state["final_link"] = {"behavior_shadow_id": 2, "personality_shadow_id": 4, "root_shadow_id": 8, "link_key": "2_4_8"}
    state["depth_block"]["sphere"]["main_value"] = "проявленность"
    state["depth_block"]["protection"]["main_value"] = "от осуждения и оценки"
    state["depth_block"]["price"]["main_value"] = "упущенные возможности"
    passport = assemble_passport(state)

    assert passport["title"] == "Тень бесконечной подготовки"
    assert passport["formula_mechanism"].startswith("Ты хочешь действовать")
    assert passport["main_sphere"] == "проявленность"
    assert "secondary_note" not in passport


def test_passport_routes_for_required_shadow_links():
    expected_titles = {
        "1_4_8": "Тень неуверенного старта",
        "2_5_7": "Тень откладывания роста",
        "3_6_9": "Тень возврата в старый сценарий",
    }

    for route_key, title in expected_titles.items():
        db, _, session_id, response = run_route_to_passport(route_key)
        session = get_session(db, session_id)
        assert session.state["final_link"]["link_key"] == route_key
        assert session.state["passport"]["title"] == title
        assert response.meta["link_key"] == route_key
        assert "secondary_note" not in session.state["passport"]


def test_engine_low_confidence_fallback_selects_shadow_2_and_routes_to_4():
    db = make_db()
    engine = ScenarioEngine(db)
    session_id = engine.create_session().session_id
    start_level_1(engine, db, session_id)

    answer_v_shadow(engine, db, session_id, fact="В", inner="В")
    answer_v_shadow(engine, db, session_id, fact="В", inner="В")
    response = answer_v_shadow(engine, db, session_id, fact="В", inner="В")

    state = get_session(db, session_id).state
    assert get_session(db, session_id).current_stage == "checkpoint_1"
    assert state["level_1"]["main_shadow_id"] == 2
    assert state["session_meta"]["low_confidence"] is True
    assert state["session_meta"]["route_fallback"] is True
    assert response.meta["route_to"] == 4


def test_route_fallback_for_hypothesis_g_and_none():
    state = default_state("s", "now")
    state["level_1"]["main_shadow_id"] = 1
    state["level_1"]["shadow_1"]["hypothesis_answer"] = "Г"
    assert route_level_2(state["level_1"]) == (4, True)

    state = default_state("s", "now")
    state["level_1"]["main_shadow_id"] = 1
    state["level_1"]["shadow_1"]["hypothesis_answer"] = None
    assert route_level_2(state["level_1"]) == (4, True)


def test_engine_root_correction_checks_alternative_when_base_root_is_weak():
    db = make_db()
    engine = ScenarioEngine(db)
    session_id = engine.create_session().session_id
    start_level_1(engine, db, session_id)

    answer_ab_shadow(engine, db, session_id, main="A", hypothesis="A")
    answer_v_shadow(engine, db, session_id)
    answer_v_shadow(engine, db, session_id)
    send_choice(engine, db, session_id, "go")
    answer_ab_shadow(engine, db, session_id, main="A")

    assert get_session(db, session_id).current_shadow_id == 8
    response = answer_v_shadow(engine, db, session_id, fact="В", inner="В")
    assert response.meta["shadow_id"] == 7
    response = answer_ab_shadow(engine, db, session_id, main="A")

    state = get_session(db, session_id).state
    assert get_session(db, session_id).current_stage == "checkpoint_2"
    assert state["level_3"]["main_shadow_id"] == 7
    assert {int(root_id) for root_id in state["level_3_checks"]} == {8, 7}


def test_regression_no_shadow_10_and_no_all_10_route():
    db = make_db()
    engine = ScenarioEngine(db)
    assert 10 not in engine.shadow_map
    assert [shadow["shadow_id"] for shadow in engine.shadows] == list(range(1, 10))


def test_regression_normal_route_checks_one_personality_and_one_root_only():
    db, _, session_id, _ = run_route_to_passport("2_5_7")
    state = get_session(db, session_id).state

    assert state["level_2"]["checked_shadow_id"] == 5
    assert state["level_2"]["main_shadow_id"] == 5
    assert "level_2_checks" not in state
    assert {int(root_id) for root_id in state["level_3_checks"]} == {7}
    assert state["level_3"]["main_shadow_id"] == 7
    assert 10 not in [state["level_1"]["main_shadow_id"], state["level_2"]["main_shadow_id"], state["level_3"]["main_shadow_id"]]


def test_intro_prompt_contains_exact_examples_and_level_intro_copy():
    db = make_db()
    engine = ScenarioEngine(db)
    created = engine.create_session()

    assert "Как я могу к тебе обращаться?" in created.assistant_message
    assert "Перед тем, как начнем" not in created.assistant_message

    response = send_text(engine, db, created.session_id, "Анна")
    assert "Скажи, пожалуйста, сколько тебе лет?" in response.assistant_message
    assert "Перед тем, как начнем" not in response.assistant_message

    response = send_text(engine, db, created.session_id, "34")
    assert "Теперь можно перейти к первому замеру." in response.assistant_message
    assert "Перед тем, как начнем" in response.assistant_message
    assert "— жизнь,  в которой меньше сжатия и больше живого движения" in response.assistant_message
    assert "— спокойная и своя жизнь без постоянного внутреннего напряжения " in response.assistant_message
    assert "И тд" in response.assistant_message

    response = send_text(engine, db, created.session_id, "Хочу свободы")
    assert "Теперь коротко о том, как устроен механизм" in response.assistant_message
    response = send_choice(engine, db, created.session_id, "go")
    assert "Сначала посмотрим, как ты чаще всего себя останавливаешь" in response.assistant_message
    assert "«большему, лучшему, другому, твоему»" in response.assistant_message


def test_pdf_endpoints_return_russian_pdfs():
    client = TestClient(app)
    expected_sources = {
        "blueprint_sample": "Пример полного «Чертежа дома»",
        "shadow_tools": "10 главных инструментов борьбы с Тенями",
    }
    for pdf_type, source_text in expected_sources.items():
        response = client.get(f"/api/v1/pdf/{pdf_type}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.content.startswith(b"%PDF-")
        assert source_text in project_file(f"backend/app/data/pdf_sources/{pdf_type}.txt").read_text(encoding="utf-8")


def test_reset_endpoint_starts_clean_session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = TestingSession()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        created = client.post("/api/v1/sessions")
        assert created.status_code == 200
        old_session_id = created.json()["session_id"]

        reset = client.post(f"/api/v1/sessions/{old_session_id}/reset")
        assert reset.status_code == 200
        payload = reset.json()
        assert payload["session_id"] != old_session_id
        assert "Как я могу к тебе обращаться?" in payload["assistant_message"]
        assert payload["input_mode"] == "text"
        assert get_session(db, old_session_id).status == "reset"
    finally:
        app.dependency_overrides.clear()
