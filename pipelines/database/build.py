"""Build the SQLite database from the raw inputs (pipelines/data/inputs) and the reviewed corrections (pipelines/data/curated).

Run: python -m pipelines.database.build

Every decision the build makes is a named rule, recorded on the row it affects (`*_basis`, `scope_reason`,
`cutoff_observation.status`), and every case a person should look at is written to data/review/.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from uniadvisor import db
from uniadvisor.config import load_data_config
from uniadvisor.data import school_docs, scope, sources
from pipelines.database.cache import HttpCache, check_row
from uniadvisor.data.text import combo_key, fold, name_words, nfc, norm_code, same_program_name
from pipelines.facts.build import build_facts
from pipelines.facts.sheets import insert_sheets
from uniadvisor.paths import BUILD_DIR, COLLECTED_CACHE_DIR, COLLECTED_DIR, CURATED_DIR, DB_PATH, INPUTS_DIR

SOURCES = [
    ("unipilot", "UniPilot export (schools, programs, methods, combinations, 2026)", "export",
     "pipelines/data/inputs/unipilot", None, "No per-row URL; checked by people on a sample"),
    ("moet_tt09_2022", "Danh mục ngành đào tạo trình độ đại học (Thông tư 09/2022/TT-BGDĐT)", "regulation",
     "https://hoatieu.vn/phap-luat/danh-muc-cac-nganh-dao-tao-trinh-do-dai-hoc-215006", None,
     "Every code and name checked against the cached page"),
    ("vnexpress", "VnExpress tra cứu điểm chuẩn", "website", "https://diemthi.vnexpress.net", None,
     "Separate THPT cutoff column; tuition per year"),
    ("tuyensinh247", "Tuyensinh247 điểm chuẩn", "website", "https://diemthi.tuyensinh247.com", None,
     "Method read from the cached page (admission_name)"),
    ("vietnamnet", "VietNamNet tra cứu điểm chuẩn", "website", "https://vietnamnet.vn", None,
     "Mixes methods; THPT rows picked by their note"),
    ("curated", "Reviewed corrections (pipelines/data/curated)", "curated", "pipelines/data/curated", None, None),
    (school_docs.SOURCE_ID, "Schools' own documents (đề án, thông báo) captured by people", "document",
     "pipelines/data/manual_sources", None, "Values entered into pipelines/data/curated/school_*.csv; source_url is the captured file"),
    ("onet_31_0", "O*NET 31.0 Database (USDOL/ETA), CC BY 4.0", "export",
     "https://www.onetcenter.org/database.html", "2026-10-06",
     "This product includes information from the O*NET 31.0 Database by USDOL/ETA, used under CC BY 4.0. "
     "UniAdvisor has modified it (selection, aggregation per ngành, translation). USDOL/ETA has not approved, "
     "endorsed, or tested these modifications."),
    ("cip_crosswalk", "CIP 2020 to O*NET-SOC 2019 crosswalk (O*NET Resource Center)", "export",
     "https://www.onetcenter.org/crosswalks.html", "2026-10-06", None),
]

UNIPILOT_FETCHED = None  # the export carries no retrieval date


@dataclass
class Review:
    """Cases for people, written as CSV files (one per kind)."""
    rows: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))

    def add(self, kind: str, **row):
        self.rows[kind].append(row)

    def write(self, out_dir: Path) -> dict[str, int]:
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob("*.csv"):
            old.unlink()
        counts = {}
        for kind, rows in sorted(self.rows.items()):
            pd.DataFrame(rows).to_csv(out_dir / f"{kind}.csv", index=False, encoding="utf-8-sig")
            counts[kind] = len(rows)
        return counts


def _read_curated(curated: Path, name: str) -> pd.DataFrame:
    path = curated / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig").map(nfc)


# ---------------------------------------------------------------- catalog, subjects, combinations

def insert_moet(conn, moet: pd.DataFrame) -> dict[str, str]:
    """Insert the catalog; return ngành code -> official name."""
    order = {"linh_vuc": 0, "nhom_nganh": 1, "nganh": 2}
    moet = moet.sort_values(by="level", key=lambda s: s.map(order))
    conn.executemany(
        "INSERT INTO moet_major VALUES (?,?,?,?,?,?, 'moet_tt09_2022')",
        [(r.code, r.level, r.name, r.parent or None, r.former_code or None, r.note or None)
         for r in moet.itertuples()],
    )
    nganh = moet[moet["level"] == "nganh"]
    return dict(zip(nganh["code"], nganh["name"]))


def insert_moet_extra(conn, curated: Path, review: Review) -> dict[str, str]:
    """pipelines/data/curated/moet_extra.csv: ngành codes schools use that are not in Thông tư 09/2022 (later additions), with
    the name the school's document prints. A code needs 7 digits,
    a first digit 7 (đại học) and an existing nhóm ngành (its first 5 digits); otherwise it goes to review."""
    rows = _read_curated(curated, "moet_extra.csv")
    groups = {c for (c,) in conn.execute("SELECT code FROM moet_major WHERE level = 'nhom_nganh'")}
    known = {c for (c,) in conn.execute("SELECT code FROM moet_major")}
    out = {}
    for r in rows.itertuples():
        code, name = r.code.strip(), r.name.strip()
        issue = ("not_7_digits_starting_with_7" if not re.fullmatch(r"7\d{6}", code)
                 else "already_in_catalog" if code in known or code in out
                 else "nhom_nganh_unknown" if code[:5] not in groups else None)
        if issue:
            review.add("moet_extra", code=code, name=name, issue=issue, source_file=r.source_file)
            continue
        conn.execute("INSERT INTO moet_major VALUES (?, 'nganh', ?, ?, NULL, ?, ?)",
                     (code, name, code[:5], f"{r.source_file}; {r.note}".strip("; "), school_docs.SOURCE_ID))
        out[code] = name
    return out


def insert_display_names(conn, curated: Path, review: Review) -> int:
    """pipelines/data/curated/display_names.csv -> display_name. Codes outside the catalog go to review, not the database."""
    rows = _read_curated(curated, "display_names.csv")
    known = {c for (c,) in conn.execute("SELECT code FROM moet_major WHERE level IN ('nhom_nganh', 'nganh')")}
    n = 0
    for r in rows.itertuples():
        if r.code not in known:
            review.add("display_names", code=r.code, issue="code_not_in_catalog")
            continue
        aliases = "; ".join(a.strip() for a in r.aliases.split(";") if a.strip())
        conn.execute("INSERT INTO display_name VALUES (?,?,?,?,?, 'curated')",
                     (r.code, r.display_name.strip() or None, aliases or None, r.status, r.source))
        n += 1
    return n


def insert_school_aliases(conn, curated: Path, review: Review) -> int:
    """pipelines/data/curated/school_aliases.csv -> school_alias. Unknown school codes go to review."""
    rows = _read_curated(curated, "school_aliases.csv")
    known = {c for (c,) in conn.execute("SELECT code FROM school")}
    n = 0
    for r in rows.itertuples():
        if r.school_code not in known or not r.alias.strip():
            review.add("school_aliases", school_code=r.school_code, alias=r.alias, issue="unknown_school_or_empty")
            continue
        conn.execute("INSERT INTO school_alias VALUES (?,?,?,?, 'curated')",
                     (r.school_code, r.alias.strip(), r.status, r.source))
        n += 1
    return n


def vnexpress_combo_titles(cache: HttpCache) -> dict[str, set[str]]:
    """Combination code -> subject-name lists shown in VnExpress pages (title attribute)."""
    titles: dict[str, set[str]] = defaultdict(set)
    for url in list(cache._by_url):
        if "loadbenchmark" not in url:
            continue
        try:
            page = json.loads(cache.body(url)).get("html", "")
        except (json.JSONDecodeError, AttributeError):
            continue
        for title, code in re.findall(r'<a title="([^"]*)">\s*([A-Z0-9]+)\s*</a>', page):
            if title.strip():
                titles[code].add(nfc(title))
    return titles


def insert_subjects_and_combos(conn, u, cache: HttpCache, review: Review) -> dict[str, list[str]]:
    subjects = u["subjects"]
    conn.executemany(
        "INSERT INTO subject VALUES (?,?,?, 'unipilot')",
        [(r.code, r.name_vi, 0 if r.code == "NK" else 1) for r in subjects.itertuples()],
    )
    parts = u["combo_parts"].sort_values(["combo_code", "position"])
    combos: dict[str, list[str]] = {}
    for code, grp in parts.groupby("combo_code"):
        combos[code] = list(grp["subject_code"])
        conn.execute("INSERT INTO combo VALUES (?, 1, 'unipilot')", (code,))
        conn.executemany("INSERT INTO combo_subject VALUES (?,?,?)",
                         [(code, int(r.position), r.subject_code) for r in grp.itertuples()])
    # Cross-check against the subject names VnExpress shows for each code; a code the export does not define is
    # defined from VnExpress when every page shows the same three subjects and each maps to an exam subject.
    name_to_code = {fold(r.name_vi): r.code for r in subjects.itertuples()}
    for code, titles in sorted(vnexpress_combo_titles(cache).items()):
        mapped = {tuple(name_to_code.get(fold(t)) for t in title.split(",")) for title in titles}
        if code not in combos:
            usable = {m for m in mapped if None not in m and len(m) == 3 and "NK" not in m}
            if len(mapped) == 1 and len(usable) == 1:
                subjects_ = list(next(iter(usable)))
                combos[code] = subjects_
                conn.execute("INSERT INTO combo VALUES (?, 1, 'vnexpress')", (code,))
                conn.executemany("INSERT INTO combo_subject VALUES (?,?,?)",
                                 [(code, i + 1, s) for i, s in enumerate(subjects_)])
                review.add("combo_definitions", combo=code, issue="defined_from_vnexpress",
                           vnexpress=" | ".join(sorted(titles)), unipilot="")
            else:
                review.add("combo_definitions", combo=code, issue="vnexpress_names_not_all_exam_subjects",
                           vnexpress=" | ".join(sorted(titles)), unipilot="")
            continue
        for title, shown in zip(sorted(titles), [tuple(name_to_code.get(fold(t)) for t in x.split(","))
                                                 for x in sorted(titles)]):
            if None not in shown and sorted(shown) != sorted(combos[code]):
                review.add("combo_definitions", combo=code, issue="subjects_differ", vnexpress=title,
                           unipilot=",".join(combos[code]))
    return combos


def ensure_combo(conn, combos: dict[str, list[str]], code: str):
    if code not in combos:
        combos[code] = []
        conn.execute("INSERT INTO combo VALUES (?, 0, NULL)", (code,))


def apply_program_combos(conn, programs: dict[str, dict], combos: dict[str, list[str]], curated: Path,
                         review: Review):
    """pipelines/data/curated/program_combos.csv sets a program's combinations (they replace what the sites give). An "anchor +
    any 2" rule (`TO+2`) becomes one combination per set of three subjects, so the student's best set is scored like
    any other combination; their codes contain '+' ('Toán+Lí+Hóa')."""
    rows = school_docs.load_program_combos(curated)
    if not rows:
        return
    exam = {c for (c,) in conn.execute("SELECT code FROM subject WHERE is_exam = 1")}
    by_key = defaultdict(list)
    for pid, p in programs.items():
        by_key[(p["school_code"], p["program_code"])].append(pid)
    for (school, code), (tokens, source_file) in rows.items():
        pids = by_key.get((school, code))
        if not pids:
            review.add("program_combos_unmatched", school_code=school, program_code=code, combos=";".join(tokens),
                       source_file=source_file)
            continue
        found = []
        for t in tokens:
            rule = school_docs.ANY_TWO.match(t)
            if rule:
                for c, subjects in school_docs.any_two(rule.group(1), exam).items():
                    if c not in combos:
                        combos[c] = subjects
                        conn.execute("INSERT INTO combo VALUES (?, 1, ?)", (c, school_docs.SOURCE_ID))
                        conn.executemany("INSERT INTO combo_subject VALUES (?,?,?)",
                                         [(c, i + 1, s) for i, s in enumerate(subjects)])
                    found.append(c)
            else:
                found.append(t)
        for pid in pids:
            programs[pid]["combos"] = list(dict.fromkeys(found))
            programs[pid]["combo_source"] = school_docs.SOURCE_ID



def apply_school_combos(conn, u, obs: pd.DataFrame, combos: dict[str, list[str]], curated: Path, review: Review):
    """A school's own definition of a combination code (pipelines/data/curated/school_combos.csv) becomes a code of its own,
    'AH2@KSA', in that school's programs and cutoffs, when it differs from the shared code or the shared code is
    undefined."""
    defs = school_docs.load_combos(curated, set(u["subjects"]["code"]), review)
    if not defs:
        return
    for (school, code), subjects in sorted(defs.items()):
        scoped = f"{code}{school_docs.SCOPED}{school}"
        if sorted(subjects) == sorted(combos.get(code) or []):
            continue
        combos[scoped] = subjects
        conn.execute("INSERT INTO combo VALUES (?, 1, ?)", (scoped, school_docs.SOURCE_ID))
        conn.executemany("INSERT INTO combo_subject VALUES (?,?,?)",
                         [(scoped, i + 1, s) for i, s in enumerate(subjects)])
    obs["combos"] = [school_docs.scope_combos(list(c), s, defs, combos) for c, s in zip(obs["combos"],
                                                                                          obs["school_code"])]
    obs["combo_key"] = obs["combos"].map(combo_key)
    school_of = dict(zip(u["programs"]["id"], u["programs"]["school_code"]))
    pc = u["program_combos"]
    pc["combo_code"] = [school_docs.scope_combos([c], school_of.get(pid, ""), defs, combos)[0]
                        for c, pid in zip(pc["combo_code"], pc["program_id"])]


# ---------------------------------------------------------------- schools

def build_schools(conn, u, curated: Path, cfg, review: Review) -> dict[str, dict]:
    overrides = _read_curated(curated, "school_overrides.csv")
    overrides = {r.school_code: r for r in overrides.itertuples()} if len(overrides) else {}
    schools = {}
    for r in u["schools"].itertuples():
        city, basis = scope.decide_school_city(r.address, r.province)
        reason = None
        if city == "HCM_FORMER":
            if cfg["include_former_provinces_merged_into_hcm"]:
                city = "HCM"
            else:
                city, reason = None, "former_province_merged_into_hcm"
        province_city = scope.province_to_city(r.province)
        if r.id in overrides:
            o = overrides[r.id]
            city, basis = (o.city or None), "override"
            reason = o.reason or None
        if reason is None and city is None:
            reason = "city_not_hn_hcm"
        if reason is None and r.school_type == "college":
            reason = "not_university"
        in_scope = reason is None
        if r.id in overrides and overrides[r.id].in_scope in ("0", "1"):
            in_scope = overrides[r.id].in_scope == "1"
            reason = None if in_scope else (overrides[r.id].reason or "override")
        schools[r.id] = {"city": city, "in_scope": in_scope, "name": r.name_vi}
        conn.execute(
            "INSERT INTO school VALUES (?,?,?,?,?,?,?,?, 'unipilot')",
            (r.id, r.name_vi, r.school_type or None, 1 if r.is_military_or_police == "True" else 0, city, basis,
             int(in_scope), None if in_scope else reason),
        )
        # Cases for people: city decided without an address, address and province field disagree,
        # or a name that suggests a campus elsewhere.
        campus, place = scope.campus_place(r.name_vi)
        flags = []
        if basis == "province_field" and (city or province_city):
            flags.append("city_from_province_field_only")
        if basis.startswith("address") and province_city and city not in (province_city, None) :
            flags.append("address_and_province_field_disagree")
        if basis == "address_other_province" and province_city:
            flags.append("province_field_says_" + province_city + "_address_elsewhere")
        if campus in ("outside", "unclear") and in_scope:
            flags.append(f"name_suggests_campus:{place or 'unclear'}")
        region = scope.strip_accents(r.name_vi)
        if in_scope and (("phia nam" in region or "mien nam" in region) and city == "HN"
                         or ("phia bac" in region or "mien bac" in region) and city == "HCM"):
            flags.append("name_region_contradicts_city")
        if reason == "former_province_merged_into_hcm":
            flags.append("former_province_merged_into_hcm")
        if flags and r.school_type != "college":
            review.add("school_city", school_code=r.id, name=r.name_vi, decided_city=city or "",
                       in_scope=int(in_scope), basis=basis, province_field=r.province, address=r.address,
                       flags=";".join(flags))
    return schools


# ---------------------------------------------------------------- observations

def load_observations(inputs: Path, cache: HttpCache, cfg, collected: Path | None = None,
                      curated: Path | None = None) -> tuple[pd.DataFrame, dict]:
    frames = [sources.load_vnexpress(inputs, collected), sources.load_tuyensinh247(inputs, collected),
              sources.load_vietnamnet(inputs, collected)]
    if curated is not None:
        frames.append(school_docs.load_cutoffs(curated))
    obs = pd.concat(frames, ignore_index=True)
    obs["doc_method"] = obs["doc_method"].fillna("") if "doc_method" in obs else ""
    skipped = obs[~obs["year"].isin(cfg["cutoff_years"])].groupby("source_id").size().to_dict()
    obs = obs[obs["year"].isin(cfg["cutoff_years"])].reset_index(drop=True)
    checks, methods = [], []
    for r in obs.itertuples():
        status, page_row = check_row(cache, r.url, r.program_code, r.score)
        checks.append(status)
        if r.source_id == "vnexpress":
            methods.append("thpt")                      # the THPT column of the page
        elif r.source_id == school_docs.SOURCE_ID:
            methods.append("thpt" if r.doc_method in ("thpt", "thpt_mixed") else "other")
        elif r.source_id == "tuyensinh247":
            if page_row is None:
                methods.append("unknown")
            elif "thpt" in fold(page_row.method) and not page_row.converted:
                methods.append("thpt")
            else:
                methods.append("other")
        else:
            methods.append(sources.vietnamnet_method(r.note))
    obs["cache_check"] = checks
    obs["method"] = methods
    obs["combo_key"] = obs["combos"].map(combo_key)
    obs["program_id"] = None
    obs["status"] = None
    return obs, skipped


# ---------------------------------------------------------------- programs

def _apply_aliases(obs: pd.DataFrame, curated: Path):
    """pipelines/data/curated/program_code_aliases.csv (school_code, old_code, new_code, reviewed_by, reviewed_on): a site's old
    program code read as the new one. Optional: no file while there are no rows."""
    aliases = _read_curated(curated, "program_code_aliases.csv")
    for a in aliases.itertuples() if len(aliases) else []:
        mask = (obs["school_code"] == a.school_code) & (obs["program_code"] == norm_code(a.old_code))
        obs.loc[mask, "program_code"] = norm_code(a.new_code)


def name_key(name: str) -> str:
    """A program or catalog name reduced for exact comparison: brackets, numbering, a short 'CNTT:'-style prefix and a
    trailing '- Chương trình ...' removed; '&' read as 'và'; spaces around hyphens normalised; lowercase."""
    core = re.sub(r"\([^)]*\)|^\s*\(?\d+\)\s*|^[^:]{1,12}:\s*", " ", nfc(name))
    core = re.sub(r"\s*-\s*(chương trình|ct|clc|ctđt).*$", "", core, flags=re.I)
    core = re.sub(r"\s*&\s*", " và ", core)
    core = re.sub(r"\s*-\s*", " - ", core)
    return fold(core)


def suggest_moet(name: str, by_name: dict[str, str]) -> str:
    """A catalog code whose official name equals the program name (compared with name_key), or ''."""
    return by_name.get(name_key(name), "")


def _link_renamed_codes(obs: pd.DataFrame, programs: dict[str, dict], cfg, review: Review):
    """A code seen only before the latest year, at a school whose latest-year program has exactly the same name and no
    cutoff of its own in that earlier year, is the same program under a new code: its rows move to that program."""
    latest = cfg["latest_program_year"]
    linked = obs[obs["program_id"].notna()]
    years_of = linked.groupby("program_id")["year"].apply(set).to_dict()
    current: dict[tuple[str, str], list[str]] = defaultdict(list)
    for pid, p in programs.items():
        if "unipilot" in p["sources"] or latest in years_of.get(pid, set()):
            current[(p["school_code"], name_key(p["name"]))].append(pid)
    for old_pid, p in list(programs.items()):
        years = years_of.get(old_pid, set())
        if "unipilot" in p["sources"] or not years or latest in years:
            continue
        targets = [t for t in current.get((p["school_code"], name_key(p["name"])), [])
                   if t != old_pid and not (years & years_of.get(t, set()))]
        if len(targets) != 1:
            continue
        obs.loc[obs["program_id"] == old_pid, "program_id"] = targets[0]
        del programs[old_pid]
        review.add("renamed_code_links", school_code=p["school_code"], old_code=p["program_code"],
                   new_program_id=targets[0], name=p["name"], years=";".join(map(str, sorted(years))))


def link_key(code: str) -> str:
    """Program codes compared without punctuation: '7310102_01' = '731010201', '7420101KD' = '7420101_KD'."""
    return re.sub(r"[^0-9A-Z]", "", norm_code(code))


def build_programs(u, obs: pd.DataFrame, schools, catalog: dict[str, str], combos, conn, curated: Path, cfg,
                   review: Review) -> dict[str, dict]:
    latest = cfg["latest_program_year"]
    thpt_ids = sources.unipilot_thpt_programs(u)
    thpt_label = sources.unipilot_thpt_method_label(u)
    pc = u["program_combos"]
    up_combos = pc[pc["method_label"] == thpt_label].groupby("program_id")["combo_code"].apply(list).to_dict()
    methods = u["methods"].groupby("program_id")["method_label"].apply(set).to_dict()
    # Combinations of combined exam methods, for programs that have no exam-only method.
    combined_combos = (pc[pc["method_label"].map(sources.is_combined_exam_method)]
                       .groupby("program_id")["combo_code"].apply(lambda s: list(dict.fromkeys(s))).to_dict())

    programs: dict[str, dict] = {}
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in u["programs"].itertuples():
        if not schools.get(r.school_code, {}).get("in_scope"):
            continue
        pid = r.program_id
        programs[pid] = {
            "school_code": r.school_code, "program_code": r.program_code, "name": r.name_vi,
            "raw_moet": r.major_code, "sources": {"unipilot"}, "years": {int(r.year)},
            "thpt_unipilot": r.id in thpt_ids,
            "combos": up_combos.get(r.id) or combined_combos.get(r.id, []), "combo_source": "unipilot",
            "methods": methods.get(r.id, set()),
        }
        by_key[(r.school_code, link_key(r.norm_code))].append(pid)

    # Link observations to programs; programs only the cutoff sites know are added.
    _apply_aliases(obs, curated)
    for (school, code), idx in obs.groupby(["school_code", "program_code"]).groups.items():
        rows = obs.loc[idx]
        if not schools.get(school, {}).get("in_scope"):
            obs.loc[idx, "status"] = "excluded:school_out_of_scope"
            continue
        candidates = by_key.get((school, link_key(code)), [])
        if not candidates and "_" in code:
            # Sites sometimes prefix the school's code with the MOET code: '7310101_401' for export code '401'.
            suffix = by_key.get((school, link_key(code.rsplit("_", 1)[1])), [])
            if len(suffix) == 1:
                candidates = suffix
        if not candidates and "_" in code:
            # Or suffix the export's shared code: 'NTHCN18_KHDL' for one of the programs coded 'NTHCN18'.
            # Linked only on an exact program name; unmatched rows become programs of their own.
            prefix = by_key.get((school, link_key(code.split("_", 1)[0])), [])
            unmatched = []
            for i, r in rows.iterrows():
                named = [p for p in prefix if fold(programs[p]["name"]) == fold(r.program_name)]
                if len(named) == 1:
                    obs.at[i, "program_id"] = named[0]
                else:
                    unmatched.append(i)
            if not unmatched:
                continue
            idx, rows = unmatched, obs.loc[unmatched]
        if len(candidates) > 1:
            # Several programs share the code (e.g. split quotas): link a row only by exact name.
            for i, r in rows.iterrows():
                named = [p for p in candidates if fold(programs[p]["name"]) == fold(r.program_name)]
                if len(named) == 1:
                    obs.at[i, "program_id"] = named[0]
                else:
                    obs.at[i, "status"] = "excluded:ambiguous_program"
                    review.add("unlinked_observations", source=r.source_id, school_code=school, program_code=code,
                               year=r.year, program_name=r.program_name, score=r.score,
                               candidates=";".join(candidates), url=r.url)
            continue
        if candidates:
            pid = candidates[0]
        else:
            pid = f"{school}:{code}"
            first = rows.sort_values("year", ascending=False).iloc[0]
            programs[pid] = {
                "school_code": school, "program_code": code, "name": first.program_name, "raw_moet": "",
                "sources": set(), "years": set(), "thpt_unipilot": False, "combos": [], "combo_source": None,
            }
        obs.loc[idx, "program_id"] = pid

    _link_renamed_codes(obs, programs, cfg, review)
    priority = cfg["cutoff_source_priority"]
    for pid, grp in obs[obs["program_id"].notna()].groupby("program_id"):
        p = programs[pid]
        p["sources"].update(grp["source_id"])
        p["years"].update(grp["year"])
        p["thpt_cutoff"] = bool((grp["method"] == "thpt").any())
        if not p["combos"]:
            # Combinations from the most preferred site's latest year.
            for year in sorted(grp["year"].unique(), reverse=True):
                for src in priority:
                    sel = grp[(grp["year"] == year) & (grp["source_id"] == src) & (grp["method"] == "thpt")]
                    found = list(dict.fromkeys(c for cs in sel["combos"] for c in cs))
                    if found:
                        p["combos"], p["combo_source"] = found, src
                        break
                if p["combos"]:
                    break
    apply_program_combos(conn, programs, combos, curated, review)

    overrides = _read_curated(curated, "program_overrides.csv")
    overrides = {r.program_id: r for r in overrides.itertuples()} if len(overrides) else {}
    catalog_by_name = {name_key(n): c for c, n in catalog.items()}
    for pid, p in programs.items():
        # MOET ngành code: the export's major code, else a program code starting with a catalog code, else a
        # program code containing exactly one 7-digit run that is a catalog code ('F7340101').
        moet, basis = None, None
        embedded = [c for c in re.findall(r"(?<!\d)\d{7}(?!\d)", p["program_code"]) if c in catalog]
        if p["raw_moet"] in catalog:
            moet, basis = p["raw_moet"], "unipilot"
        elif p["program_code"][:7] in catalog:
            moet, basis = p["program_code"][:7], "program_code_prefix"
        elif len(set(embedded)) == 1:
            moet, basis = embedded[0], "program_code_contains"
        elif suggest_moet(p["name"], catalog_by_name):
            # The program's name equals an official ngành name; applied but marked unreviewed and listed for a
            # person to confirm (2026-10-06: exact name matches first, official documents later).
            moet, basis = suggest_moet(p["name"], catalog_by_name), "name_match_unreviewed"
        if pid in overrides and overrides[pid].moet_code:
            moet, basis = overrides[pid].moet_code, "override"
        p["moet"], p["moet_basis"] = moet, basis

        reason = None
        campus, place = scope.campus_place(p["name"])
        combined = {m for m in p.get("methods", ()) if sources.is_combined_exam_method(m)}
        if latest not in p["years"]:
            reason = f"not_seen_in_{latest}"
        elif not p["thpt_unipilot"] and combined and all(sources.is_talent_method(m) for m in combined):
            reason = "talent_test_required"
        elif not p["thpt_unipilot"] and not combined and not p.get("thpt_cutoff"):
            # No exam-based method at all. Programs whose only exam-based method is combined stay in scope,
            # marked is_mixed_method = 1.
            reason = "no_thpt_method"
        elif campus == "outside":
            reason = f"campus_outside_hn_hcm:{place}"
        elif p["combos"] and all(
            combos.get(c) and any(s == "NK" for s in combos[c]) for c in p["combos"]
        ):
            reason = "talent_test_required"
        if pid in overrides and overrides[pid].in_scope in ("0", "1"):
            reason = None if overrides[pid].in_scope == "1" else (overrides[pid].reason or "override")
        p["in_scope"], p["reason"] = reason is None, reason
        p["city"] = place if campus == "inside" else schools[p["school_code"]]["city"]
        if pid in overrides and getattr(overrides[pid], "city", ""):
            p["city"] = overrides[pid].city

        if p["in_scope"] and campus == "unclear":
            review.add("program_campus", program_id=pid, name=p["name"], issue="campus_words_without_place")
        if p["in_scope"] and basis == "name_match_unreviewed":
            review.add("program_moet_code", program_id=pid, name=p["name"], issue="name_match_unreviewed",
                       code_seen="", sources=";".join(sorted(p["sources"])), name_match_suggestion=moet,
                       suggestion_name=catalog.get(moet, ""), moet_code="", reviewed_by="")
        if p["in_scope"] and moet is None:
            # The catalog is Thông tư 09/2022 only. A MOET-style code outside it
            # (a later addition) is listed so a person can map the program to a Thông tư 09/2022 ngành.
            styled = re.match(r"7\d{6}", p["raw_moet"] or "") or re.match(r"7\d{6}", p["program_code"])
            suggestion = suggest_moet(p["name"], catalog_by_name)
            review.add("program_moet_code", program_id=pid, name=p["name"],
                       issue="code_not_in_tt09_2022" if styled else "no_code",
                       code_seen=styled.group(0) if styled else "", sources=";".join(sorted(p["sources"])),
                       name_match_suggestion=suggestion, suggestion_name=catalog.get(suggestion, ""),
                       moet_code="", reviewed_by="")
        if reason == f"not_seen_in_{latest}":
            review.add("programs_not_in_latest_year", program_id=pid, name=p["name"],
                       years=";".join(map(str, sorted(p["years"]))), sources=";".join(sorted(p["sources"])))

    # The same program listed under two school codes (e.g. a main school also listing its campus's programs):
    # same school-specific code (not a 7-digit MOET-style code, which many schools share), same name, same city.
    seen: dict[tuple, list[str]] = defaultdict(list)
    for pid, p in programs.items():
        code = norm_code(p["program_code"])
        if p["in_scope"] and not re.fullmatch(r"7\d{6}", code):
            seen[(code, fold(p["name"]), p["city"])].append(pid)
    for (code, _, city), pids in seen.items():
        if len({programs[x]["school_code"] for x in pids}) > 1:
            review.add("program_duplicates", program_code=code, name=programs[pids[0]]["name"], city=city,
                       program_ids=";".join(sorted(pids)))
    return programs


# ---------------------------------------------------------------- cutoffs

def _choose_from_source(rows: pd.DataFrame) -> tuple[list[tuple[str, float, int]], str | None]:
    """Cutoffs of one source for one program-year: [(combo_key, score, row index)] or a conflict reason."""
    distinct = rows.drop_duplicates(["combo_key", "score"])
    if distinct["score"].nunique() == 1:
        # One value, however the rows list combinations (some sites repeat it with and without them): one cutoff.
        return [("*", distinct.iloc[0].score, distinct.index[0])], None
    keys = list(distinct["combo_key"])
    sets = [set(k.split(";")) if k else set() for k in keys]
    if any(not s for s in sets):
        return [], "rows_without_combinations"
    if len(set(keys)) < len(keys):
        return [], "different_scores_same_combinations"
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            if sets[i] & sets[j]:
                return [], "overlapping_combinations"
    return [(k, r.score, i) for k, (i, r) in zip(keys, distinct.iterrows())], None


def _scale(rows: pd.DataFrame, chosen_scores: list[float], max40: float) -> tuple[int, str]:
    """Scale of a program-year's cutoffs, from every usable THPT observation of it (any site)."""
    stated = {sources.stated_scale(n) for n in rows["note"]} - {None}
    scores = [s for s in rows["score"] if s is not None] + chosen_scores
    if 100 in stated:
        return 100, "stated_in_note"
    if any(s > max40 for s in scores):
        return 100, "score_above_40_assumed_100"
    if any(30 < s <= max40 for s in scores):
        return 40, "score_above_30"
    if 40 in stated or any(sources.doubled_subject(n) for n in rows["note"]):
        return 40, "stated_in_note"
    if 30 in stated:
        return 30, "stated_in_note"
    return 30, "assumed_max_score_le_30"


