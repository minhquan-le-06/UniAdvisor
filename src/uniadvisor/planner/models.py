"""Inputs and outputs of the list rules. Plain data; no database access."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    """Admission levels, in shift-down order."""
    MO_UOC = "mo_uoc"
    THU_SUC = "thu_suc"
    VUA_SUC = "vua_suc"
    AN_TOAN = "an_toan"


LEVEL_ORDER = [Level.MO_UOC, Level.THU_SUC, Level.VUA_SUC, Level.AN_TOAN]


@dataclass(frozen=True)
class Profile:
    """What the student entered."""
    scores: dict[str, float]                  # subject code -> score (0-10), expected or real
    home_province: str
    area: str = "KV3"                         # khu vực: KV1, KV2-NT, KV2, KV3
    category: str = "none"                    # đối tượng: none, UT1, UT2
    graduation_year: int | None = None        # default: the admission year
    budget_trieu: float | None = None         # tuition budget, triệu đồng / năm; None = no budget given
    near_home: bool = False                   # "muốn học gần nhà?"
    extra_points: dict[str, float] = field(default_factory=dict)   # school code -> points the student entered
    removed_schools: frozenset[str] = frozenset()
    removed_programs: frozenset[str] = frozenset()
    favorite_school: str | None = None        # one school the student prefers
    # Per-student corrections: the student's own admission score at a school, as
    # (score, scale) on the school's published scale, and how much higher (+) or lower (-) the student thinks a
    # school's cutoffs really are, in points on 30.
    own_scores: dict[str, tuple[float, int]] = field(default_factory=dict)
    cutoff_shifts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ShortlistItem:
    """One item of the student's shortlist (a hướng học)."""
    main_code: str                            # a ngành (7 digits) or nhóm ngành (5 digits) code
    close_codes: tuple[str, ...] = ()         # the 1-2 close ngành the student kept
    further_close_codes: tuple[str, ...] = () # next closest ngành, in closeness order (for the an toàn top-up)
    # Other ngành of the same nhóm, then of the same lĩnh vực, for the an toàn top-up after the further close ngành;
    # only the three lists' safety floor fills it, when a list misses the floor.
    wider_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cutoff:
    year: int
    combos: frozenset[str] | None             # None: the cutoff applies to every combination
    score_30: float                           # converted to 30 points
    score: float                              # as published
    scale: int
    is_mixed_method: bool


@dataclass(frozen=True)
class ProgramFacts:
    """A program as the rules see it (loaded from the database by repository.py)."""
    id: str
    school_code: str
    school_name: str
    name: str
    moet_code: str | None
    city: str | None                          # 'HN' | 'HCM'
    combos: dict[str, tuple[str, ...]]        # accepted combination -> its exam subjects (known ones only)
    cutoffs: tuple[Cutoff, ...]
    tuition_max_vnd: int | None
    tuition_min_vnd: int | None = None
    tuition_year: int | None = None
    is_mixed_method: bool = False
    tuition_basis: str | None = None          # None: stated per year; else how it was converted (school_docs)
    disputes: tuple[tuple[int, str, str], ...] = ()   # (year, source, value as published) another source disagrees
    employment: tuple[float, int] | None = None       # (rate 0-1, graduation year) the school states for the ngành


@dataclass(frozen=True)
class StudentScore:
    """The student's best combination for one program and the resulting level."""
    combo: str
    exam_total: float                         # sum of the 3 subjects, on 30 points
    priority: float
    extra: float
    score: float                              # exam_total + priority + extra, or the own score converted to 30
    cutoffs: dict[int, Cutoff]                # year -> the cutoff that applies to this combination
    level: Level
    capped_mixed_method: bool = False         # would be an toàn, but a mixed-method cutoff caps it (list.yaml)
    own_score: tuple[float, int] | None = None   # the student's own score at the school (score, scale) was used
    cutoff_shift: float = 0.0                 # the student's correction of this school's cutoffs (points on 30)


@dataclass(frozen=True)
class Candidate:
    program: ProgramFacts
    item_index: int                           # 0 or 1
    relation: str                             # 'main', 'group', 'close', 'further_close', 'favorite_school',
                                              # 'wider' (same nhóm / lĩnh vực, for the safety floor)
    relation_code: str                        # the shortlist code that brought it in
    closeness_rank: int                       # 0 for main/group/close; 1.. for further close ngành; for
                                              # favorite_school 1 same nhóm, 2 same lĩnh vực, 3 any ngành
    student: StudentScore
    school_score: int                         # 0-100
    tuition_unknown: bool
    over_budget: bool
    far_from_home: bool
    favorite: bool = False                    # at the student's favorite school

    @property
    def level(self) -> Level:
        return self.student.level

    @property
    def latest_cutoff(self) -> float:
        """Latest year's cutoff on 30 points, with the student's correction of this school's cutoffs."""
        return self.student.cutoffs[max(self.student.cutoffs)].score_30 + self.student.cutoff_shift

    @property
    def gap(self) -> float:
        """Latest year's cutoff minus the student's score for this program (both on 30 points; positive = the
        student is below the cutoff). Rounded so that float noise does not decide the order."""
        return round(self.latest_cutoff - self.student.score, 4)

    @property
    def is_mixed_method(self) -> bool:
        return self.program.is_mixed_method or any(c.is_mixed_method for c in self.student.cutoffs.values())


@dataclass(frozen=True)
class Wish:
    nv: int                                   # 1..15
    candidate: Candidate


@dataclass(frozen=True)
class Excluded:
    """A program the shortlist brought in that is not on the list, and why (for "why isn't X on my list")."""
    program_id: str
    item_index: int
    reason: str            # removed_school, removed_program, no_cutoff, no_usable_combination, weak_combination,
                           # below_floor, taken_by_item1, quota_full, not_in_hn_hcm


@dataclass(frozen=True)
class ListResult:
    wishes: list[Wish]
    excluded: list[Excluded]
    notes: list[str]       # codes explaining a short list or a top-up, e.g. 'short_list:12', 'topped_up:1:2'
    candidates: list[Candidate] = field(default_factory=list)   # every evaluated program (to explain changes)
