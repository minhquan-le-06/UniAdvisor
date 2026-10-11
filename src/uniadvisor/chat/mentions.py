"""Finding what a message talks about: subjects, schools, ngành, wish numbers, levels, areas, categories.

Rules and name matching only. Matching ignores case
and accents and works on whole words. A name that is also an everyday word is only taken where it cannot be the
everyday word (see each finder).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from uniadvisor.ui.catalog import Catalog, initials, search_key
from uniadvisor.chat.numbers import find_numbers, normalise
from uniadvisor.data.scope import strip_accents
from uniadvisor.planner.models import Level


@dataclass(frozen=True)
class Token:
    raw: str          # as typed (case kept)
    key: str          # lowercase, no accents
    start: int        # offsets in the normalised text
    end: int


def tokens(text: str) -> list[Token]:
    """Word tokens of a message; offsets refer to normalise(text)."""
    norm = normalise(text)
    raw = re.sub(r"\s+", " ", text.strip())
    raw = raw if len(raw) == len(norm) else norm                     # case is only kept when offsets line up
    return [Token(raw[m.start():m.end()], strip_accents(m.group(0)), m.start(), m.end())
            for m in re.finditer(r"[^\W_]+", norm)]


@dataclass(frozen=True)
class Mention:
    kind: str                     # 'subject', 'school', 'nganh', 'nv', 'level', 'area', 'category'
    values: tuple[str, ...]       # one value, or several when the name is ambiguous
    start: int
    end: int
    text: str                     # the words that matched


def _windows(toks: list[Token], index: dict[str, set[str]], max_len: int, accept=None) -> list[Mention]:
    """Longest-first, non-overlapping matches of token windows against index keys (space-joined token keys)."""
    out, i = [], 0
    while i < len(toks):
        for n in range(min(max_len, len(toks) - i), 0, -1):
            window = toks[i:i + n]
            key = " ".join(t.key for t in window)
            if key in index and (accept is None or accept(window, key, i)):
                out.append(Mention("", tuple(sorted(index[key])), window[0].start, window[-1].end,
                                   " ".join(t.raw for t in window)))
                i += n
                break
        else:
            i += 1
    return out


# ---------------------------------------------------------------- subjects

# (words, subject code). Short forms are also everyday words ('văn', 'anh', 'sử' ~ 'sư', 'hóa' ~ 'hoa'): they count
# as a subject only when a number follows within 3 words ("toán 8", "văn được 7,5") or "điểm" / "môn" precedes.
SUBJECT_WORDS = [
    ("toan", "TO", True), ("toan hoc", "TO", False), ("mon toan", "TO", False),
    ("van", "VA", True), ("ngu van", "VA", False), ("mon van", "VA", False),
    ("anh", "N1", True), ("tieng anh", "N1", False), ("anh van", "N1", False), ("ngoai ngu", "N1", False),
    ("ly", "LI", True), ("li", "LI", True), ("vat ly", "LI", False), ("vat li", "LI", False),
    ("hoa", "HO", True), ("hoa hoc", "HO", False),
    ("sinh", "SI", True), ("sinh hoc", "SI", False),
    ("su", "SU", True), ("lich su", "SU", False),
    ("dia", "DI", True), ("dia ly", "DI", False), ("dia li", "DI", False),
    ("gdktpl", "GDKTPL", False), ("ktpl", "GDKTPL", False), ("kinh te phap luat", "GDKTPL", False),
    ("giao duc kinh te va phap luat", "GDKTPL", False), ("kinh te va phap luat", "GDKTPL", False),
    ("tin", "TI", True), ("tin hoc", "TI", False),
    ("cong nghe cong nghiep", "CNCN", False), ("cncn", "CNCN", False),
    ("cong nghe nong nghiep", "CNNN", False), ("cnnn", "CNNN", False),
    ("tieng nga", "N2", False), ("tieng phap", "N3", False), ("tieng trung", "N4", False),
    ("tieng duc", "N5", False), ("tieng nhat", "N6", False), ("tieng han", "N7", False),
]


def find_subjects(text: str, known: set[str] | None = None) -> list[Mention]:
    toks = tokens(text)
    index: dict[str, set[str]] = {}
    short: set[str] = set()
    for words, code, is_short in SUBJECT_WORDS:
        if known is None or code in known:
            index.setdefault(words, set()).add(code)
            if is_short:
                short.add(words)
    numbers = find_numbers(normalise(text))

    def accept(window, key, i):
        if key not in short or (i > 0 and toks[i - 1].key in ("diem", "mon")):    # "điểm hóa", "môn văn"
            return True
        end = window[-1].end
        following = [t for t in toks[i + len(window):i + len(window) + 4]]
        limit = following[-1].end if following else end
        return any(end <= n.start <= limit + 1 for n in numbers)

    return [Mention("subject", m.values, m.start, m.end, m.text) for m in _windows(toks, index, 6, accept)]


# ---------------------------------------------------------------- schools

SCHOOL_PREFIXES = ["truong dai hoc", "dai hoc", "hoc vien", "truong si quan", "truong", "dh", "hv"]
SCHOOL_WORDS = {"truong", "dai", "hoc", "vien", "dh", "hv"}
# City / campus endings dropped to get the name students say ("Kinh tế Quốc dân", "Bách khoa"); longest first.
CITY_SUFFIXES = sorted(["dai hoc quoc gia ha noi", "dai hoc quoc gia tp hcm", "dai hoc quoc gia tp ho chi minh",
                        "tp ho chi minh", "thanh pho ho chi minh", "tp hcm", "ho chi minh", "ha noi", "phia nam",
                        "phia bac", "co so phia nam", "co so 2", "tru so chinh"], key=len, reverse=True)
# Ways to write the two cities: a name ending in one of them is also indexed with the others.
CITY_SPELLINGS = [["tp ho chi minh", "thanh pho ho chi minh", "ho chi minh", "tp hcm", "hcm", "tphcm", "sai gon"],
                  ["ha noi", "hn"]]


class SchoolIndex:
    """School names as students write them: without 'Trường Đại học' / 'Học viện', with or without the city, the
    first letters of the name (ktqd), a curated alias (NEU, Bách khoa TP.HCM), or the code typed in capitals (BKA)."""

    def __init__(self, schools: dict[str, str], places: set[str] = frozenset(),
                 aliases: dict[str, list[str]] | None = None):
        self.names = schools
        self.index: dict[str, set[str]] = {}
        self.weak: set[str] = set()          # keys that need 'trường' / 'đại học' before them
        self.caps: set[str] = set()          # short abbreviations that must be typed in capitals ('NEU', 'IU')
        for code, name in schools.items():
            for key in self._keys(name):
                self.index.setdefault(key, set()).add(code)
        for key in self.index:
            if len(key.split()) == 1 or key in places:
                self.weak.add(key)
        for code, names in (aliases or {}).items():
            if code not in schools:
                continue
            for alias in names:
                for key in self._variants(search_key(alias)):
                    self.index.setdefault(key, set()).add(code)
                    self.weak.discard(key)
                    if len(key) <= 4 and alias.upper() == alias.replace("a", "A"):   # NEU, IU, HaUI
                        self.caps.add(key)              # 'neu' is also 'nếu' typed without accents

    @staticmethod
    def _variants(key: str) -> set[str]:
        out = {key}
        for spellings in CITY_SPELLINGS:
            for s in spellings:
                if key.endswith(" " + s):
                    head = key[:-len(s) - 1]
                    out |= {f"{head} {other}" for other in spellings}
        return out

    @classmethod
    def _keys(cls, name: str) -> set[str]:
        base = search_key(re.sub(r"\([^)]*\)", " ", name))
        for prefix in SCHOOL_PREFIXES:
            if base.startswith(prefix + " "):
                base = base[len(prefix) + 1:]
                break
        keys = cls._variants(base)
        for suffix in CITY_SUFFIXES:
            if base.endswith(" " + suffix):
                keys.add(base[:-len(suffix) - 1])
                break
        abbrev = initials(base)
        if abbrev and len(abbrev) >= 3:
            keys.add(abbrev)
        return {k for k in keys if k}

    def find(self, text: str) -> list[Mention]:
        toks = tokens(text)
        out = []
        codes = set(self.names)
        for t in toks:                                   # a code typed in capitals: 'BKA', 'NHF'
            if t.raw.isupper() and t.raw in codes:
                out.append(Mention("school", (t.raw,), t.start, t.end, t.raw))
        taken = [(m.start, m.end) for m in out]

        def accept(window, key, i):
            if any(not (window[-1].end <= a or window[0].start >= b) for a, b in taken):
                return False
            if key in self.caps and sum(ch.isupper() for ch in window[0].raw) < 2:
                return False
            if key in self.weak:
                return i > 0 and toks[i - 1].key in SCHOOL_WORDS
            return True

        out += [Mention("school", m.values, m.start, m.end, m.text) for m in _windows(toks, self.index, 10, accept)]
        return sorted(out, key=lambda m: m.start)


# ---------------------------------------------------------------- ngành

class NganhIndex:
    """ngành / nhóm ngành names, display names, aliases and abbreviations (from the catalog).

    A key that is a name or curated alias of some code beats first-letter abbreviations of unrelated codes: 'CNTT' is
    Công nghệ thông tin (and its nhóm), not Công nghệ truyền thông.
    """

    def __init__(self, catalog: Catalog):
        strong: dict[str, set[str]] = {}
        weak: dict[str, set[str]] = {}
        for code, m in catalog.majors.items():
            keys, alias_keys, abbrevs, _ = catalog._index[code]
            curated = {a.replace(" ", "") for a in alias_keys}
            for key in keys | alias_keys | (abbrevs & curated):
                strong.setdefault(key, set()).add(code)
            for key in abbrevs - curated:
                weak.setdefault(key, set()).add(code)
        family = {c: {c, m.parent} | set(m.children) for c, m in catalog.majors.items()}
        self.index = {k: set(v) for k, v in strong.items()}
        for key, codes in weak.items():
            if key in strong:
                related = set().union(*(family[c] for c in strong[key]))
                codes = {c for c in codes if c in related}
            self.index.setdefault(key, set()).update(codes)

    def find(self, text: str) -> list[Mention]:
        toks = tokens(text)

        def accept(window, key, i):
            if len(key) <= 2:                             # 'AI', 'IT', 'PR': only in capitals ('ai' = "who")
                return window[0].raw.isupper()
            return key not in {"nganh", "hoc", "khac"}

        return [Mention("nganh", m.values, m.start, m.end, m.text) for m in _windows(toks, self.index, 10, accept)]


def prefer_nganh(codes: tuple[str, ...], catalog: Catalog) -> tuple[str, ...]:
    """A name shared by a nhóm ngành and one of its ngành ('CNTT') means the ngành."""
    nganh = [c for c in codes if len(c) == 7]
    if len(nganh) == 1 and all(len(c) == 7 or c == catalog.majors[nganh[0]].parent for c in codes):
        return (nganh[0],)
    return codes


# ---------------------------------------------------------------- wish numbers, levels, area, category

_NV = re.compile(r"\b(?:nv|nguyen vong|nguyện vọng)\s*(?:so\s*|số\s*)?(\d{1,2})\b")


def find_nv(text: str) -> list[Mention]:
    norm = normalise(text)
    return [Mention("nv", (m.group(1),), m.start(), m.end(), m.group(0)) for m in _NV.finditer(norm)]


LEVEL_WORDS = {"an toan": Level.AN_TOAN, "vua suc": Level.VUA_SUC, "thu suc": Level.THU_SUC, "mo uoc": Level.MO_UOC}


def find_levels(text: str) -> list[Mention]:
    toks = tokens(text)
    index = {k: {v.value} for k, v in LEVEL_WORDS.items()}
    return [Mention("level", m.values, m.start, m.end, m.text) for m in _windows(toks, index, 2)]


_AREA = re.compile(r"\b(?:kv|khu vuc)\s*([123])(?:\s*[-_ ]?\s*(nt|nong thon))?\b")
_CATEGORY = re.compile(r"\b(?:ut|uu tien|doi tuong uu tien|nhom uu tien)\s*([12])\b"
                       r"|\b(?:doi tuong|nhom doi tuong|nhom)\s*0?([1-6])\b")
_NO_CATEGORY = re.compile(r"\bkhong\s+(?:thuoc\s+)?(?:dien\s+|doi tuong\s+|nhom\s+)?uu tien\b")


def find_area(text: str) -> list[Mention]:
    """'KV1', 'kv2-nt', 'khu vực 2 nông thôn', 'KV3'."""
    key = strip_accents(normalise(text))
    out = []
    for m in _AREA.finditer(key):
        n, nt = m.group(1), m.group(2)
        if nt and n != "2":
            continue
        out.append(Mention("area", ("KV2-NT" if nt else f"KV{n}",), m.start(), m.end(), m.group(0)))
    return out


def find_category(text: str) -> list[Mention]:
    """'UT1', 'ưu tiên 2', 'đối tượng 01' (nhóm 01-03 -> UT1, 04-06 -> UT2, Thông tư 06/2026), 'không ưu tiên'."""
    key = strip_accents(normalise(text))
    out = [Mention("category", ("none",), m.start(), m.end(), m.group(0)) for m in _NO_CATEGORY.finditer(key)]
    for m in _CATEGORY.finditer(key):
        if any(o.start <= m.start() < o.end for o in out):
            continue
        if m.group(1):
            value = f"UT{m.group(1)}"
        else:
            value = "UT1" if int(m.group(2)) <= 3 else "UT2"
        out.append(Mention("category", (value,), m.start(), m.end(), m.group(0)))
    return sorted(out, key=lambda m: m.start)
