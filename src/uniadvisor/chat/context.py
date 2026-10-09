"""What the chat needs to know about the student's current plan and our data. Built per message; read-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from uniadvisor.app.catalog import Catalog, search_key
from uniadvisor.app.state import SCALES, PlanState
from uniadvisor.chat.mentions import NganhIndex, SchoolIndex
from uniadvisor.plan.models import ListResult, ProgramFacts


@dataclass
class Indexes:
    """Name indexes, built once per app start (they depend only on the data)."""
    schools: SchoolIndex
    nganh: NganhIndex

    @classmethod
    def build(cls, catalog: Catalog, all_schools: dict[str, str], provinces: list[str],
              school_aliases: dict[str, list[str]]) -> "Indexes":
        return cls(SchoolIndex(all_schools, {search_key(p) for p in provinces}, school_aliases), NganhIndex(catalog))


@dataclass
class ChatContext:
    catalog: Catalog
    subjects: dict[str, str]                       # exam subject code -> name
    school_names: dict[str, str]                   # in-scope schools
    all_school_names: dict[str, str]               # every school in the database (for "why isn't X there")
    programs: dict[str, ProgramFacts]              # program id -> facts (in scope, HN/HCM, with a MOET code)
    indexes: Indexes
    state: PlanState
    result: ListResult | None                      # the current list (None when it cannot be built yet)
    list_cfg: dict = field(default_factory=dict)
    facts: object = None                           # app.facts.FactsIndex (step 6), None when not loaded

    @cached_property
    def wishes_by_nv(self) -> dict[int, object]:
        return {w.nv: w for w in self.result.wishes} if self.result else {}

    @cached_property
    def schools_on_list(self) -> list[str]:
        if not self.result:
            return []
        seen: list[str] = []
        for w in self.result.wishes:
            if w.candidate.program.school_code not in seen:
                seen.append(w.candidate.program.school_code)
        return seen

    @cached_property
    def scales(self) -> dict[str, tuple[int, ...]]:
        """School -> the scales its cutoffs are published on (30, 40, 100)."""
        out: dict[str, set[int]] = {}
        for p in self.programs.values():
            out.setdefault(p.school_code, set()).update(c.scale for c in p.cutoffs)
        return {s: tuple(sorted(v)) for s, v in out.items()}

    def scale_for(self, school: str, value: float) -> int:
        """The scale a score the student gives for a school is on: the smallest of the school's scales it fits in
        (85 at a school publishing on 30 and 100 is on 100)."""
        scales = self.scales.get(school) or SCALES
        return next((k for k in scales if value <= k), max(scales))

    def school_label(self, code: str) -> str:
        return self.all_school_names.get(code, code)

    def program_label(self, program_id: str) -> str:
        p = self.programs.get(program_id)
        return f"{self.school_label(p.school_code)} · {p.name}" if p else program_id

    def shortlist_codes(self) -> list[str]:
        return [e.main for e in self.state.shortlist]
