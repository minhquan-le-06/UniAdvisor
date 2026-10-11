"""Tests for the student's score, candidates (4.1) and the 15-wish strategy (4.5), on synthetic programs.

The student scores 8 in Toán, Vật lí and Hóa học: 24.0 on A00 with no priority (KV3). With one cutoff C (used for
both years): an toàn C <= 22, vừa sức 22 < C <= 24, thử sức 24 < C < 25.5, mơ ước C >= 25.5.
"""

import random

import pytest

from uniadvisor.config import load_list_config, load_provinces, load_rules
from uniadvisor.planner.models import Cutoff, Level, ProgramFacts, Profile, ShortlistItem
from uniadvisor.planner.scoring import best_exam_total, evaluate
from uniadvisor.planner.strategy import build_list

RULES, CFG, PROVINCES = load_rules(2027), load_list_config(), load_provinces()
A00 = {"A00": ("HO", "LI", "TO")}
STUDENT = Profile(scores={"TO": 8.0, "LI": 8.0, "HO": 8.0}, home_province="Hà Nội")
CUTOFF = {Level.AN_TOAN: 21.0, Level.VUA_SUC: 23.0, Level.THU_SUC: 25.0, Level.MO_UOC: 26.0}
PARENTS = {"7480101": "74801", "7480103": "74801", "7480201": "74802", "7480104": "74801", "7340101": "73401"}


def prog(pid, moet="7480201", cutoff=23.0, city="HN", tuition=None, school=None, cutoffs=None, combos=None,
         mixed=False):
    cuts = cutoffs if cutoffs is not None else (Cutoff(2025, None, cutoff, cutoff, 30, False),
                                                Cutoff(2026, None, cutoff, cutoff, 30, False))
    return ProgramFacts(pid, school or pid.split(":")[0], f"Trường {pid}", f"Ngành {pid}", moet, city,
                        combos or dict(A00), tuple(cuts), tuition, is_mixed_method=mixed)


def many(prefix, level, n, moet="7480201", start=0, **kw):
    """n programs at one level; cutoffs differ slightly so ordering is visible."""
    base = CUTOFF[level]
    return [prog(f"{prefix}{i:02d}:{moet}", moet, round(base - i * 0.01, 2), **kw) for i in range(start, start + n)]


def run(programs, shortlist, profile=STUDENT):
    return build_list(profile, shortlist, programs, PARENTS, RULES, CFG, PROVINCES, 2027)


def levels(result):
    return [w.candidate.level for w in result.wishes]


def level_counts(result, item):
    return {lv: sum(w.candidate.level == lv for w in result.wishes if w.candidate.item_index == item) for lv in Level}


# ---------------------------------------------------------------- the student's score

def test_best_combination_wins():
    p = prog("S:1", combos={"A00": ("HO", "LI", "TO"), "D01": ("N1", "TO", "VA")},
             cutoffs=(Cutoff(2026, frozenset({"A00"}), 25.0, 25.0, 30, False),
                      Cutoff(2026, frozenset({"D01"}), 20.0, 20.0, 30, False)))
    student = Profile(scores={"TO": 8.0, "LI": 8.0, "HO": 8.0, "N1": 7.0, "VA": 7.0}, home_province="Hà Nội")
    s, reason = evaluate(p, student, RULES, CFG, 2027)
    assert reason is None and s.combo == "D01" and s.level == Level.AN_TOAN     # 22.0 vs 20.0 beats 24.0 vs 25.0
    assert s.exam_total == 22.0


def test_priority_and_extra_points_are_added():
    student = Profile(scores={"TO": 7.0, "LI": 7.0, "HO": 7.0}, home_province="Hà Nội", area="KV1",
                      extra_points={"S": 0.5})
    s, _ = evaluate(prog("S:1", cutoff=21.0), student, RULES, CFG, 2027)
    assert (s.exam_total, s.priority, s.extra, s.score) == (21.0, 0.75, 0.5, 22.25)
    s2, _ = evaluate(prog("T:1", cutoff=21.0), student, RULES, CFG, 2027)
    assert s2.extra == 0.0                                       # extra points are per school


