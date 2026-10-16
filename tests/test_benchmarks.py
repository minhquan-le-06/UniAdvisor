"""The list test bench (pipelines/benchmarks/bench.py) on the fake database."""

from uniadvisor.config import load_list_config, load_provinces, load_rules
from pipelines.benchmarks import bench
from uniadvisor.planner.models import Level
from uniadvisor.planner.repository import load_nganh_parents, load_programs


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


def test_useless_counts_split_item2_below_item1():
    from tests.test_planner_strategy import prog, run
    from uniadvisor.planner.models import ShortlistItem
    r = run([prog("V:1", cutoff=23.0), prog("T:1", cutoff=24.5), prog("Y:1", moet="7340101", cutoff=24.5)],
            [ShortlistItem("7480201"), ShortlistItem("7340101")])
    by = {w.candidate.program.id: w.candidate for w in r.wishes}       # the student has 24: gaps -1, 0.5, 0.5
    assert bench.useless_counts([by["V:1"], by["T:1"]]) == (1, 0)       # same item: harder below easier
    assert bench.useless_counts([by["V:1"], by["Y:1"]]) == (0, 1)       # item 2 below item 1: counted apart
    assert bench.useless_counts([by["T:1"], by["V:1"]]) == (0, 0)


def test_calibration_counts_failures_and_model(tmp_path):
    import numpy as np
    from pipelines.benchmarks import calibration
    from uniadvisor.planner.chances import ChangeModel
    path = tmp_path / "history.csv"
    path.write_text("school_code,year,key_code,score,scale,status\n"
                    "A,2023,1,20,30,single_source\nA,2024,1,21,30,single_source\nA,2025,1,24,30,single_source\n"
                    "B,2023,1,20,30,single_source\nB,2024,1,20,30,single_source\nB,2025,1,21,30,single_source\n"
                    "C,2023,1,20,40,single_source\n", encoding="utf-8")
    history = calibration.load_history(path)
    assert set(history) == {("A", "1"), ("B", "1")}                     # 40-point rows left out
    model = ChangeModel(np.zeros(0), np.array([-1.0, 0.0, 1.0, 3.0]), (2025, 2026), 4)
    assert calibration.fail_probability(model, 2.0) == 0.25             # only the +3 change beats a 2-point margin
    rows = calibration.calibrate(history, model, max_change=5.0, margins=(2.0,))
    overall = rows[-1]
    assert overall.year is None and overall.n == 2
    assert overall.history == 0.5                                       # A: 24 > 21 + 2 fails; B: 21 <= 22 holds
    assert 0 < overall.model <= 0.25