def to_30(score: float, scale: int) -> float:
    """Linear conversion to the 30-point scale."""
    return round(score * 30 / scale, 4)


def mixed_method_programs(programs: dict[str, dict], review: Review) -> dict[str, str]:
    """Programs whose cutoff in the export's year mixes the exam score with other criteria -> rule name.

    The sites show such cutoffs in their THPT column, often on a 30-point scale (e.g. QST: "THPT + Học bạ"), so the
    score alone does not reveal them. Evidence is the export's list of admission methods:
    - the program lists a combined method using the exam score and no exam-only method; or
    - the program is not in the export, and its school lists no exam-only method for any program but does list a
      combined one.
    """
    by_school: dict[str, list[dict]] = defaultdict(list)
    for p in programs.values():
        if "unipilot" in p["sources"]:
            by_school[p["school_code"]].append(p)
    no_exam_only_schools = {
        s for s, ps in by_school.items()
        if not any(p["thpt_unipilot"] for p in ps)
        and any(sources.is_combined_exam_method(m) for p in ps for m in p.get("methods", ()))
    }
    out = {}
    for pid, p in programs.items():
        combined = any(sources.is_combined_exam_method(m) for m in p.get("methods", ()))
        if "unipilot" in p["sources"]:
            if not p["thpt_unipilot"] and combined:
                out[pid] = "export_lists_only_combined_methods"
            elif not p["thpt_unipilot"] and p.get("thpt_cutoff") and p["in_scope"]:
                review.add("cutoff_without_exam_method_in_export", program_id=pid, name=p["name"],
                           export_methods="; ".join(sorted(p["methods"])))
        elif p["school_code"] in no_exam_only_schools:
            out[pid] = "school_lists_no_exam_only_method"
    return out


