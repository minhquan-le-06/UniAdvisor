"""Cleaning the generated students: the writer LLM's answers -> option codes.

The writers copy option labels into JSON, imperfectly (trials of 2026-10-08): a string where a list was asked, several
options joined with '|', "" for none, near-miss labels ("Văn học" for "Ngữ văn", "Vật lý" for "Vật lí"), labels of
another question, labels with foreign characters ("Lịch史"). Since 2026-10-09 the notebook asks for option codes
instead (shorter, fewer copying mistakes); both are read, a near-miss code of 5+ letters counts
("thi_nghiem" style slips). Cleaning maps every answer to the question's own option
codes, drops what does not match, applies the questionnaire's rules (max picks, not_in) and notes every repair, so the
audit can count them per family.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field

from uniadvisor.ui.catalog import search_key
from uniadvisor.majors.questions import Question, Questionnaire

SPLIT = ("|", ";", ",", "/")          # option labels never contain these (questions.check)
# Chinese characters a writer slipped into a Vietnamese word (Qwen: "Lịch史", "Ngữ文"), read as their Sino-Vietnamese
# syllable; the label is then matched as usual (qwen run of 2026-10-08: 151 subject scores and 97 Q1 answers).
HAN_VIET = {"史": " sử", "文": " văn", "地": " địa", "理": " lí", "化": " hóa", "学": " học", "數": " số", "数": " số"}
FUZZY = 0.85                          # difflib ratio on accent-free labels for a near-miss label to count
# Free texts written partly in Chinese (qwen, LLM review of 2026-10-08): flagged, and left out of the reader report.
CJK = re.compile(r"[㐀-鿿豈-﫿]")

# A whole answer written as a word instead of JSON (mistral: "null" 149 times; gemma: "[]"), read as skipped / none.
SKIPPED = {"null", "none"}
NONE = {"[]", "không", "không có", "khong", "khong co"}


@dataclass
class Clean:
    answers: dict = field(default_factory=dict)       # question id -> [codes] | code | None (skipped)
    scores: dict = field(default_factory=dict)        # subject code -> expected exam score (0-10)
    text: str = ""
    issues: list[str] = field(default_factory=list)   # "kind:question:detail", for the audit
    moved: dict = field(default_factory=dict)         # question id -> codes written under its sibling, not yet placed

    @property
    def answered(self) -> int:
        return sum(v is not None for v in self.answers.values())


class Cleaner:
    def __init__(self, qn: Questionnaire, aliases: dict[str, str] | None = None,
                 siblings: list[list[str]] | None = None):
        self.qn = qn
        self.aliases = {search_key(k): v for k, v in (aliases or {}).items()}      # e.g. "Văn học" -> "Ngữ văn"
        self.exact = {q.id: {o.label: o.code for o in q.options} for q in qn.questions}
        self.keys = {q.id: {search_key(o.label): o.code for o in q.options} for q in qn.questions}
        self.codes = {q.id: {o.code.lower(): o.code for o in q.options} for q in qn.questions}
        # Two halves of one list (Q4 "Em thích làm những việc nào?" and Q5 "Còn những việc này?"): an option of one
        # written under the other is moved to it (every writer mixes them: 200-980 options per family, 2026-10-09).
        self.sibling = {a: b for pair in (siblings or []) for a, b in (pair, pair[::-1])}
        self.order = {q.id: i for i, q in enumerate(qn.questions)}

    def match(self, qid: str, label: str) -> tuple[str | None, str]:
        """(option code, how): exact (the label), code (the option code, any case), accents (same letters, other
        accents or case), alias, code_fuzzy (a near-miss code of 5+ letters), fuzzy; (None, 'foreign') when nothing
        fits."""
        if any(ch in label for ch in HAN_VIET):
            for ch, syllable in HAN_VIET.items():
                label = label.replace(ch, syllable)
            label = " ".join(label.split())
            code, how = self.match(qid, label)
            return code, ("han" if code else how)
        if label.strip() in self.exact[qid]:
            return self.exact[qid][label.strip()], "exact"
        if label.strip().lower() in self.codes[qid]:
            return self.codes[qid][label.strip().lower()], "code"
        keys = self.keys[qid]
        k = search_key(label)
        if k in keys:
            return keys[k], "accents"
        alias = self.aliases.get(k)
        if alias and search_key(alias) in keys:
            return keys[search_key(alias)], "alias"
        raw = label.strip().lower()
        if len(raw) >= 5:
            near = difflib.get_close_matches(raw, list(self.codes[qid]), n=1, cutoff=FUZZY)
            if near:
                return self.codes[qid][near[0]], "code_fuzzy"
        close = difflib.get_close_matches(k, list(keys), n=1, cutoff=FUZZY) if k else []
        return (keys[close[0]], "fuzzy") if close else (None, "foreign")

    @staticmethod
    def items(value) -> list[str] | None:
        """The raw answer as a list of strings; None when skipped."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            value = str(value)
        if isinstance(value, str):
            if value.strip().lower() in SKIPPED:
                return None
            value = [value]
        out = []
        for v in value:
            if not isinstance(v, str) or v.strip().lower() in SKIPPED | NONE:
                continue
            for sep in SPLIT:
                v = v.replace(sep, "|")
            out += [p.strip() for p in v.split("|") if p.strip()]
        return out

    def question(self, q: Question, raw, clean: Clean):
        items = self.items(raw)
        moved = clean.moved.pop(q.id, [])
        if items is None and not moved:
            clean.answers[q.id] = None
            return
        items = items or []
        if isinstance(raw, str) and len(items) > 1:
            clean.issues.append(f"joined:{q.id}")
        codes = []
        for label in items:
            code, how = self.match(q.id, label)
            if code is None and q.id in self.sibling and self.move(q.id, label, clean):
                continue
            if code is None:
                clean.issues.append(f"foreign:{q.id}:{label}")
            elif code in codes:
                clean.issues.append(f"duplicate:{q.id}:{label}")
            else:
                codes.append(code)
                if how not in ("exact", "code"):
                    clean.issues.append(f"{how}:{q.id}:{label}")
        for code in moved:
            if code not in codes:
                codes.append(code)
        if q.not_in:
            before = set(self.picked(clean.answers.get(q.not_in)))
            if before & set(codes):
                clean.issues.append(f"not_in:{q.id}")
                codes = [c for c in codes if c not in before]
        if q.kind == "single":
            if len(codes) > 1:
                clean.issues.append(f"too_many:{q.id}")
            clean.answers[q.id] = codes[0] if codes else None
            if not codes and items:
                clean.issues.append(f"lost:{q.id}")
            return
        if q.max and len(codes) > q.max:
            clean.issues.append(f"too_many:{q.id}")
            codes = codes[:q.max]
        if items and not codes:
            clean.issues.append(f"lost:{q.id}")
        clean.answers[q.id] = codes

    def move(self, qid: str, label: str, clean: Clean) -> bool:
        """Place an option of the sibling question written under `qid` where it belongs; False when it is not one."""
        sib = self.sibling[qid]
        code, _ = self.match(sib, label)
        if code is None:
            return False
        clean.issues.append(f"moved:{qid}:{label}")
        if self.order[sib] > self.order[qid]:                   # not cleaned yet: added when it is
            clean.moved.setdefault(sib, []).append(code)
        else:
            got = self.picked(clean.answers.get(sib))
            if code not in got:
                clean.answers[sib] = got + [code]
        return True

    @staticmethod
    def picked(value) -> list[str]:
        return [] if value is None else ([value] if isinstance(value, str) else list(value))

    def scores(self, raw, clean: Clean):
        if not isinstance(raw, dict):
            if raw is not None:
                clean.issues.append("scores:not_an_object")
            return
        for name, value in raw.items():
            if value is None:                                   # a subject listed without a score (gemma)
                continue
            code, how = self.match("q1", str(name))
            try:
                v = float(str(value).replace(",", "."))
            except ValueError:
                v = None
            if code is None or v is None or not 0 <= v <= 10:
                clean.issues.append(f"scores:dropped:{name}")
                continue
            clean.scores[code] = v

    def clean(self, data: dict) -> Clean:
        c = Clean()
        for q in self.qn.questions:                     # in order, so not_in sees the earlier question
            self.question(q, data.get(q.id), c)
        self.scores(data.get("diem"), c)
        text = data.get("ke_them")
        c.text = text.strip() if isinstance(text, str) else ""
        if n := len(CJK.findall(c.text)):
            c.issues.append(f"text:chinese:{n}")
        return c

    def too_many(self, clean: Clean, share: float) -> list[str]:
        """Multi questions without a maximum (Q12) answered with more than `share` of their options: the writer
        ticking nearly everything (LLM review of 2026-10-08), not a student's dislikes. Sibling questions count as
        the one list they are."""
        out = []
        for q in self.qn.questions:
            if q.kind != "multi" or q.max or self.order[self.sibling.get(q.id, q.id)] < self.order[q.id]:
                continue
            ids = [q.id] + ([self.sibling[q.id]] if q.id in self.sibling else [])
            picks = sum(len(self.picked(clean.answers.get(i))) for i in ids)
            if picks > share * sum(len(self.qn.get(i).options) for i in ids):
                out.append(q.id)
        return out


