"""The "Chưa xác định ngành" path: the 12 questions of config/questionnaire.yaml, then the nhóm ngành
that fit the answers best, each with the student's own picks that speak for it. The student adds suggestions to the
same picks as the search path, then compares and orders them as usual.

Scores: the data scores (majors.score) until the learned model is ready (majors.model). The free-text box is read by
local rules into options (majors.reader); the guesses are shown for the student to keep or drop, and only kept ones
become answers. Nothing is stored or sent: the answers and the text live in the Streamlit session only (the text is not
saved in the plan file).
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from uniadvisor.ui.quiz import METHOD_NOTE, guess_text, guesses, hint, normalize_answers, numbering, suggestions
from uniadvisor.ui.service import AppData
from uniadvisor.majors.questions import Question

DROPDOWN_FROM = 9            # a capped question with more options than this: a dropdown (it enforces the cap)
def key(qid: str) -> str:
    return f"quiz_{qid}"


def defaults(d: AppData) -> dict[str, object]:
    """Session keys of the questions and their empty values (session.init_session keeps them across pages)."""
    if d.suggester is None:
        return {}
    return {key(q.id): (None if q.kind == "single" else []) for q in d.suggester.qn.questions}


def answer_widgets(d: AppData, answers: dict) -> dict[str, object]:
    """Option codes (a loaded plan) -> the questionnaire widgets' values (labels)."""
    if d.suggester is None:
        return {}
    out = defaults(d)
    for q in d.suggester.qn.questions:
        label = {o.code: o.label for o in q.options}
        value = answers.get(q.id)
        if q.kind == "single":
            out[key(q.id)] = label.get(value) if isinstance(value, str) else None
        elif isinstance(value, list):
            out[key(q.id)] = [label[c] for c in value if c in label]
    return out


def _widget(q: Question, title: str):
    labels = [o.label for o in q.options]
    if q.kind == "single":
        st.pills(title, labels, key=key(q.id), selection_mode="single")
    elif q.max and len(labels) > DROPDOWN_FROM:
        st.multiselect(title, labels, key=key(q.id), max_selections=q.max, placeholder="Bỏ qua")
    else:
        st.pills(title, labels, key=key(q.id), selection_mode="multi")


def collect(d: AppData) -> tuple[dict, list[str]]:
    """The answers as option codes, with the questionnaire's rules applied; notes on what was changed."""
    picked = {}
    for q in d.suggester.qn.questions:
        by = q.by_label()
        value = st.session_state.get(key(q.id))
        picked[q.id] = ((by[value].code if value in by else None) if q.kind == "single"
                        else [by[v].code for v in (value or []) if v in by])
    return normalize_answers(d.suggester.qn, picked)


def _apply_guesses(d: AppData, number: dict):
    """Add the guesses the student kept to the answers (the questionnaire's rules apply: max picks, not_in)."""
    ss = st.session_state
    texts = {guess_text(d, number, g): g for g in ss.get("quiz_guesses", [])}
    for t in ss.get("quiz_guess_keep") or []:
        qid, code, _ = texts[t]
        q = d.suggester.qn.get(qid)
        label = {o.code: o.label for o in q.options}[code]
        if q.kind == "single":
            ss[key(qid)] = label
        elif label not in (ss.get(key(qid)) or []):
            ss[key(qid)] = list(ss.get(key(qid)) or []) + [label]
    ss["quiz_answers"], ss["quiz_notes"] = collect(d)
    ss["quiz_guesses"] = []


def _guess_panel(d: AppData, number: dict):
    found = st.session_state.get("quiz_guesses") or []
    if not found:
        return
    options = [guess_text(d, number, g) for g in found]
    with st.container(border=True):
        st.markdown("**Từ phần em kể, ứng dụng đoán thêm:**")
        st.pills("Em bỏ chọn điều nào không đúng, rồi bấm “Thêm vào câu trả lời”.", options, selection_mode="multi",
                 default=options, key="quiz_guess_keep")
        st.button("Thêm vào câu trả lời", key="quiz_guess_apply", on_click=_apply_guesses, args=(d, number))


def questionnaire(d: AppData, picks: list[str], max_picks: int, on_pick: Callable[[str], None]):
    s = d.suggester
    if s is None:
        st.info("Chưa có dữ liệu để gợi ý ngành.")
        return
    qn = s.qn
    number = numbering(qn)
    st.subheader("Trả lời vài câu hỏi")
    st.caption("12 câu, khoảng 5 phút. Câu nào chưa chắc, em cứ bỏ qua. Câu trả lời chỉ nằm trong phiên làm việc "
               "này, ứng dụng không lưu lại.")
    with st.form("quiz_form", border=True):
        for q in qn.questions:
            _widget(q, f"{number[q.id]}. {q.text} ({hint(q, number)})")
        if d.reader is not None:
            st.text_area(qn.free_text_label + " (không bắt buộc)", key="quiz_text", placeholder=qn.free_text_placeholder,
                         max_chars=1000)
        submitted = st.form_submit_button("Xem gợi ý", type="primary", icon=":material/lightbulb:")
    if submitted:
        st.session_state["quiz_answers"], st.session_state["quiz_notes"] = collect(d)
        st.session_state["quiz_guesses"] = guesses(d, st.session_state.get("quiz_text") or "",
                                                 st.session_state["quiz_answers"])
    _guess_panel(d, number)
    answers = st.session_state.get("quiz_answers")
    if not answers:
        return
    for note in st.session_state.get("quiz_notes", []):
        st.caption(note)
    answered = sum(v is not None for v in answers.values())
    if answered == 0:
        st.info("Em chưa trả lời câu nào. Em chọn vài câu trả lời rồi bấm “Xem gợi ý” nhé.")
        return
    st.subheader("Nhóm ngành có thể hợp với em")
    if answered < 4:
        st.caption("Em mới trả lời ít câu; trả lời thêm sẽ cho gợi ý sát hơn.")
    for sug in suggestions(d, answers):
        code = sug["code"]
        c1, c2 = st.columns([5, 1])
        text = f"**{sug['label']}**"
        if sug["reasons"]:
            text += "  \n:gray[Vì em chọn: " + ", ".join(sug["reasons"]) + "]"
        text += "  \n:gray[Gồm: " + ", ".join(sug["children"]) + (", ..." if sug["more_children"] else "") + "]"
        c1.markdown(text)
        picked = code in picks
        c2.button("Đã chọn" if picked else "Chọn", key=f"quiz_add_{code}", on_click=on_pick, args=(code,),
                  disabled=picked or len(picks) >= max_picks)
    st.caption(METHOD_NOTE)