def set_mixed_method(conn, programs, scales: dict[str, dict], mixed: dict[str, str], latest: int):
    """program.is_mixed_method for the latest year, with its evidence."""
    for pid, p in programs.items():
        if pid in mixed:
            flag, basis = 1, mixed[pid]
        elif scales.get(pid, {}).get(latest, (None, False))[1]:
            flag, basis = 1, f"cutoff_{latest}_on_100_point_scale"
        elif p["thpt_unipilot"]:
            flag, basis = 0, "export_lists_exam_only_method"
        elif p.get("thpt_cutoff") and "unipilot" not in p["sources"]:
            flag, basis = 0, "site_thpt_column"
        else:
            flag, basis = None, None
        conn.execute("UPDATE program SET is_mixed_method = ?, mixed_method_basis = ? WHERE id = ?",
                     (flag, basis, pid))


def load_kept_apart(curated: Path) -> frozenset[str]:
    """Site-only programs a reviewer would not merge into the export program of the same name
    (site_programs_kept_apart.csv: program_id, export_program, reason, reviewed_by, reviewed_on). Optional: no file
    while there are no rows."""
    rows = _read_curated(curated, "site_programs_kept_apart.csv")
    return frozenset(rows["program_id"]) if len(rows) else frozenset()


def load_same_program(curated: Path) -> set[tuple[str, int]]:
    """(program id, year) pairs a person confirmed as the same program despite a different name in that year."""
    rows = _read_curated(curated, "same_program.csv")
    return {(r.program_id, int(r.year)) for r in rows.itertuples()} if len(rows) else set()