def test_missing_subject_means_no_usable_combination():
    student = Profile(scores={"TO": 8.0, "LI": 8.0}, home_province="Hà Nội")
    assert evaluate(prog("S:1"), student, RULES, CFG, 2027) == (None, "no_usable_combination")


def test_weak_combinations_are_not_used():
    """A01 27 and D01 23: a D01-only program is left out; a program admitting both is scored on A01."""
    student = Profile(scores={"TO": 9.0, "LI": 9.0, "N1": 9.0, "VA": 5.0}, home_province="Hà Nội")
    d01_only = prog("SGD:1", cutoff=23.0, combos={"D01": ("N1", "TO", "VA")})
    both = prog("UET:1", cutoff=26.0, combos={"A01": ("LI", "N1", "TO"), "D01": ("N1", "TO", "VA")})
    best = best_exam_total([d01_only, both], student.scores)
    assert best == 27.0
    assert evaluate(d01_only, student, RULES, CFG, 2027, best) == (None, "weak_combination")
    assert evaluate(d01_only, student, RULES, CFG, 2027)[1] is None            # without the rule it would be used
    s, _ = evaluate(both, student, RULES, CFG, 2027, best)
    assert s.combo == "A01" and s.exam_total == 27.0
    close = Profile(scores={"TO": 9.0, "LI": 9.0, "N1": 9.0, "VA": 7.5}, home_province="Hà Nội")   # D01 25.5
    assert evaluate(d01_only, close, RULES, CFG, 2027, best_exam_total([d01_only, both], close.scores))[1] is None
    own = Profile(scores=student.scores, home_province="Hà Nội", own_scores={"SGD": (25.0, 30)})
    assert evaluate(d01_only, own, RULES, CFG, 2027, best)[1] is None        # the student's own score still counts
    result = run([d01_only, both], [ShortlistItem("7480201")], student)
    assert [w.candidate.program.id for w in result.wishes] == ["UET:1"]
    assert ("SGD:1", "weak_combination") in [(e.program_id, e.reason) for e in result.excluded]


def test_no_cutoff_and_floor():
    assert evaluate(prog("S:1", cutoffs=()), STUDENT, RULES, CFG, 2027) == (None, "no_cutoff")
    weak = Profile(scores={"TO": 6.5, "HO": 6.5, "SI": 7.0}, home_province="Hà Nội")
    yk = prog("Y:1", moet="7720101", cutoff=20.0, combos={"B00": ("HO", "SI", "TO")})
    assert evaluate(yk, weak, RULES, CFG, 2027) == (None, "below_floor")            # 20.0 < 20.5 (Y khoa)
    with_priority = Profile(scores=weak.scores, home_province="Hà Nội", area="KV1")
    s, reason = evaluate(yk, with_priority, RULES, CFG, 2027)
    assert reason is None and s.score == 20.75                                       # priority counts for floors
    extra_only = Profile(scores=weak.scores, home_province="Hà Nội", extra_points={"Y": 1.0})
    assert evaluate(yk, extra_only, RULES, CFG, 2027) == (None, "below_floor")       # school extra points do not


def test_converted_and_mixed_cutoffs_are_used():
    p = prog("M:1", cutoffs=(Cutoff(2025, None, 24.5, 24.5, 30, False), Cutoff(2026, None, 24.0, 80.0, 100, True)),
             mixed=True)
    s, _ = evaluate(p, STUDENT, RULES, CFG, 2027)
    assert s.level == Level.THU_SUC and {y: c.score_30 for y, c in s.cutoffs.items()} == {2025: 24.5, 2026: 24.0}


def test_mixed_method_is_never_an_toan():
    plain, _ = evaluate(prog("P:1", cutoff=21.0), STUDENT, RULES, CFG, 2027)
    mixed, _ = evaluate(prog("M:1", cutoff=21.0, mixed=True), STUDENT, RULES, CFG, 2027)
    assert plain.level == Level.AN_TOAN and not plain.capped_mixed_method
    assert mixed.level == Level.VUA_SUC and mixed.capped_mixed_method          # 24.0 >= 21.0 + 2, but mixed
    one_year = prog("Y:1", cutoffs=(Cutoff(2025, None, 21.0, 21.0, 30, False),
                                    Cutoff(2026, None, 20.0, 66.7, 100, True)))
    s, _ = evaluate(one_year, STUDENT, RULES, CFG, 2027)
    assert s.level == Level.VUA_SUC and s.capped_mixed_method                 # a mixed cutoff in either year
    lower, _ = evaluate(prog("L:1", cutoff=23.0, mixed=True), STUDENT, RULES, CFG, 2027)
    assert lower.level == Level.VUA_SUC and not lower.capped_mixed_method      # below the cap: unchanged


