"""The list test bench (plan/bench.py) on the fake database."""

from uniadvisor.config import load_list_config, load_provinces, load_rules
from uniadvisor.plan import bench
from uniadvisor.plan.models import Level
from uniadvisor.plan.repository import load_nganh_parents, load_programs


def test_bench_measures_every_list(fake_db):
    ms = bench.run_bench(load_programs(fake_db), load_nganh_parents(fake_db), lambda code: [], load_rules(2027),
                         load_list_config(), load_provinces(), 2027, cases=[("Máy tính", ("74801",))],
                         totals=(20.0, 26.0))
    assert [(m.total, m.city) for m in ms] == [(20.0, "HN"), (20.0, "HCM"), (26.0, "HN"), (26.0, "HCM")]
    for m in ms:
        assert m.wishes == sum(m.levels.values()) <= 15
        assert m.safe == m.levels[Level.AN_TOAN] and m.mixed_safe == 0 and m.duplicated == 0
    strong = [m for m in ms if m.total == 26.0]
    assert all(m.safe >= 1 for m in strong)
    assert "| 26 | 2 |" in bench.render(ms)


def test_student_has_the_band_total_on_every_combination():
    p = bench.student(24.0, "Hà Nội")
    assert round(p.scores["TO"] + p.scores["LI"] + p.scores["HO"], 2) == 24.0
    assert round(p.scores["VA"] + p.scores["SU"] + p.scores["DI"], 2) == 24.0


def test_shortlist_takes_two_close_and_five_further():
    close = {"A": ["A", "B", "C", "D", "E", "F", "G", "H", "I"]}
    (item,) = bench.shortlist(["A"], lambda c: close[c])
    assert item.close_codes == ("B", "C") and item.further_close_codes == ("D", "E", "F", "G", "H")
