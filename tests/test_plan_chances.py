"""Chances of being admitted at each level (plan/chances.py) and their Vietnamese text."""

import numpy as np
import pytest

from tests.test_plan_strategy import STUDENT, prog, run
from uniadvisor.app.texts import chance_lines, chance_pct, no_admission_warning
from uniadvisor.config import load_list_config
from uniadvisor.plan.chances import ChangeModel, Chances, chances
from uniadvisor.plan.models import Level, ShortlistItem

CFG = load_list_config()


def model(school=(0.0,), program=(-0.5, 0.5)):
    return ChangeModel(np.array(school), np.array(program), (2025, 2026), 2)


def test_fit_on_the_fake_database(fake_db):
    m = ChangeModel.fit(fake_db, (2025, 2026), CFG)
    # programs with one non-mixed cutoff in both years: CS1, YK, DD, SPT, NNA, MIL:CS (IT2 is per combination in
    # 2026, KTPM's 2026 cutoff is mixed); too few schools with 3 programs, so no school shifts
    assert m.n_programs == 6 and len(m.school_shifts) == 0 and len(m.program_shifts) == 6
    assert abs(float(np.mean(m.program_shifts))) < 1e-9                      # centred: no trend
    assert ChangeModel.fit(fake_db, (2025, 2026), CFG).program_shifts.tolist() == m.program_shifts.tolist()


def test_chances_follow_the_margins():
    # the student scores 24.0; cutoffs 21 (an toàn, +3), 24 (vừa sức, margin 0), 26 (mơ ước, -2)
    r = run([prog("A:1", cutoff=26.0), prog("B:1", cutoff=24.0), prog("C:1", cutoff=21.0)],
            [ShortlistItem("7480201")])
    assert [w.candidate.level for w in r.wishes] == [Level.MO_UOC, Level.VUA_SUC, Level.AN_TOAN]
    ch = chances(r, model(), CFG)
    assert ch.at_least[Level.MO_UOC] == 0.0                                  # 2 points short, changes are ±0.5
    assert 0.4 < ch.at_least[Level.VUA_SUC] < 0.6                            # at the cutoff: half the years
    assert ch.at_least[Level.AN_TOAN] == 1.0 and ch.none == 0.0
    assert ch == chances(r, model(), CFG)                                    # same list, same chances
    up = chances(r, model(), CFG, score_shift=1.0)
    assert up.at_least[Level.VUA_SUC] == 1.0 and up.score_shift == 1.0


def test_programs_of_one_school_move_together():
    # two wishes 1 point above their cutoffs: independent programs almost never both fail; one school shift can
    r = run([prog("S:1", cutoff=23.0), prog("S:2", cutoff=23.0, moet="7480201")], [ShortlistItem("7480201")])
    shared = chances(r, model(school=(2.0, 0.0, 0.0, 0.0), program=(0.0,)), CFG)   # +2: cutoffs rise
    assert 0.2 < shared.none < 0.3                                           # the school's bad year: both fail


@pytest.mark.parametrize("p, text", [(0.995, "≥ 99%"), (0.99, "≥ 99%"), (0.986, "98%"), (0.33, "33%"),
                                     (0.004, "< 1%"), (0.0, "< 1%")])
def test_chance_pct(p, text):
    assert chance_pct(p, 0.99) == text


def test_chance_lines():
    ch = Chances(0.0, {Level.MO_UOC: 0.06, Level.THU_SUC: 0.33, Level.VUA_SUC: 0.98, Level.AN_TOAN: 1.0}, 0.0)
    (line,) = chance_lines([ch], 0.99, expected=True)
    assert line == ("Nếu em thi đúng như dự kiến, khả năng trúng tuyển một nguyện vọng mơ ước: 6% · thử sức trở lên: "
                    "33% · vừa sức trở lên: 98% · một nguyện vọng bất kỳ trong danh sách: ≥ 99%")
    assert chance_lines([ch], 0.99, expected=False)[0].startswith("Với điểm của em, ")


def test_no_admission_warning():
    assert no_admission_warning(0.8, 0.99).startswith("Với danh sách này, khả năng em không trúng tuyển nguyện vọng "
                                                      "nào là khoảng 80%")