def test_own_score_at_a_school_replaces_the_total_and_lifts_the_cap():
    # cutoff 20.0 on 30 in 2025, 66.7/100 (mixed) in 2026; the student says their score at the school is 80/100
    p = prog("M:1", cutoffs=(Cutoff(2025, None, 20.0, 20.0, 30, False), Cutoff(2026, None, 20.01, 66.7, 100, True)))
    own = Profile(scores=STUDENT.scores, home_province="Hà Nội", own_scores={"M": (80.0, 100)},
                  extra_points={"M": 1.0})
    s, _ = evaluate(p, own, RULES, CFG, 2027)
    assert s.own_score == (80.0, 100) and s.score == 24.0 and s.extra == 0.0   # 80/100 -> 24 on 30; extra included
    assert list(s.cutoffs) == [2026]                                           # only cutoffs on the same scale
    assert s.level == Level.AN_TOAN and not s.capped_mixed_method             # 24.0 >= 20.01 + 2, own formula
    other, _ = evaluate(prog("T:1", cutoff=21.0, mixed=True), own, RULES, CFG, 2027)
    assert other.own_score is None and other.capped_mixed_method               # per school
    on_30 = Profile(scores=STUDENT.scores, home_province="Hà Nội", own_scores={"M": (25.0, 30)})
    s30, _ = evaluate(p, on_30, RULES, CFG, 2027)
    assert s30.own_score == (25.0, 30) and list(s30.cutoffs) == [2025] and s30.level == Level.AN_TOAN
    no_match = Profile(scores=STUDENT.scores, home_province="Hà Nội", own_scores={"M": (35.0, 40)})
    s40, _ = evaluate(p, no_match, RULES, CFG, 2027)
    assert s40.own_score is None and s40.score == 24.0 and s40.capped_mixed_method   # no cutoff on 40: as before


def test_cutoff_shift_moves_the_level_and_the_gap():
    shifted = Profile(scores=STUDENT.scores, home_province="Hà Nội", cutoff_shifts={"S": 1.5})
    s, _ = evaluate(prog("S:1", cutoff=21.0), shifted, RULES, CFG, 2027)
    assert s.level == Level.VUA_SUC and s.cutoff_shift == 1.5                 # 24.0 < 21.0 + 1.5 + 2
    easier = Profile(scores=STUDENT.scores, home_province="Hà Nội", cutoff_shifts={"S": -1.0})
    r = run([prog("S:7480201", cutoff=24.5), prog("T:7480201", cutoff=24.2)], [ShortlistItem("7480201")], easier)
    by_id = {w.candidate.program.id: w.candidate for w in r.wishes}
    assert by_id["S:7480201"].level == Level.VUA_SUC and by_id["S:7480201"].gap == -0.5   # 24.5 - 1 vs 24.0
    assert by_id["T:7480201"].level == Level.THU_SUC and by_id["T:7480201"].gap == 0.2
    assert by_id["S:7480201"].latest_cutoff == 23.5


# ---------------------------------------------------------------- quotas and shift-down

def full_pool(n=8, moet="7480201", **kw):
    return [p for lv in Level for p in many(lv.value[:2].upper(), lv, n, moet, **kw)]


def test_one_item_quotas():
    r = run(full_pool(), [ShortlistItem("7480201")])
    counts = {lv: levels(r).count(lv) for lv in Level}
    assert counts == {Level.MO_UOC: 3, Level.THU_SUC: 5, Level.VUA_SUC: 4, Level.AN_TOAN: 3}
    assert len(r.wishes) == 15 and [w.nv for w in r.wishes] == list(range(1, 16))
    assert levels(r)[-3:] == [Level.AN_TOAN] * 3                                     # an toàn at the bottom
    assert r.notes == []


