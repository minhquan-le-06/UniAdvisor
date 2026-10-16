"""The three recommended lists and their pentagons.

The lists are built by the same rules (planner/strategy.py) and differ only in which programs fill each level: the
programs closest to the chosen ngành; the best career fit (a student who answered the 12 questions) or, without
answers, the student's strongest subject combination; or the cheapest. Each list must keep the chance of no admission at or below a floor (the chance engine, planner/chances.py); a
list that misses it gets one more an toàn slot at a time, and when no an toàn program of its ngành is left, an toàn
programs of other ngành of the same nhóm, then of the same lĩnh vực. A list's pentagon is its expected outcome: each corner averages one value over the wish the student is admitted
to in the simulated years.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from enum import Enum

from uniadvisor.planner.chances import ChangeModel, Chances, chances
from uniadvisor.planner.models import Candidate, Level, ListResult, ProgramFacts, Profile, ShortlistItem
from uniadvisor.planner.strategy import build_list, default_quotas


class Priority(str, Enum):
    NGANH = "dung_nganh"            # Đúng ngành nhất
    CAREER = "nghe_nghiep"          # Hợp sở thích nhất (needs the student's answers to the 12 questions)
    MON = "hop_mon"                 # Hợp môn học nhất: in place of Hợp sở thích nhất when there are no answers
                                    # (2026-10-08)
    COST = "tiet_kiem"              # Tiết kiệm nhất


def priorities(facts: "ListFacts") -> tuple[Priority, Priority, Priority]:
    """The three lists: Hợp sở thích nhất when the student answered the 12 questions, else Hợp môn học nhất."""
    return (Priority.NGANH, Priority.CAREER if facts.career else Priority.MON, Priority.COST)


def usable(priority: Priority, facts: "ListFacts") -> Priority:
    """The list that can be built: Hợp sở thích nhất without career scores (the answers were cleared, or an old plan
    file) becomes Hợp môn học nhất, the list that takes its place."""
    return Priority.MON if priority is Priority.CAREER and not facts.career else priority


CORNERS = ("hop_mon", "nguyen_vong_cao", "dung_nganh", "hoc_phi", "nghe_nghiep")
HIGH_LEVELS = (Level.MO_UOC, Level.THU_SUC)
SHIFT_FROM = (Level.MO_UOC, Level.THU_SUC, Level.VUA_SUC)    # slots given to an toàn by the floor, in this order


@dataclass(frozen=True)
class ListFacts:
    """What the lists need beyond the programs: closeness of ngành and the student's career scores."""
    closeness: dict[tuple[str, str], float] = field(default_factory=dict)   # (ngành, other ngành) -> 0-1
    children: dict[str, tuple[str, ...]] = field(default_factory=dict)      # nhóm ngành -> its ngành
    nganh_parent: dict[str, str] = field(default_factory=dict)              # ngành -> nhóm ngành
    career: dict[str, float] = field(default_factory=dict)                  # ngành -> 0-1 (1 = best fit)

    def close_score(self, main: str, other: str) -> float | None:
        mains = self.children.get(main, ()) if len(main) == 5 else (main,)
        scores = [self.closeness[(m, other)] for m in mains if (m, other) in self.closeness]
        return max(scores) if scores else None

    def career_of(self, c: Candidate) -> float | None:
        return self.career.get(c.program.moet_code or "")


def nganh_fit(c: Candidate, shortlist: list[ShortlistItem], facts: ListFacts) -> float | None:
    """1 for the chosen ngành (or nhóm); a close ngành's closeness score; 0 for a favorite-school program outside the
    shortlist; None when the closeness is not known (a close ngành the student added by hand)."""
    if c.relation in ("main", "group"):
        return 1.0
    if c.relation == "favorite_school":
        return 0.0
    score = facts.close_score(shortlist[c.item_index].main_code, c.relation_code)
    if c.relation == "wider":                        # another ngành of the nhóm / lĩnh vực: 0 unless known close
        return score or 0.0
    return score


def tuition_value(c: Candidate, budget_trieu: float | None) -> float | None:
    """Affordability: 1 within the budget, budget / tuition above it. None when the tuition is unknown or no budget
    was given (without a budget there is nothing to be affordable against; saving money is the Tiết kiệm nhất list's
    priority, not a corner)."""
    fee = c.program.tuition_max_vnd
    if fee is None or budget_trieu is None:
        return None
    budget = budget_trieu * 1_000_000
    return 1.0 if fee <= budget else budget / fee


def pick_key(priority: Priority, shortlist: list[ShortlistItem], facts: ListFacts,
             profile: Profile) -> Callable[[Candidate], tuple]:
    """Which programs fill a level first. Every key starts with the favorite school and ends
    with the usual school score, higher cutoff, id."""
    def tail(c: Candidate):
        return (-c.school_score, -c.latest_cutoff, c.program.id)

    if priority is Priority.NGANH:
        def key(c):
            fit = nganh_fit(c, shortlist, facts)
            return (-c.favorite, 0 if c.relation in ("main", "group") else 1, -(fit if fit is not None else -1), *tail(c))
    elif priority is Priority.CAREER:
        def key(c):          # career fit only: employment rates cover too few schools to break ties fairly
            career = facts.career_of(c)
            return (-c.favorite, career is None, -(career or 0.0), *tail(c))
    elif priority is Priority.MON:
        def key(c):                                  # the student's best combination total for the program
            return (-c.favorite, -c.student.exam_total, *tail(c))
    else:
        def key(c):                                  # over-budget programs never get here (drop_over_budget)
            fee = c.program.tuition_max_vnd
            return (-c.favorite, fee is None, fee if fee is not None else 0, *tail(c))
    return key


