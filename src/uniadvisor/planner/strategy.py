"""Build the ordered list of nguyện vọng from the shortlist. Deterministic: every sort has an
explicit tie-break ending in the program id."""

from __future__ import annotations

from collections.abc import Iterable

from uniadvisor.planner.models import (
    LEVEL_ORDER, Candidate, Excluded, Level, ListResult, ProgramFacts, Profile, ShortlistItem, Wish,
)
from uniadvisor.planner.rules import home_city, school_score
from uniadvisor.planner.scoring import best_exam_total, evaluate


def within_level_key(c: Candidate):
    """Which programs fill a level: the student's favorite school first, then
    highest school score; ties -> higher cutoff (latest year) first; then a stable id."""
    return (-c.favorite, -c.school_score, -c.latest_cutoff, c.program.id)


def default_quotas(list_cfg: dict, n_items: int) -> list[dict[Level, int]]:
    cfg = list_cfg["quotas"]["one_item" if n_items == 1 else "two_items"]
    return [{Level(k): v for k, v in cfg[f"item{i + 1}"].items()} for i in range(n_items)]


def _favorite_tier(code: str | None, shortlist: list[ShortlistItem]) -> int:
    """How near a favorite-school program's ngành is to the shortlist: 1 same nhóm ngành, 2 same lĩnh vực, 3 any."""
    code = code or ""
    mains = [i.main_code for i in shortlist]
    if any(code[:5] == m[:5] for m in mains):
        return 1
    if any(code[:3] == m[:3] for m in mains):
        return 2
    return 3


def list_order_key(c: Candidate):
    """Order of the chosen wishes within a part of the list: the largest gap between the
    latest cutoff and the student's score first (the hardest for this student on top, the surest at the bottom);
    ties -> higher school score; then a stable id."""
    return (-c.gap, -c.school_score, c.program.id)


def _claims(shortlist: list[ShortlistItem], programs: Iterable[ProgramFacts], nganh_parent: dict[str, str],
            favorite: str | None = None):
    """(item index, relation, relation code, closeness rank, program) for every program the shortlist brings in.

    Order of claims decides who keeps a program shared by both items: item 1's main
    and close ngành, then item 2's, then the favorite school's other programs (item 1's an toàn slots only, by tier:
    same nhóm ngành, same lĩnh vực, any), then the further close ngành used only for the an toàn top-up (item 1's
    first).
    """
    by_code: dict[str, list[ProgramFacts]] = {}
    for p in programs:
        if p.moet_code:
            by_code.setdefault(p.moet_code, []).append(p)
    group_members: dict[str, list[str]] = {}
    for code, parent in nganh_parent.items():
        group_members.setdefault(parent, []).append(code)

    def programs_of(code: str) -> list[ProgramFacts]:
        return sorted(by_code.get(code, []), key=lambda p: p.id)

    claims = []
    for i, item in enumerate(shortlist):
        if len(item.main_code) == 5:          # a nhóm ngành: every ngành in the group
            for code in sorted(group_members.get(item.main_code, [])):
                claims += [(i, "group", item.main_code, 0, p) for p in programs_of(code)]
        else:
            claims += [(i, "main", item.main_code, 0, p) for p in programs_of(item.main_code)]
        for code in item.close_codes:
            claims += [(i, "close", code, 0, p) for p in programs_of(code)]
    if favorite:
        # The favorite school's other programs, for item 1's an toàn slots only, nearest ngành first.
        claims += sorted(((0, "favorite_school", p.moet_code or "", _favorite_tier(p.moet_code, shortlist), p)
                          for code in sorted(by_code) for p in programs_of(code) if p.school_code == favorite),
                         key=lambda c: (c[3], c[4].id))
    for i, item in enumerate(shortlist):
        for rank, code in enumerate(item.further_close_codes, start=1):
            claims += [(i, "further_close", code, rank, p) for p in programs_of(code)]
    for i, item in enumerate(shortlist):
        for rank, code in enumerate(item.wider_codes, start=1):
            claims += [(i, "wider", code, rank, p) for p in programs_of(code)]
    return claims