def test_empty_slots_shift_down():
    pool = many("TH", Level.THU_SUC, 2) + many("VU", Level.VUA_SUC, 20) + many("AN", Level.AN_TOAN, 20)
    r = run(pool, [ShortlistItem("7480201")])
    counts = {lv: levels(r).count(lv) for lv in Level}
    # mơ ước 3 -> thử sức (5+3=8, only 2) -> vừa sức gets 4 + 6 = 10; an toàn keeps 3
    assert counts == {Level.MO_UOC: 0, Level.THU_SUC: 2, Level.VUA_SUC: 10, Level.AN_TOAN: 3}
    assert "shifted_down:1:mo_uoc:3" in r.notes and "shifted_down:1:thu_suc:6" in r.notes


def test_an_toan_top_up_from_further_close_in_closeness_order():
    pool = (many("MO", Level.MO_UOC, 5) + many("TH", Level.THU_SUC, 8) + many("VU", Level.VUA_SUC, 8)
            + many("AN", Level.AN_TOAN, 1)
            + many("F1", Level.AN_TOAN, 1, moet="7480104") + many("F2", Level.AN_TOAN, 3, moet="7480103"))
    item = ShortlistItem("7480201", further_close_codes=("7480104", "7480103"))
    r = run(pool, [item])
    safe = [w.candidate for w in r.wishes if w.candidate.level == Level.AN_TOAN]
    assert [c.program.moet_code for c in safe] == ["7480201", "7480104", "7480103"]   # own first, then closeness
    assert [c.relation for c in safe] == ["main", "further_close", "further_close"]
    assert "topped_up:1:2" in r.notes and len(r.wishes) == 15


def test_short_list_when_top_up_runs_out():
    pool = many("MO", Level.MO_UOC, 3) + many("TH", Level.THU_SUC, 5) + many("VU", Level.VUA_SUC, 4)
    r = run(pool, [ShortlistItem("7480201", further_close_codes=("7480104",))])
    assert len(r.wishes) == 12
    assert "short:1:3" in r.notes and "short_list:12" in r.notes


def test_further_close_is_not_used_when_not_needed():
    pool = full_pool() + many("F1", Level.AN_TOAN, 3, moet="7480104")
    r = run(pool, [ShortlistItem("7480201", further_close_codes=("7480104",))])
    assert all(w.candidate.relation == "main" for w in r.wishes)


# ---------------------------------------------------------------- two items and ordering

def test_two_items_quotas_and_order():
    pool = full_pool(moet="7480201") + full_pool(moet="7340101")
    r = run(pool, [ShortlistItem("7480201"), ShortlistItem("7340101")])
    items = [w.candidate.item_index for w in r.wishes]
    lv = levels(r)
    assert items.count(0) == 11 and items.count(1) == 4
    # item 1's non-an-toàn (9), item 2's non-an-toàn (3), an toàn: item 1's 2 then item 2's 1
    assert items == [0] * 9 + [1] * 3 + [0, 0, 1]
    assert lv[:12].count(Level.AN_TOAN) == 0 and lv[12:] == [Level.AN_TOAN] * 3
    assert level_counts(r, 0) == {Level.MO_UOC: 3, Level.THU_SUC: 3, Level.VUA_SUC: 3, Level.AN_TOAN: 2}
    assert level_counts(r, 1) == {Level.MO_UOC: 0, Level.THU_SUC: 2, Level.VUA_SUC: 1, Level.AN_TOAN: 1}  # no mơ ước


def test_a_program_appears_once_item1_first():
    shared = prog("SH:7480201", "7480201", CUTOFF[Level.VUA_SUC])
    r = run([shared], [ShortlistItem("7480201"), ShortlistItem("74802")])
    assert [w.candidate.item_index for w in r.wishes] == [0]
    assert [(e.program_id, e.item_index, e.reason) for e in r.excluded] == [("SH:7480201", 1, "taken_by_item1")]


