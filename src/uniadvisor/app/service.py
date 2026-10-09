"""What the page needs from the data and the rules, without Streamlit (so it can be tested alone).

The database path comes from the UNIADVISOR_DB environment variable (tests point it at the fake database) or defaults
to data/build/uniadvisor.db, which is built from the committed inputs when it is missing (a fresh deployment).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from uniadvisor import db
from uniadvisor.app.catalog import Catalog
from uniadvisor.app.facts import FactsIndex
from uniadvisor.app.plan_file import Known
from uniadvisor.app.state import PlanState
from uniadvisor.chat.classify import Classifier, load_classifier
from uniadvisor.chat.context import ChatContext, Indexes
from uniadvisor.config import load_data_config, load_list_config, load_provinces, load_rules, province_names
from uniadvisor.paths import DB_PATH, ROOT
from uniadvisor.plan.chances import ChangeModel, Chances, chances
from uniadvisor.plan.lists import ListFacts, Priority, Recommended, build_with_floor, recommend, usable
from uniadvisor.plan.models import ListResult, ProgramFacts, ShortlistItem
from uniadvisor.plan.repository import load_programs
from uniadvisor.plan.strategy import build_list
from uniadvisor.suggest.model import LearnedScorer
from uniadvisor.suggest.reader import Reader, load_reader
from uniadvisor.suggest.score import DataScorer

ENV_DB = "UNIADVISOR_DB"
MODEL_DIR = ROOT / "models" / "suggester"   # step 7 learned model (when ready)
FURTHER_CLOSE = 5          # next closest ngành used for the an toàn top-up (config/facts.yaml closeness.further)


def db_path() -> Path:
    return Path(os.environ.get(ENV_DB) or DB_PATH)


def ensure_db() -> Path:
    """The database path; builds the default database when it is missing (about a minute)."""
    path = db_path()
    if not path.exists() and ENV_DB not in os.environ:
        from uniadvisor.data.build import build
        build()
    return path


@dataclass
class AppData:
    catalog: Catalog
    programs: list[ProgramFacts]
    subjects: dict[str, str]                 # exam subject code -> name, in display order (used ones)
    provinces: list[str]                     # names a student picks from
    province_city: dict[str, str]
    admission_year: int
    rules: dict
    list_cfg: dict
    school_names: dict[str, str]                 # in-scope schools
    all_school_names: dict[str, str]             # every school (the chat answers "why isn't X there" for any)
    school_aliases: dict[str, list[str]]
    facts: FactsIndex = None
    sheets: dict[str, str] = None                # nhóm ngành -> reviewed fact sheet (markdown); drafts are not shown
    change_model: ChangeModel | None = None      # how cutoffs moved between the two years (chances); None: too few
    suggester: DataScorer | None = None          # step 7 "Em chưa biết gì" (data scores until the model is ready)
    closeness: dict[tuple[str, str], float] = None   # (ngành, other ngành) -> closeness score (step 6)
    career_scorer: DataScorer | None = None      # the same data scores per ngành: career fit
    reader: Reader | None = None                 # step 7 free-text reader ("Kể thêm về em" -> options)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppData":
        conn = db.connect(path or ensure_db())
        try:
            catalog = Catalog.load(conn)
            facts = FactsIndex.load(conn, catalog)
            programs = load_programs(conn)
            # Exam subjects some in-scope program's combination uses: the ones worth asking a score for.
            subjects = dict(conn.execute(
                """SELECT DISTINCT s.code, s.name FROM subject s JOIN combo_subject cs ON cs.subject_code = s.code
                   JOIN combo k ON k.code = cs.combo_code AND k.subjects_known = 1
                   JOIN program_combo pc ON pc.combo_code = k.code
                   JOIN program p ON p.id = pc.program_id AND p.in_scope = 1
                   WHERE s.is_exam = 1""").fetchall())
            school_names = dict(conn.execute("SELECT code, name FROM school WHERE in_scope = 1").fetchall())
            all_school_names = dict(conn.execute("SELECT code, name FROM school").fetchall())
            school_aliases: dict[str, list[str]] = {}
            for code, alias in conn.execute("SELECT school_code, alias FROM school_alias ORDER BY school_code, alias"):
                school_aliases.setdefault(code, []).append(alias)
            tables = {t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            sheets = dict(conn.execute("SELECT code, markdown FROM fact_sheet WHERE status = 'reviewed'").fetchall()
                          ) if "fact_sheet" in tables else {}
            try:
                change_model = ChangeModel.fit(conn, tuple(load_data_config()["cutoff_years"]), load_list_config())
            except ValueError:
                change_model = None
            suggester = DataScorer.load(conn, catalog) if "nganh_interest" in tables else None
            learned = LearnedScorer.load(MODEL_DIR, suggester) if suggester is not None else None
            if learned is not None and learned.info.get("ready"):     # suggest/train.py decides (held-out family)
                suggester = learned
            career_scorer = DataScorer.load(conn, catalog, level="nganh") if "nganh_interest" in tables else None
            closeness = {(a, b): s for a, b, s in conn.execute("SELECT nganh_code, other_code, score FROM nganh_close")
                         } if "nganh_close" in tables else {}
        finally:
            conn.close()
        year = load_data_config()["target_admission_year"]
        names = province_names()
        first = [n for n in ("Hà Nội", "TP. Hồ Chí Minh") if n in names]
        return cls(catalog, programs, _subject_order(subjects), first + sorted(set(names) - set(first),
                                                                               key=_vi_sort_key),
                   load_provinces(), year, load_rules(year), load_list_config(), school_names, all_school_names,
                   school_aliases, facts, sheets, change_model, suggester, closeness, career_scorer,
                   load_reader(suggester.qn) if suggester is not None else None)

    @cached_property
    def indexes(self) -> Indexes:
        return Indexes.build(self.catalog, self.all_school_names, self.provinces, self.school_aliases)

    @cached_property
    def classifier(self) -> Classifier:
        return load_classifier(self.indexes.schools, self.indexes.nganh, set(self.subjects))

    @cached_property
    def programs_by_id(self) -> dict[str, ProgramFacts]:
        return {p.id: p for p in self.programs}

    def chat_context(self, state: PlanState, result: ListResult | None) -> ChatContext:
        return ChatContext(self.catalog, self.subjects, self.school_names, self.all_school_names,
                           self.programs_by_id, self.indexes, state, result, self.list_cfg, self.facts)

    def known(self) -> Known:
        return Known(frozenset(self.subjects), frozenset(self.provinces), frozenset(self.catalog.majors),
                     frozenset(self.school_names), frozenset(p.id for p in self.programs))

    def shortlist_items(self, state: PlanState) -> list[ShortlistItem]:
        """The student's shortlist plus, per item, the next closest ngành (step 6) for the an toàn top-up (spec 4.5)."""
        items = []
        for item in state.to_shortlist():
            taken = {item.main_code, *item.close_codes}
            further = tuple(c for c in self.facts.get(item.main_code).close
                            if c not in taken and self.catalog.majors[c].level == "nganh")[:FURTHER_CLOSE]
            items.append(ShortlistItem(item.main_code, item.close_codes, further))
        return items

    def chances(self, state: PlanState, result: ListResult) -> list[Chances]:
        """The list's chances: at the score entered; with expected scores also 1 point lower and higher."""
        if self.change_model is None or not result.wishes:
            return []
        shifts = self.list_cfg["chances"]["score_shifts_before_exam"] if state.score_kind == "expected" else [0.0]
        return [chances(result, self.change_model, self.list_cfg, s) for s in shifts]

    def list_facts(self, answers: dict | None = None) -> ListFacts:
        """Closeness of ngành, and the career scores from the student's answers to the 12 questions (step 7 data
        scores per ngành: each ngành's rank among all ngành, 1 = best fit); no answers, no career scores."""
        career = {}
        if answers and self.career_scorer is not None and any(v is not None for v in answers.values()):
            ranked = self.career_scorer.rank(answers)
            n = len(ranked)
            career = {g: 1 - i / (n - 1) for i, g in enumerate(ranked)} if n > 1 else {}
        children = {c: tuple(m.children) for c, m in self.catalog.majors.items() if m.level == "nhom_nganh"}
        return ListFacts(self.closeness or {}, children, self.catalog.nganh_parents(), career)

    def recommend(self, state: PlanState) -> list[Recommended]:
        """The three recommended lists."""
        return recommend(state.to_profile(), self.shortlist_items(state), self.programs, self.catalog.nganh_parents(),
                         self.rules, self.list_cfg, self.province_city, self.admission_year, self.change_model,
                         self.list_facts(state.answers))

    def chosen(self, state: PlanState) -> Recommended | None:
        """The list the student chose, rebuilt with their changes (None: no list chosen yet). A chosen Nghề nghiệp
        nhất without answers is built as Hợp môn nhất (plan.lists.usable); the page says so."""
        if state.list_choice not in {p.value for p in Priority}:
            return None
        facts = self.list_facts(state.answers)
        return build_with_floor(state.to_profile(), self.shortlist_items(state), self.programs,
                                self.catalog.nganh_parents(), self.rules, self.list_cfg, self.province_city,
                                self.admission_year, self.change_model, facts,
                                usable(Priority(state.list_choice), facts))

    def build_list(self, state: PlanState) -> ListResult:
        """The chosen list (controls, chat and the 'what changed' text all work on it); before a choice, the list of
        the plain rules."""
        chosen = self.chosen(state)
        if chosen is not None:
            return chosen.result
        return build_list(state.to_profile(), self.shortlist_items(state), self.programs,
                          self.catalog.nganh_parents(), self.rules, self.list_cfg, self.province_city,
                          self.admission_year)


# Compulsory subjects first, then the usual elective subjects, then foreign languages; the rest by name.
_SUBJECT_ORDER = ["TO", "VA", "N1", "LI", "HO", "SI", "SU", "DI", "GDKTPL", "TI", "CNCN", "CNNN"]


def _subject_order(subjects: dict[str, str]) -> dict[str, str]:
    order = [c for c in _SUBJECT_ORDER if c in subjects]
    order += sorted((c for c in subjects if c not in order), key=lambda c: _vi_sort_key(subjects[c]))
    return {c: subjects[c] for c in order}


def _vi_sort_key(text: str) -> str:
    from uniadvisor.app.catalog import search_key
    return search_key(text)
