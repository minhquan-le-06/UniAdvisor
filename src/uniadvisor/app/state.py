"""Everything a student enters, in one object (spec 2, 6). The Streamlit page keeps one PlanState per session; the
plan file (plan_file.py) is this object as JSON. Nothing here is stored or sent anywhere."""

from __future__ import annotations

from dataclasses import dataclass, field

from uniadvisor.plan.models import Profile, ShortlistItem

AREAS = ["KV1", "KV2-NT", "KV2", "KV3"]
CATEGORIES = ["none", "UT1", "UT2"]
SCORE_KINDS = ["expected", "real"]          # before the exam: expected scores; after: real ones
MAX_CLOSE = 2                               # spec 3.3: 1-2 close ngành per item
MAX_ITEMS = 2
SCALES = (30, 40, 100)                      # cutoff scales schools publish (data/build: cutoff.scale)
MAX_CUTOFF_SHIFT = 5.0                      # a student's correction of a school's cutoffs, points on 30


@dataclass
class ShortlistEntry:
    main: str                               # ngành (7 digits) or nhóm ngành (5 digits)
    close: list[str] = field(default_factory=list)

LIST_CHOICES = ("dung_nganh", "nghe_nghiep", "hop_mon", "tiet_kiem")   # plan.lists.Priority values


@dataclass
class PlanState:
    scores: dict[str, float] = field(default_factory=dict)       # subject code -> 0..10
    score_kind: str = "expected"
    home_province: str | None = None
    area: str = "KV3"
    category: str = "none"
    graduation_year: int | None = None                           # None: the admission year
    budget_trieu: float | None = None
    near_home: bool = False
    favorite_school: str | None = None                           # school code (design decision 2026-10-07)
    picks: list[str] = field(default_factory=list)              # step 1 candidates, in the order picked
    shortlist: list[ShortlistEntry] = field(default_factory=list)
    extra_points: dict[str, float] = field(default_factory=dict) # school code -> points (entered in step 5)
    own_scores: dict[str, tuple[float, int]] = field(default_factory=dict)   # school -> (score, scale), step 5
    cutoff_shifts: dict[str, float] = field(default_factory=dict)            # school -> points on 30, step 5
    removed_schools: list[str] = field(default_factory=list)
    removed_programs: list[str] = field(default_factory=list)
    # Three recommended lists (design decision 2026-10-08): the step 7 answers (option codes; they
    # give the career scores), the list the student chose (a plan.lists.Priority value; None: not chosen yet) and the
    # three lists as recommended when the student chose (program ids, pentagon), kept unchanged in the plan file.
    answers: dict = field(default_factory=dict)
    list_choice: str | None = None
    recommended: list[dict] = field(default_factory=list)

    def missing_for_list(self) -> list[str]:
        """What step 2 still needs (spec 2: scores and province are required)."""
        missing = []
        if not self.scores:
            missing.append("scores")
        if not self.home_province:
            missing.append("home_province")
        if not self.shortlist:
            missing.append("shortlist")
        return missing

    def to_profile(self) -> Profile:
        return Profile(scores=dict(self.scores), home_province=self.home_province or "", area=self.area,
                       category=self.category, graduation_year=self.graduation_year, budget_trieu=self.budget_trieu,
                       near_home=self.near_home, extra_points=dict(self.extra_points),
                       own_scores=dict(self.own_scores), cutoff_shifts=dict(self.cutoff_shifts),
                       favorite_school=self.favorite_school,
                       removed_schools=frozenset(self.removed_schools),
                       removed_programs=frozenset(self.removed_programs))

    def to_shortlist(self) -> list[ShortlistItem]:
        # No further close ngành until closeness is computed (spec 3.4, build step 6): no an toàn top-up yet.
        return [ShortlistItem(e.main, tuple(e.close)) for e in self.shortlist]