def test_nhom_nganh_item_takes_every_nganh_in_the_group():
    pool = [prog("A:7480101", "7480101"), prog("B:7480103", "7480103"), prog("C:7480201", "7480201")]
    r = run(pool, [ShortlistItem("74801")])
    assert sorted(w.candidate.program.id for w in r.wishes) == ["A:7480101", "B:7480103"]
    assert {w.candidate.relation for w in r.wishes} == {"group"}


def test_close_nganh_are_candidates():
    pool = [prog("A:7480201", "7480201"), prog("B:7480101", "7480101"), prog("C:7480103", "7480103")]
    r = run(pool, [ShortlistItem("7480201", close_codes=("7480101",))])
    assert {(w.candidate.program.id, w.candidate.relation) for w in r.wishes} == {("A:7480201", "main"),
                                                                                  ("B:7480101", "close")}


def test_list_order_gap_then_school_score_then_id():
    pool = [prog("A:7480201", cutoff=23.0, tuition=40_000_000),       # over budget: school score 80
            prog("B:7480201", cutoff=22.5), prog("C:7480201", cutoff=23.5),
            prog("D:7480201", cutoff=23.5), prog("E:7480201", cutoff=23.5, tuition=40_000_000)]
    student = Profile(scores=STUDENT.scores, home_province="Hà Nội", budget_trieu=30)
    r = run(pool, [ShortlistItem("7480201")], student)
    assert [w.candidate.program.id for w in r.wishes] == ["C:7480201", "D:7480201", "E:7480201", "A:7480201",
                                                          "B:7480201"]
    assert [w.candidate.school_score for w in r.wishes] == [100, 100, 80, 80, 100]


def test_list_order_by_gap_within_each_part():
    r = run(full_pool(), [ShortlistItem("7480201")])
    gaps = [w.candidate.gap for w in r.wishes]
    assert gaps[:12] == sorted(gaps[:12], reverse=True)
    assert gaps[12:] == sorted(gaps[12:], reverse=True)


def test_list_order_uses_the_students_own_score_per_program():
    # A has the higher cutoff, but 2 extra points at school A make it closer for this student than B
    pool = [prog("A:7480201", cutoff=25.0), prog("B:7480201", cutoff=24.5)]
    student = Profile(scores=STUDENT.scores, home_province="Hà Nội", extra_points={"A": 2.0})
    r = run(pool, [ShortlistItem("7480201")], student)
    assert [(w.candidate.program.id, w.candidate.gap) for w in r.wishes] == [("B:7480201", 0.5), ("A:7480201", -1.0)]


def test_school_score_decides_who_fills_a_full_level():
    pool = (many("MO", Level.MO_UOC, 3) + many("TH", Level.THU_SUC, 5) + many("VU", Level.VUA_SUC, 4)
            + many("AN", Level.AN_TOAN, 3) + [prog("FAR:7480201", cutoff=21.5, city="HCM")])
    near = Profile(scores=STUDENT.scores, home_province="Nghệ An", near_home=True)
    r = run(pool, [ShortlistItem("7480201")], near)
    assert [w.candidate.program.id for w in r.wishes][-3:] == ["AN00:7480201", "AN01:7480201", "AN02:7480201"]
    assert ("FAR:7480201", 0, "not_selected") in [(e.program_id, e.item_index, e.reason) for e in r.excluded]


# ---------------------------------------------------------------- student's changes

def test_removed_schools_and_wishes_are_excluded():
    pool = [prog("A:7480201"), prog("B:7480201"), prog("C:7480201")]
    student = Profile(scores=STUDENT.scores, home_province="Hà Nội", removed_schools=frozenset({"A"}),
                      removed_programs=frozenset({"B:7480201"}))
    r = run(pool, [ShortlistItem("7480201")], student)
    assert [w.candidate.program.id for w in r.wishes] == ["C:7480201"]
    assert {(e.program_id, e.reason) for e in r.excluded} == {("A:7480201", "removed_school"),
                                                             ("B:7480201", "removed_program")}


