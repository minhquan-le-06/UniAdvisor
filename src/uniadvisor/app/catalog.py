"""The ngành / nhóm ngành a student can pick in step 1, with their display names, search and the facts available so
far (spec 3.2, 3.4, 3.6). Loaded once from the database into memory; no database access after loading.

Only codes offered by an in-scope program taught in Hà Nội or TP.HCM are listed (spec 3.4: "only ngành offered by
in-scope programs").
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from uniadvisor.data.scope import strip_accents


def search_key(text: str | None) -> str:
    """Lowercase, no accents ('đ' -> 'd'), words separated by single spaces: 'Tài chính - Ngân hàng' ->
    'tai chinh ngan hang'."""
    return " ".join(re.findall(r"[a-z0-9]+", strip_accents(text or "")))


def initials(text: str) -> str | None:
    """'Công nghệ thông tin' -> 'cntt'. Vietnamese abbreviations are usually the first letters of the syllables;
    names of 2-6 words only (longer names have no everyday abbreviation)."""
    words = search_key(text).split()
    return "".join(w[0] for w in words) if 2 <= len(words) <= 6 else None


@dataclass
class Major:
    code: str
    level: str                       # 'nganh' | 'nhom_nganh'
    official: str                    # MOET name (Thông tư 09/2022)
    display: str | None              # name students know (display_name table); None: use the official name
    aliases: list[str]
    parent: str | None               # nhóm ngành of a ngành
    display_status: str | None       # 'draft' | 'reviewed' | None (no row)
    n_programs: int = 0              # in-scope programs in Hà Nội / TP.HCM
    n_programs_hn: int = 0
    n_programs_hcm: int = 0
    n_with_cutoff: int = 0
    children: list[str] = field(default_factory=list)   # ngành of a nhóm ngành, most programs first

    @property
    def label(self) -> str:
        return self.display or self.official


@dataclass(frozen=True)
class Hit:
    code: str
    tier: int                        # 0 exact (name, alias, abbreviation), 1 name starts with the query,
                                     # 2 every word matches, 3 matched a school's program name only
    matched: str                     # the text that matched, for "khớp với ..." hints


@dataclass(frozen=True)
class ComboShare:
    combo: str
    subjects: tuple[str, ...]        # subject names
    n_programs: int
    share: float                     # of the code's programs that list any known combination


class Catalog:
    def __init__(self, majors: dict[str, Major], program_names: dict[str, list[str]],
                 combo_counts: dict[str, Counter], subject_counts: dict[str, Counter], combo_programs: dict[str, int],
                 combo_subjects: dict[str, tuple[str, ...]], subject_names: dict[str, str]):
        self.majors = majors
        self.program_names = program_names              # ngành code -> distinct school program names
        self._combo_counts = combo_counts               # code -> Counter(combo -> programs)
        self._subject_counts = subject_counts           # code -> Counter(subject -> programs)
        self._combo_programs = combo_programs           # code -> programs with at least one known combination
        self.combo_subjects = combo_subjects            # combo -> subject codes
        self.subject_names = subject_names
        self._index = {code: self._fields(m) for code, m in majors.items()}

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> "Catalog":
        majors: dict[str, Major] = {}
        rows = conn.execute(
            """SELECT m.code, m.level, m.name, m.parent_code, d.display_name, d.aliases, d.status
               FROM moet_major m LEFT JOIN display_name d ON d.code = m.code
               WHERE m.level IN ('nganh', 'nhom_nganh') ORDER BY m.code"""
        ).fetchall()
        for code, level, name, parent, display, aliases, status in rows:
            majors[code] = Major(code, level, name, display, [a.strip() for a in (aliases or "").split(";")
                                                             if a.strip()],
                                 parent if level == "nganh" else None, status)

        program_names: dict[str, set[str]] = defaultdict(set)
        cutoff_ids = {pid for (pid,) in conn.execute("SELECT DISTINCT program_id FROM cutoff")}
        programs = conn.execute(
            """SELECT id, moet_code, name, city FROM program
               WHERE in_scope = 1 AND moet_code IS NOT NULL AND city IN ('HN', 'HCM')"""
        ).fetchall()
        by_program: dict[str, str] = {}
        for pid, moet, name, city in programs:
            m = majors.get(moet)
            if m is None:
                continue
            by_program[pid] = moet
            program_names[moet].add(name)
            for x in (m, majors.get(m.parent)):
                if x is None:
                    continue
                x.n_programs += 1
                x.n_programs_hn += city == "HN"
                x.n_programs_hcm += city == "HCM"
                x.n_with_cutoff += pid in cutoff_ids
        majors = {c: m for c, m in majors.items() if m.n_programs}
        for m in majors.values():
            if m.parent in majors:
                majors[m.parent].children.append(m.code)
        for m in majors.values():
            m.children.sort(key=lambda c: (-majors[c].n_programs, c))   # spec 3.6: most programs first

        exam = {code for (code,) in conn.execute("SELECT code FROM subject WHERE is_exam = 1")}
        combo_subjects: dict[str, list[str]] = defaultdict(list)
        for combo, subject in conn.execute(
            """SELECT cs.combo_code, cs.subject_code FROM combo_subject cs JOIN combo k ON k.code = cs.combo_code
               WHERE k.subjects_known = 1 ORDER BY cs.combo_code, cs.position"""
        ):
            combo_subjects[combo].append(subject)
        # "anchor + any 2" sets ('Toán+Lí+Hóa', data.build.apply_program_combos) would swamp the shares: left out
        known = {c: tuple(s) for c, s in combo_subjects.items()
                 if len(s) == 3 and all(x in exam for x in s) and "+" not in c}
        program_combos: dict[str, set[str]] = defaultdict(set)
        for pid, combo in conn.execute("SELECT program_id, combo_code FROM program_combo"):
            if pid in by_program and combo in known:
                program_combos[pid].add(combo)
        counts: dict[str, Counter] = defaultdict(Counter)          # code -> combo -> programs
        subjects: dict[str, Counter] = defaultdict(Counter)        # code -> subject -> programs
        with_known: Counter = Counter()                            # code -> programs with a known combination
        for pid, pcombos in program_combos.items():
            moet = by_program[pid]
            for code in (moet, majors[moet].parent):
                if code in majors:
                    counts[code].update(pcombos)
                    subjects[code].update({s for c in pcombos for s in known[c]})
                    with_known[code] += 1
        subject_names = dict(conn.execute("SELECT code, name FROM subject").fetchall())
        return cls(majors, {c: sorted(n) for c, n in program_names.items()}, counts, subjects, dict(with_known),
                   known, subject_names)

    # ------------------------------------------------------------------ names

    def label(self, code: str) -> str:
        m = self.majors.get(code)
        return m.label if m else code

    def official(self, code: str) -> str:
        m = self.majors.get(code)
        return m.official if m else code

    def nganh_codes(self) -> list[str]:
        return sorted(c for c, m in self.majors.items() if m.level == "nganh")

    def nganh_parents(self) -> dict[str, str]:
        return {c: m.parent for c, m in self.majors.items() if m.level == "nganh" and m.parent}

    # ------------------------------------------------------------------ search

    @staticmethod
    def _fields(m: Major):
        names = [m.official] + ([m.display] if m.display else [])
        parts = [p for n in names for p in re.split(r"[,()]|\.\.\.", n) if search_key(p)]
        keys = {search_key(x) for x in names + parts}
        alias_keys = {search_key(a) for a in m.aliases}
        abbrevs = {a.replace(" ", "") for a in alias_keys} | {x for x in map(initials, names + parts) if x}
        words = set(" ".join(keys | alias_keys).split())
        return keys, alias_keys, abbrevs, words

    def search(self, query: str, limit: int = 20) -> list[Hit]:
        """Codes matching the query, best first: tier, then more programs, then ngành before nhóm, then code.

        Matching ignores case and accents. Abbreviations match exactly ("cntt", "KHMT"); names and aliases match from
        their start or word by word ("ky thuat phan"); a ngành also matches when the query appears, as whole words,
        in a program name a school uses ("logistics" -> Quản trị kinh doanh via "Quản trị kinh doanh (Logistics)").
        """
        q = search_key(query)
        if len(q.replace(" ", "")) < 2:
            return []
        compact, tokens = q.replace(" ", ""), q.split()

        def every_word(words) -> bool:
            return all(any(w.startswith(t) for w in words) for t in tokens)

        hits: list[Hit] = []
        for code, m in self.majors.items():
            keys, alias_keys, abbrevs, words = self._index[code]
            tier = matched = None
            if q in keys or q in alias_keys or compact in abbrevs:
                tier, matched = 0, query
            elif any(k.startswith(q) for k in keys | alias_keys):
                tier = 1
            elif every_word(words):
                tier = 2
            else:
                for name in self.program_names.get(code, []) if m.level == "nganh" else []:
                    if f" {q} " in f" {search_key(name)} ":          # the query as whole words, in order
                        tier, matched = 3, name
                        break
            if tier is not None:
                hits.append(Hit(code, tier, matched or m.label))
        hits.sort(key=lambda h: (h.tier, -self.majors[h.code].n_programs, self.majors[h.code].level != "nganh",
                                 h.code))
        return hits[:limit]

    # ------------------------------------------------------------------ facts

    def combo_shares(self, code: str, top: int = 5) -> list[ComboShare]:
        """The combinations most programs of this code accept (spec 3.4 "strong subjects"): share of programs."""
        total = self._combo_programs.get(code, 0)
        out = []
        for combo, n in sorted(self._combo_counts.get(code, Counter()).items(), key=lambda x: (-x[1], x[0]))[:top]:
            out.append(ComboShare(combo, tuple(self.subject_names.get(s, s) for s in self.combo_subjects[combo]),
                                  n, n / total))
        return out

    def subject_counts(self, code: str) -> tuple[Counter, int]:
        """(subject code -> programs accepting a combination with it, programs with any known combination)."""
        return Counter(self._subject_counts.get(code, Counter())), self._combo_programs.get(code, 0)

    def subject_shares(self, code: str) -> list[tuple[str, float]]:
        """(subject name, share of this code's programs accepting at least one combination with it), most first."""
        total = self._combo_programs.get(code, 0)
        if not total:
            return []
        return sorted(((self.subject_names.get(s, s), n / total)
                       for s, n in self._subject_counts.get(code, Counter()).items()), key=lambda x: (-x[1], x[0]))
