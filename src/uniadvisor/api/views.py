"""JSON for the web pages. Every function takes the loaded AppData and a student's PlanState and returns plain
dicts and lists (what the page shows, already worded), built from the same functions the Streamlit pages use
(ui/list_view.py, ui/quiz.py, ui/major_info.py, ui/texts.py ...). Nothing here reads a table row out: only results
computed for one student, names and fixed texts leave the server.
"""

from __future__ import annotations

from uniadvisor.chat.changes import CHANGE_KINDS, Item, describe
from uniadvisor.chat.pipeline import Reply
from uniadvisor.explanations import build_wish_explanation
from uniadvisor.planner.lists import CORNERS, Priority, Recommended
from uniadvisor.planner.models import LEVEL_ORDER, ListResult
from uniadvisor.ui import list_view, quiz
from uniadvisor.ui.change_card import DEFAULT_RANGE, NUMBER_RANGES, param_label
from uniadvisor.ui.facts import ONET_CREDIT
from uniadvisor.ui.list_summary import LIST_VI, unknown_fees_text
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import (AREAS, CATEGORIES, COMPULSORY, MAX_CLOSE, MAX_CUTOFF_SHIFT, MAX_ELECTIVES, MAX_ITEMS,
                                 SCALES, SCORE_KINDS, PlanState)
from uniadvisor.config import load_data_config
from uniadvisor.planner.chances import Chances
from uniadvisor.ui.texts import (CATEGORY_VI, CHANCE_LEVEL_VI, CHANCE_SHIFT_VI, EXTRA_POINTS_REMINDER,
                                 HOW_THE_LIST_IS_BUILT, INCOME_CONTEXT, LEVEL_HELP, LEVEL_VI, MIXED_METHOD_NOTE,
                                 chance_lines, chance_note, chance_pct, city_text, cutoff_text, favorite_note,
                                 no_admission_warning, note_texts, relation_text, student_score_text, tuition_text,
                                 wish_rows)

MAX_PICKS = 6                     # ngành a student can pick to compare (the Streamlit page's limit)
# Electives in the order students know them (the THPT exam since 2025); other exam subjects follow.
ELECTIVE_ORDER = ["N1", "LI", "HO", "SI", "SU", "DI", "GDKTPL", "TI", "CNCN", "CNNN"]
SLOT = {Priority.NGANH: 0, Priority.CAREER: 1, Priority.MON: 1, Priority.COST: 2}   # one colour slot per list
MISSING_VI = {"scores": "điểm các môn (phần Về em)", "home_province": "tỉnh/thành nơi em ở (phần Về em)",
              "shortlist": "hướng học 1 (phần Xếp hướng học)"}


# ---------------------------------------------------------------- meta

def meta(d: AppData) -> dict:
    """What the forms need before any student data: choices, limits and the fixed texts."""
    electives = [c for c in ELECTIVE_ORDER if c in d.subjects and c not in COMPULSORY]
    electives += [c for c in d.subjects if c not in electives and c not in COMPULSORY]
    return {
        "admission_year": d.admission_year,
        "subjects": [{"code": c, "name": n} for c, n in d.subjects.items()],
        "compulsory": [c for c in COMPULSORY if c in d.subjects],
        "electives": electives,
        "max_electives": MAX_ELECTIVES,
        "provinces": d.provinces,
        "areas": [{"code": a, "label": a} for a in AREAS],
        "categories": [{"code": c, "label": CATEGORY_VI[c]} for c in CATEGORIES],
        "score_kinds": list(SCORE_KINDS),
        "schools": sorted(({"code": c, "name": n} for c, n in d.school_names.items()), key=lambda s: s["name"]),
        "limits": {"max_picks": MAX_PICKS, "max_items": MAX_ITEMS, "max_close": MAX_CLOSE, "scales": list(SCALES),
                   "max_cutoff_shift": MAX_CUTOFF_SHIFT},
        "number_ranges": {k: list(v) for k, v in NUMBER_RANGES.items()} | {"default": list(DEFAULT_RANGE)},
        "questions": quiz.definitions(d),
        "has_free_text": d.reader is not None,
        "texts": {
            "how_the_list_is_built": HOW_THE_LIST_IS_BUILT,
            "levels": [{"code": lv.value, "name": LEVEL_VI[lv], "help": LEVEL_HELP[lv]} for lv in reversed(LEVEL_ORDER)],
            "extra_points_reminder": EXTRA_POINTS_REMINDER,
            "mixed_method_note": MIXED_METHOD_NOTE,
            "income_context": INCOME_CONTEXT,
            "onet_credit": ONET_CREDIT,
            "quiz_method_note": quiz.METHOD_NOTE,
            "pentagon_note": list_view.PENTAGON_NOTE,
            "lists": [{"priority": p.value, "name": LIST_VI[p], "help": list_view.LIST_HELP[p], "slot": SLOT[p]}
                      for p in Priority],
            "corners": [{"code": c, "name": list_view.CORNER_VI[c], "help": list_view.CORNER_HELP[c]} for c in CORNERS],
        },
    }


