"""Test bench for the list rules: many invented students across score bands, measured on the real database.

Every student is equally good in every subject (each subject = total / 3), so a band's total is the student's exam
total on any combination. For each band and each shortlist case it builds the list and measures what a person would
check by hand: does the list reach 15 wishes, how the levels spread, whether a wish sits below an easier one (a
useless wish), whether the same program appears twice, how many an toàn wishes there are and at how many schools.

Run: python -m uniadvisor.plan.bench   (writes data/build/bench.md)
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from uniadvisor.data.text import name_words
from uniadvisor.plan.chances import ChangeModel, chances
from uniadvisor.plan.models import LEVEL_ORDER, Level, ListResult, Profile, ShortlistItem
from uniadvisor.plan.strategy import build_list

SUBJECTS = ("TO", "VA", "N1", "LI", "HO", "SI", "SU", "DI")
TOTALS = (15.0, 17.0, 19.0, 21.0, 23.0, 25.0, 27.0, 29.0)
CLOSE_PROPOSED, FURTHER_CLOSE = 2, 5          # as the app does (app/service.py, step 6)
USELESS_MARGIN = 0.5                          # a wish counts as useless when it is harder by more than this

# (label, shortlist main codes): one item, then two items.
CASES = [
    ("CNTT", ("7480201",)), ("Khoa học máy tính", ("7480101",)), ("Quản trị kinh doanh", ("7340101",)),
    ("Kế toán", ("7340301",)), ("Marketing", ("7340115",)), ("Ngôn ngữ Anh", ("7220201",)), ("Luật", ("7380101",)),
    ("Báo chí", ("7320101",)), ("Y khoa", ("7720101",)), ("Điều dưỡng", ("7720301",)),
    ("Kỹ thuật cơ khí", ("7520103",)), ("Sư phạm Toán", ("7140209",)), ("Logistics", ("7510605",)),
    ("CNTT + QTKD", ("7480201", "7340101")), ("Ngôn ngữ Anh + QTKD", ("7220201", "7340101")),
    ("Kế toán + Tài chính", ("7340301", "7340201")), ("Báo chí + Luật", ("7320101", "7380101")),
]


@dataclass(frozen=True)
class Measure:
    case: str
    total: float
    city: str
    wishes: int
    levels: dict[Level, int]
    useless: int
    duplicated: int               # wishes whose school and name (variant markers kept) repeat an earlier wish
    safe: int
    safe_schools: int
    safe_most_at_one_school: int
    mixed_safe: int
    none: float | None = None             # chance of no admission at the score entered (plan/chances.py)
    none_minus_1: float | None = None     # ... if the real score is 1 point lower


def student(total: float, province: str) -> Profile:
    return Profile(scores={s: round(total / 3, 4) for s in SUBJECTS}, home_province=province)


def shortlist(codes: Iterable[str], close: Callable[[str], list[str]]) -> list[ShortlistItem]:
    items = []
    for code in codes:
        ranked = [c for c in close(code) if c != code]
        items.append(ShortlistItem(code, tuple(ranked[:CLOSE_PROPOSED]),
                                   tuple(ranked[CLOSE_PROPOSED:CLOSE_PROPOSED + FURTHER_CLOSE])))
    return items


def measure(case: str, total: float, city: str, result: ListResult, model: ChangeModel | None = None,
            list_cfg: dict | None = None) -> Measure:
    ws = [w.candidate for w in result.wishes]
    useless = sum(any(later.gap > earlier.gap + USELESS_MARGIN for earlier in ws[:j]) for j, later in enumerate(ws))
    seen, duplicated = set(), 0
    for c in ws:
        key = (c.program.school_code, frozenset(name_words(c.program.name, keep_variant=True)))
        duplicated += key in seen
        seen.add(key)
    safe = [c for c in ws if c.level == Level.AN_TOAN]
    per_school = Counter(c.program.school_code for c in safe)
    none = none_minus_1 = None
    if model is not None and ws:
        none, none_minus_1 = (chances(result, model, list_cfg, s).none for s in (0.0, -1.0))
    return Measure(case, total, city, len(ws), {lv: sum(c.level == lv for c in ws) for lv in LEVEL_ORDER}, useless,
                   duplicated, len(safe), len(per_school), max(per_school.values(), default=0),
                   sum(c.is_mixed_method for c in safe), none, none_minus_1)


def run_bench(programs, nganh_parent: dict[str, str], close: Callable[[str], list[str]], rules: dict, list_cfg: dict,
              provinces: dict[str, str], admission_year: int, cases=CASES, totals=TOTALS,
              homes=(("HN", "Hà Nội"), ("HCM", "TP. Hồ Chí Minh")), model: ChangeModel | None = None) -> list[Measure]:
    programs = list(programs)
    out = []
    for label, codes in cases:
        items = shortlist(codes, close)
        for total in totals:
            for city, province in homes:
                result = build_list(student(total, province), items, programs, nganh_parent, rules, list_cfg,
                                    provinces, admission_year)
                out.append(measure(label, total, city, result, model, list_cfg))
    return out


def render(ms: list[Measure]) -> str:
    out = ["# List test bench", "",
           "Invented students, equally good in every subject (each subject = total / 3), KV3, no budget, no gần nhà; "
           f"{len({m.case for m in ms})} shortlist cases x {len({m.total for m in ms})} totals x 2 home cities "
           f"= {len(ms)} lists. Close ngành as the app proposes them. A wish is useless when it is harder for the "
           f"student (cutoff minus score) by more than {USELESS_MARGIN} than a wish above it.", "",
           "## By total", "",
           "| total | lists | 15 wishes | mean wishes | mơ ước / thử sức / vừa sức / an toàn (mean) | no an toàn | "
           "useless (mean) | duplicated | mixed an toàn | an toàn at 1 school only | no admission: mean / worst | "
           "... if 1 point lower |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for total in sorted({m.total for m in ms}):
        g = [m for m in ms if m.total == total]
        n = len(g)
        mean = lambda f: sum(f(m) for m in g) / n  # noqa: E731
        lv = " / ".join(f"{mean(lambda m: m.levels[x]):.1f}" for x in LEVEL_ORDER)
        out.append(f"| {total:g} | {n} | {sum(m.wishes == 15 for m in g)} | {mean(lambda m: m.wishes):.1f} | {lv} | "
                   f"{sum(m.safe == 0 for m in g)} | {mean(lambda m: m.useless):.2f} | "
                   f"{sum(m.duplicated for m in g)} | {sum(m.mixed_safe for m in g)} | "
                   f"{sum(m.safe > 1 and m.safe_schools == 1 for m in g)} | {_risk(g, 'none')} | "
                   f"{_risk(g, 'none_minus_1')} |")
    out += ["", "## By case", "", "| case | 15 wishes | useless (mean) | no an toàn | shortest list |",
            "|---|---|---|---|---|"]
    for case in dict.fromkeys(m.case for m in ms):
        g = [m for m in ms if m.case == case]
        out.append(f"| {case} | {sum(m.wishes == 15 for m in g)} / {len(g)} | "
                   f"{sum(m.useless for m in g) / len(g):.2f} | {sum(m.safe == 0 for m in g)} | "
                   f"{min(m.wishes for m in g)} |")
    return "\n".join(out) + "\n"


def _risk(g: list[Measure], field: str) -> str:
    vals = [getattr(m, field) for m in g if getattr(m, field) is not None]
    return f"{100 * sum(vals) / len(vals):.2f}% / {100 * max(vals):.1f}%" if vals else "-"


def main():
    from uniadvisor import db
    from uniadvisor.app.catalog import Catalog
    from uniadvisor.app.facts import FactsIndex
    from uniadvisor.config import load_data_config, load_list_config, load_provinces, load_rules
    from uniadvisor.paths import BUILD_DIR
    from uniadvisor.plan.repository import load_nganh_parents, load_programs

    conn = db.connect()
    catalog = Catalog.load(conn)
    facts = FactsIndex.load(conn, catalog)
    year = load_data_config()["target_admission_year"]
    close = lambda code: [c for c in facts.get(code).close if catalog.majors[c].level == "nganh"]  # noqa: E731
    cfg = load_list_config()
    model = ChangeModel.fit(conn, tuple(load_data_config()["cutoff_years"]), cfg)
    ms = run_bench(load_programs(conn), load_nganh_parents(conn), close, load_rules(year), cfg, load_provinces(), year,
                   model=model)
    text = render(ms)
    (BUILD_DIR / "bench.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
