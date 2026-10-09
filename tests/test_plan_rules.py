"""Unit tests for the single rules of spec section 4 and the section 8 regulation facts."""

import pytest

from uniadvisor.config import load_list_config, load_provinces, load_rules, province_names
from uniadvisor.plan.models import Cutoff, Level
from uniadvisor.plan.rules import cutoffs_for_combo, floor_for, home_city, level_for, priority_points, school_score

RULES = load_rules(2027)
CFG = load_list_config()


# ---------------------------------------------------------------- priority points

@pytest.mark.parametrize("total, area, category, expected", [
    (20.0, "KV1", "none", 0.75),
    (20.0, "KV2-NT", "none", 0.5),
    (20.0, "KV2", "none", 0.25),
    (20.0, "KV3", "none", 0.0),
    (20.0, "KV3", "UT1", 2.0),
    (20.0, "KV1", "UT2", 1.75),
    (22.49, "KV1", "UT1", 2.75),                    # just below the taper threshold: full points
    (22.5, "KV1", "UT1", 2.75),                     # at the threshold: (30 - 22.5) / 7.5 * 2.75 = 2.75
    (26.25, "KV1", "none", 0.38),                   # (30 - 26.25) / 7.5 * 0.75 = 0.375 -> 0.38 (half-up)
    (25.5, "KV2", "none", 0.15),                    # 4.5 / 7.5 * 0.25 = 0.15
    (23.7, "KV2", "none", 0.21),                    # 6.3 / 7.5 * 0.25 = 0.21
    (24.0, "KV1", "UT1", 2.2),                      # 6 / 7.5 * 2.75 = 2.2
    (27.0, "KV2-NT", "UT2", 0.6),                   # 3 / 7.5 * 1.5 = 0.6
    (28.1, "KV1", "none", 0.19),                    # 1.9 / 7.5 * 0.75 = 0.19
    (26.25, "KV2", "none", 0.13),                   # 0.125 -> 0.13
    (30.0, "KV1", "UT1", 0.0),
])
def test_priority_points(total, area, category, expected):
    assert priority_points(total, area, category, 2027, 2027, RULES) == expected


def test_area_points_count_in_graduation_year_and_the_next_only():
    assert priority_points(20.0, "KV1", "UT2", 2027, 2027, RULES) == pytest.approx(1.75)
    assert priority_points(20.0, "KV1", "UT2", 2026, 2027, RULES) == pytest.approx(1.75)
    assert priority_points(20.0, "KV1", "UT2", 2025, 2027, RULES) == pytest.approx(1.0)   # category only
    assert priority_points(20.0, "KV1", "none", None, 2027, RULES) == pytest.approx(0.75)  # default: this year


def test_priority_rejects_unknown_codes():
    with pytest.raises(ValueError):
        priority_points(20.0, "KV4", "none", 2027, 2027, RULES)
    with pytest.raises(ValueError):
        priority_points(20.0, "KV1", "UT3", 2027, 2027, RULES)


# ---------------------------------------------------------------- floors

@pytest.mark.parametrize("code, expected", [
    ("7720101", 20.5),      # Y khoa: most specific prefix 772010
    ("7720201", 20.5),      # Dược học
    ("7720501", 20.5),      # Răng - Hàm - Mặt
    ("7720301", 17.0),      # Điều dưỡng: 7720
    ("7720110", 17.0),      # Y học dự phòng: starts 772011, so only 7720 applies
    ("7140209", 19.0),      # Sư phạm Toán học: 71402
    ("7140101", None),      # Giáo dục học: 71401 is not teacher training
    ("7480201", None),
    (None, None),
])
def test_floor_for(code, expected):
    assert floor_for(code, RULES) == expected


# ---------------------------------------------------------------- levels

@pytest.mark.parametrize("score, cutoffs, expected", [
    (27.0, [25.0, 24.0], Level.AN_TOAN),     # exactly 2 above the higher
    (26.99, [25.0, 24.0], Level.VUA_SUC),
    (25.0, [25.0, 24.0], Level.VUA_SUC),     # reaching the higher cutoff counts as above it
    (24.99, [25.0, 24.0], Level.THU_SUC),    # above one of the two
    (24.0, [25.0, 24.0], Level.THU_SUC),
    (22.51, [25.0, 24.0], Level.THU_SUC),    # less than 1.5 below the lower
    (22.5, [25.0, 24.0], Level.MO_UOC),      # exactly 1.5 below the lower
    (15.0, [25.0, 24.0], Level.MO_UOC),
    (24.0, [24.0], Level.VUA_SUC),           # one year of cutoffs counts as both
    (23.0, [24.0], Level.THU_SUC),
    (22.5, [24.0], Level.MO_UOC),
    (24.1 + 0.9, [25.0], Level.VUA_SUC),     # float noise does not change the level
])
def test_level_for(score, cutoffs, expected):
    assert level_for(score, cutoffs, CFG["levels"]["safe_margin"], CFG["levels"]["dream_gap"]) == expected