def catalog(d: AppData) -> list[dict]:
    """Every ngành and nhóm ngành a student can pick, for the dropdowns (names only)."""
    return [{"code": c, "label": m.label, "level": m.level} for c, m in sorted(d.catalog.majors.items())]


def proposed_close(d: AppData, code: str, exclude: set[str]) -> list[dict]:
    codes = d.facts.proposed_close(code, MAX_CLOSE, exclude=exclude | {code})
    nganh = set(d.catalog.nganh_codes())
    return [{"code": c, "label": d.catalog.label(c)} for c in codes if c in nganh]


# ---------------------------------------------------------------- questionnaire

def questionnaire(d: AppData, picked: dict, text: str) -> dict:
    """Clean the answers, read the free text into guesses the student may keep, and suggest nhóm ngành."""
    if d.suggester is None:
        return {"answers": {}, "notes": [], "guesses": [], "suggestions": [], "answered": 0}
    answers, notes = quiz.normalize_answers(d.suggester.qn, picked)
    number = quiz.numbering(d.suggester.qn)
    guesses = [{"question": q, "option": o, "words": w, "text": quiz.guess_text(d, number, (q, o, w))}
               for q, o, w in quiz.guesses(d, text or "", answers)]
    return {"answers": answers, "notes": notes, "guesses": guesses, "suggestions": quiz.suggestions(d, answers),
            "answered": sum(v is not None for v in answers.values())}


# ---------------------------------------------------------------- wishes and chances, structured for cards

def wish_items(result: ListResult, items: list[str], catalog) -> list[dict]:
    """One entry per wish with its parts apart (the same words as the table rows of `wish_rows`)."""
    years = load_data_config()["cutoff_years"]
    out = []
    for w in result.wishes:
        c = w.candidate
        out.append({
            "nv": w.nv, "program_id": c.program.id, "level": c.level.value, "level_name": LEVEL_VI[c.level],
            "school": c.program.school_name, "school_code": c.program.school_code, "program": c.program.name,
            "mixed": c.is_mixed_method, "other_codes": [pid.split(":", 1)[-1] for pid in c.other_codes],
            "item": c.item_index + 1, "relation": relation_text(c, items, catalog),
            "score": student_score_text(c), "score_value": round(c.student.score, 2),
            "cutoffs": [{"year": y, "text": cutoff_text(c, y, with_year=False) or "chưa có"} for y in years],
            "tuition": tuition_text(c), "over_budget": c.over_budget,
            "city": city_text(c), "far": c.far_from_home, "favorite": c.favorite,
        })
    return out


def chance_rows(chs: list[Chances], cap: float, expected: bool) -> list[dict]:
    """Per score shift, the chance of each level or better: the numbers behind `chance_lines`, for bars."""
    return [{"shift": ch.score_shift,
             "label": CHANCE_SHIFT_VI.get(ch.score_shift, "Với điểm của em") if expected else "Với điểm của em",
             "levels": [{"level": lv.value, "name": CHANCE_LEVEL_VI[lv], "p": round(p, 4), "text": chance_pct(p, cap)}
                        for lv, p in ch.at_least.items()]} for ch in chs]


# ---------------------------------------------------------------- the three lists

def _pentagon(rec: Recommended) -> dict | None:
    if not rec.pentagon:
        return None
    return {"values": dict(rec.pentagon.values), "unknown": dict(rec.pentagon.unknown), "none": rec.pentagon.none}


