"""The free-text reader (design: "the free text is read only into the options and shown to the
student to confirm"): "Kể thêm về em" -> options of the 12 questions, by plain phrases (config/free_text_reader.yaml).

Rules, not a learned model: a classifier trained on the generated students' texts (tried 2026-10-08) learned to guess
options that merely go with what a student wrote ("lập trình" -> Một mình, Văn phòng) and missed plain statements
("ghét máu"), i.e. it put words in the student's mouth. The rules read only what the text says: each guess comes with
the words it came from, and the student confirms every guess. A clause that says a dislike ("không thích", "ghét",
"sợ" ...) sends subjects to Q2, topics to Q7 and work conditions to Q12. Nothing is stored or sent.

    python -m uniadvisor.majors.reader          # report on the generated students' texts -> models/text_reader/report.md
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from uniadvisor.data.scope import strip_accents
from uniadvisor.paths import CONFIG_DIR, ROOT
from uniadvisor.majors.questions import Questionnaire, load_questionnaire

CONFIG = CONFIG_DIR / "free_text_reader.yaml"
OUT = ROOT / "models" / "text_reader"


def _lower(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def _plain(text: str) -> str:
    return strip_accents(_lower(text)).replace("đ", "d")


def _safe_plain(phrase: str) -> bool:
    """An accent-free phrase that cannot be confused: two words or more, or one word of 5+ letters."""
    words = phrase.split()
    return len(words) >= 2 or len(phrase) >= 5


def _pattern(phrases: list[str]) -> re.Pattern | None:
    phrases = sorted({p for p in phrases if p}, key=len, reverse=True)
    if not phrases:
        return None
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(p) for p in phrases) + r")(?!\w)")


@dataclass(frozen=True)
class Guess:
    question: str
    option: str
    words: str                        # the words of the text it came from


class Reader:
    def __init__(self, qn: Questionnaire, cfg: dict):
        self.qn = qn
        label = {(q.id, o.code): o.label for q in qn.questions for o in q.options}
        self.breaks = cfg["clause_breaks"]
        self.negation = self._matcher(cfg["negation"])
        cancel = cfg.get("negation_cancel", [])
        self.cancelled = re.compile(r"(?<!\w)(" + "|".join(re.escape(c) for c in cancel) + r") $") if cancel else None
        self.masks = [re.compile(m) for m in cfg.get("mask", [])]
        # (positive question, negative question or None, option code, matcher)
        self.rules: list[tuple[str | None, str | None, str, tuple]] = []
        for code, phrases in cfg["subjects"].items():
            self.rules.append(("q1", "q2", code, self._matcher(phrases + [label[("q1", code)]])))
        for code, phrases in cfg["topics"].items():
            self.rules.append(("q6", "q7", code, self._matcher(phrases + [label[("q6", code)]])))
        for qid, options in cfg["positive"].items():
            for code, phrases in options.items():
                self.rules.append((qid, None, code, self._matcher(phrases + [label[(qid, code)]])))
        for qid, options in cfg["negative"].items():
            for code, phrases in options.items():
                self.rules.append((None, qid, code, self._matcher(phrases + [label[(qid, code)]])))

    @staticmethod
    def _matcher(phrases: list[str]) -> tuple:
        accented = [_lower(p) for p in phrases]
        plain = [_plain(p) for p in phrases if _safe_plain(_plain(p))]
        return _pattern(accented), _pattern(plain)

    @staticmethod
    def _find(matcher: tuple, lower: str, plain: str) -> str | None:
        accented, unaccented = matcher
        m = accented.search(lower) if accented else None
        if m is None and unaccented is not None:
            m = unaccented.search(plain)
        return m.group(1) if m else None

    def _negative(self, lower: str, plain: str) -> bool:
        """A dislike cue in the clause, not cancelled by a "không" right before it ("không ngại", "không sợ")."""
        for text, pattern in zip((lower, plain), self.negation):
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                before = text[:m.start()]
                if self.cancelled is None or not self.cancelled.search(_plain(before) if text is plain else before):
                    return True
        return False

    def clauses(self, text: str) -> list[str]:
        t = " " + _lower(text) + " "
        for b in self.breaks:
            t = t.replace(b, "|")
        return [c.strip() for c in t.split("|") if c.strip()]

    def read(self, text: str) -> list[Guess]:
        out: dict[tuple[str, str], Guess] = {}
        for clause in self.clauses(text or ""):
            lower = clause
            for m in self.masks:
                lower = m.sub(lambda x: " " * len(x.group(0)), lower)
            plain = _plain(lower)
            negative = self._negative(lower, plain)
            for pos_q, neg_q, code, matcher in self.rules:
                qid = neg_q if negative else pos_q
                if qid is None:
                    continue
                words = self._find(matcher, lower, plain)
                if words and (qid, code) not in out:
                    out[(qid, code)] = Guess(qid, code, words)
        order = {q.id: i for i, q in enumerate(self.qn.questions)}
        return sorted(out.values(), key=lambda g: (order[g.question], g.option))


def load_reader(qn: Questionnaire | None = None, path: Path = CONFIG) -> Reader:
    return Reader(qn or load_questionnaire(), yaml.safe_load(path.read_text(encoding="utf-8")))


def ticked(answers: dict) -> set[tuple[str, str]]:
    out = set()
    for qid, v in answers.items():
        for code in ([v] if isinstance(v, str) else (v or [])):
            out.add((qid, code))
    return out


PARTS = {"subjects, topics, activities (q1-q7)": ("q1", "q2", "q3", "q4", "q5", "q6", "q7"),
         "place and way of working (q8-q11)": ("q8", "q9", "q10", "q11"),
         "conditions not wanted (q12)": ("q12",)}


def evaluate(reader: Reader, rows: list[tuple[str, dict]], questions: tuple[str, ...] | None = None) -> dict:
    """Precision: share of guesses the student also ticked; texts with a guess; guesses per text. A lower bound: the
    writers mention things they did not tick, most of all in Q12 and the single-answer questions, whose number of
    ticks the generation plan capped ("ghét môi trường ồn ào" without ticking Tiếng ồn lớn)."""
    guesses = hits = with_guess = 0
    for text, answers in rows:
        got = [g for g in reader.read(text) if questions is None or g.question in questions]
        t = ticked(answers)
        guesses += len(got)
        hits += sum((g.question, g.option) in t for g in got)
        with_guess += bool(got)
    n = len(rows)
    return {"n": n, "precision": hits / guesses if guesses else 0.0, "texts_with_a_guess": with_guess / n if n else 0.0,
            "guesses_per_text": guesses / n if n else 0.0}


HAND_WRITTEN = [                     # LLM-drafted checks of plain student phrasing (draft, 2026-10-08)
    ("em thích vẽ và chụp ảnh, sau này muốn làm thiết kế", {("q4", "drawing"), ("q4", "photo")}),
    ("em rất ghét máu, không muốn làm trong bệnh viện", {("q12", "blood")}),
    ("em thich lap trinh va giai toan kho", {("q4", "code"), ("q4", "hard_problem")}),
    ("em muốn đi làm ở văn phòng, không thích làm ngoài trời", {("q8", "office"), ("q12", "outdoor_work")}),
    ("mình thích nấu ăn với chăm sóc con vật", {("q4", "cooking"), ("q4", "animals")}),
    ("em thích kinh tế, muốn sau này quản lý doanh nghiệp", {("q6", "economics"), ("q6", "business")}),
    ("em học tốt toán nhưng không thích hóa học", {("q1", "TO"), ("q2", "HO")}),
    ("sở thích của em là đọc truyện và viết về lịch sử", {("q5", "novels"), ("q6", "history"), ("q1", "SU")}),
]


def main():
    from pipelines.majors_model.train import load_students

    qn = load_questionnaire()
    reader = load_reader(qn)
    students = load_students()
    kept = students[(students["dropped"] == "") & (students["text"].str.strip() != "")
                    & ~students["issues"].str.contains("text:chinese", regex=False)]    # no use reading Chinese
    labels = {(q.id, o.code): o.label for q in qn.questions for o in q.options}
    lines = ["# Free-text reader report", "",
             "Rules (config/free_text_reader.yaml), checked on the generated students' free texts: a guess counts as right "
             "when the student also ticked the option (a lower bound: writers mention things they did not tick).", "",
             "| Family | texts | precision | texts with a guess | guesses per text |", "|---|---|---|---|---|"]
    for family, g in kept.groupby("family"):
        rows = list(zip(g["text"], g["parsed"]))
        r = evaluate(reader, rows)
        lines.append(f"| {family}, all | {r['n']} | {r['precision']:.1%} | {r['texts_with_a_guess']:.0%} | "
                     f"{r['guesses_per_text']:.2f} |")
        for part, qs in PARTS.items():
            r = evaluate(reader, rows, qs)
            lines.append(f"| {family}, {part} | {r['n']} | {r['precision']:.1%} | {r['texts_with_a_guess']:.0%} | "
                         f"{r['guesses_per_text']:.2f} |")
    lines += ["", "Hand-written texts (drafted checks): expected options, and what the reader found.", ""]
    passed = 0
    for text, expected in HAND_WRITTEN:
        got = {(g.question, g.option) for g in reader.read(text)}
        ok = expected <= got and not (got - expected - {("q1", "SU")})
        passed += ok
        lines.append(f"- {'ok' if ok else '**differs**'}: \"{text}\" -> "
                     + (", ".join(f"{q} {labels[(q, o)]}" for q, o in sorted(got)) or "(nothing)"))
    lines.insert(4, f"Hand-written checks: {passed}/{len(HAND_WRITTEN)}.\n")
    OUT.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