def plan_issues(clean: Clean, counts: dict) -> list[str]:
    """Where a cleaned student departs from the notebook's plan (attributes 'counts')."""
    out = []
    for qid, k in counts.items():
        got = Cleaner.picked(clean.answers.get(qid))
        if k is None and got:
            out.append(f"plan_skip:{qid}")
        elif k is not None and clean.answers.get(qid) is not None and len(got) != k:
            out.append(f"plan_count:{qid}")
    return out


def unaccented(text: str) -> str:
    """'Em thích Địa lí' -> 'Em thich Dia li': typed without Vietnamese accents, case kept."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return unicodedata.normalize("NFC", "".join(ch for ch in text if unicodedata.category(ch) != "Mn"))


def text_as_asked(clean: Clean, attrs: dict):
    """The free text as the notebook's attributes asked for it. No writer left it empty when asked to (0 of about
    1,900) or typed without accents (0 of about 1,900; files of 2026-10-08), so both are applied here: the reader is
    then also tested on unaccented texts, and on students who write nothing."""
    if attrs.get("free_text") == "để trống" and clean.text:
        clean.text = ""
        clean.issues.append("text:blanked")
    elif attrs.get("free_text_style") == "không dấu" and unaccented(clean.text) != clean.text:
        clean.text = unaccented(clean.text)
        clean.issues.append("text:unaccented")


def to_row(student: dict, clean: Clean) -> dict:
    return {"student_id": student["student_id"], "family": student["family"], "target_group": student["target_group"],
            "answers": json.dumps(clean.answers, ensure_ascii=False), "scores": json.dumps(clean.scores),
            "text": clean.text, "answered": clean.answered, "issues": ";".join(clean.issues)}
