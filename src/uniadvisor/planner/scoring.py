"""The student's score and level for one program and the ministry floor.

30 is the main scale. The student's total for a combination is the plain sum of its three
exam subjects (no subject weights); cutoffs are compared through their linear conversion to 30 points.
"""

from __future__ import annotations

from uniadvisor.planner.models import LEVEL_ORDER, Level, ProgramFacts, Profile, StudentScore
from uniadvisor.planner.rules import cutoffs_for_combo, floor_for, level_for, priority_points, too_far_above


def best_exam_total(programs, scores: dict[str, float]) -> float | None:
    """The student's best plain 3-subject total over every combination the programs admit with (None: none usable)."""
    best, seen = None, set()
    for p in programs:
        for combo, subjects in p.combos.items():
            if combo in seen:
                continue
            seen.add(combo)
            if len(subjects) == 3 and all(s in scores for s in subjects):
                total = sum(scores[s] for s in subjects)
                best = total if best is None or total > best else best
    return best


def evaluate(program: ProgramFacts, profile: Profile, rules: dict, list_cfg: dict,
             admission_year: int, best_total: float | None = None) -> tuple[StudentScore | None, str | None]:
    """(best StudentScore, None) or (None, reason) with reason in no_usable_combination, weak_combination,
    below_floor, no_cutoff, too_hard (more than `levels.dream_max_gap` below the lower cutoff for every combination).

    Only the student's strong combinations count: given `best_total` (best_exam_total over all programs), a
    combination more than `levels.weak_combination_gap` below it is not used, and a program left with none is
    `weak_combination` (unless the student entered their own score at that school).

    For each accepted combination whose subjects the student has: exam total, priority (tapered on that total),
    the extra points the student entered for this school. A mixed-method program is at most
    `levels.mixed_method_max_level` (its converted cutoff is not comparable with the exam total). The combination
    giving the best level is used; ties go to the larger margin over the higher cutoff, then over the lower, then the
    combination code.

    Per-student corrections: when the student entered their own score at the school, it
    replaces exam total + priority + extra for the years whose cutoff is on the same scale, without the mixed-method
    cap; a cutoff shift for the school is added to every cutoff it compares with.
    """
    totals = []
    for combo, subjects in sorted(program.combos.items()):
        if len(subjects) != 3 or any(s not in profile.scores for s in subjects):
            continue
        exam_total = round(sum(profile.scores[s] for s in subjects), 6)
        prio = priority_points(exam_total, profile.area, profile.category, profile.graduation_year,
                               admission_year, rules)
        totals.append((combo, exam_total, prio))
    if not totals:
        return None, "no_usable_combination"
    gap = list_cfg["levels"].get("weak_combination_gap")
    if best_total is not None and gap is not None and program.school_code not in profile.own_scores:
        totals = [t for t in totals if t[1] + 1e-9 >= best_total - gap]
        if not totals:
            return None, "weak_combination"

    floor = floor_for(program.moet_code, rules)
    if floor is not None and max(t + p for _, t, p in totals) + 1e-9 < floor:
        return None, "below_floor"
    if not program.cutoffs:
        return None, "no_cutoff"

    extra = profile.extra_points.get(program.school_code, 0.0)
    own = profile.own_scores.get(program.school_code)
    shift = profile.cutoff_shifts.get(program.school_code, 0.0)
    lv = list_cfg["levels"]
    cap = Level(lv.get("mixed_method_max_level", Level.AN_TOAN.value))
    options = []
    out_of_reach = False
    for combo, exam_total, prio in totals:
        cutoffs = cutoffs_for_combo(program.cutoffs, combo)
        own_cutoffs = {y: c for y, c in cutoffs.items() if own and c.scale == own[1]}
        if own_cutoffs:
            # The student's own score at this school, on the school's scale: it already holds priority and the
            # school's extra points, and it is computed by the school's own formula, so no mixed-method cap.
            cutoffs, score, capped_by_method = own_cutoffs, round(own[0] * 30 / own[1], 6), False
        elif cutoffs:
            score = round(exam_total + prio + extra, 6)
            capped_by_method = program.is_mixed_method or any(c.is_mixed_method for c in cutoffs.values())
        else:
            continue
        values = [c.score_30 + shift for c in cutoffs.values()]
        if lv.get("dream_max_gap") is not None and too_far_above(score, values, lv["dream_max_gap"]):
            out_of_reach = True
            continue
        level = level_for(score, values, lv["safe_margin"], lv["dream_gap"])
        capped = capped_by_method and LEVEL_ORDER.index(level) > LEVEL_ORDER.index(cap)
        options.append(StudentScore(combo, exam_total, prio, 0.0 if own_cutoffs else extra, score, cutoffs,
                                    cap if capped else level, capped, own if own_cutoffs else None, shift))
    if not options:
        return None, "too_hard" if out_of_reach else "no_usable_combination"

    def rank(o: StudentScore):
        values = [c.score_30 + o.cutoff_shift for c in o.cutoffs.values()]
        return (-LEVEL_ORDER.index(o.level), -(o.score - max(values)), -(o.score - min(values)), o.combo)

    return sorted(options, key=rank)[0], None
