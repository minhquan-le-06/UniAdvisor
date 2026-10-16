"""Check the chances against past cutoffs: how often would an an toàn wish have failed, and how often does the chance
model (planner/chances.py) say it fails?

The history is the old repository's cutoff table (2018-2026, one THPT-exam cutoff per program and year). It is read
here only to check, never imported into the database (decision of 2026-10-07). For each program and year y with
cutoffs in the two years before: a student at the an toàn line, the higher of those two cutoffs plus a margin, fails
when the year-y cutoff is above their score. The model's failure for the same rows is the chance that a school shift
plus a program shift (drawn from the current database's changes, as the list does) exceeds the student's margin over
the year y-1 cutoff. The level rule uses margin 2 (config/list.yaml `levels.safe_margin`); 1 and 3 are shown for scale.

    python -m pipelines.benchmarks.calibration [--history PATH]      # -> data/calibration.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from uniadvisor.paths import ROOT
from uniadvisor.planner.chances import ChangeModel

HISTORY = ROOT.parent / "UniAdvisor-legacy" / "MLAI_test" / "artifacts" / "build" / "cutoffs_consensus.csv"
MARGINS = (1.0, 2.0, 3.0)


def load_history(path: Path) -> dict[tuple[str, str], dict[int, float]]:
    """(school, program key) -> year -> cutoff, 30-point rows only, disputed rows left out."""
    out: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("scale") != "30" or r.get("status") == "disputed" or not r.get("score"):
                continue
            out[(r["school_code"], r["key_code"])][int(r["year"])] = float(r["score"])
    return out


def fail_probability(model: ChangeModel, margin: float) -> float:
    """P(school shift + program shift > margin): the chance model's failure at this margin over the latest cutoff."""
    p = np.sort(model.program_shifts)
    schools = model.school_shifts if len(model.school_shifts) else np.zeros(1)
    # for each school shift s: share of program shifts p with s + p > margin
    return float(np.mean([1 - np.searchsorted(p, margin - s, side="right") / len(p) for s in schools]))


@dataclass(frozen=True)
class Row:
    year: int | None                   # None: every year
    margin: float
    n: int
    history: float                     # share of rows where the an toàn wish failed
    model: float                       # the model's mean failure chance for the same rows


def calibrate(history: dict[tuple[str, str], dict[int, float]], model: ChangeModel, max_change: float,
              margins=MARGINS) -> list[Row]:
    cases = []                         # (year, cutoff y-2, y-1, y)
    for years in history.values():
        for y, c in years.items():
            a, b = years.get(y - 2), years.get(y - 1)
            if a is None or b is None or abs(b - a) > max_change or abs(c - b) > max_change:
                continue
            cases.append((y, a, b, c))
    rows = []
    for margin in margins:
        per_year = defaultdict(lambda: ([], []))
        for y, a, b, c in cases:
            score = max(a, b) + margin
            hist, mod = per_year[y]
            hist.append(c > score + 1e-9)
            mod.append(fail_probability(model, score - b))
        for y in sorted(per_year):
            hist, mod = per_year[y]
            rows.append(Row(y, margin, len(hist), float(np.mean(hist)), float(np.mean(mod))))
        hist = [x for h, _ in per_year.values() for x in h]
        mod = [x for _, m in per_year.values() for x in m]
        if hist:
            rows.append(Row(None, margin, len(hist), float(np.mean(hist)), float(np.mean(mod))))
    return rows


def render(rows: list[Row], model: ChangeModel, source: Path) -> str:
    lines = ["# Chances: check against past cutoffs", "",
             f"History: `{source.name}` of the old repository (30-point rows, disputed left out; read only to check). "
             f"Model: changes {model.years[0]} -> {model.years[1]} of the current database ({model.n_programs} "
             "programs). A row is a program and year y with cutoffs in y-2 and y-1; the student sits at the higher of "
             "those plus the margin (margin 2 = the an toàn line). Changes over the list's `max_change` are left out "
             "as data errors, as the model does.", "",
             "| margin | year | rows | an toàn failed in the past | model's failure chance |",
             "|---|---|---|---|---|"]
    for r in rows:
        year = "all" if r.year is None else str(r.year)
        line = f"| {r.margin:g} | {year} | {r.n} | {r.history:.2%} | {r.model:.2%} |"
        lines.append(f"| **{r.margin:g}** | **all** | **{r.n}** | **{r.history:.2%}** | **{r.model:.2%}** |"
                     if r.year is None else line)
    return "\n".join(lines) + "\n"


def main():
    from uniadvisor import db
    from uniadvisor.config import load_data_config, load_list_config
    from uniadvisor.paths import BUILD_DIR

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--history", type=Path, default=HISTORY)
    args = ap.parse_args()
    if not args.history.exists():
        print(f"No cutoff history at {args.history} (the old repository is not on this machine); nothing to check.")
        return
    cfg = load_list_config()
    model = ChangeModel.fit(db.connect(), tuple(load_data_config()["cutoff_years"]), cfg)
    rows = calibrate(load_history(args.history), model, cfg["chances"]["max_change"])
    text = render(rows, model, args.history)
    (BUILD_DIR / "calibration.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