def reused_code(name_then: str, name_now: str, moet_now: str | None, catalog_by_name: dict[str, str]) -> bool:
    """Whether an earlier year's row under a program's code is another program, in this order:
    1. one name's words contain the other's (the same name, a shorter form, a specialisation in brackets): same;
    2. the earlier name is exactly an official ngành name and the program has a ngành code: the catalog decides.
       Another ngành ("Đông phương học" under a code that is Đông Nam Á học in 2026) is another program; the same
       ngành ("Ngôn ngữ Anh" for "Tiếng Anh thương mại", 7220201) is the same program;
    3. otherwise the names' word overlap decides (text.same_program_name)."""
    then_words, now_words = name_words(name_then), name_words(name_now)
    if then_words <= now_words or now_words <= then_words:
        return False
    then_code = suggest_moet(name_then, catalog_by_name)
    if then_code and moet_now:
        return then_code != moet_now
    return not same_program_name(name_then, name_now)


def merge_site_duplicates(obs: pd.DataFrame, programs, review: Review, tol: float = 0.01,
                          keep_apart: frozenset[str] = frozenset()) -> int:
    """Programs only the cutoff sites know that are an export program under another code format ('7340101' for the
    export's '7340101DKK', '527' for 'KT527', 'B7310101' for '7310101'): same school, the same name words including
    variant markers (CLC and standard are different programs), the same ngành code when both are known, exactly one
    such export program, and no source giving the two different values for the same year. Their rows move to the export
    program and the site program goes out of scope, so one program never fills two wishes. Site programs in
    `keep_apart` (pipelines/data/curated/site_programs_kept_apart.csv: a reviewer was unsure they are the same program) are not
    merged. Returns the number merged."""
    export: dict[tuple[str, frozenset], list[str]] = defaultdict(list)
    for pid, p in programs.items():
        if p["in_scope"] and "unipilot" in p["sources"]:
            export[(p["school_code"], frozenset(name_words(p["name"], keep_variant=True)))].append(pid)
    linked = obs[obs["program_id"].notna() & obs["score"].notna()]
    values = linked.groupby(["program_id", "year", "source_id"])["score"].apply(set).to_dict()
    n = 0
    for pid, p in sorted(programs.items()):
        if not p["in_scope"] or "unipilot" in p["sources"] or pid in keep_apart:
            continue
        words = frozenset(name_words(p["name"], keep_variant=True))
        targets = [t for t in export.get((p["school_code"], words), [])
                   if not (p["moet"] and programs[t]["moet"] and p["moet"] != programs[t]["moet"])]
        if not words or len(targets) != 1:
            continue
        target = targets[0]
        clash = [(y, src) for (q, y, src), mine in values.items() if q == pid and (target, y, src) in values
                 and not any(abs(a - b) <= tol for a in mine for b in values[(target, y, src)])]
        if clash:
            review.add("site_duplicates_not_merged", program_id=pid, name=p["name"], export_program=target,
                       name_there=programs[target]["name"], differing=";".join(f"{y} {src}" for y, src in clash))
            continue
        obs.loc[obs["program_id"] == pid, "program_id"] = target
        programs[target]["sources"] |= p["sources"]
        p["in_scope"], p["reason"] = False, f"duplicate_of:{target}"
        review.add("site_duplicates_merged", program_id=pid, name=p["name"], merged_into=target,
                   name_there=programs[target]["name"], sources=";".join(sorted(p["sources"])))
        n += 1
    return n