def recommend(d: AppData, state: PlanState) -> dict:
    """The three lists as cards, the recommended one, and the table of corners."""
    missing = state.missing_for_list()
    if missing:
        return {"missing": missing, "missing_text": [MISSING_VI[m] for m in missing]}
    recs = d.recommend(state)
    summary = list_view.summary(d, state, recs)
    cap = d.list_cfg["chances"]["display_cap"]
    pick = summary.pick
    items = [e.main for e in state.shortlist]
    cards = []
    for rec, card in zip(recs, summary.cards):
        cards.append({
            "priority": rec.priority.value, "slot": SLOT[rec.priority], "name": card.name, "fit": card.fit,
            "good": card.good, "bad": card.bad, "notes": card.notes, "warning": card.warning,
            "same_as": card.same_as, "blocked": card.blocked,
            "recommended": bool(pick and pick.priority is rec.priority),
            "pentagon": None if card.blocked else _pentagon(rec),
            "n_wishes": len(rec.result.wishes),
            "wishes": None if card.blocked else wish_rows(rec.result, items, d.catalog),
            "wish_items": None if card.blocked else wish_items(rec.result, items, d.catalog),
            "no_admission": rec.chances.none if rec.chances else None,
        })
    return {
        "missing": [], "intro": summary.intro, "safe_line": summary.safe_line, "notes": summary.notes,
        "pick": {"priority": pick.priority.value, "name": pick.name, "reason": pick.reason} if pick else None,
        "cards": cards,
        "no_answers_note": None if list_view.has_career(recs) else list_view.NO_ANSWERS_NOTE,
        "corner_rows": list_view.corner_rows(recs),
        "at_least_one_text": list_view.at_least_one_text(recs, cap),
        "snapshot": list_view.snapshot(recs),
    }


# ---------------------------------------------------------------- the chosen list

def _controls(d: AppData, state: PlanState, result: ListResult) -> dict:
    """What the adjust panel needs: per-school numbers, the wishes and schools that can be removed, what was removed."""
    schools = []
    for w in result.wishes:
        code = w.candidate.program.school_code
        if code not in schools:
            schools.append(code)
    schools += [s for s in [*state.extra_points, *state.own_scores, *state.cutoff_shifts] if s not in schools]
    schools = list(dict.fromkeys(schools))
    scales = d.chat_context(state, result).scales
    prog = d.programs_by_id
    return {
        "schools": [{"code": s, "name": d.all_school_names.get(s, s), "extra": state.extra_points.get(s, 0.0),
                     "own": state.own_scores[s][0] if s in state.own_scores else None,
                     "scales": list(scales.get(s, ())), "shift": state.cutoff_shifts.get(s, 0.0)} for s in schools],
        "wishes": [{"id": w.candidate.program.id, "nv": w.nv,
                    "label": f"NV{w.nv} · {w.candidate.program.school_name} · {w.candidate.program.name}"}
                   for w in result.wishes],
        "removed_schools": [{"code": s, "name": d.all_school_names.get(s, s)} for s in state.removed_schools],
        "removed_programs": [{"id": p, "label": f"{prog[p].school_name} · {prog[p].name}" if p in prog else p}
                             for p in state.removed_programs],
        "shortlist": [{"main": e.main, "label": d.catalog.label(e.main),
                       "close": [{"code": c, "label": d.catalog.label(c)} for c in e.close]} for e in state.shortlist],
        "scores": dict(state.scores), "area": state.area, "category": state.category,
        "budget_trieu": state.budget_trieu, "near_home": state.near_home,
    }


