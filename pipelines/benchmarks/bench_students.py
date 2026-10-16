"""Three-list bench on realistic students: uneven subjects and answers to the 12 questions.

The other benches use students equally good in every subject who never answer the questionnaire, so the Hợp môn
corner is always 100% and the Hợp sở thích nhất list is never built. Here the students are Module 2's generated
students (pipelines/data/students/clean/students.csv, local, not committed): kept students of the training families
with 4-6 exam subjects (the THPT exam: Toán, Ngữ văn and two chosen subjects; some writers gave many more), up to
`PER_GROUP` per target nhóm ngành, home in Hà Nội or TP.HCM in turn. Each runs through the app's own path
(ui/service.py `AppData.recommend`) with its target nhóm ngành as the only shortlist item and its answers, so the
second list is Hợp sở thích nhất.

    python -m pipelines.benchmarks.bench_students        # -> data/bench_students.md
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from pipelines.benchmarks.bench import measure
from uniadvisor.paths import ROOT
from uniadvisor.planner.lists import CORNERS, Priority, overlap

STUDENTS = ROOT / "pipelines" / "data" / "students" / "clean" / "students.csv"
PER_GROUP = 3
SEED = 7
HOMES = ("Hà Nội", "TP. Hồ Chí Minh")
NAMES = {Priority.NGANH: "Đúng ngành", Priority.CAREER: "Nghề nghiệp", Priority.MON: "Hợp môn",
         Priority.COST: "Tiết kiệm"}


def pick_students(rows: list[dict], families: list[str], groups: set[str], per_group: int = PER_GROUP,
                  seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    by_group = defaultdict(list)
    for r in rows:
        if r["dropped"] or r["family"] not in families or r["target_group"] not in groups or not r["scores"]:
            continue
        scores = json.loads(r["scores"])
        if 4 <= len(scores) <= 6 and "TO" in scores and "VA" in scores:
            by_group[r["target_group"]].append(r)
    out = []
    for g in sorted(by_group):
        rows_g = sorted(by_group[g], key=lambda r: r["student_id"])
        out += rng.sample(rows_g, min(per_group, len(rows_g)))
    return out


def run(d, students: list[dict]) -> list[dict]:
    from uniadvisor.ui.state import PlanState, ShortlistEntry

    out = []
    for k, s in enumerate(students):
        state = PlanState(scores={c: float(v) for c, v in json.loads(s["scores"]).items()},
                          home_province=HOMES[k % 2], shortlist=[ShortlistEntry(s["target_group"])],
                          answers=json.loads(s["answers"]))
        recs = d.recommend(state)
        exam = sum(sorted(state.scores.values(), reverse=True)[:3])
        for r in recs:
            m = measure(s["target_group"], exam, HOMES[k % 2], r.result, None, d.list_cfg, d.rules)
            out.append({"student": s["student_id"], "group": s["target_group"], "priority": r.priority, "m": m,
                        "floor": r.floor_met, "none": r.chances.none if r.chances else None,
                        "corners": dict(r.pentagon.values) if r.pentagon else {},
                        "overlap": {o.priority: overlap(r.result, o.result) for o in recs if o is not r}})
    return out


def render(rows: list[dict], n_students: int) -> str:
    lines = ["# Three-list bench on realistic students", "",
             f"{n_students} of Module 2's generated students (4-6 exam subjects, answers to the 12 questions, the target "
             "nhóm ngành as the shortlist; see the module docstring). Corners are the pentagon's, 0-100%, averaged "
             "over the lists that have a value. Useless: a wish harder by more than 0.5 than a wish above it.", "",
             "| list | lists | 15 wishes | mean wishes | meets floor | no admission: mean / worst | "
             + " | ".join(c for c in CORNERS) + " | useless (mean) | duplicated | sư phạm late | "
             "an toàn at 1 school only | overlap with the others |",
             "|---|---|---|---|---|---|" + "---|" * len(CORNERS) + "---|---|---|---|---|"]
    by = defaultdict(list)
    for r in rows:
        by[r["priority"]].append(r)
    for p in sorted(by, key=lambda p: list(Priority).index(p)):
        g = by[p]
        ms = [r["m"] for r in g]
        nones = [r["none"] for r in g if r["none"] is not None]
        corners = []
        for c in CORNERS:
            vals = [r["corners"][c] for r in g if r["corners"].get(c) is not None]
            corners.append(f"{100 * sum(vals) / len(vals):.0f}% ({len(vals)})" if vals else "no data")
        ov = [v for r in g for v in r["overlap"].values()]
        lines.append(
            f"| {NAMES[p]} | {len(g)} | {sum(m.wishes == 15 for m in ms)} | {sum(m.wishes for m in ms) / len(ms):.1f} | "
            f"{sum(r['floor'] for r in g)} | "
            + (f"{100 * sum(nones) / len(nones):.2f}% / {100 * max(nones):.1f}%" if nones else "-") + " | "
            + " | ".join(corners) + f" | {sum(m.useless for m in ms) / len(ms):.2f} | {sum(m.duplicated for m in ms)} | "
            f"{sum(m.teacher_late for m in ms)} | {sum(m.safe > 1 and m.safe_schools == 1 for m in ms)} | "
            f"{100 * sum(ov) / len(ov):.0f}% |")
    return "\n".join(lines) + "\n"


def main():
    import csv

    from uniadvisor.majors.score import load_config
    from uniadvisor.paths import BUILD_DIR
    from uniadvisor.ui.service import AppData

    sys.stdout.reconfigure(encoding="utf-8")
    if not STUDENTS.exists():
        print(f"No generated students at {STUDENTS} (run pipelines.majors_model.prepare first); nothing to bench.")
        return
    d = AppData.load()
    with open(STUDENTS, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    groups = {c for c, m in d.catalog.majors.items() if m.level == "nhom_nganh"}
    students = pick_students(rows, load_config()["model"]["train_families"], groups)
    text = render(run(d, students), len(students))
    (BUILD_DIR / "bench_students.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
