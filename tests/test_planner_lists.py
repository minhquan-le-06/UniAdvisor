"""The three recommended lists and their pentagons, on the fake database."""

from dataclasses import replace

import numpy as np
import pytest

from uniadvisor.config import load_list_config, load_provinces, load_rules
from uniadvisor.planner.chances import ChangeModel, chances
from uniadvisor.planner.lists import (
    CORNERS, ListFacts, Priority, _shift_to_safe, build_with_floor, overlap, pentagon, pick_key, recommend,
)
from uniadvisor.planner.models import Level, Profile, ShortlistItem
from uniadvisor.planner.repository import load_nganh_parents, load_programs
from uniadvisor.planner.strategy import default_quotas

STUDENT = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0, "SI": 6.0}, home_province="Nghệ An")
SHORTLIST = [ShortlistItem("74801", close_codes=("7480201",))]


@pytest.fixture
def data(fake_db):
    return load_programs(fake_db), load_nganh_parents(fake_db)


def model(program=(-0.5, 0.5)):
    return ChangeModel(np.array([0.0]), np.array(program), (2025, 2026), 2)


def run(data, facts=ListFacts(), m=None, profile=STUDENT, shortlist=SHORTLIST):
    programs, parents = data
    return recommend(profile, shortlist, programs, parents, load_rules(2027), load_list_config(), load_provinces(),
                     2027, m if m is not None else model(), facts)


def test_three_lists_one_per_priority(data):
    recs = run(data)
    assert [r.priority for r in recs] == [Priority.NGANH, Priority.MON, Priority.COST]      # no answers: Hợp môn
    for r in recs:
        assert r.result.wishes and r.pentagon is not None and set(r.pentagon.values) == set(CORNERS)
        assert all(v is None or 0.0 <= v <= 1.0 for v in r.pentagon.values.values())
        assert r.chances is not None and abs(sum(r.chances.admitted) + r.chances.none - 1) < 1e-9


def test_cost_list_prefers_known_cheaper_programs(data):
    programs, _ = data
    fee = {p.id: p.tuition_max_vnd for p in programs}
    recs = {r.priority: r for r in run(data)}
    picked = lambda r: [fee[w.candidate.program.id] for w in r.result.wishes]
    cost, nganh = picked(recs[Priority.COST]), picked(recs[Priority.NGANH])
    known = lambda xs: sorted(x for x in xs if x is not None)
    assert sum(x is None for x in cost) <= sum(x is None for x in nganh)
    assert known(cost) <= known(nganh) or len(known(cost)) > len(known(nganh))


def test_cost_list_never_picks_a_program_over_the_budget(data):
    """Tiết kiệm nhất drops programs whose fee is above the budget (2026-10-15); the other lists only rank them."""
    budget = 30.0                                              # the shortlist's programs cost 28 and 35 triệu
    recs = {r.priority: r for r in run(data, profile=replace(STUDENT, budget_trieu=budget))}
    over = lambda r: [w for w in r.result.wishes if (w.candidate.program.tuition_max_vnd or 0) > budget * 1_000_000]
    assert not over(recs[Priority.COST])
    assert any(e.reason == "over_budget" for e in recs[Priority.COST].result.excluded)
    assert over(recs[Priority.NGANH])                          # the other lists still show them, flagged
    no_budget = {r.priority: r for r in run(data)}
    assert not any(e.reason == "over_budget" for e in no_budget[Priority.COST].result.excluded)


def test_nganh_list_takes_the_main_nganh_first(data):
    facts = ListFacts(closeness={("7480101", "7480201"): 0.8}, children={"74801": ("7480101", "7480103")})
    rec = next(r for r in run(data, facts) if r.priority is Priority.NGANH)
    by_level = {}
    for w in rec.result.wishes:
        by_level.setdefault(w.candidate.level, []).append(w.candidate.relation)
    for relations in by_level.values():          # within a level, the group's own ngành before the close ngành
        assert relations == sorted(relations, key=lambda r: r != "group")
    fits = rec.pentagon.values["dung_nganh"]
    assert fits is not None and fits > 0.8


