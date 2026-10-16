"""The Streamlit-free view logic the pages and the web API share: the questionnaire rules, the change step and the
list view helpers."""

import pytest

from uniadvisor.chat.changes import Item
from uniadvisor.majors.questions import Option, Question, Questionnaire
from uniadvisor.planner.lists import Priority
from uniadvisor.ui import list_view, major_info, quiz
from uniadvisor.ui.change_card import DEFAULT_RANGE, NUMBER_RANGES, param_label
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import PlanState, ShortlistEntry

QN = Questionnaire(
    questions=(
        Question("q1", "Một câu", "single", (Option("a", "A"), Option("b", "B"))),
        Question("q2", "Thích", "multi", (Option("x", "X"), Option("y", "Y"), Option("z", "Z")), max=2),
        Question("q3", "Không thích", "multi", (Option("x", "X"), Option("y", "Y"), Option("w", "W")), not_in="q2"),
    ),
    subjects_knowledge={}, free_text_label="", free_text_placeholder="")


def test_answers_keep_valid_codes_and_apply_the_limits():
    answers, notes = quiz.normalize_answers(QN, {"q1": "b", "q2": ["x", "y", "z", "nope"], "q3": ["x", "w"]})
    assert answers == {"q1": "b", "q2": ["x", "y"], "q3": ["w"]}
    assert notes == ["Câu 2: chỉ tính 2 lựa chọn đầu.", "Câu 3: bỏ lựa chọn trùng với câu 2."]


def test_empty_and_wrong_answers_become_none():
    answers, notes = quiz.normalize_answers(QN, {"q1": "zzz", "q2": [], "q3": None})
    assert answers == {"q1": None, "q2": None, "q3": None} and notes == []
    assert quiz.normalize_answers(QN, {"q1": ["a"]})[0]["q1"] is None            # a list is not a single answer


def test_hint_words():
    number = quiz.numbering(QN)
    assert quiz.hint(QN.questions[0], number) == "chọn 1"
    assert quiz.hint(QN.questions[1], number) == "chọn tối đa 2"
    assert quiz.hint(QN.questions[2], number) == "chọn bao nhiêu cũng được, khác câu 2"


@pytest.fixture(scope="module")
def data(fake_db_path):
    return AppData.load(fake_db_path)


def student():
    return PlanState(scores={"TO": 8.0, "VA": 7.0, "LI": 7.0, "N1": 8.0}, home_province="Hà Nội",
                     shortlist=[ShortlistEntry("7480201", [])])


def test_apply_items_reports_done_errors_and_the_diff(data):
    start = student()
    res = data.apply_items(start, [Item("set_score", {"subject": "TO", "value": 9.5}),
                                   Item("set_score", {"subject": "TO", "value": 12}), Item("undo")])
    assert res.applied and res.state.scores["TO"] == 9.5 and start.scores["TO"] == 8.0   # the input is not changed
    assert len(res.done) == 1 and len(res.errors) == 1 and res.diff
    none = data.apply_items(start, [Item("set_score", {"subject": "TO", "value": 12})])
    assert not none.applied and none.state is start and none.diff == ""


def test_list_for_waits_for_what_the_list_needs(data):
    assert data.list_for(PlanState()) is None
    assert data.list_for(student()).wishes


def test_list_view_words_and_table(data):
    state = student()
    recs = data.recommend(state)
    snap = list_view.snapshot(recs)
    assert [r["priority"] for r in snap] == [r.priority.value for r in recs]
    rows = list_view.corner_rows(recs)
    assert [r["Góc"] for r in rows] == ["Hợp môn", "Nguyện vọng cao", "Đúng ngành", "Học phí phù hợp", "Nghề nghiệp"]
    assert "Đúng ngành nhất" in rows[0]
    assert set(list_view.LIST_HELP) == set(Priority)
    assert list_view.summary(data, state, recs).cards


def test_major_info(data):
    hit = major_info.search(data, "cntt")[0]
    assert hit["code"] == "7480201" and hit["where"].endswith("ở TP.HCM")
    detail = major_info.detail(data, "7480201")
    assert detail["kind"] == "Ngành" and detail["income"]
    assert major_info.credit([detail]) is None or "O*NET" in major_info.credit([detail])


def test_change_card_words():
    assert NUMBER_RANGES["set_score"] == (0.0, 10.0, 0.25) and DEFAULT_RANGE[1] == 1000.0
    assert param_label(Item("set_cutoff_shift"), "value").startswith("Cao hơn bao nhiêu điểm")
    assert param_label(Item("set_score"), "subject") == "Môn nào?"


def test_suggestions_work_with_a_learned_scorer(data):
    """Whatever scorer the database loads (the data scores, or the learned model once it is ready), the questions
    produce suggestions: the real database loads the learned one."""
    import numpy as np
    from uniadvisor.majors.model import Features, LearnedScorer
    base = data.suggester
    scorer = getattr(base, "data", base)
    features = Features.from_questionnaire(scorer)
    learned = LearnedScorer(scorer, features, 1.0, np.zeros((len(features.options), len(scorer.codes))))
    data.suggester = learned
    try:
        q = scorer.qn.questions[0]
        answers = {q.id: q.options[0].code if q.kind == "single" else [q.options[0].code]}
        out = quiz.suggestions(data, answers)
        assert out and {"code", "label", "reasons", "children"} <= set(out[0])
    finally:
        data.suggester = base
