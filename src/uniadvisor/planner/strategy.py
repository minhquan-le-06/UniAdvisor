"""Build the ordered list of nguyện vọng from the shortlist. Deterministic: every sort has an
explicit tie-break ending in the program id."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import replace

from uniadvisor.data.text import name_words
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


def in_safe_part(c: Candidate) -> bool:
    """The wish sits in the list's last part: an toàn, or a mixed-method program the student passes by 2 points but
    which is capped to vừa sức (2026-10-14: ordered by its real gap, so it no longer sits above easier-looking an toàn
    wishes; it keeps its vừa sức label)."""
    return c.level == Level.AN_TOAN or c.student.capped_mixed_method


def spread_by_school(cands: list[Candidate]) -> list[Candidate]:
    """Each school's first program in the given order, then each school's second, ...: an toàn slots go to more than
    one school when the candidates allow (2026-10-14, agent's default: one school's bad year should not take every
    safe wish). The student's favorite school keeps its place first (it may take every an toàn slot, 2026-10-07)."""
    seen: Counter = Counter()
    ranked = []
    for i, c in enumerate(c for c in cands if not c.favorite):
        ranked.append((seen[c.program.school_code], i, c))
        seen[c.program.school_code] += 1
    return [c for c in cands if c.favorite] + [c for _, _, c in sorted(ranked, key=lambda t: (t[0], t[1]))]