def test_level_needs_a_cutoff():
    with pytest.raises(ValueError):
        level_for(20.0, [], 2.0, 1.5)


def test_cutoffs_for_combo_prefers_per_combination_cutoff():
    cut = (Cutoff(2025, None, 23.5, 23.5, 30, False),
           Cutoff(2026, frozenset({"A00"}), 23.0, 23.0, 30, False),
           Cutoff(2026, frozenset({"D01", "A01"}), 24.0, 24.0, 30, False))
    assert {y: c.score_30 for y, c in cutoffs_for_combo(cut, "A00").items()} == {2025: 23.5, 2026: 23.0}
    assert {y: c.score_30 for y, c in cutoffs_for_combo(cut, "D01").items()} == {2025: 23.5, 2026: 24.0}
    assert {y: c.score_30 for y, c in cutoffs_for_combo(cut, "B00").items()} == {2025: 23.5}  # 2026 has none for B00


# ---------------------------------------------------------------- school score

@pytest.mark.parametrize("tuition, budget, near, city, home, expected", [
    (30_000_000, None, False, "HN", "HN", (100, False, False)),      # no budget: no penalty
    (None, 20, False, "HN", "HN", (100, False, False)),              # unknown fee: no penalty
    (30_000_000, 30, False, "HN", "HN", (100, False, False)),        # at the budget
    (36_000_000, 30, False, "HN", "HN", (90, True, False)),          # exactly 20% over
    (36_100_000, 30, False, "HN", "HN", (80, True, False)),          # more than 20% over
    (30_000_000, 30, True, "HCM", "HN", (80, False, True)),          # far from home
    (40_000_000, 30, True, "HCM", "HN", (60, True, True)),           # penalties add up
    (30_000_000, 30, False, "HCM", "HN", (100, False, False)),       # "gần nhà" not asked
    (30_000_000, 30, True, "HCM", None, (100, False, False)),        # home city unknown
])
def test_school_score(tuition, budget, near, city, home, expected):
    assert school_score(tuition, budget, near, city, home, CFG) == expected


# ---------------------------------------------------------------- provinces

def test_province_list_and_home_city():
    provinces = load_provinces()
    names = province_names()
    assert len(names) == 61 and len(set(names)) == 61
    assert "Bình Dương" not in names and "Bà Rịa - Vũng Tàu" not in names
    assert home_city("Bình Dương", provinces) == "HCM"
    assert home_city("Bà Rịa - Vũng Tàu", provinces) == "HCM"
    assert home_city("Huế", provinces) == "HN" and home_city("Thừa Thiên Huế", provinces) == "HN"
    assert home_city("Quảng Trị", provinces) == "HN"
    assert home_city("Đà Nẵng", provinces) == "HCM" and home_city("Kon Tum", provinces) == "HCM"
    assert home_city("Hà Nội", provinces) == "HN"
    assert home_city("Atlantis", provinces) is None


def test_list_quotas_add_up_to_max_wishes():
    total = RULES["application"]["max_wishes"]
    q = CFG["quotas"]
    assert sum(q["one_item"]["item1"].values()) == total
    assert sum(q["two_items"]["item1"].values()) + sum(q["two_items"]["item2"].values()) == total
    assert q["one_item"]["item1"] == {"mo_uoc": 3, "thu_suc": 5, "vua_suc": 4, "an_toan": 3}
    # design decision 2026-10-07: item 2 has no mơ ước slot (it could almost never be used); item 1 takes it
    assert q["two_items"]["item1"] == {"mo_uoc": 3, "thu_suc": 3, "vua_suc": 3, "an_toan": 2}
    assert q["two_items"]["item2"] == {"mo_uoc": 0, "thu_suc": 2, "vua_suc": 1, "an_toan": 1}
