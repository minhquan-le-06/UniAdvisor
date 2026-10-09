"""Step 1 path "Em chưa biết gì" (spec 2, 3.5): the 12 questions of config/step7_questions.yaml, then the nhóm ngành
that fit the answers best, each with the student's own picks that speak for it. The student adds suggestions to the
same picks as the search path, then compares and orders them as usual.

Scores: the data scores (suggest.score) until the learned model is ready (suggest.model). The free-text box is read by
local rules into options (suggest.reader); the guesses are shown for the student to keep or drop, and only kept ones
become answers. Nothing is stored or sent: the answers and the text live in the Streamlit session only (the text is not
saved in the plan file).
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from uniadvisor.app.service import AppData
from uniadvisor.suggest.questions import Question

DROPDOWN_FROM = 9            # a capped question with more options than this: a dropdown (it enforces the cap)
METHOD_NOTE = ("Gợi ý được tính từ dữ liệu nghề nghiệp O*NET (sở thích nghề nghiệp, kiến thức cần có, điều kiện làm "
               "việc) và các tổ hợp xét tuyển của từng nhóm ngành. Đây là bản đầu tiên, chưa học từ câu trả lời của học "
               "sinh; em nên xem kỹ từng nhóm ngành trước khi chọn.")


def key(qid: str) -> str:
    return f"s7_{qid}"


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


def _hint(q: Question, number: dict[str, int]) -> str:
    if q.kind == "single":
        how = "chọn 1"
    elif q.max:
        how = f"chọn tối đa {q.max}"
    else:
        how = "chọn bao nhiêu cũng được"
    if q.not_in:
        how += f", khác câu {number[q.not_in]}"
    return how


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
    qn = d.suggester.qn
    number = {q.id: i for i, q in enumerate(qn.questions, 1)}
    answers, notes = {}, []
    for q in qn.questions:
        by = q.by_label()
        value = st.session_state.get(key(q.id))
        if q.kind == "single":
            answers[q.id] = by[value].code if value in by else None
            continue
        codes = [by[v].code for v in (value or []) if v in by]
        if q.not_in and answers.get(q.not_in):
            kept = [c for c in codes if c not in answers[q.not_in]]
            if len(kept) < len(codes):
                notes.append(f"Câu {number[q.id]}: bỏ lựa chọn trùng với câu {number[q.not_in]}.")
            codes = kept
        if q.max and len(codes) > q.max:
            notes.append(f"Câu {number[q.id]}: chỉ tính {q.max} lựa chọn đầu.")
            codes = codes[:q.max]
        answers[q.id] = codes or None
    return answers, notes


def guesses(d: AppData, text: str, answers: dict) -> list[tuple[str, str, str]]:
    """The reader's guesses the student has not ticked: (question id, option code, the words they came from)."""
    if d.reader is None or not text.strip():
        return []
    have = {(qid, c) for qid, v in answers.items() for c in ([v] if isinstance(v, str) else (v or []))}
    return [(g.question, g.option, g.words) for g in d.reader.read(text) if (g.question, g.option) not in have]


def _guess_text(d: AppData, number: dict, g: tuple[str, str, str]) -> str:
    q = d.suggester.qn.get(g[0])
    label = {o.code: o.label for o in q.options}[g[1]]
    return f"Câu {number[g[0]]}: {label} (từ “{g[2]}”)"


def _apply_guesses(d: AppData, number: dict):
    """Add the guesses the student kept to the answers (the questionnaire's rules apply: max picks, not_in)."""
    ss = st.session_state
    texts = {_guess_text(d, number, g): g for g in ss.get("s7_guesses", [])}
    for t in ss.get("s7_guess_keep") or []:
        qid, code, _ = texts[t]
        q = d.suggester.qn.get(qid)
        label = {o.code: o.label for o in q.options}[code]
        if q.kind == "single":
            ss[key(qid)] = label
        elif label not in (ss.get(key(qid)) or []):
            ss[key(qid)] = list(ss.get(key(qid)) or []) + [label]
    ss["s7_answers"], ss["s7_notes"] = collect(d)
    ss["s7_guesses"] = []


def _guess_panel(d: AppData, number: dict):
    found = st.session_state.get("s7_guesses") or []
    if not found:
        return
    options = [_guess_text(d, number, g) for g in found]
    with st.container(border=True):
        st.markdown("**Từ phần em kể, ứng dụng đoán thêm:**")
        st.pills("Em bỏ chọn điều nào không đúng, rồi bấm “Thêm vào câu trả lời”.", options, selection_mode="multi",
                 default=options, key="s7_guess_keep")
        st.button("Thêm vào câu trả lời", key="s7_guess_apply", on_click=_apply_guesses, args=(d, number))


def questionnaire(d: AppData, picks: list[str], max_picks: int, on_pick: Callable[[str], None]):
    s = d.suggester
    if s is None:
        st.info("Chưa có dữ liệu để gợi ý ngành.")
        return
    qn = s.qn
    number = {q.id: i for i, q in enumerate(qn.questions, 1)}
    st.subheader("Trả lời vài câu hỏi")
    st.caption("12 câu, khoảng 5 phút. Câu nào chưa chắc, em cứ bỏ qua. Câu trả lời chỉ nằm trong phiên làm việc "
               "này, ứng dụng không lưu lại.")
    with st.form("s7_form", border=True):
        for q in qn.questions:
            _widget(q, f"{number[q.id]}. {q.text} ({_hint(q, number)})")
        if d.reader is not None:
            st.text_area(qn.free_text_label + " (không bắt buộc)", key="s7_text", placeholder=qn.free_text_placeholder,
                         max_chars=1000)
        submitted = st.form_submit_button("Xem gợi ý", type="primary", icon=":material/lightbulb:")
    if submitted:
        st.session_state["s7_answers"], st.session_state["s7_notes"] = collect(d)
        st.session_state["s7_guesses"] = guesses(d, st.session_state.get("s7_text") or "",
                                                 st.session_state["s7_answers"])
    _guess_panel(d, number)
    answers = st.session_state.get("s7_answers")
    if not answers:
        return
    for note in st.session_state.get("s7_notes", []):
        st.caption(note)
    answered = sum(v is not None for v in answers.values())
    if answered == 0:
        st.info("Em chưa trả lời câu nào. Em chọn vài câu trả lời rồi bấm “Xem gợi ý” nhé.")
        return
    cfg = s.cfg["suggest"]
    st.subheader("Nhóm ngành có thể hợp với em")
    if answered < 4:
        st.caption("Em mới trả lời ít câu; trả lời thêm sẽ cho gợi ý sát hơn.")
    labels = {(q.id, o.code): o.label for q in qn.questions for o in q.options}
    cat = d.catalog
    for code, reasons in s.suggest(answers, cfg["top"], cfg["reasons"]):
        m = cat.majors[code]
        c1, c2 = st.columns([5, 1])
        text = f"**{m.label}**"
        if reasons:
            text += "  \n:gray[Vì em chọn: " + ", ".join(labels[r] for r in reasons) + "]"
        text += "  \n:gray[Gồm: " + ", ".join(cat.label(c) for c in m.children[:4]) + \
                (", ..." if len(m.children) > 4 else "") + "]"
        c1.markdown(text)
        picked = code in picks
        c2.button("Đã chọn" if picked else "Chọn", key=f"s7_add_{code}", on_click=on_pick, args=(code,),
                  disabled=picked or len(picks) >= max_picks)
    st.caption(METHOD_NOTE)