def _outside_school_fields(programs, review: Review):
    """For people: programs only the sites know whose lĩnh vực (first 3 digits of the ngành code) the school teaches in
    none of its export programs, e.g. a 'Giáo dục Mầm non' row on NEU's VnExpress page; likely a site error."""
    taught: dict[str, set[str]] = defaultdict(set)
    for p in programs.values():
        if p["in_scope"] and "unipilot" in p["sources"] and p.get("moet"):
            taught[p["school_code"]].add(p["moet"][:3])
    for pid, p in sorted(programs.items()):
        if (p["in_scope"] and "unipilot" not in p["sources"] and p.get("moet") and p["school_code"] in taught
                and p["moet"][:3] not in taught[p["school_code"]]):
            review.add("program_outside_school_fields", program_id=pid, name=p["name"], moet_code=p["moet"],
                       sources=";".join(sorted(p["sources"])), school_fields=";".join(sorted(taught[p["school_code"]])))


def exclude_reused_codes(obs: pd.DataFrame, programs, cfg, review: Review, catalog: dict[str, str],
                         confirmed: set[tuple[str, int]] | None = None) -> int:
    """Earlier-year rows that belong to another program: the school reused the code (reused_code). A cutoff jump does
    not tell them apart (many reused codes move by less than 0.5 points). Wrongly dropping a year costs little, since
    one year counts as both; keeping another program's cutoff gives a wrong level. Returns the number of
    rows excluded."""
    confirmed = confirmed or set()
    catalog_by_name = {name_key(n): c for c, n in catalog.items()}
    latest = cfg["latest_program_year"]
    # Where a name lives now: (school, name words) -> in-scope programs. A row of another program moves to the one
    # program at the school that has exactly its name now (QHX05's 2025 "Đông phương học" -> QHX06), if that program
    # has no row of its own for that year and source.
    by_name: dict[tuple[str, frozenset], list[str]] = defaultdict(list)
    for pid, p in programs.items():
        if p["in_scope"]:
            by_name[(p["school_code"], frozenset(name_words(p["name"])))].append(pid)
    pending = obs["status"].isna() & obs["program_id"].notna() & (obs["year"] < latest)
    def elsewhere(r) -> bool:
        """The row's exact name is another program's at the school now, and neither name contains the other (QHX17's
        2025 "Quản trị văn phòng" is QHX19 now, although it half-matches QHX17's "Quản trị dịch vụ du lịch và lữ
        hành"). A variant's row ("Sư phạm Vật lí (học bằng tiếng Anh)" for "Sư phạm Vật lí (dạy Toán bằng tiếng
        Anh)") contains or is contained in its own name, so it stays even though the plain program has the name."""
        words = frozenset(name_words(r.program_name))
        own = frozenset(name_words(programs[r.program_id]["name"]))
        return not (words <= own or own <= words) and any(
            t != r.program_id for t in by_name.get((programs[r.program_id]["school_code"], words), []))

    reused = [i for i, r in obs[pending].iterrows()
              if (r.program_id, int(r.year)) not in confirmed
              and (reused_code(r.program_name, programs[r.program_id]["name"], programs[r.program_id].get("moet"),
                               catalog_by_name) or elsewhere(r))]
    # A program's own rows block a move onto it, except rows that are leaving it themselves (in a shift every
    # program's earlier row belongs to another code).
    staying = obs[obs["program_id"].notna()].drop(index=reused)
    has_row = set(zip(staying["program_id"], staying["year"], staying["source_id"]))
    n, seen = 0, set()
    for i in reused:
        r = obs.loc[i]
        p = programs[r.program_id]
        current = p["name"]
        targets = [t for t in by_name.get((p["school_code"], frozenset(name_words(r.program_name))), [])
                   if t != r.program_id]
        if len(targets) == 1 and (targets[0], r.year, r.source_id) not in has_row:
            obs.at[i, "program_id"] = targets[0]
            if (r.program_id, r.year, r.source_id, "relinked") not in seen:
                seen.add((r.program_id, r.year, r.source_id, "relinked"))
                review.add("cutoff_relinked", program_id=r.program_id, year=r.year, source=r.source_id,
                           name_in_source=r.program_name, moved_to=targets[0], name_there=programs[targets[0]]["name"],
                           score=r.raw_score, url=r.url)
            continue
        obs.at[i, "status"] = "excluded:name_differs_from_latest_year"
        n += 1
        if (r.program_id, r.year, r.source_id) not in seen:
            seen.add((r.program_id, r.year, r.source_id))
            review.add("cutoff_name_changed", program_id=r.program_id, year=r.year, source=r.source_id,
                       name_in_source=r.program_name, current_name=current, score=r.raw_score, url=r.url,
                       same_program="", reviewed_by="")
    return n


