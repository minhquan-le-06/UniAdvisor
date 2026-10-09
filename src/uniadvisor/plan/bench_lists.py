"""Test bench for the three recommended lists: the bench's invented students (plan/bench.py),
each given the three lists. Measures, per total: how often each list meets the safety floor and how often the floor had
to move slots, the chance of no admission, whether each list wins its own corner, how much the lists overlap, and
useless wishes (as in the list bench).

    python -m uniadvisor.plan.bench_lists        # -> data/build/bench_lists.md

The bench students did not answer the 12 questions, so their second list is Hợp môn nhất (Nghề nghiệp nhất needs the
answers, design decision 2026-10-08) and the Nghề nghiệp corner has no data; `run` takes career scores for tests.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from uniadvisor.plan.bench import CASES, TOTALS, USELESS_MARGIN, shortlist, student
from uniadvisor.plan.lists import ListFacts, Priority, overlap, recommend
from uniadvisor.plan.models import Level

OWN_CORNER = {Priority.NGANH: "dung_nganh", Priority.CAREER: "nghe_nghiep", Priority.MON: "hop_mon",
              Priority.COST: "hoc_phi"}


@dataclass(frozen=True)
class Row:
    case: str
    total: float
    city: str
    priority: Priority
    wishes: int
    floor_met: bool
    floor_moved: int                  # slots the floor moved to an toàn
    wider: int                        # an toàn wishes of other ngành (same nhóm / lĩnh vực) the floor added
    none: float | None
    own_best: bool | None             # the list is best (or tied) on its own corner; None: no data
    useless: int
    overlaps: dict[Priority, float]


def run(programs, nganh_parent, close, rules, list_cfg, provinces, year, model, facts: ListFacts,
        cases=CASES, totals=TOTALS, homes=(("HN", "Hà Nội"), ("HCM", "TP. Hồ Chí Minh"))) -> list[Row]:
    programs = list(programs)
    rows = []
    for label, codes in cases:
        items = shortlist(codes, close)
        for total in totals:
            for city, province in homes:
                recs = recommend(student(total, province), items, programs, nganh_parent, rules, list_cfg,
                                 provinces, year, model, facts)
                for r in recs:
                    corner = OWN_CORNER[r.priority]
                    vals = [x.pentagon.values.get(corner) for x in recs if x.pentagon]
                    mine = r.pentagon.values.get(corner) if r.pentagon else None
                    best = None if mine is None else mine >= max(v for v in vals if v is not None) - 1e-9
                    ws = [w.candidate for w in r.result.wishes]
                    useless = sum(any(later.gap > earlier.gap + USELESS_MARGIN for earlier in ws[:j])
                                  for j, later in enumerate(ws))
                    base_safe = sum(q[Level.AN_TOAN.value] for q in
                                    list_cfg["quotas"]["one_item" if len(items) == 1 else "two_items"].values())
                    moved = sum(q[Level.AN_TOAN] for q in r.quotas) - base_safe
                    rows.append(Row(label, total, city, r.priority, len(ws), r.floor_met, moved,
                                    sum(c.relation == "wider" for c in ws),
                                    r.chances.none if r.chances else None, best, useless,
                                    {o.priority: overlap(r.result, o.result) for o in recs if o is not r}))
    return rows


def render(rows: list[Row], floor: float) -> str:
    names = {Priority.NGANH: "Đúng ngành", Priority.CAREER: "Nghề nghiệp", Priority.MON: "Hợp môn",
             Priority.COST: "Tiết kiệm"}
    lines = ["# Three-list test bench", "",
             f"Bench students (plan/bench.py), {len({(r.case, r.total, r.city) for r in rows})} students x 3 lists. "
             f"Floor: chance of no admission at most {floor:.0%} at the score entered. The bench students did not "
             "answer the 12 questions: their second list is Hợp môn nhất and the Nghề nghiệp corner has no data.", "",
             "| total | list | meets floor | floor moved slots (mean) | wider wishes (mean) | no admission: mean / worst"
             " | best on its own corner | useless (mean) | overlap with the others (mean) |",
             "|---|---|---|---|---|---|---|---|---|"]
    groups = defaultdict(list)
    for r in rows:
        groups[(r.total, r.priority)].append(r)
    for (total, p), g in sorted(groups.items(), key=lambda x: (x[0][0], list(Priority).index(x[0][1]))):
        nones = [r.none for r in g if r.none is not None]
        best = [r.own_best for r in g if r.own_best is not None]
        ov = [v for r in g for v in r.overlaps.values()]
        lines.append(f"| {total:g} | {names[p]} | {sum(r.floor_met for r in g)}/{len(g)} | "
                     f"{sum(r.floor_moved for r in g) / len(g):.1f} | {sum(r.wider for r in g) / len(g):.1f} | "
                     + (f"{sum(nones) / len(nones):.1%} / {max(nones):.1%}" if nones else "-") + " | "
                     + (f"{sum(best)}/{len(best)}" if best else "no data") + f" | "
                     f"{sum(r.useless for r in g) / len(g):.2f} | {sum(ov) / len(ov):.0%} |")
    return "\n".join(lines) + "\n"


def main():
    from uniadvisor import db
    from uniadvisor.app.service import AppData
    from uniadvisor.config import load_data_config, load_list_config, load_provinces, load_rules
    from uniadvisor.paths import BUILD_DIR
    from uniadvisor.plan.chances import ChangeModel
    from uniadvisor.plan.repository import load_nganh_parents, load_programs

    d = AppData.load()
    conn = db.connect()
    year = load_data_config()["target_admission_year"]
    cfg = load_list_config()
    model = ChangeModel.fit(conn, tuple(load_data_config()["cutoff_years"]), cfg)
    close = lambda code: [c for c in d.facts.get(code).close if d.catalog.majors[c].level == "nganh"]  # noqa: E731
    rows = run(load_programs(conn), load_nganh_parents(conn), close, load_rules(year), cfg, load_provinces(), year,
               model, d.list_facts())
    text = render(rows, cfg["three_lists"]["max_no_admission"])
    (BUILD_DIR / "bench_lists.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