def test_subject_list_prefers_the_strongest_combinations(data):
    recs = {r.priority: r for r in run(data)}
    mon = recs[Priority.MON]
    for level in {w.candidate.level for w in mon.result.wishes}:     # within a level, best combination total first
        totals = [w.candidate for w in mon.result.wishes if w.candidate.level == level]
        pool = sorted((c for c in mon.result.candidates if c.level == level and c.relation in ("main", "group", "close")
                       and c.item_index == 0), key=lambda c: -c.student.exam_total)
        assert min(c.student.exam_total for c in totals) >= pool[len(totals) - 1].student.exam_total - 1e-9
    assert mon.pentagon.values["hop_mon"] >= recs[Priority.NGANH].pentagon.values["hop_mon"] - 1e-9


def test_career_list_with_answers(data):
    facts = ListFacts(career={"7480201": 1.0, "7480101": 0.2, "7480103": 0.1})
    recs = run(data, facts)
    assert [r.priority for r in recs] == [Priority.NGANH, Priority.CAREER, Priority.COST]   # answers: Nghề nghiệp
    career = recs[1].pentagon.values["nghe_nghiep"]
    assert career is not None and career >= recs[0].pentagon.values["nghe_nghiep"] - 1e-9


def test_career_corner_needs_scores(data):
    facts = ListFacts(career={"7480201": 1.0, "7480101": 0.2, "7480103": 0.1})
    assert run(data, facts)[0].pentagon.values["nghe_nghiep"] is not None
    assert run(data)[0].pentagon.values["nghe_nghiep"] is None           # no answers: no career scores, no value


def test_wider_codes_same_group_then_field():
    from uniadvisor.planner.lists import wider_codes
    facts = ListFacts(closeness={("7480201", "7480202"): 0.9},
                      children={"74802": ("7480201", "7480202", "7480203"), "74801": ("7480101",)},
                      nganh_parent={"7480201": "74802", "7480202": "74802", "7480203": "74802", "7480101": "74801",
                                    "7340101": "73401"})
    item = ShortlistItem("7480201", close_codes=("7480203",))
    assert wider_codes(item, facts) == ("7480202", "7480101")       # same nhóm (closest first), then same lĩnh vực


def test_pentagon_averages_over_the_admitted_wish(data):
    rec = run(data)[0]
    ch = rec.chances
    sure = type(ch)(ch.score_shift, ch.at_least, 0.0, tuple(1.0 if i == 0 else 0.0 for i in range(len(ch.admitted))))
    pg = pentagon(rec.result, sure, STUDENT, SHORTLIST, ListFacts())
    first = rec.result.wishes[0].candidate
    assert pg.values["nguyen_vong_cao"] == (1.0 if first.level in (Level.MO_UOC, Level.THU_SUC) else 0.0)
    best = max(c.student.exam_total for c in rec.result.candidates)
    assert pg.values["hop_mon"] == pytest.approx(first.student.exam_total / best)


def test_floor_moves_slots_to_an_toan():
    q = default_quotas(load_list_config(), 1)
    moved = _shift_to_safe(q)
    assert moved[0][Level.MO_UOC] == q[0][Level.MO_UOC] - 1 and moved[0][Level.AN_TOAN] == q[0][Level.AN_TOAN] + 1
    assert sum(moved[0].values()) == sum(q[0].values())
    none_left = [{Level.MO_UOC: 0, Level.THU_SUC: 0, Level.VUA_SUC: 0, Level.AN_TOAN: 15}]
    assert _shift_to_safe(none_left) is None