def build_cutoffs(conn, obs: pd.DataFrame, programs, cfg, review: Review,
                  school_scales: dict[tuple[str, int], list] | None = None,
                  same_program: set[tuple[str, int]] | None = None,
                  catalog: dict[str, str] | None = None) -> tuple[dict[str, dict], dict[str, str]]:
    school_scales = school_scales or {}
    mixed = mixed_method_programs(programs, review)
    priority = cfg["cutoff_source_priority"]
    tol = cfg["cutoff_agreement_tolerance"]
    per_program: dict[str, dict] = defaultdict(dict)

    pending = obs["status"].isna()
    obs.loc[pending & obs["program_id"].notna() & ~obs["program_id"].map(
        lambda p: bool(p) and programs.get(p, {}).get("in_scope", False)), "status"] = "excluded:program_out_of_scope"
    pending = obs["status"].isna()
    obs.loc[pending & (obs["method"] == "other"), "status"] = "excluded:not_thpt_method"
    obs.loc[pending & (obs["method"] == "unknown"), "status"] = "excluded:method_unknown"
    pending = obs["status"].isna()
    obs.loc[pending & (obs["cache_check"] == "mismatch"), "status"] = "excluded:cache_mismatch"
    obs.loc[pending & obs["score"].isna(), "status"] = "excluded:no_score"
    exclude_reused_codes(obs, programs, cfg, review, catalog or {}, same_program)
    for i, r in obs[obs["cache_check"] == "mismatch"].iterrows():
        review.add("cache_mismatches", source=r.source_id, school_code=r.school_code, program_code=r.program_code,
                   year=r.year, score=r.raw_score, url=r.url)

    usable = obs[obs["status"].isna()]
    for (pid, year), grp in usable.groupby(["program_id", "year"]):
        picks: dict[str, list] = {}
        for src in priority:
            rows = grp[grp["source_id"] == src]
            if rows.empty:
                continue
            picked, conflict = _choose_from_source(rows)
            if conflict:
                obs.loc[rows.index, "status"] = f"excluded:conflict_within_source:{conflict}"
                review.add("cutoff_conflicts", program_id=pid, year=year, source=src, issue=conflict,
                           rows=" | ".join(f"{r.combo_key or '-'}={r.raw_score}" for r in rows.itertuples()),
                           url=rows.iloc[0].url)
            else:
                picks[src] = picked
        if not picks:
            continue
        chosen_src = next(iter(picks))      # most preferred source with a usable value
        chosen = picks[chosen_src]
        # Refinement: when the preferred site gives one value and a later site gives per-combination cutoffs,
        # one of which equals that value, the per-combination cutoffs are the more specific fact.
        if len(chosen) == 1 and chosen[0][0] == "*":
            for src, picked in list(picks.items())[1:]:
                if len(picked) > 1 and any(abs(s - chosen[0][1]) <= tol for _, s, _ in picked):
                    chosen, chosen_src = picked, src
                    break
        obs.loc[grp.index[grp["source_id"] == chosen_src], "status"] = "unused"
        obs.loc[[i for _, _, i in chosen], "status"] = "chosen"
        scores = [s for _, s, _ in chosen]
        for i, r in grp.iterrows():
            if obs.at[i, "status"] is None or pd.isna(obs.at[i, "status"]):
                agrees = any(abs(r.score - s) <= tol for s in scores)
                obs.at[i, "status"] = "agrees" if agrees else "disagrees"
                if not agrees:
                    review.add("cutoff_disagreements", program_id=pid, year=year, chosen_source=chosen_src,
                               chosen=";".join(f"{k}={s}" for k, s, _ in chosen), other_source=r.source_id,
                               other=f"{r.combo_key or '-'}={r.raw_score}", other_note=r.note, other_url=r.url)
        scale, scale_basis = _scale(grp, scores, cfg["scale_40_max"])
        stated = school_docs.stated_scale(school_scales, pid, year)
        if stated and scale_basis in ("assumed_max_score_le_30", "score_above_30") and max(scores) <= stated:
            scale, scale_basis = stated, "school_document_states_scale"
        # Mixed method: a 100-point score combines methods; for the export's year, so does a program whose export
        # entry lists only combined methods (the export does not describe earlier years).
        mixed_basis = mixed.get(pid) if int(year) == cfg["latest_program_year"] else None
        if scale == 100:
            mixed_basis = "score_on_100_point_scale" + (f";{mixed_basis}" if mixed_basis else "")
        if chosen_src == school_docs.SOURCE_ID and (obs.loc[[i for _, _, i in chosen], "doc_method"]
                                                    == "thpt_mixed").any():
            mixed_basis = "school_document_states_combined_method" + (f";{mixed_basis}" if mixed_basis else "")
        for key, score, i in chosen:
            conn.execute("INSERT INTO cutoff VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (pid, int(year), key, float(score), scale, scale_basis, to_30(float(score), scale),
                          int(mixed_basis is not None), mixed_basis, chosen_src, obs.at[i, "url"]))
        per_program[pid][int(year)] = (scale, mixed_basis is not None)
    return per_program, mixed


def build_weights(conn, obs: pd.DataFrame, programs) -> dict[str, str]:
    """Doubled subjects stated in VietNamNet notes on THPT rows (latest year wins)."""
    found: dict[str, tuple[int, str, str]] = {}
    sel = obs[(obs["source_id"] == "vietnamnet") & (obs["method"] == "thpt") & obs["program_id"].notna()]
    for r in sel.sort_values("year").itertuples():
        subject = sources.doubled_subject(r.note)
        if subject and programs[r.program_id]["in_scope"]:
            found[r.program_id] = (r.year, subject, r.note)
    for pid, (year, subject, note) in found.items():
        conn.execute("INSERT INTO program_weight VALUES (?,?,2.0,'vietnamnet',?)", (pid, subject, f"{year}: {note}"))
    return {pid: s for pid, (_, s, _) in found.items()}


