"""Values people captured from the schools' own documents (data/manual_sources), entered into data/curated:

- school_cutoffs.csv: cutoffs of schools no cutoff site covers (one row per program, year and combination group).
- school_combos.csv: combination codes a school defines for itself (e.g. UEH's AH2), which may differ from the same
  code elsewhere or be undefined in the export.
- school_tuition.csv: tuition per program or group of programs.
- school_employment.csv: the share of a school's graduates of one ngành who have a job ("tỷ lệ sinh viên tốt nghiệp
  có việc làm"), per graduation year.
- school_scales.csv: the score scale a school states for its exam-score cutoffs of a year (e.g. TDTU 2025:
  'thang 40'), for all its programs or those whose code fully matches `program_pattern`, for the cutoffs the sites
  give without a scale.

Each loader returns plain data; build.py applies it. Rows that cannot be used go to review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from uniadvisor.data.sources import OBS_COLUMNS, norm_code, parse_score, split_combos

SOURCE_ID = "school_document"
SCOPED = "@"            # a school's own definition of a combination code: 'AH2@KSA'


def _read(curated: Path, name: str) -> pd.DataFrame:
    path = curated / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def combo_label(code: str) -> str:
    """The code as the school writes it: 'AH2@KSA' -> 'AH2'."""
    return code.split(SCOPED, 1)[0]


# ---------------------------------------------------------------- cutoffs

def load_cutoffs(curated: Path) -> pd.DataFrame:
    """Observations in the cutoff sites' shape, plus doc_method ('thpt' / 'thpt_mixed' / 'other')."""
    df = _read(curated, "school_cutoffs.csv")
    if df.empty:
        return pd.DataFrame(columns=OBS_COLUMNS + ["doc_method"])
    notes = [("; ".join(x for x in (f"Thang điểm: {s}" if s else "", n) if x)) for s, n in zip(df["scale"], df["note"])]
    out = pd.DataFrame({
        "source_id": SOURCE_ID,
        "school_code": df["school_code"].str.strip().str.upper(),
        "program_code": df["program_code"].map(norm_code),
        "program_name": df["program_name"].str.strip(),
        "year": df["year"].astype(int),
        "combos": df["combos"].map(lambda c: [] if c.strip() in ("", "*") else split_combos(c)),
        "score": df["score"].map(parse_score),
        "raw_score": df["score"],
        "note": notes,
        "url": df["source_file"],
        "tuition_raw": "",
        "doc_method": df["method"].str.strip(),
    })
    return out


# ---------------------------------------------------------------- combinations

def load_combos(curated: Path, subjects: set[str], review) -> dict[tuple[str, str], list[str]]:
    """(school, code) -> subject codes, for rows whose three subjects are known exam subjects."""
    out = {}
    for r in _read(curated, "school_combos.csv").itertuples():
        parts = [p.strip() for p in r.subjects.split(";") if p.strip()]
        if len(parts) != 3 or any(p not in subjects for p in parts):
            review.add("school_combos_unusable", school_code=r.school_code, combo=r.combo_code, subjects=r.subjects,
                       source_file=r.source_file, note=r.note)
            continue
        out[(r.school_code.strip().upper(), r.combo_code.strip().upper())] = parts
    return out


def scope_combos(codes: list[str], school: str, defs: dict[tuple[str, str], list[str]],
                 global_defs: dict[str, list[str]]) -> list[str]:
    """Replace a code by the school's own definition when the school defines it differently from the shared code
    (or the shared code is undefined)."""
    out = []
    for c in codes:
        own = defs.get((school, c))
        if own is not None and sorted(own) != sorted(global_defs.get(c) or []):
            out.append(f"{c}{SCOPED}{school}")
        else:
            out.append(c)
    return out


# The 2025 exam's subjects (2 compulsory + 2 chosen), short names for the codes of "anchor + any 2" combinations.
# KHTN, KHXH and NN are the old exam's aggregate tests, not chosen subjects.
ANY_TWO_SUBJECTS = {"TO": "Toán", "VA": "Văn", "LI": "Lí", "HO": "Hóa", "SI": "Sinh", "SU": "Sử", "DI": "Địa",
                    "GDKTPL": "KTPL", "TI": "Tin", "CNCN": "CN công nghiệp", "CNNN": "CN nông nghiệp", "N1": "Anh",
                    "N2": "Nga", "N3": "Pháp", "N4": "Trung", "N5": "Đức", "N6": "Nhật", "N7": "Hàn"}