def chosen(d: AppData, state: PlanState) -> dict:
    """The page after the student chose a list: its header, the wishes, how the chances look and the controls."""
    missing = state.missing_for_list()
    if missing:
        return {"missing": missing, "missing_text": [MISSING_VI[m] for m in missing]}
    rec = d.chosen(state)
    result = rec.result if rec is not None else d.build_list(state)
    items = [e.main for e in state.shortlist]
    cc = d.list_cfg["chances"]
    header = None
    if rec is not None:
        header = {
            "priority": rec.priority.value, "name": LIST_VI[rec.priority], "help": list_view.LIST_HELP[rec.priority],
            "slot": SLOT[rec.priority], "pentagon": _pentagon(rec),
            "fallback_note": list_view.CAREER_FALLBACK_NOTE
            if state.list_choice == Priority.CAREER.value and rec.priority is Priority.MON else None,
            "fees_note": unknown_fees_text(rec),
        }
    out = {
        "missing": [], "header": header,
        "list_choice": state.list_choice, "empty": not result.wishes,
        "empty_text": "Chưa lập được nguyện vọng nào: không có chương trình nào của ngành em chọn có điểm chuẩn mà em "
                      "có đủ điểm các môn trong tổ hợp xét tuyển.",
        "notes": note_texts(result, items, d.catalog),
        "favorite_note": favorite_note(d.school_names[state.favorite_school], result)
        if state.favorite_school in d.school_names else None,
        "expected_note": state.score_kind == "expected",
        "mixed_method": any(w.candidate.is_mixed_method for w in result.wishes),
        "wishes": wish_rows(result, items, d.catalog),
        "wish_items": wish_items(result, items, d.catalog),
        "wish_numbers": [w.nv for w in result.wishes],
        "levels": [LEVEL_VI[w.candidate.level] for w in result.wishes],
        "score_caption": "Điểm chuẩn là của phương thức xét điểm thi THPT, quy đổi về thang 30. Điểm của em gồm tổng 3 "
                         f"môn của tổ hợp có lợi nhất và điểm ưu tiên ({state.area}, "
                         f"{CATEGORY_VI[state.category].lower()}).",
        "controls": _controls(d, state, result),
    }
    chs = d.chances(state, result)
    at_entered = next((c for c in chs if c.score_shift == 0.0), None)
    out["no_admission_warning"] = (no_admission_warning(at_entered.none, cc["display_cap"])
                                   if at_entered and at_entered.none > cc["warn_no_admission_above"] else None)
    out["chances"] = {"lines": chance_lines(chs, cc["display_cap"], state.score_kind == "expected"),
                      "rows": chance_rows(chs, cc["display_cap"], state.score_kind == "expected"),
                      "note": chance_note(d.change_model.years)} if chs else None
    return out


def explain(d: AppData, state: PlanState, nv: int) -> dict | None:
    """The fixed explanation of one wish of the list the student sees ("Vì sao NVn ở đây?")."""
    result = d.list_for(state)
    if result is None:
        return None
    wish = next((w for w in result.wishes if w.nv == nv), None)
    if wish is None:
        return None
    e = build_wish_explanation(wish, d.chat_context(state, result))
    return {"wish_no": e.wish_no, "level": e.level, "title": e.title, "verdict": e.verdict,
            "numbers": list(e.numbers), "why_in_list": e.why_in_list, "placement": e.placement,
            "notices": list(e.notices), "markdown": e.markdown()}


# ---------------------------------------------------------------- chat and changes

def item_json(item: Item, d: AppData, state: PlanState, result: ListResult | None) -> dict:
    """A change for the card: what it says, what is still open and the choices for it."""
    ctx = d.chat_context(state, result)
    return {
        "kind": item.kind, "params": item.params, "text": item.text, "open": list(item.open),
        "options": {p: [[v, label] for v, label in opts] for p, opts in item.options.items()},
        "description": describe(item, ctx),
        "labels": {p: param_label(item, p) for p in item.open},
        "range": list(NUMBER_RANGES.get(item.kind, DEFAULT_RANGE)),
    }


def chat_reply(d: AppData, state: PlanState, reply: Reply) -> dict:
    result = d.list_for(state)
    return {"answers": list(reply.answers), "help": reply.help,
            "items": [item_json(i, d, state, result) for i in reply.items]}


def item_from_json(raw: dict) -> Item:
    """The change the student confirmed (open parameters filled in); raises ValueError when it is not one."""
    kind = raw.get("kind")
    if kind not in CHANGE_KINDS:
        raise ValueError("Thay đổi không hợp lệ.")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("Thay đổi không hợp lệ.")
    return Item(kind, dict(params), {}, list(raw.get("open") or []), str(raw.get("text") or ""))
