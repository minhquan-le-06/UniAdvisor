"""The student's chance of being admitted at each level of the list or better.

Not a cutoff forecast: next year's cutoff of a program is its latest cutoff plus a change drawn from how the database's
own cutoffs moved from the earlier to the latest year, centred at zero (no trend). The change is a shift shared by
every program of a school (programs of one school move together) plus the program's own shift. Each simulated year
the student is admitted to the highest wish they reach; the chances are the shares of simulated years.

- Changes are measured on in-scope programs with one cutoff for all combinations in both years and no mixed method
  (their conversion is not trusted). Changes larger than `chances.max_change` are left out: most are data errors
  (a misread scale, a reused code), and they would make every list look riskier than it is.
- A school's shift is the mean change of its programs, shrunk towards zero by how few programs it has (a school with
  three programs tells little); schools with fewer than `chances.min_school_programs` programs give no shift. The
  program shifts are what is left after removing the school's mean.
- Deterministic: a fixed seed, so the same list gives the same chances.

Known limits (said in the app): one year of change shows no nationwide shift like 2025's (centring at zero assumes
none); mixed-method programs use the same changes although their conversion is uncertain.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from uniadvisor.planner.models import LEVEL_ORDER, Level, ListResult


@dataclass(frozen=True)
class ChangeModel:
    school_shifts: np.ndarray          # one value per school with enough programs (shrunk)
    program_shifts: np.ndarray         # residual change per program
    years: tuple[int, int]
    n_programs: int

    @classmethod
    def fit(cls, conn: sqlite3.Connection, years: tuple[int, int], cfg: dict) -> "ChangeModel":
        c = cfg["chances"]
        rows = conn.execute(
            """SELECT c.program_id, p.school_code, c.year, c.score_30 FROM cutoff c JOIN program p ON p.id = c.program_id
               WHERE p.in_scope = 1 AND c.combo_key = '*' AND c.is_mixed_method = 0 AND c.year IN (?, ?)
               ORDER BY c.program_id, c.year""", years).fetchall()
        by_program: dict[str, dict] = defaultdict(dict)
        school_of: dict[str, str] = {}
        for pid, school, year, score in rows:
            by_program[pid][year] = score
            school_of[pid] = school
        changes = {pid: v[years[1]] - v[years[0]] for pid, v in by_program.items()
                   if len(v) == 2 and abs(v[years[1]] - v[years[0]]) <= c["max_change"]}
        if not changes:
            raise ValueError("No program has cutoffs in both years to measure changes on")
        mean = float(np.mean(list(changes.values())))
        per_school: dict[str, list[float]] = defaultdict(list)
        for pid in sorted(changes):
            per_school[school_of[pid]].append(changes[pid] - mean)
        big = {s: v for s, v in per_school.items() if len(v) >= c["min_school_programs"]}
        if len(big) < 2:                   # too few schools to tell a school's shift from a program's
            return cls(np.zeros(0), np.sort(np.array([x for v in per_school.values() for x in v])), tuple(years),
                       len(changes))
        residuals = np.array([x - np.mean(v) for v in big.values() for x in v])
        means = np.array([np.mean(v) for v in big.values()])
        sizes = np.array([len(v) for v in big.values()])
        # Variance between schools beyond what their programs' spread explains, then shrink each school's mean.
        between = max(float(np.var(means, ddof=1)) - float(np.var(residuals, ddof=1)) / float(np.mean(sizes)), 0.0)
        shrink = between / (between + float(np.var(residuals, ddof=1)) / sizes) if between > 0 else np.zeros(len(sizes))
        return cls(np.sort(means * shrink), np.sort(residuals), tuple(years), len(changes))


@dataclass(frozen=True)
class Chances:
    score_shift: float                 # points added to the student's score (0 = as entered; -1, +1 before the exam)
    at_least: dict[Level, float]       # P(admitted at a wish of this level or a higher one)
    none: float                        # P(admitted nowhere on the list)
    admitted: tuple[float, ...] = ()   # per wish (list order): P(this wish is the one the student is admitted to)


def chances(result: ListResult, model: ChangeModel, cfg: dict, score_shift: float = 0.0) -> Chances:
    """Simulated chances for one list (the list is not rebuilt for the shifted score: it is the student's list)."""
    c = cfg["chances"]
    wishes = [w.candidate for w in result.wishes]
    rng = np.random.default_rng(c["seed"])
    n = c["draws"]
    schools = sorted({w.program.school_code for w in wishes})
    school_shift = {s: rng.choice(model.school_shifts, n) if len(model.school_shifts) else np.zeros(n)
                    for s in schools}
    admitted_level = np.full(n, -1)                        # index in LEVEL_ORDER of the wish the student gets
    admitted_wish = np.full(n, -1)                         # index of that wish in the list
    for k, w in enumerate(wishes):
        margin = w.student.score + score_shift - w.latest_cutoff
        reach = margin >= school_shift[w.program.school_code] + rng.choice(model.program_shifts, n) - 1e-9
        first = (admitted_wish == -1) & reach
        admitted_level[first] = LEVEL_ORDER.index(w.level)
        admitted_wish[first] = k
    at_least = {lv: float(np.mean((admitted_level >= 0) & (admitted_level <= i))) for i, lv in enumerate(LEVEL_ORDER)}
    admitted = tuple(float(np.mean(admitted_wish == k)) for k in range(len(wishes)))
    return Chances(score_shift, at_least, float(np.mean(admitted_level == -1)), admitted)