ANY_TWO = re.compile(r"^(TO|VA)\+2$")          # "TO+2": Toán and any two other subjects of the exam


def any_two(anchor: str, known: set[str] | None = None) -> dict[str, list[str]]:
    """'TO' -> {'Toán+Lí+Hóa': ['TO', 'LI', 'HO'], ...}: every set of the anchor and two other exam subjects (of
    `known`, when given), coded by the subjects' short names (the code is what the app shows)."""
    others = [s for s in ANY_TWO_SUBJECTS if s != anchor and (known is None or s in known)]
    return {"+".join(ANY_TWO_SUBJECTS[s] for s in (anchor, a, b)): [anchor, a, b]
            for i, a in enumerate(others) for b in others[i + 1:]}


def load_program_combos(curated: Path) -> dict[tuple[str, str], tuple[list[str], str]]:
    """(school, program code) -> (combination tokens, source_file) from program_combos.csv: the combinations a
    reviewed list gives for a program whose combinations the sites do not give (2026-10-09). A token is a
    combination code or an "anchor + any 2" rule (`TO+2`, `VA+2`)."""
    out = {}
    for r in _read(curated, "program_combos.csv").itertuples():
        tokens = [t.strip().upper() for t in r.combos.split(";") if t.strip()]
        if tokens:
            out[(r.school_code.strip().upper(), r.program_code.strip())] = (tokens, r.source_file)
    return out


# ---------------------------------------------------------------- tuition

def _year(school_year: str) -> int | None:
    m = re.match(r"\s*(\d{4})", school_year or "")
    return int(m.group(1)) if m else None


UNIT_VI = {"per_year": "năm", "per_semester": "học kỳ", "per_course": "khóa", "per_credit": "tín chỉ"}
# How a per-year amount was obtained from another unit (design decision 2026-10-07, 2c); NULL in the database when
# the document states the amount per year.
FACTOR_BASES = {
    "semesters_per_year_stated",       # per semester x the semesters per year the document states
    "semesters_per_year_owner_rule",   # per semester x 2 (the document does not say)
    "course_years_stated",             # whole course / the course years the document states
    "free",                            # the document says the program is free (miễn học phí): 0 per year
}