def test_extra_points_raise_the_level():
    pool = [prog("A:7480201", cutoff=24.5)]
    assert levels(run(pool, [ShortlistItem("7480201")])) == [Level.THU_SUC]
    student = Profile(scores=STUDENT.scores, home_province="Hà Nội", extra_points={"A": 0.5})
    assert levels(run(pool, [ShortlistItem("7480201")], student)) == [Level.VUA_SUC]


def test_mixed_method_mark_travels_with_the_wish():
    pool = [prog("M:7480201", mixed=True), prog("N:7480201")]
    r = run(pool, [ShortlistItem("7480201")])
    assert {w.candidate.program.id: w.candidate.is_mixed_method for w in r.wishes} == {"M:7480201": True,
                                                                                      "N:7480201": False}


# ---------------------------------------------------------------- determinism and input checks

def test_same_input_same_output_whatever_the_program_order():
    pool = full_pool() + full_pool(moet="7340101")
    shortlist = [ShortlistItem("7480201"), ShortlistItem("7340101")]
    expected = [w.candidate.program.id for w in run(pool, shortlist).wishes]
    for seed in range(5):
        shuffled = pool[:]
        random.Random(seed).shuffle(shuffled)
        assert [w.candidate.program.id for w in run(shuffled, shortlist).wishes] == expected


def test_shortlist_must_have_one_or_two_items():
    with pytest.raises(ValueError):
        run([], [])
    with pytest.raises(ValueError):
        run([], [ShortlistItem("7480201")] * 3)


# ---------------------------------------------------------------- favorite school

def fav_student(school="F"):
    return Profile(scores=STUDENT.scores, home_province="Hà Nội", favorite_school=school)


def test_favorite_school_wins_slots_in_every_level():
    pool = full_pool() + [prog("F:1", cutoff=CUTOFF[Level.THU_SUC] - 0.5), prog("F:2", cutoff=CUTOFF[Level.VUA_SUC] - 0.5)]
    plain = run(pool, [ShortlistItem("7480201")])
    fav = run(pool, [ShortlistItem("7480201")], fav_student())
    assert not {"F:1", "F:2"} & {w.candidate.program.id for w in plain.wishes}   # lower cutoff than the others
    assert {"F:1", "F:2"} <= {w.candidate.program.id for w in fav.wishes}
    assert all(w.candidate.favorite == (w.candidate.program.school_code == "F") for w in fav.wishes)


def test_favorite_school_may_take_every_an_toan_slot_with_other_nganh():
    pool = full_pool() + [prog("F:7480101", "7480101", CUTOFF[Level.AN_TOAN]),      # same lĩnh vực 748: tier 2
                          prog("F:7340101", "7340101", CUTOFF[Level.AN_TOAN]),      # another lĩnh vực: tier 3
                          prog("F:7340102", "7340101", CUTOFF[Level.THU_SUC])]      # not an toàn: never used
    r = run(pool, [ShortlistItem("7480201")], fav_student())
    safe = [w.candidate for w in r.wishes if w.candidate.level == Level.AN_TOAN]
    assert len(safe) == 3
    fav = sorted((c.program.id, c.relation, c.closeness_rank) for c in safe if c.favorite)
    assert fav == [("F:7340101", "favorite_school", 3), ("F:7480101", "favorite_school", 2)]
    assert "F:7340102" not in {w.candidate.program.id for w in r.wishes}


def test_favorite_school_other_nganh_only_for_item_1():
    pool = full_pool() + full_pool(moet="7340101") + [prog("F:7520103", "7520103", CUTOFF[Level.AN_TOAN])]
    r = run(pool, [ShortlistItem("7480201"), ShortlistItem("7340101")], fav_student())
    f = [w.candidate for w in r.wishes if w.candidate.favorite]
    assert [(c.program.id, c.item_index, c.closeness_rank) for c in f] == [("F:7520103", 0, 3)]
    assert len(r.wishes) == 15


def test_no_favorite_school_changes_nothing():
    pool = full_pool() + [prog("F:7340101", "7340101", CUTOFF[Level.AN_TOAN])]
    a, b = run(pool, [ShortlistItem("7480201")]), run(pool, [ShortlistItem("7480201")], fav_student("NONE"))
    assert [w.candidate.program.id for w in a.wishes] == [w.candidate.program.id for w in b.wishes]
