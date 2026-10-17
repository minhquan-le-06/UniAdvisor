"""The 12-question flow without Streamlit: the questions as data, the rules that clean the answers, the reader's guesses
from free text and the nhóm ngành suggested. discover.py draws them in Streamlit; the web API (api/views.py) returns
them as JSON.
"""

from __future__ import annotations

from uniadvisor.majors.questions import Question
from uniadvisor.ui.service import AppData

METHOD_NOTE = ("Gợi ý được tính từ dữ liệu nghề nghiệp O*NET (sở thích nghề nghiệp, kiến thức cần có, điều kiện làm "
               "việc) và các tổ hợp xét tuyển của từng nhóm ngành, cộng với trọng số mô hình học từ hồ sơ học sinh giả định "
               "do mô hình ngôn ngữ viết, chưa học từ câu trả lời của học sinh thật; em nên xem kỹ từng nhóm ngành "
               "trước khi chọn.")


def reason_label(q: Question, o) -> str:
    """An answer as a reason after "Vì em chọn": a disliked subject, topic or working condition says so, so that
    "Sức khỏe" picked under "không muốn học" is not read as a liked topic."""
    if o.subject and q.negative:
        return f"không thích {o.label}"
    if q.negative:
        return f"không muốn học {o.label[0].lower()}{o.label[1:]}"
    if any(x.against for x in q.options):              # q12: working conditions the student does not want
        return f"không muốn {o.label[0].lower()}{o.label[1:]}"
    return o.label


def hint(q: Question, number: dict[str, int]) -> str:
    if q.kind == "single":
        how = "chọn 1"
    elif q.max:
        how = f"chọn tối đa {q.max}"
    else:
        how = "chọn bao nhiêu cũng được"
    if q.not_in:
        how += f", khác câu {number[q.not_in]}"
    return how


def numbering(qn) -> dict[str, int]:
    return {q.id: i for i, q in enumerate(qn.questions, 1)}


def normalize_answers(qn, picked: dict) -> tuple[dict, list[str]]:
    """The answers as option codes, with the questionnaire's rules applied; notes on what was changed.
    `picked`: question id -> one option code (single) or a list of codes (multiple); unknown codes are ignored."""
    number = numbering(qn)
    answers, notes = {}, []
    for q in qn.questions:
        valid = {o.code for o in q.options}
        value = picked.get(q.id)
        if q.kind == "single":
            answers[q.id] = value if isinstance(value, str) and value in valid else None
            continue
        codes = [c for c in (value or []) if c in valid]
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


def definitions(d: AppData) -> list[dict]:
    """The questions for a form: id, number, text, how many to pick, and the options."""
    if d.suggester is None:
        return []
    qn = d.suggester.qn
    number = numbering(qn)
    return [{"id": q.id, "number": number[q.id], "text": q.text, "kind": q.kind, "max": q.max,
             "not_in": q.not_in, "hint": hint(q, number),
             "options": [{"code": o.code, "label": o.label} for o in q.options]} for q in qn.questions]


def guesses(d: AppData, text: str, answers: dict) -> list[tuple[str, str, str]]:
    """The reader's guesses the student has not ticked: (question id, option code, the words they came from)."""
    if d.reader is None or not text.strip():
        return []
    have = {(qid, c) for qid, v in answers.items() for c in ([v] if isinstance(v, str) else (v or []))}
    return [(g.question, g.option, g.words) for g in d.reader.read(text) if (g.question, g.option) not in have]


def maybe_guesses(d: AppData, text: str, answers: dict, rule_guesses: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """What the rules did not see, read by meaning (majors/semantic.py); [] when the model is not available."""
    if d.semantic is None or not text.strip():
        return []
    have = {(qid, c) for qid, v in answers.items() for c in ([v] if isinstance(v, str) else (v or []))}
    have |= {(q, o) for q, o, _ in rule_guesses}
    return [(g.question, g.option, g.words) for g in d.semantic.read(text, have)]


def guess_text(d: AppData, number: dict, g: tuple[str, str, str]) -> str:
    q = d.suggester.qn.get(g[0])
    label = {o.code: o.label for o in q.options}[g[1]]
    return f"Câu {number[g[0]]}: {label} (từ “{g[2]}”)"


def suggestions(d: AppData, answers: dict) -> list[dict]:
    """The nhóm ngành that fit the answers best, each with the answers that speak for it; [] when nothing was answered."""
    if d.suggester is None or not any(v is not None for v in answers.values()):
        return []
    s = d.suggester
    cfg = s.cfg["suggest"]
    labels = {(q.id, o.code): reason_label(q, o) for q in s.qn.questions for o in q.options}
    cat = d.catalog
    out = []
    for code, reasons in s.suggest(answers, cfg["top"], cfg["reasons"]):
        m = cat.majors[code]
        out.append({"code": code, "label": m.label, "reasons": [labels[r] for r in reasons],
                    "children": [cat.label(c) for c in m.children[:4]], "more_children": len(m.children) > 4})
    return out