# ---------------------------------------------------------------- tuition

_MONEY = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+")


def parse_tuition(raw: str, lo: int, hi: int) -> tuple[int, int] | None:
    text = nfc(raw).strip()
    if not text or text in {"--", "-"}:
        return None
    if re.search(r"[a-zA-ZÀ-ỹ]", text):          # words (per credit, 'đang cập nhật') -> not a yearly amount
        return None
    values = [int(v.replace(".", "")) for v in _MONEY.findall(text)]
    if not 1 <= len(values) <= 2 or not all(lo <= v <= hi for v in values):
        return None
    return min(values), max(values)


def build_tuition(obs: pd.DataFrame, cfg, review: Review) -> dict[str, tuple]:
    out = {}
    sel = obs[(obs["source_id"] == "vnexpress") & obs["program_id"].notna() & (obs["tuition_raw"] != "")]
    for pid, grp in sel.groupby("program_id"):
        for year in sorted(grp["year"].unique(), reverse=True):
            rows = grp[grp["year"] == year]
            parsed = [parse_tuition(t, cfg["tuition_min_vnd"], cfg["tuition_max_vnd"]) for t in rows["tuition_raw"]]
            for raw, val in zip(rows["tuition_raw"], parsed):
                if val is None:
                    review.add("tuition_unparsed", program_id=pid, year=year, tuition_raw=raw)
            parsed = [v for v in parsed if v]
            if parsed:
                raws = " | ".join(dict.fromkeys(rows["tuition_raw"]))
                out[pid] = (min(v[0] for v in parsed), max(v[1] for v in parsed), int(year), raws, "vnexpress", None)
                break
    return out


# ---------------------------------------------------------------- main

