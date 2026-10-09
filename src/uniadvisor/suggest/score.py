"""Step 7 data scores: how well each nhóm ngành fits a set of answers, from v2's own tables only.

Every option of the questionnaire points to data (config/step7_questions.yaml): Holland types (nganh_interest), an O*NET
knowledge area (nganh_knowledge), a Work Context element (nganh_work_context) or an exam subject (admission
combinations + the subject's knowledge area). A nhóm ngành's profile combines its ngành weighted by their program
counts. Each feature is standardised across the groups (z-score), so an option scores a group by how unusual the
group is on that feature. An answer's score for a group = sum over answered questions of question weight x the mean
score of the picked options; disliked subjects and topics (Q2, Q7) and the Work Context options marked `against`
count negative. Options without data ("learned only") score 0 here; the learned model adds small weights later.

This is the baseline the learned model has to beat, and what the app uses until then.
"""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import yaml

from uniadvisor.app.catalog import Catalog
from uniadvisor.paths import CONFIG_DIR
from uniadvisor.suggest.questions import Option, Questionnaire, load_questionnaire

CONFIG = CONFIG_DIR / "suggest.yaml"
RIASEC = {"R": "Realistic", "I": "Investigative", "A": "Artistic", "S": "Social", "E": "Enterprising",
          "C": "Conventional"}

Answers = dict[str, "list[str] | str | None"]        # question id -> option codes (multi), one code (single), None