def build_list(profile: Profile, shortlist: list[ShortlistItem], programs: Iterable[ProgramFacts],
               nganh_parent: dict[str, str], rules: dict, list_cfg: dict, provinces: dict[str, str],
               admission_year: int, pick_key=within_level_key,
               quotas: list[dict[Level, int]] | None = None,
               pool: tuple[str, ...] = ("main", "group", "close")) -> ListResult:
    """`pick_key` decides which programs fill a level and `pool` which relations may fill one (the three lists differ
    only there); `quotas` replaces config's quotas (the three lists' safety floor moves slots to
    an toàn)."""
    if not 1 <= len(shortlist) <= 2:
        raise ValueError("The shortlist has 1 or 2 items")
    home = home_city(profile.home_province, provinces)
    if quotas is None:
        quotas = default_quotas(list_cfg, len(shortlist))
    max_wishes = rules["application"]["max_wishes"]
    if sum(sum(q.values()) for q in quotas) != max_wishes:
        raise ValueError(f"Quotas must add up to {max_wishes}")

    programs = list(programs)
    best_total = best_exam_total(programs, profile.scores)      # weak combinations are not used
    candidates: list[Candidate] = []
    excluded: list[Excluded] = []
    owner: dict[str, int] = {}                      # program id -> item that claimed it first
    for item_index, relation, code, rank, p in _claims(shortlist, programs, nganh_parent, profile.favorite_school):
        extension = relation in ("further_close", "favorite_school", "wider")
        if p.id in owner:
            if owner[p.id] != item_index and not extension:
                excluded.append(Excluded(p.id, item_index, f"taken_by_item{owner[p.id] + 1}"))
            continue
        owner[p.id] = item_index
        reason = None
        if p.school_code in profile.removed_schools:
            reason = "removed_school"
        elif p.id in profile.removed_programs:
            reason = "removed_program"
        elif p.city not in ("HN", "HCM"):
            reason = "not_in_hn_hcm"
        student = None
        if reason is None:
            student, reason = evaluate(p, profile, rules, list_cfg, admission_year, best_total)
        if reason is not None:
            if not extension:
                excluded.append(Excluded(p.id, item_index, reason))
            continue
        score, over, far = school_score(p.tuition_max_vnd, profile.budget_trieu, profile.near_home, p.city, home,
                                        list_cfg)
        candidates.append(Candidate(p, item_index, relation, code, rank, student, score,
                                    p.tuition_max_vnd is None, over, far, p.school_code == profile.favorite_school))

    selected: list[list[Candidate]] = []           # per item: chosen non-top-up candidates
    topped: list[list[Candidate]] = []             # per item: an toàn top-ups
    notes: list[str] = []
    chosen_ids: set[str] = set()
    for i, quota in enumerate(quotas):
        own = [c for c in candidates if c.item_index == i and c.relation in pool]
        pools = {lv: sorted((c for c in own if c.level == lv), key=pick_key) for lv in LEVEL_ORDER}
        # The favorite school may take every an toàn slot of item 1, with ngành outside the shortlist when it must
        #: its own programs first, then its other programs by tier, then the rest.
        near = list(shortlist[i].further_close_codes)          # within a tier, ngành closer to item 1 first
        extra = sorted((c for c in candidates if c.item_index == i and c.relation == "favorite_school"
                        and c.level == Level.AN_TOAN),
                       key=lambda c: (c.closeness_rank, near.index(c.relation_code) if c.relation_code in near
                                      else len(near), *within_level_key(c)))
        if extra:
            safe = pools[Level.AN_TOAN]
            pools[Level.AN_TOAN] = [c for c in safe if c.favorite] + extra + [c for c in safe if not c.favorite]
        chosen: list[Candidate] = []
        carry = 0
        for lv in LEVEL_ORDER:                       # empty slots shift down (mơ ước -> ... -> an toàn)
            want = quota[lv] + carry
            take = pools[lv][:want]
            chosen += take
            carry = want - len(take)
            if carry and lv != Level.AN_TOAN:
                notes.append(f"shifted_down:{i + 1}:{lv.value}:{carry}")
        top_up: list[Candidate] = []
        if carry:                                     # too few an toàn: further close ngành, in closeness order,
            further = sorted((c for c in candidates if c.item_index == i and c.relation == "further_close"
                              and c.level == Level.AN_TOAN),
                             key=lambda c: (c.closeness_rank, *within_level_key(c)))
            wider = sorted((c for c in candidates if c.item_index == i and c.relation == "wider"   # then wider
                            and c.level == Level.AN_TOAN and c.program.id not in chosen_ids),
                           key=lambda c: (c.closeness_rank, *within_level_key(c)))
            top_up = (further + wider)[:carry]
            if top_up:
                notes.append(f"topped_up:{i + 1}:{len(top_up)}")
            if carry > len(top_up):
                notes.append(f"short:{i + 1}:{carry - len(top_up)}")
        selected.append(chosen)
        topped.append(top_up)
        chosen_ids |= {c.program.id for c in chosen + top_up}
        excluded += [Excluded(c.program.id, i, "not_selected") for c in own if c.program.id not in chosen_ids]

    # Final order: item 1's non-an-toàn wishes, item 2's, then all an toàn (item 1's first; each item's
    # own an toàn before its top-ups). Within a part: largest cutoff-minus-score gap first.
    ordered: list[Candidate] = []
    for chosen in selected:
        ordered += sorted((c for c in chosen if c.level != Level.AN_TOAN), key=list_order_key)
    for chosen, top_up in zip(selected, topped):
        ordered += sorted((c for c in chosen if c.level == Level.AN_TOAN), key=list_order_key)
        ordered += top_up
    if len(ordered) < max_wishes:
        notes.append(f"short_list:{len(ordered)}")
    wishes = [Wish(n, c) for n, c in enumerate(ordered, start=1)]
    return ListResult(wishes, excluded, notes, candidates)