def build(inputs: Path = INPUTS_DIR, curated: Path = CURATED_DIR, out_db: Path = DB_PATH,
          review_dir: Path | None = None, cfg: dict | None = None, collected: Path | None = None,
          collected_cache: Path | None = None) -> dict:
    """`collected` / `collected_cache`: our own collectors' CSVs and HTTP cache (pipelines/data/collected, pipelines/data/cache/http),
    read in addition to the old inputs. Tests leave them out."""
    cfg = cfg or load_data_config()
    review_dir = review_dir or out_db.parent / "review"
    review = Review()
    cache = HttpCache(inputs / "http_cache", collected_cache)
    conn = db.create(out_db)
    conn.executemany("INSERT INTO source VALUES (?,?,?,?,?,?)", SOURCES)

    catalog = insert_moet(conn, sources.load_moet(inputs))
    catalog.update(insert_moet_extra(conn, curated, review))
    insert_display_names(conn, curated, review)
    u = sources.load_unipilot(inputs)
    combos = insert_subjects_and_combos(conn, u, cache, review)
    schools = build_schools(conn, u, curated, cfg, review)
    insert_school_aliases(conn, curated, review)
    obs, skipped_years = load_observations(inputs, cache, cfg, collected, curated)
    apply_school_combos(conn, u, obs, combos, curated, review)
    programs = build_programs(u, obs, schools, catalog, combos, conn, curated, cfg, review)
    merge_site_duplicates(obs, programs, review, keep_apart=load_kept_apart(curated))
    _outside_school_fields(programs, review)
    tuition = build_tuition(obs, cfg, review)
    # A school's own document wins over VnExpress when it is for the same or a later year.
    for pid, doc in school_docs.load_tuition(curated, programs, review).items():
        if pid not in tuition or (doc[2] or 0) >= (tuition[pid][2] or 0):
            tuition[pid] = doc

    for pid, p in programs.items():
        for c in p["combos"]:
            ensure_combo(conn, combos, c)
        t = tuition.get(pid)
        conn.execute(
            """INSERT INTO program (id, school_code, program_code, name, city, moet_code, moet_code_basis, score_scale,
                   scale_basis, in_scope, scope_reason, tuition_min_vnd, tuition_max_vnd, tuition_year, tuition_raw,
                   tuition_source_id, tuition_basis, source_ids)
               VALUES (?,?,?,?,?,?,?,NULL,'no_cutoff',?,?,?,?,?,?,?,?,?)""",
            (pid, p["school_code"], p["program_code"], p["name"], p["city"], p["moet"], p["moet_basis"], int(p["in_scope"]),
             p["reason"], *(t[:4] if t else (None, None, None, None)), t[4] if t else None, t[5] if t else None,
             ";".join(sorted(p["sources"]))),
        )
        conn.executemany("INSERT INTO program_combo VALUES (?,?,?)",
                         [(pid, c, p["combo_source"]) for c in p["combos"]])
        if p["in_scope"]:
            undefined = [c for c in p["combos"] if not combos.get(c)]
            if undefined:
                review.add("program_combos_undefined", program_id=pid, name=p["name"],
                           undefined=";".join(undefined), all_combos=";".join(p["combos"]))

    conn.executemany(
        "INSERT INTO school_employment VALUES (?,?,?,?,?,?,?,?,?)",
        [(*row, school_docs.SOURCE_ID) for row in
         school_docs.load_employment(curated, programs, review, curated.parent / "manual_sources")])

    scales, mixed = build_cutoffs(conn, obs, programs, cfg, review, school_docs.load_scales(curated, review),
                                  load_same_program(curated), catalog)
    set_mixed_method(conn, programs, scales, mixed, cfg["latest_program_year"])
    build_weights(conn, obs, programs)      # kept as information; cutoffs are compared on score_30
    latest_year = max(cfg["cutoff_years"])
    for pid, by_year in scales.items():
        year = max(by_year)
        scale = by_year[year][0]
        conn.execute("UPDATE program SET score_scale = ?, scale_basis = ? WHERE id = ?",
                     (scale, f"cutoff_{year}_on_{scale}", pid))
    # Cases for people: a 100-point scale inferred from the score alone.
    for pid, name, year in conn.execute(
        """SELECT DISTINCT p.id, p.name, c.year FROM program p JOIN cutoff c ON c.program_id = p.id
           WHERE p.in_scope = 1 AND c.scale_basis = 'score_above_40_assumed_100' ORDER BY p.id, c.year"""
    ).fetchall():
        review.add("program_scale", program_id=pid, name=name, scale=100, latest_cutoff_year=year,
                   issue="score_above_40_assumed_100_point_scale")
    # Cases for people: the two years disagree a lot on 30 points, or the scale changes between years. Levels compare
    # the student with both years, so a wrong scale or value in one year changes the level.
    jump = cfg["year_jump_review"]
    for pid, name, s0, s1, sc0, sc1, m0, m1 in conn.execute(
        """SELECT p.id, p.name, a.s30, b.s30, a.scale, b.scale, a.mixed, b.mixed
           FROM program p
           JOIN (SELECT program_id, MAX(score_30) s30, MAX(scale) scale, MAX(is_mixed_method) mixed FROM cutoff
                 WHERE year = ? GROUP BY program_id) a ON a.program_id = p.id
           JOIN (SELECT program_id, MAX(score_30) s30, MAX(scale) scale, MAX(is_mixed_method) mixed FROM cutoff
                 WHERE year = ? GROUP BY program_id) b ON b.program_id = p.id
           WHERE p.in_scope = 1 ORDER BY p.id""", tuple(cfg["cutoff_years"])
    ).fetchall():
        issues = []
        if abs(s0 - s1) >= jump:
            issues.append(f"converted_cutoffs_differ_by_{abs(s0 - s1):.2f}")
        if sc0 != sc1:
            issues.append(f"scale_{sc0}_to_{sc1}")
        if issues:
            review.add("cutoff_year_changes", program_id=pid, name=name, **{
                f"cutoff_30_{cfg['cutoff_years'][0]}": s0, f"cutoff_30_{cfg['cutoff_years'][1]}": s1,
                f"scale_{cfg['cutoff_years'][0]}": sc0, f"scale_{cfg['cutoff_years'][1]}": sc1,
                f"mixed_{cfg['cutoff_years'][0]}": m0, f"mixed_{cfg['cutoff_years'][1]}": m1},
                issue=";".join(issues))
    # Schools that have 40-point programs: their other programs were assumed to be on 30 points.
    forty = conn.execute("""SELECT DISTINCT p.school_code FROM program p JOIN cutoff c ON c.program_id = p.id
                            WHERE c.scale = 40""").fetchall()
    for (school,) in forty:
        for pid, name in conn.execute(
            """SELECT DISTINCT p.id, p.name FROM program p JOIN cutoff c ON c.program_id = p.id
               WHERE p.school_code = ? AND p.in_scope = 1 AND c.scale_basis = 'assumed_max_score_le_30'""",
            (school,),
        ):
            review.add("program_scale", program_id=pid, name=name, scale="30", latest_cutoff_year=latest_year,
                       issue="assumed_30_at_school_with_40_point_programs")

    conn.executemany(
        """INSERT INTO cutoff_observation (source_id, school_code, program_code, program_id, year, combos, score,
               raw_score, note, status, cache_check, source_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r.source_id, r.school_code, r.program_code, r.program_id, int(r.year), ";".join(r.combos),
          None if pd.isna(r.score) else float(r.score), r.raw_score, r.note or None,
          r.status if isinstance(r.status, str) else "unused", r.cache_check, r.url) for r in obs.itertuples()],
    )

    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany("INSERT INTO meta VALUES (?,?)", [
        ("built_at", built_at), ("target_admission_year", str(cfg["target_admission_year"])),
        ("cutoff_years", ",".join(map(str, cfg["cutoff_years"]))),
        ("skipped_rows_other_years", json.dumps(skipped_years)),
    ])
    conn.commit()
    _sample_for_people(conn, review)
    _name_vs_moet(conn, review)
    if (inputs / "onet_31_0").exists():
        facts = build_facts(conn, inputs, curated, review)
        facts["fact_sheets"] = insert_sheets(conn, curated / "fact_sheets")
        conn.execute("INSERT INTO meta VALUES ('facts', ?)", (json.dumps(facts),))
        conn.commit()
    _mixed_method_list(conn, review, cfg["cutoff_years"], programs)
    counts = review.write(review_dir)
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        raise RuntimeError(f"Foreign key violations: {fk[:5]}")
    conn.close()
    return {"db": out_db, "review_dir": review_dir, "review_counts": counts, "skipped_years": skipped_years,
            "cache_size": len(cache)}


# Words that say nothing about the subject studied (program variants, places, joining words); ignored when comparing a
# program's name with its MOET ngành name.
_NAME_NOISE = {"va", "cac", "cua", "trong", "nganh", "chuyen", "chuong", "trinh", "hoc", "tien", "tang", "cuong",
               "tieng", "anh", "chat", "luong", "cao", "dac", "biet", "he", "co", "so", "ha", "noi", "hcm", "tp",
               "quoc", "te", "lien", "ket", "dinh", "huong"}


def _name_vs_moet(conn: sqlite3.Connection, review: Review):
    """In-scope programs whose name shares no word with their MOET ngành name. Mostly specialisations (Trí tuệ nhân
    tạo under Khoa học máy tính), but also wrong codes in the export (a 'Luật Kinh tế' coded as Tâm lý học): a wrong
    code puts the program in the wrong student's list."""
    def words(text):
        return set(re.findall(r"[a-z0-9]+", scope.strip_accents(text))) - _NAME_NOISE

    for pid, name, code, moet_name, basis in conn.execute(
        """SELECT p.id, p.name, p.moet_code, m.name, p.moet_code_basis FROM program p
           JOIN moet_major m ON m.code = p.moet_code WHERE p.in_scope = 1 ORDER BY p.id"""
    ).fetchall():
        a, b = words(name), words(moet_name)
        if a and b and not a & b:
            review.add("program_name_vs_moet", program_id=pid, name=name, moet_code=code, moet_name=moet_name,
                       moet_code_basis=basis)


def _sample_for_people(conn: sqlite3.Connection, review: Review, n: int = 50, seed: int = 2027):
    """A fixed random sample of in-scope programs with every fact and its source, for a person to check."""
    rows = conn.execute(
        """SELECT p.id, s.name, s.city, p.name, p.moet_code, m.name, p.score_scale,
                  (SELECT group_concat(combo_code, ';') FROM program_combo WHERE program_id = p.id),
                  (SELECT group_concat(year || ':' || combo_key || '=' || score || ' [' || source_id || ']', ' | ')
                     FROM cutoff WHERE program_id = p.id),
                  p.tuition_min_vnd, p.tuition_max_vnd, p.tuition_year,
                  (SELECT group_concat(DISTINCT source_url) FROM cutoff WHERE program_id = p.id)
           FROM program p JOIN school s ON s.code = p.school_code LEFT JOIN moet_major m ON m.code = p.moet_code
           WHERE p.in_scope = 1 ORDER BY p.id"""
    ).fetchall()
    sample = pd.DataFrame(rows).sample(n=min(n, len(rows)), random_state=seed) if rows else pd.DataFrame()
    cols = ["program_id", "school", "city", "program_name", "moet_code", "moet_name", "scale", "combos", "cutoffs",
            "tuition_min", "tuition_max", "tuition_year", "urls"]
    for r in sample.itertuples(index=False):
        review.add("people_check_sample", **dict(zip(cols, r)), checked_by="", result="", comment="")


def _mixed_method_list(conn: sqlite3.Connection, review: Review, years: list[int], programs: dict[str, dict]):
    """In-scope programs marked mixed method (program or any cutoff): one row per program, with the evidence, each
    year's cutoff as published and converted to 30 points, the site's own note and the page URL."""
    progs = conn.execute(
        """SELECT p.id, p.school_code, s.name, p.city, p.name, p.moet_code, m.name, p.is_mixed_method,
                  p.mixed_method_basis
           FROM program p JOIN school s ON s.code = p.school_code LEFT JOIN moet_major m ON m.code = p.moet_code
           WHERE p.in_scope = 1 AND (p.is_mixed_method = 1 OR EXISTS
                 (SELECT 1 FROM cutoff c WHERE c.program_id = p.id AND c.is_mixed_method = 1))
           ORDER BY p.id"""
    ).fetchall()
    for pid, school, school_name, city, name, moet, moet_name, flag, basis in progs:
        row = {"program_id": pid, "school_code": school, "school": school_name, "city": city or "",
               "program_name": name, "moet_code": moet or "", "moet_name": moet_name or "",
               "is_mixed_method_2026": "" if flag is None else flag, "mixed_method_basis_2026": basis or "",
               "export_methods_2026": "; ".join(sorted(programs[pid].get("methods", ())))}
        for year in years:
            cut = conn.execute(
                """SELECT combo_key, score, scale, score_30, is_mixed_method, mixed_method_basis, source_url
                   FROM cutoff WHERE program_id = ? AND year = ? ORDER BY combo_key""", (pid, year)).fetchall()
            label = lambda k, v: f"{k}={v:g}" if k != "*" else f"{v:g}"  # noqa: E731
            row[f"cutoff_{year}"] = " | ".join(label(c[0], c[1]) for c in cut)
            row[f"scale_{year}"] = ";".join(sorted({str(c[2]) for c in cut}))
            row[f"cutoff_{year}_on_30"] = " | ".join(label(c[0], round(c[3], 2)) for c in cut)
            row[f"mixed_{year}"] = ";".join(sorted({str(c[4]) for c in cut}))
            row[f"mixed_basis_{year}"] = ";".join(sorted({c[5] for c in cut if c[5]}))
            row[f"url_{year}"] = cut[0][6] if cut else ""
        notes = conn.execute(
            "SELECT DISTINCT note FROM cutoff_observation WHERE program_id = ? AND status = 'chosen' "
            "AND note IS NOT NULL AND note != '--' AND year IN "
            "(SELECT year FROM cutoff WHERE program_id = ? AND is_mixed_method = 1)", (pid, pid)).fetchall()
        row["site_note"] = " | ".join(n for (n,) in notes)
        review.add("mixed_method_programs", **row)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)
    result = build(out_db=args.out, collected=COLLECTED_DIR, collected_cache=COLLECTED_CACHE_DIR)
    from pipelines.database.coverage import write_report
    report = write_report(args.out, result, BUILD_DIR / "coverage.md" if args.out == DB_PATH
                          else args.out.with_name("coverage.md"))
    print(report)


if __name__ == "__main__":
    main()
