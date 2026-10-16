"""The Streamlit session: data loading, session keys <-> PlanState, and the change history (every change is
applied through commit(), so it can be undone and its effect on the list described).

Everything here lives in the browser tab's session only.
"""

from __future__ import annotations

import streamlit as st

from uniadvisor.ui.discover import answer_widgets, defaults
from uniadvisor.ui.service import AppData, db_path, ensure_db
from uniadvisor.ui.state import COMPULSORY, MAX_CLOSE, MAX_ELECTIVES, PlanState, ShortlistEntry
from uniadvisor.chat.changes import Item
from uniadvisor.chat.diff import describe_diff
from uniadvisor.planner.models import ListResult

PAGES = ["1. Về em", "2. Chọn ngành", "3. Danh sách nguyện vọng", "4. Lưu kế hoạch"]
PATHS = ["Đã có ngành quan tâm", "Chưa xác định ngành"]
MAX_HISTORY = 30

# Widget keys kept across pages (Streamlit forgets a widget's value when its page is not drawn).
PERSISTENT = ("score_kind", "province", "area", "category", "grad_year", "budget", "near_home", "favorite_school",
              "path", "item1", "item2", "close1", "close2", "elective1", "elective2")


@st.cache_resource(show_spinner="Đang chuẩn bị dữ liệu...")
def _data(path: str) -> AppData:
    return AppData.load(ensure_db() if path == str(db_path()) else path)


def data() -> AppData:
    return _data(str(db_path()))


def init_session(d: AppData):
    ss = st.session_state
    ss.setdefault("page", PAGES[0])
    for code in d.subjects:
        ss.setdefault(f"score_{code}", None)
    ss.setdefault("score_kind", "expected")
    ss.setdefault("elective1", None)
    ss.setdefault("elective2", None)
    ss.setdefault("province", None)
    ss.setdefault("area", "KV3")
    ss.setdefault("category", "none")
    ss.setdefault("grad_year", d.admission_year)
    ss.setdefault("budget", None)
    ss.setdefault("near_home", False)
    ss.setdefault("favorite_school", None)
    ss.setdefault("path", PATHS[0])
    ss.setdefault("picks", [])
    ss.setdefault("item1", None)
    ss.setdefault("item2", None)
    ss.setdefault("close1", [])
    ss.setdefault("close2", [])
    ss.setdefault("extra_points", {})
    ss.setdefault("own_scores", {})
    ss.setdefault("cutoff_shifts", {})
    ss.setdefault("removed_schools", [])
    ss.setdefault("removed_programs", [])
    ss.setdefault("history", [])
    ss.setdefault("chat_log", [])
    ss.setdefault("list_choice", None)
    ss.setdefault("recommended", [])
    questions = defaults(d)                     # questionnaire answers, kept while the student switches pages
    for k, v in questions.items():
        ss.setdefault(k, v)
    for key in [f"score_{c}" for c in d.subjects] + list(PERSISTENT) + list(questions):
        ss[key] = ss[key]


def exam_subjects(d: AppData) -> list[str]:
    """The subjects whose scores count: Toán, Ngữ văn and the two the student chose on Về em."""
    ss = st.session_state
    chosen = [c for c in COMPULSORY if c in d.subjects]
    return chosen + [ss[k] for k in ("elective1", "elective2") if ss.get(k) in d.subjects and ss[k] not in chosen]


def current_state(d: AppData) -> PlanState:
    ss = st.session_state
    shortlist = []
    for i in (1, 2):
        main = ss.get(f"item{i}")
        if main and main not in [e.main for e in shortlist]:
            shortlist.append(ShortlistEntry(main, [c for c in ss.get(f"close{i}", []) if c != main][:MAX_CLOSE]))
    return PlanState(
        scores={c: float(ss[f"score_{c}"]) for c in exam_subjects(d) if ss.get(f"score_{c}") is not None},
        score_kind=ss["score_kind"], home_province=ss["province"], area=ss["area"], category=ss["category"],
        graduation_year=int(ss["grad_year"]) if ss["grad_year"] is not None else None,
        budget_trieu=float(ss["budget"]) if ss["budget"] is not None else None, near_home=bool(ss["near_home"]),
        favorite_school=ss["favorite_school"],
        picks=list(ss["picks"]), shortlist=shortlist, extra_points=dict(ss["extra_points"]),
        own_scores=dict(ss["own_scores"]), cutoff_shifts=dict(ss["cutoff_shifts"]),
        removed_schools=list(ss["removed_schools"]), removed_programs=list(ss["removed_programs"]),
        answers=dict(ss.get("quiz_answers") or {}), list_choice=ss.get("list_choice"),
        recommended=list(ss.get("recommended", [])),
    )


def apply_state(state: PlanState, d: AppData):
    """Put a plan into the widgets' session keys (called from a callback, before the widgets exist)."""
    ss = st.session_state
    for code in d.subjects:
        ss[f"score_{code}"] = state.scores.get(code)
    electives = [c for c in d.subjects if c in state.scores and c not in COMPULSORY][:MAX_ELECTIVES]
    ss["elective1"], ss["elective2"] = (electives + [None, None])[:2]
    ss["score_kind"], ss["province"], ss["area"], ss["category"] = (state.score_kind, state.home_province,
                                                                    state.area, state.category)
    ss["grad_year"] = state.graduation_year or d.admission_year
    ss["budget"], ss["near_home"] = state.budget_trieu, state.near_home
    ss["favorite_school"] = state.favorite_school
    picks = list(state.picks)
    for e in state.shortlist:
        if e.main not in picks:
            picks.append(e.main)
    ss["picks"] = picks
    for i in (1, 2):
        entry = state.shortlist[i - 1] if len(state.shortlist) >= i else None
        ss[f"item{i}"] = entry.main if entry else None
        ss[f"close{i}"] = list(entry.close) if entry else []
    ss["extra_points"] = dict(state.extra_points)
    ss["own_scores"], ss["cutoff_shifts"] = dict(state.own_scores), dict(state.cutoff_shifts)
    ss["removed_schools"], ss["removed_programs"] = list(state.removed_schools), list(state.removed_programs)
    ss["list_choice"], ss["recommended"] = state.list_choice, list(state.recommended)
    ss["quiz_answers"] = dict(state.answers) or None
    for k, v in answer_widgets(d, state.answers).items():       # the questionnaire shows the loaded answers
        ss[k] = v


def list_for(d: AppData, state: PlanState) -> ListResult | None:
    return d.list_for(state)


def commit(d: AppData, items: list[Item]) -> dict:
    """Apply changes (in order) as one step of the history; 'undo' items undo first. Returns and remembers
    {'done': [...], 'errors': [...], 'diff': str} for the page to show."""
    ss = st.session_state
    done, errors = [], []
    old = current_state(d)
    undo = any(i.kind == "undo" for i in items)
    if undo:
        if ss["history"]:
            apply_state(ss["history"].pop(), d)
            done.append("Hoàn tác thay đổi gần nhất")
        else:
            errors.append("Chưa có thay đổi nào để hoàn tác.")
    start = current_state(d)
    res = d.apply_items(start, items, before=old)
    done += res.done
    errors += res.errors
    diff = res.diff
    if res.applied:
        ss["history"] = (ss["history"] + [start])[-MAX_HISTORY:]
        apply_state(res.state, d)
    elif done:                             # an undo alone still changes the list
        final = current_state(d)
        diff = describe_diff(list_for(d, old), list_for(d, final), old, final)
    ss["last_change"] = {"done": done, "errors": errors, "diff": diff}
    return ss["last_change"]