def merge_same_programs(candidates: list[Candidate]) -> tuple[list[Candidate], list[Excluded]]:
    """One program published under several codes (campus or quota variants, a quota split by combination): same item,
    school, name (variant words kept), ngành code and city. The easiest for the student (smallest gap) is kept and
    names the others; the others are left out (owner, 2026-10-14)."""
    groups: dict[tuple, list[Candidate]] = {}
    for c in candidates:
        p = c.program
        key = (c.item_index, p.school_code, frozenset(name_words(p.name, keep_variant=True)), p.moet_code, p.city)
        groups.setdefault(key, []).append(c)
    kept_ids, excluded, others = set(), [], {}
    for group in groups.values():
        best = min(group, key=lambda c: (c.gap, c.program.id))
        kept_ids.add(best.program.id)
        rest = sorted(c.program.id for c in group if c is not best)
        if rest:
            others[best.program.id] = tuple(rest)
            excluded += [Excluded(pid, best.item_index, "same_program_other_code") for pid in rest]
    out = [replace(c, other_codes=others[c.program.id]) if c.program.id in others else c
           for c in candidates if c.program.id in kept_ids]
    return out, excluded


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
               pool: tuple[str, ...] = ("main", "group", "close"),
               drop_over_budget: bool = False) -> ListResult:
    """`pick_key` decides which programs fill a level and `pool` which relations may fill one (the three lists differ
    only there); `quotas` replaces config's quotas (the three lists' safety floor moves slots to
    an toàn).  `drop_over_budget` (Tiết kiệm nhất): a program whose published fee is above the student's budget is
    never a candidate; an unknown fee stays, and with no budget nothing is dropped."""
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
        if over and drop_over_budget:
            if not extension:
                excluded.append(Excluded(p.id, item_index, "over_budget"))
            continue
        candidates.append(Candidate(p, item_index, relation, code, rank, student, score,
                                    p.tuition_max_vnd is None, over, far, p.school_code == profile.favorite_school))

    candidates, merged = merge_same_programs(candidates)
    excluded += merged

    # Teacher training (sư phạm) counts only at the first `max_position` wishes (rules: application.teacher_training):
    # at most that many sư phạm wishes, placed first; the other slots go to other ngành (owner, 2026-10-14).
    tt = rules["application"].get("teacher_training") or {}
    tt_prefixes, tt_max = tuple(tt.get("prefixes", ())), tt.get("max_position")

    def is_tt(c: Candidate) -> bool:
        return bool(tt_prefixes) and tt_max is not None and (c.program.moet_code or "").startswith(tt_prefixes)

    tt_used = 0
    tt_out: set[str] = set()                       # sư phạm programs left out because the limit was reached

    def allowed(c: Candidate, limit: int | None = None) -> bool:
        nonlocal tt_used
        if not is_tt(c):
            return True
        if tt_used >= (tt_max if limit is None else limit):
            tt_out.add(c.program.id)
            return False
        tt_used += 1
        return True

    selected: list[list[Candidate]] = []           # per item: chosen non-top-up candidates
    topped: list[list[Candidate]] = []             # per item: an toàn top-ups
    notes: list[str] = []
    chosen_ids: set[str] = set()
    for i, quota in enumerate(quotas):
        own = [c for c in candidates if c.item_index == i and c.relation in pool]
        pools = {lv: sorted((c for c in own if c.level == lv), key=pick_key) for lv in LEVEL_ORDER}
        if tt_max is not None and sum(map(is_tt, own)) > tt_max - tt_used:
            # More sư phạm programs than the limit leaves: the item's further close ngành that are not sư phạm may
            # fill any level, after its own programs, closest ngành first.
            more = [c for c in candidates if c.item_index == i and c.relation == "further_close"
                    and c.relation not in pool and not is_tt(c)]
            for lv in LEVEL_ORDER:
                pools[lv] += sorted((c for c in more if c.level == lv),
                                    key=lambda c: (c.closeness_rank, *within_level_key(c)))
        pools[Level.AN_TOAN] = spread_by_school(pools[Level.AN_TOAN])
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
        # Part of the sư phạm limit is kept for an toàn slots, so a sư phạm list does not lose its safe wishes to
        # the ambitious ones filled first.
        # The an toàn top-up's own sư phạm programs (further close, wider ngành) count as well.
        safe_tt = {c.program.id for c in pools[Level.AN_TOAN] if is_tt(c)} | {
            c.program.id for c in candidates if c.item_index == i and c.relation in ("further_close", "wider")
            and c.level == Level.AN_TOAN and is_tt(c)}
        reserve = (min(quota[Level.AN_TOAN], len(safe_tt), max(tt_max - tt_used, 0))
                   if tt_max is not None else 0)
        chosen: list[Candidate] = []
        taken: set[str] = set()
        carry = 0
        for lv in LEVEL_ORDER:                       # empty slots shift down (mơ ước -> ... -> an toàn)
            want = quota[lv] + carry
            limit = None if lv == Level.AN_TOAN or tt_max is None else tt_max - reserve
            take = []
            for c in pools[lv]:
                if len(take) >= want:
                    break
                if c.program.id not in taken and allowed(c, limit):
                    take.append(c)
                    taken.add(c.program.id)
            chosen += take
            carry = want - len(take)
            if carry and lv != Level.AN_TOAN:
                notes.append(f"shifted_down:{i + 1}:{lv.value}:{carry}")
        top_up: list[Candidate] = []
        if carry:                                     # too few an toàn: further close ngành, in closeness order,
            further = sorted((c for c in candidates if c.item_index == i and c.relation == "further_close"
                              and c.level == Level.AN_TOAN and c.program.id not in taken | chosen_ids),
                             key=lambda c: (c.closeness_rank, *within_level_key(c)))
            wider = sorted((c for c in candidates if c.item_index == i and c.relation == "wider"   # then wider
                            and c.level == Level.AN_TOAN and c.program.id not in taken | chosen_ids),
                           key=lambda c: (c.closeness_rank, *within_level_key(c)))
            for c in further + wider:
                if len(top_up) >= carry:
                    break
                if allowed(c):
                    top_up.append(c)
            if top_up:
                notes.append(f"topped_up:{i + 1}:{len(top_up)}")
            if carry > len(top_up):
                notes.append(f"short:{i + 1}:{carry - len(top_up)}")
        selected.append(chosen)
        topped.append(top_up)
        chosen_ids |= {c.program.id for c in chosen + top_up}
        excluded += [Excluded(c.program.id, i, "not_selected") for c in own
                     if c.program.id not in chosen_ids and c.program.id not in tt_out]
    excluded += [Excluded(c.program.id, c.item_index, "teacher_training_limit") for c in candidates
                 if c.program.id in tt_out and c.program.id not in chosen_ids]

    # Final order: the sư phạm wishes first (they count only there); then item 1's other wishes outside the safe part,
    # item 2's, then the safe part (an toàn and capped mixed-method; item 1's first; each item's own before its
    # top-ups). Within a part: largest cutoff-minus-score gap first.
    every = [c for chosen, top_up in zip(selected, topped) for c in chosen + top_up]
    first = sorted((c for c in every if is_tt(c)), key=list_order_key)
    if first:
        notes.append(f"teacher_training_first:{len(first)}")
    ordered: list[Candidate] = list(first)
    for chosen in selected:
        ordered += sorted((c for c in chosen if not in_safe_part(c) and not is_tt(c)), key=list_order_key)
    for chosen, top_up in zip(selected, topped):
        ordered += sorted((c for c in chosen if in_safe_part(c) and not is_tt(c)), key=list_order_key)
        ordered += [c for c in top_up if not is_tt(c)]
    if len(ordered) < max_wishes:
        notes.append(f"short_list:{len(ordered)}")
    wishes = [Wish(n, c) for n, c in enumerate(ordered, start=1)]
    return ListResult(wishes, excluded, notes, candidates)