def test_floor_on_a_risky_list(data):
    programs, parents = data
    cfg = load_list_config()
    risky = model(program=(-3.0, 3.0))                 # cutoffs move a lot: every wish is uncertain
    rec = build_with_floor(STUDENT, SHORTLIST, programs, parents, load_rules(2027), cfg, load_provinces(), 2027,
                           risky, ListFacts(), Priority.NGANH)
    plain = chances(run(data, m=risky)[0].result, risky, cfg)
    assert rec.chances.none <= plain.none
    assert rec.floor_met == (rec.chances.none <= cfg["three_lists"]["max_no_admission"])


def test_overlap(data):
    recs = run(data)
    assert overlap(recs[0].result, recs[0].result) == 1.0
    assert 0.0 <= overlap(recs[0].result, recs[2].result) <= 1.0


def test_bench_lists_runs(data):
    from pipelines.benchmarks.bench_lists import render, run as bench_run
    programs, parents = data
    rows = bench_run(programs, parents, lambda code: [], load_rules(2027), load_list_config(), load_provinces(), 2027,
                     model(), ListFacts(), cases=[("KHMT", ("7480101",))], totals=(24.0,))
    assert len(rows) == 6 and {r.priority for r in rows} == {Priority.NGANH, Priority.MON, Priority.COST}
    text = render(rows, 0.05)
    assert "| 24 | Đúng ngành |" in text and "| 24 | Tiết kiệm |" in text


def test_career_list_needs_answers():
    from uniadvisor.planner.lists import priorities, usable
    answered = ListFacts(career={"7480101": 1.0})
    assert priorities(ListFacts()) == (Priority.NGANH, Priority.MON, Priority.COST)
    assert priorities(answered) == (Priority.NGANH, Priority.CAREER, Priority.COST)
    assert usable(Priority.CAREER, ListFacts()) is Priority.MON          # chosen, then the answers were cleared
    assert usable(Priority.CAREER, answered) is Priority.CAREER
    assert usable(Priority.MON, answered) is Priority.MON                # a chosen Hợp môn list stays


def test_career_list_ignores_employment_rate(data):
    """Career fit only (2026-10-15): few schools have a rate, so it must not order programs of one ngành."""
    facts = ListFacts(career={"7480201": 1.0, "7480101": 0.2, "7480103": 0.1})
    rec = run(data, facts)[1]
    key = pick_key(Priority.CAREER, SHORTLIST, facts, STUDENT)
    rated = lambda c, job: replace(c, program=replace(c.program, employment=job))
    c = next(c for c in rec.result.candidates if c.program.moet_code == "7480101")
    low, high, unknown = rated(c, (0.80, 2024)), rated(c, (0.95, 2024)), rated(c, None)
    assert key(low) == key(high) == key(unknown)
    better_fit = next(c for c in rec.result.candidates if c.program.moet_code == "7480201" and not c.favorite)
    assert key(better_fit) < key(high)                         # the better career fit still comes first


def test_the_fee_corner_is_affordability_and_needs_a_budget(data):
    """1 within the budget, budget / fee above it; without a budget there is nothing to be affordable against."""
    rec = run(data)[0]
    sure = type(rec.chances)(rec.chances.score_shift, rec.chances.at_least, 0.0,
                             tuple(1.0 if i == 0 else 0.0 for i in range(len(rec.chances.admitted))))
    fee = rec.result.wishes[0].candidate.program.tuition_max_vnd
    assert pentagon(rec.result, sure, STUDENT, SHORTLIST, ListFacts()).values["hoc_phi"] is None
    tight = replace(STUDENT, budget_trieu=fee / 2_000_000)                    # half the fee
    assert pentagon(rec.result, sure, tight, SHORTLIST, ListFacts()).values["hoc_phi"] == pytest.approx(0.5)
    roomy = replace(STUDENT, budget_trieu=fee / 1_000_000 + 10)
    assert pentagon(rec.result, sure, roomy, SHORTLIST, ListFacts()).values["hoc_phi"] == 1.0
