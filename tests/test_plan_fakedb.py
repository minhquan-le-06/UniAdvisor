"""The list rules end to end on the fake database (tests/fakedb.py), through the repository loader."""

import pytest

from uniadvisor.config import load_list_config, load_provinces, load_rules
from uniadvisor.plan.models import Level, Profile, ShortlistItem
from uniadvisor.plan.repository import load_nganh_parents, load_programs
from uniadvisor.plan.strategy import build_list

STUDENT = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0, "SI": 6.0}, home_province="Nghệ An")


@pytest.fixture
def data(fake_db):
    return load_programs(fake_db), load_nganh_parents(fake_db)


def build(data, shortlist, profile=STUDENT):
    programs, parents = data
    return build_list(profile, shortlist, programs, parents, load_rules(2027), load_list_config(), load_provinces(),
                      2027)


def test_loader_keeps_only_in_scope_programs_with_city(data):
    programs, _ = data
    ids = {p.id for p in programs}
    assert "OUT:CS" not in ids and "HNA:CS1" in ids
    nna = next(p for p in programs if p.id == "HCB:NNA")
    assert sorted(c.score_30 for c in nna.cutoffs) == [25.125, 25.5]          # 40-point cutoffs converted
    ktpm = next(p for p in programs if p.id == "HCB:KTPM")
    assert ktpm.is_mixed_method and {c.year: c.score_30 for c in ktpm.cutoffs} == {2025: 24.5, 2026: 24.0}


def test_group_item_with_close_nganh(data):
    r = build(data, [ShortlistItem("74801", close_codes=("7480201",))])
    by_id = {w.candidate.program.id: w.candidate for w in r.wishes}
    assert set(by_id) == {"HNA:CS1", "HNA:SE", "HCB:KTPM", "MIL:CS", "HNA:IT2"}
    assert ("HNA:AI", "no_cutoff") in {(e.program_id, e.reason) for e in r.excluded}
    # IT2 accepts A00 and D01. D01 = 23.0 vs 2025 single cutoff 23.5 and 2026 D01 cutoff 24.0 (margin -1.0 to the
    # higher) beats A00 = 22.0 vs 23.5 / 23.0 (margin -1.5)
    it2 = by_id["HNA:IT2"].student
    assert it2.combo == "D01" and it2.level == Level.THU_SUC
    assert {y: c.score_30 for y, c in it2.cutoffs.items()} == {2025: 23.5, 2026: 24.0}
    assert by_id["HCB:KTPM"].is_mixed_method and by_id["HCB:KTPM"].relation == "group"
    assert by_id["HNA:SE"].student.level == Level.VUA_SUC                     # one year: 22.0 used as both
    assert by_id["HNA:IT2"].relation == "close"
    assert "short_list:5" in r.notes


def test_health_floors(data):
    r = build(data, [ShortlistItem("7720101", close_codes=("7720301",))])
    levels = {w.candidate.program.id: w.candidate.level for w in r.wishes}
    assert levels == {"HCB:YK": Level.MO_UOC, "HCB:DD": Level.AN_TOAN}       # B00 = 21.0 vs 27/26.5 and 19/18
    weak = Profile(scores={"TO": 6.5, "HO": 6.5, "SI": 6.0}, home_province="Nghệ An")
    r = build(data, [ShortlistItem("7720101", close_codes=("7720301",))], weak)
    assert [w.candidate.program.id for w in r.wishes] == ["HCB:DD"]          # 19.0 >= 17.0 (other health)
    assert ("HCB:YK", "below_floor") in {(e.program_id, e.reason) for e in r.excluded}   # 19.0 < 20.5


def test_teacher_training_floor(data):
    weak = Profile(scores={"TO": 6.0, "LI": 6.0, "HO": 6.5}, home_province="Nghệ An")      # A00 = 18.5 < 19.0
    r = build(data, [ShortlistItem("7140209")], weak)
    assert r.wishes == [] and r.excluded[0].reason == "below_floor"
    kv1 = Profile(scores=weak.scores, home_province="Nghệ An", area="KV1")                  # 18.5 + 0.75 >= 19.0
    assert [w.candidate.program.id for w in build(data, [ShortlistItem("7140209")], kv1).wishes] == ["HCB:SPT"]


def test_budget_and_home_city(data):
    student = Profile(scores=STUDENT.scores, home_province="Nghệ An", budget_trieu=30, near_home=True)
    r = build(data, [ShortlistItem("7480101")], student)
    by_id = {w.candidate.program.id: w.candidate for w in r.wishes}
    assert by_id["HNA:CS1"].over_budget and by_id["HNA:CS1"].school_score == 90        # 35 > 30, within 20%
    assert not by_id["HNA:CS1"].far_from_home                                          # Nghệ An -> Hà Nội
    assert by_id["MIL:CS"].tuition_unknown and by_id["MIL:CS"].school_score == 100


def test_loader_attaches_the_latest_employment_rate(fake_db_path, tmp_path):
    import shutil
    import sqlite3
    path = tmp_path / "x.db"
    shutil.copy(fake_db_path, path)
    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO school_employment VALUES (?, '7480101', ?, ?, 'HNA_viec_lam_1.pdf', NULL, NULL, NULL,"
                     " 'school_document')", [("HNA", 2023, 0.9), ("HNA", 2024, 0.95)])
    by_id = {p.id: p for p in load_programs(conn)}
    conn.close()
    assert by_id["HNA:CS1"].employment == (0.95, 2024)
    assert by_id["HNA:IT2"].employment is None                  # another ngành