def load_config(path=CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class Group:
    code: str
    label: str
    interest: dict[str, float] = field(default_factory=dict)       # Holland type name -> O*NET score (1-7)
    knowledge: dict[str, float] = field(default_factory=dict)      # knowledge area -> importance (1-5)
    work_context: dict[str, float] = field(default_factory=dict)   # element id -> value
    subjects: dict[str, float] = field(default_factory=dict)       # subject code -> shrunk share of programs


def load_groups(conn: sqlite3.Connection, catalog: Catalog, exclude=(), prior_programs: float = 20.0,
                level: str = "nhom_nganh") -> list[Group]:
    """The nhóm ngành the model suggests: every nhóm with an in-scope program, except `exclude`. With level 'nganh':
    every ngành instead (the three lists' career fit), except those of an excluded nhóm."""
    interest, knowledge, context = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for n, r, v in conn.execute("SELECT nganh_code, riasec, score FROM nganh_interest"):
        interest[n][r] = v
    for n, e, v in conn.execute("SELECT nganh_code, element, importance FROM nganh_knowledge"):
        knowledge[n][e] = v
    for n, e, v in conn.execute("SELECT nganh_code, element_id, value FROM nganh_work_context"):
        context[n][e] = v

    codes = [c for c, m in sorted(catalog.majors.items()) if m.level == level and c not in exclude
             and (m.parent or "") not in exclude]
    totals: Counter = Counter()
    n_all = 0
    for c in codes:
        counts, n = catalog.subject_counts(c)
        totals.update(counts)
        n_all += n
    overall = {s: k / n_all for s, k in totals.items()} if n_all else {}

    groups = []
    for code in codes:
        m = catalog.majors[code]
        g = Group(code, m.label)
        for table, out in ((interest, g.interest), (knowledge, g.knowledge), (context, g.work_context)):
            kids = [c for c in (m.children if level == "nhom_nganh" else [code]) if c in table]
            total = sum(catalog.majors[c].n_programs for c in kids)
            for c in kids:
                for k, v in table[c].items():
                    out[k] = out.get(k, 0.0) + v * catalog.majors[c].n_programs / total
        counts, n = catalog.subject_counts(code)
        g.subjects = {s: (counts.get(s, 0) + prior_programs * p) / (n + prior_programs) for s, p in overall.items()}
        groups.append(g)
    return groups


def _z(values: dict[str, float], codes: list[str]) -> np.ndarray:
    """z-scores across the groups; a group without the value counts as average (0)."""
    present = [values[c] for c in codes if c in values]
    if len(present) < 2:
        return np.zeros(len(codes))
    mean, sd = float(np.mean(present)), float(np.std(present)) or 1.0
    return np.array([(values[c] - mean) / sd if c in values else 0.0 for c in codes])


class DataScorer:
    def __init__(self, qn: Questionnaire, groups: list[Group], cfg: dict):
        self.qn = qn
        self.cfg = cfg
        self.groups = groups
        self.codes = [g.code for g in groups]
        self.weights = cfg["data_scores"]["question_weight"]
        by = lambda attr: lambda key: {g.code: getattr(g, attr)[key] for g in groups if key in getattr(g, attr)}
        self._interest, self._knowledge = by("interest"), by("knowledge")
        self._context, self._subject = by("work_context"), by("subjects")
        # question id -> option code -> score per group (np array in self.codes order)
        self.table: dict[str, dict[str, np.ndarray]] = {
            q.id: {o.code: self._option(o) * (-1 if q.negative else 1) for o in q.options} for q in qn.questions}

    @classmethod
    def load(cls, conn: sqlite3.Connection, catalog: Catalog, qn: Questionnaire | None = None,
             cfg: dict | None = None, level: str = "nhom_nganh") -> "DataScorer":
        qn = qn or load_questionnaire()
        cfg = cfg or load_config()
        groups = load_groups(conn, catalog, qn.exclude_groups, cfg["data_scores"]["subject_prior_programs"], level)
        return cls(qn, groups, cfg)

    def _option(self, o: Option) -> np.ndarray:
        parts = []
        if o.holland:
            parts.append(np.mean([_z(self._interest(RIASEC[x]), self.codes) for x in o.holland], axis=0))
        if o.knowledge:
            parts.append(_z(self._knowledge(o.knowledge), self.codes))
        if o.work_context:
            parts.append(_z(self._context(o.work_context), self.codes) * (-1 if o.against else 1))
        if o.subject:
            sub = [_z(self._subject(o.subject), self.codes)]
            area = self.qn.subjects_knowledge.get(o.subject)
            if area:
                sub.append(_z(self._knowledge(area), self.codes))
            parts.append(np.mean(sub, axis=0))
        return np.mean(parts, axis=0) if parts else np.zeros(len(self.codes))

    def weight(self, qid: str) -> float:
        return float(self.weights.get(qid, self.weights["default"]))

    @staticmethod
    def picked(value) -> list[str]:
        if value is None:
            return []
        return [value] if isinstance(value, str) else list(value)

    def contributions(self, answers: Answers) -> dict[tuple[str, str], np.ndarray]:
        """(question id, option code) -> its share of the score per group."""
        out = {}
        for qid, value in answers.items():
            picks = list(dict.fromkeys(c for c in self.picked(value) if c in self.table.get(qid, {})))
            for code in picks:
                out[(qid, code)] = self.table[qid][code] * self.weight(qid) / len(picks)
        return out

    def scores(self, answers: Answers) -> np.ndarray:
        parts = self.contributions(answers)
        return np.sum(list(parts.values()), axis=0) if parts else np.zeros(len(self.codes))

    def rank(self, answers: Answers) -> list[str]:
        """Group codes, best first (ties by code, so the same answers always give the same order)."""
        s = self.scores(answers)
        return [self.codes[i] for i in sorted(range(len(self.codes)), key=lambda i: (-round(s[i], 9), self.codes[i]))]

    def suggest(self, answers: Answers, top: int = 5, reasons: int = 3) -> list[tuple[str, list[tuple[str, str]]]]:
        """The top groups with the picked options that speak most for each: [(group, [(question id, option)])]."""
        parts = self.contributions(answers)
        out = []
        for code in self.rank(answers)[:top]:
            i = self.codes.index(code)
            best = sorted(((v[i], k) for k, v in parts.items() if v[i] > 0), key=lambda x: (-x[0], x[1]))
            out.append((code, [k for _, k in best[:reasons]]))
        return out