@dataclass(frozen=True)
class Pentagon:
    values: dict[str, float | None]     # corner -> 0-1 (higher is better); None: no data
    unknown: dict[str, float]           # corner -> share of admissions with no value for it
    none: float                         # chance of no admission at the score entered


def pentagon(result: ListResult, ch: Chances, profile: Profile, shortlist: list[ShortlistItem],
             facts: ListFacts) -> Pentagon:
    wishes = [w.candidate for w in result.wishes]
    best_total = max((c.student.exam_total for c in result.candidates), default=0.0)
    per_wish = {
        "hop_mon": [c.student.exam_total / best_total if best_total else None for c in wishes],
        "nguyen_vong_cao": [1.0 if c.level in HIGH_LEVELS else 0.0 for c in wishes],
        "dung_nganh": [nganh_fit(c, shortlist, facts) for c in wishes],
        "hoc_phi": [tuition_value(c, profile.budget_trieu) for c in wishes],
        "nghe_nghiep": [facts.career_of(c) for c in wishes],
    }
    admitted = ch.admitted or tuple(0.0 for _ in wishes)
    total = sum(admitted)
    values, unknown = {}, {}
    for corner, vals in per_wish.items():
        known = sum(p for p, v in zip(admitted, vals) if v is not None)
        values[corner] = sum(p * v for p, v in zip(admitted, vals) if v is not None) / known if known else None
        unknown[corner] = (total - known) / total if total else 0.0
    return Pentagon(values, unknown, ch.none)


@dataclass(frozen=True)
class Recommended:
    priority: Priority
    result: ListResult
    quotas: list[dict[Level, int]]
    chances: Chances | None
    pentagon: Pentagon | None
    floor_met: bool


def _shift_to_safe(quotas: list[dict[Level, int]]) -> list[dict[Level, int]] | None:
    for i, q in enumerate(quotas):
        for lv in SHIFT_FROM:
            if q[lv] > 0:
                new = [dict(x) for x in quotas]
                new[i][lv] -= 1
                new[i][Level.AN_TOAN] += 1
                return new
    return None


def build_with_floor(profile: Profile, shortlist: list[ShortlistItem], programs: list[ProgramFacts],
                     nganh_parent: dict[str, str], rules: dict, list_cfg: dict, provinces: dict[str, str],
                     admission_year: int, model: ChangeModel | None, facts: ListFacts,
                     priority: Priority) -> Recommended:
    floor = list_cfg["three_lists"]["max_no_admission"]
    key = pick_key(priority, shortlist, facts, profile)
    quotas = default_quotas(list_cfg, len(shortlist))

    # Hợp sở thích nhất may fill any level from the further close ngành too (ranked by career fit), so it can choose
    # other ngành whose careers suit the student better; the other lists keep the shortlist's ngành.
    pool = ("main", "group", "close") + (("further_close",) if priority is Priority.CAREER else ())

    def build(q, items):
        return build_list(profile, items, programs, nganh_parent, rules, list_cfg, provinces, admission_year,
                          pick_key=key, quotas=q, pool=pool, drop_over_budget=priority is Priority.COST)

    def safe(r):
        return sum(w.candidate.level == Level.AN_TOAN for w in r.wishes)

    items = list(shortlist)
    result = build(quotas, items)
    if model is None or not result.wishes:
        return Recommended(priority, result, quotas, None, None, model is None and bool(result.wishes))
    ch = chances(result, model, list_cfg)
    for widen in (False, True):
        if ch.none <= floor:
            break
        if widen:                                    # no an toàn program of the list's ngành left: look wider
            items = [replace(it, wider_codes=wider_codes(it, facts)) for it in shortlist]
            attempt = build(quotas, items)
            if safe(attempt) > safe(result):
                result, ch = attempt, chances(attempt, model, list_cfg)
        while ch.none > floor:
            moved = _shift_to_safe(quotas)
            if moved is None:
                break
            attempt = build(moved, items)
            if safe(attempt) <= safe(result):      # no an toàn program left to add
                break
            quotas, result = moved, attempt
            ch = chances(result, model, list_cfg)
    return Recommended(priority, result, quotas, ch, pentagon(result, ch, profile, items, facts),
                       ch.none <= floor)


def wider_codes(item: ShortlistItem, facts: ListFacts) -> tuple[str, ...]:
    """Other ngành of the item's nhóm, then of its lĩnh vực (first three digits), closest first when the closeness is
    known, then by code; the item's own ngành and close ngành left out."""
    main = item.main_code
    taken = {main, *item.close_codes, *item.further_close_codes}
    group = main if len(main) == 5 else facts.nganh_parent.get(main, main[:5])
    same_group = [c for c in facts.children.get(group, ()) if c not in taken]
    same_field = sorted(c for c, parent in facts.nganh_parent.items()
                        if c[:3] == main[:3] and parent != group and c not in taken)

    def order(codes):
        return sorted(codes, key=lambda c: (-(facts.close_score(main, c) or 0.0), c))
    return tuple(order(same_group) + order(same_field))


def recommend(profile: Profile, shortlist: list[ShortlistItem], programs: Iterable[ProgramFacts],
              nganh_parent: dict[str, str], rules: dict, list_cfg: dict, provinces: dict[str, str],
              admission_year: int, model: ChangeModel | None, facts: ListFacts) -> list[Recommended]:
    programs = list(programs)
    return [build_with_floor(profile, shortlist, programs, nganh_parent, rules, list_cfg, provinces, admission_year,
                             model, facts, p) for p in priorities(facts)]


def overlap(a: ListResult, b: ListResult) -> float:
    """Share of programs two lists have in common (of the shorter list)."""
    x, y = {w.candidate.program.id for w in a.wishes}, {w.candidate.program.id for w in b.wishes}
    return len(x & y) / min(len(x), len(y)) if x and y else 0.0