def _vnd(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def _factor(text: str) -> float:
    """'2' -> 2.0, '1/3.5' -> 0.2857..."""
    num, _, den = text.strip().partition("/")
    return float(num) / float(den) if den else float(num)


def load_scales(curated: Path, review) -> dict[tuple[str, int], list[tuple[str, int]]]:
    """(school code, year) -> [(program pattern, scale)] stated by the school's own document; rows naming programs
    come before a school-wide row ('' or '*'), so the more specific one wins."""
    out: dict[tuple[str, int], list[tuple[str, int]]] = {}
    df = _read(curated, "school_scales.csv")
    if not df.empty and "program_pattern" not in df:
        df["program_pattern"] = ""
    for r in df.itertuples():
        if r.scale not in ("30", "40", "100") or not r.year.isdigit() or not r.source_file:
            review.add("school_document_rows", file="school_scales.csv", school_code=r.school_code,
                       issue="scale, year or source_file missing")
            continue
        pattern = "" if r.program_pattern in ("", "*") else r.program_pattern
        out.setdefault((r.school_code, int(r.year)), []).append((pattern, int(r.scale)))
    for rules in out.values():
        rules.sort(key=lambda x: x[0] == "")
    return out


def stated_scale(scales: dict[tuple[str, int], list[tuple[str, int]]], program_id: str, year: int) -> int | None:
    school, code = program_id.split(":", 1)
    for pattern, scale in scales.get((school, int(year)), []):
        if not pattern or re.fullmatch(pattern, code):
            return scale
    return None


def load_tuition(curated: Path, programs: dict[str, dict], review) -> dict[str, tuple]:
    """program id -> (min, max, year, raw, source_id, basis), per year. Rows in another unit are converted with their
    per_year_factor when factor_basis is one of FACTOR_BASES; the others go to review. A row's program_pattern is a
    full-match regex over the school's program codes ('*' = every program)."""
    out: dict[str, tuple] = {}
    by_school: dict[str, list[str]] = {}
    for pid, p in programs.items():
        by_school.setdefault(p["school_code"], []).append(pid)
    df = _read(curated, "school_tuition.csv")
    for col in ("per_year_factor", "factor_basis"):
        if not df.empty and col not in df:
            df[col] = ""
    for r in df.itertuples():
        school = r.school_code.strip().upper()
        unit, basis = r.unit.strip(), r.factor_basis.strip()
        if basis == "covered_by_per_year_row":
            continue
        if unit != "per_year" and basis not in FACTOR_BASES:
            review.add("school_tuition_not_per_year", school_code=school, programs=r.program_pattern,
                       min_vnd=r.min_vnd, max_vnd=r.max_vnd, unit=r.unit, school_year=r.school_year,
                       source_file=r.source_file, note=r.note)
            continue
        pattern = ".*" if r.program_pattern.strip() == "*" else r.program_pattern.strip()
        lo, hi = int(r.min_vnd), int(r.max_vnd or r.min_vnd)
        raw = _vnd(lo) + ("" if lo == hi else " - " + _vnd(hi)) + f"/{UNIT_VI.get(unit, unit)}"
        if unit == "per_year":
            basis = None
        else:
            f = _factor(r.per_year_factor)
            lo, hi = round(lo * f, -3), round(hi * f, -3)
            raw += f" x {r.per_year_factor.strip()} ({basis})"
        raw += f" ({r.school_year}, {r.source_file})"
        matched = [pid for pid in by_school.get(school, []) if re.fullmatch(pattern, programs[pid]["program_code"])]
        if not matched:
            review.add("school_tuition_unmatched", school_code=school, programs=r.program_pattern,
                       source_file=r.source_file, note=r.note)
        for pid in matched:
            out[pid] = (int(lo), int(hi), _year(r.school_year), raw, SOURCE_ID, basis)
    return out


# ---------------------------------------------------------------- employment rates

EMPLOYMENT_COLUMNS = ["school_code", "moet_code", "rate", "graduation_year", "source_file", "reviewed_by",
                      "reviewed_on", "note"]


def _file_part(source_file: str) -> str:
    """'Viec4/BVU/BVU.pdf p.12' -> 'Viec4/BVU/BVU.pdf' (a page or table reference may follow the file)."""
    return re.sub(r"\s+(p|tr|trang|bang)\.?\s*\S+$", "", source_file.strip(), flags=re.IGNORECASE)


def load_employment(curated: Path, programs: dict[str, dict], review, manual: Path | None = None) -> list[tuple]:
    """Rows (school_code, moet_code, graduation_year, rate, source_file, reviewed_by, reviewed_on, note) for
    school_employment. A row is kept when its rate is 0-1, its year and source file are given and the school offers
    a program of that ngành; the others go to review. A source file not found under `manual` is listed for review
    but kept (tests use invented paths)."""
    offered = {(p["school_code"], p["moet"]) for p in programs.values() if p.get("moet")}
    df = _read(curated, "school_employment.csv")
    out, seen = [], set()
    for r in df.itertuples():
        school, moet, year = r.school_code.strip().upper(), r.moet_code.strip(), r.graduation_year.strip()
        try:
            rate = float(r.rate)
        except ValueError:
            rate = None
        issue = ("rate is not a number from 0 to 1" if rate is None or not 0 <= rate <= 1 else
                 "graduation_year missing" if not re.fullmatch(r"\d{4}", year) else
                 "source_file missing" if not r.source_file.strip() else
                 "the school offers no program of this ngành" if (school, moet) not in offered else
                 "same school, ngành and year as an earlier row" if (school, moet, year) in seen else None)
        if issue:
            review.add("school_employment_rows", school_code=school, moet_code=moet, rate=r.rate,
                       graduation_year=year, source_file=r.source_file, issue=issue)
            continue
        seen.add((school, moet, year))
        if manual is not None and not (manual / _file_part(r.source_file)).exists():
            review.add("school_employment_rows", school_code=school, moet_code=moet, rate=r.rate,
                       graduation_year=year, source_file=r.source_file, issue="source file not found (row kept)")
        out.append((school, moet, int(year), rate, r.source_file.strip(), r.reviewed_by.strip() or None,
                    r.reviewed_on.strip() or None, r.note.strip() or None))
    return out
