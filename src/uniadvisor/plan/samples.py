"""Build lists for a few fixed sample students from the real database, so people can review the rules and the level
thresholds on real data (spec 9.1). The students are invented; nothing here is a real student's input.

Run: python -m uniadvisor.plan.samples   (writes data/build/sample_lists.md)
"""

from __future__ import annotations

from collections import Counter

from uniadvisor import db
from uniadvisor.config import load_data_config, load_list_config, load_provinces, load_rules
from uniadvisor.paths import BUILD_DIR
from uniadvisor.plan.models import LEVEL_ORDER, Profile, ShortlistItem
from uniadvisor.plan.repository import load_nganh_parents, load_programs
from uniadvisor.data.school_docs import combo_label
from uniadvisor.plan.strategy import build_list

SAMPLES = [
    ("Strong A00, IT, Hà Nội, no budget",
     Profile(scores={"TO": 9.0, "LI": 8.75, "HO": 8.5, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội"),
     [ShortlistItem("7480201", ("7480101",), ("7480104", "7480102"))]),
    ("Middle A00/A01/D01, IT then business, Nghệ An KV2-NT, budget 30, near home",
     Profile(scores={"TO": 7.5, "LI": 7.0, "HO": 6.5, "N1": 7.5, "VA": 7.0}, home_province="Nghệ An",
             area="KV2-NT", budget_trieu=30, near_home=True),
     [ShortlistItem("7480201", ("7480101",), ("7480104",)), ShortlistItem("73401", (), ("7340301",))]),
    ("Weaker A00/D01, accounting, Cần Thơ KV1, budget 25, near home",
     Profile(scores={"TO": 6.0, "LI": 5.5, "HO": 6.0, "N1": 5.0, "VA": 6.5}, home_province="Cần Thơ", area="KV1",
             budget_trieu=25, near_home=True),
     [ShortlistItem("7340301", ("7340201",), ("7340101", "7340115"))]),
    ("Strong B00, medicine, Đà Nẵng KV2",
     Profile(scores={"TO": 8.5, "HO": 9.0, "SI": 8.75, "VA": 7.5, "N1": 7.0}, home_province="Đà Nẵng", area="KV2"),
     [ShortlistItem("7720101", ("7720201",), ("7720301", "7720601"))]),
    ("C00, journalism, TP.HCM",
     Profile(scores={"VA": 8.0, "SU": 8.5, "DI": 8.0, "TO": 6.0, "N1": 6.5}, home_province="TP. Hồ Chí Minh"),
     [ShortlistItem("7320101", ("7320104",), ("7320108",))]),
    ("D01 strong English, English language then business, Hà Nội, budget 40",
     Profile(scores={"VA": 7.5, "TO": 7.0, "N1": 9.25, "SU": 7.0, "DI": 7.0}, home_province="Hà Nội",
             budget_trieu=40),
     [ShortlistItem("7220201", ("7220204",), ("7220209",)), ShortlistItem("7340101", ("7340120",), ())]),
]

LEVEL_VI = {"mo_uoc": "mơ ước", "thu_suc": "thử sức", "vua_suc": "vừa sức", "an_toan": "an toàn"}


def render(results) -> str:
    out = ["# Sample lists", "", "Invented students run through the list rules on the current database. "
           "Scores and cutoffs are on 30 points; cutoffs are converted linearly. `*` marks a mixed-method program.", ""]
    totals = Counter()
    for title, result in results:
        lv = Counter(w.candidate.level.value for w in result.wishes)
        totals.update(lv)
        out += [f"## {title}", "",
                f"{len(result.wishes)} wishes: " + ", ".join(f"{LEVEL_VI[x.value]} {lv.get(x.value, 0)}"
                                                             for x in LEVEL_ORDER)
                + (f". Notes: {', '.join(result.notes)}" if result.notes else ""), "",
                "| NV | item | level | school · program | ngành | score | cutoffs (2025 / 2026) | school score | city |",
                "|---|---|---|---|---|---|---|---|---|"]
        for w in result.wishes:
            c, s = w.candidate, w.candidate.student
            cuts = " / ".join(f"{s.cutoffs[y].score_30:.2f}" if y in s.cutoffs else "-" for y in (2025, 2026))
            flags = [] + (["vượt ngân sách"] if c.over_budget else []) + (["học phí chưa rõ"] if c.tuition_unknown
                                                                            else [])
            out.append(f"| {w.nv} | {c.item_index + 1} | {LEVEL_VI[c.level.value]} | {c.program.school_code} · "
                       f"{c.program.name}{' *' if c.is_mixed_method else ''} | {c.program.moet_code} ({c.relation}) "
                       f"| {s.score:.2f} ({combo_label(s.combo)}) | {cuts} | {c.school_score}"
                       f"{' · ' + ', '.join(flags) if flags else ''} | {c.program.city}"
                       f"{' · xa nhà' if c.far_from_home else ''} |")
        out.append("")
    return "\n".join(out) + "\n"


def run_samples():
    conn = db.connect()
    programs, parents = load_programs(conn), load_nganh_parents(conn)
    year = load_data_config()["target_admission_year"]
    rules, cfg, provinces = load_rules(year), load_list_config(), load_provinces()
    return [(title, build_list(p, sl, programs, parents, rules, cfg, provinces, year)) for title, p, sl in SAMPLES]


def main():
    text = render(run_samples())
    out = BUILD_DIR / "sample_lists.md"
    out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
