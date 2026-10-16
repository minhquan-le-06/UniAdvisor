"""Single list-building rules, each a pure function. Regulation facts come from config/rules/<year>.yaml only."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from uniadvisor.planner.models import Cutoff, Level

_EPS = 1e-9   # scores are compared after rounding to 6 decimals, so 24.1 + 0.9 reaches 25.0


def _r(x: float) -> float:
    return round(x, 6)


# ---------------------------------------------------------------- priority points

def priority_points(exam_total: float, area: str, category: str, graduation_year: int | None,
                    admission_year: int, rules: dict) -> float:
    """Area + category priority points on the 30-point scale, tapered for totals >= taper_from.

    `exam_total` is the student's total before priority (3 subjects, 30 points). Area points count only in the
    graduation year and the `area_valid_years_after_graduation` years after it. The result is rounded half-up to
    `round_decimals` decimals (2026-10-06).
    """
    p = rules["priority"]
    if area not in p["area"]:
        raise ValueError(f"Unknown area {area!r}")
    if category not in p["category"]:
        raise ValueError(f"Unknown category {category!r}")
    grad = admission_year if graduation_year is None else graduation_year
    area_counts = 0 <= admission_year - grad <= p["area_valid_years_after_graduation"]
    base = (p["area"][area] if area_counts else 0.0) + p["category"][category]
    if exam_total >= p["taper_from"]:
        value = max(0.0, (p["scale"] - exam_total) / p["taper_denominator"] * base)
    else:
        value = base
    return round_half_up(value, p["round_decimals"])


def round_half_up(value: float, decimals: int) -> float:
    """0.125 -> 0.13 (Python's round gives 0.12). The value is first reduced to 9 decimals to drop float noise."""
    exact = Decimal(repr(round(value, 9)))
    return float(exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- ministry floors

def floor_for(moet_code: str | None, rules: dict) -> float | None:
    """Minimum total (including priority) for a MOET ngành code; the most specific prefix wins."""
    if not moet_code:
        return None
    best: tuple[int, float] | None = None
    for floor in rules["floors"]:
        for prefix in floor["prefixes"]:
            if moet_code.startswith(prefix) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), floor["min_total"])
    return best[1] if best else None


# ---------------------------------------------------------------- levels

def level_for(score: float, cutoffs: list[float], safe_margin: float, dream_gap: float) -> Level:
    """Level from the student's score and the program's cutoffs (one or two years; one year counts as both).

    an toàn: >= higher + safe_margin; vừa sức: reaches both, < higher + safe_margin; thử sức: reaches one of the
    two, or is less than dream_gap below the lower; mơ ước: at least dream_gap below the lower.
    """
    if not cutoffs:
        raise ValueError("level_for needs at least one cutoff")
    hi, lo = max(cutoffs), min(cutoffs)
    s = _r(score)
    if s >= _r(hi + safe_margin):
        return Level.AN_TOAN
    if s >= _r(hi):
        return Level.VUA_SUC
    if s >= _r(lo) or _r(lo - s) < _r(dream_gap):
        return Level.THU_SUC
    return Level.MO_UOC


def too_far_above(score: float, cutoffs: list[float], dream_max_gap: float) -> bool:
    """True when the student is more than `dream_max_gap` below the lower of the cutoffs: out of reach, not a dream."""
    return _r(min(cutoffs) - score) > _r(dream_max_gap)


def cutoffs_for_combo(cutoffs: tuple[Cutoff, ...], combo: str) -> dict[int, Cutoff]:
    """For each year, the cutoff that applies to `combo`: its per-combination cutoff, else the year's single one."""
    out: dict[int, Cutoff] = {}
    for year in sorted({c.year for c in cutoffs}):
        rows = [c for c in cutoffs if c.year == year]
        specific = [c for c in rows if c.combos is not None and combo in c.combos]
        general = [c for c in rows if c.combos is None]
        if specific:
            out[year] = specific[0]
        elif general:
            out[year] = general[0]
    return out


# ---------------------------------------------------------------- school score

def school_score(tuition_max_vnd: int | None, budget_trieu: float | None, near_home: bool,
                 program_city: str | None, home_city: str | None, cfg: dict) -> tuple[int, bool, bool]:
    """(score 0-100, over budget, far from home). Unknown fee or no budget: no tuition penalty."""
    c = cfg["school_score"]
    score, over, far = 100, False, False
    if tuition_max_vnd is not None and budget_trieu is not None:
        tuition_trieu = tuition_max_vnd / 1_000_000
        if _r(tuition_trieu) > _r(budget_trieu):
            over = True
            if _r(tuition_trieu) <= _r(budget_trieu * (1 + c["tuition_small_over_ratio"])):
                score -= c["tuition_over_budget_small"]
            else:
                score -= c["tuition_over_budget_large"]
    if near_home and home_city is not None and program_city is not None and program_city != home_city:
        far = True
        score -= c["far_from_home"]
    return score, over, far


# ---------------------------------------------------------------- home city

def home_city(province: str, provinces: dict[str, str]) -> str | None:
    """'HN' or 'HCM' for a province name or alias (config/provinces.yaml); None when unknown."""
    return provinces.get(province)
