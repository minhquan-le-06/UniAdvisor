"""Coverage report of a built database: what is known, what is missing, what needs a person."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from uniadvisor.paths import ROOT

CITY = {"HN": "Hà Nội", "HCM": "TP.HCM"}

# A program can be placed in the list when it has a MOET code, at least one cutoff (every cutoff is
# compared on score_30, its linear conversion to 30 points), and at least one combination of known exam subjects.
# Mixed-method programs are usable and carry their is_mixed_method mark.
USABLE_SQL = """
SELECT p.id FROM program p
WHERE p.in_scope = 1 AND p.moet_code IS NOT NULL
  AND EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id)
  AND EXISTS (SELECT 1 FROM program_combo pc JOIN combo k ON k.code = pc.combo_code
              WHERE pc.program_id = p.id AND k.subjects_known = 1
                AND NOT EXISTS (SELECT 1 FROM combo_subject cs JOIN subject s ON s.code = cs.subject_code
                                WHERE cs.combo_code = k.code AND s.is_exam = 0))
"""


def _pct(n: int, d: int) -> str:
    return f"{n} ({100 * n / d:.1f}%)" if d else f"{n}"


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def compute(conn: sqlite3.Connection) -> dict:
    q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    years = [int(y) for y in one("SELECT value FROM meta WHERE key = 'cutoff_years'").split(",")]
    y0, y1 = years
    m: dict = {"years": years}

    m["obs_by_source_year"] = q("SELECT source_id, year, COUNT(*) FROM cutoff_observation GROUP BY 1, 2 ORDER BY 1, 2")
    m["cache_by_source"] = q("SELECT source_id, cache_check, COUNT(*) FROM cutoff_observation GROUP BY 1, 2 ORDER BY 1, 2")
    m["status_by_source"] = q("""SELECT source_id, CASE WHEN status LIKE 'excluded:conflict%' THEN 'excluded:conflict_within_source'
                                 ELSE status END s, COUNT(*) FROM cutoff_observation GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    m["skipped_other_years"] = json.loads(one("SELECT value FROM meta WHERE key = 'skipped_rows_other_years'"))

    m["schools_total"] = one("SELECT COUNT(*) FROM school")
    m["schools_in_scope"] = q("SELECT city, COUNT(*) FROM school WHERE in_scope = 1 GROUP BY city ORDER BY city")
    m["schools_out_reason"] = q("SELECT scope_reason, COUNT(*) FROM school WHERE in_scope = 0 GROUP BY 1 ORDER BY 2 DESC")
    m["schools_city_basis"] = q("SELECT city_basis, COUNT(*) FROM school WHERE in_scope = 1 GROUP BY 1 ORDER BY 2 DESC")
    m["schools_with_cutoffs"] = q("""SELECT s.city, COUNT(DISTINCT s.code) FROM school s JOIN program p ON p.school_code = s.code
                                    JOIN cutoff c ON c.program_id = p.id WHERE s.in_scope = 1 AND p.in_scope = 1
                                    GROUP BY s.city ORDER BY s.city""")
    m["schools_military_in_scope"] = one("SELECT COUNT(*) FROM school WHERE in_scope = 1 AND is_military_police = 1")

    m["programs_stored"] = one("SELECT COUNT(*) FROM program")
    m["programs_out_reason"] = q("""SELECT CASE WHEN scope_reason LIKE 'campus_outside%' THEN 'campus_outside_hn_hcm'
                                    ELSE scope_reason END r, COUNT(*) FROM program WHERE in_scope = 0 GROUP BY 1 ORDER BY 2 DESC""")
    ins = "FROM program p WHERE p.in_scope = 1"
    m["programs_in_scope"] = q(f"SELECT p.city, COUNT(*) {ins} GROUP BY p.city ORDER BY p.city")
    total = one(f"SELECT COUNT(*) {ins}")
    m["programs_in_scope_total"] = total
    m["moet"] = q(f"SELECT COALESCE(p.moet_code_basis, 'unknown'), COUNT(*) {ins} GROUP BY 1 ORDER BY 2 DESC")
    m["combos_known"] = one(f"SELECT COUNT(*) {ins} AND EXISTS (SELECT 1 FROM program_combo WHERE program_id = p.id)")
    m["combo_source"] = q(f"""SELECT COALESCE((SELECT MIN(source_id) FROM program_combo WHERE program_id = p.id), 'none'),
                              COUNT(*) {ins} GROUP BY 1 ORDER BY 2 DESC""")
    m["nganh_offered"] = one(f"SELECT COUNT(DISTINCT p.moet_code) {ins}")
    m["nhom_offered"] = one(f"SELECT COUNT(DISTINCT substr(p.moet_code, 1, 5)) {ins}")

    has = lambda y: f"EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id AND c.year = {y})"  # noqa: E731
    by_city = lambda cond: dict(q(f"SELECT p.city, COUNT(*) {ins} AND {cond} GROUP BY p.city"))  # noqa: E731
    m["cutoff_rows"] = [
        ("both years", by_city(f"{has(y0)} AND {has(y1)}")),
        (f"only {y0}", by_city(f"{has(y0)} AND NOT {has(y1)}")),
        (f"only {y1}", by_city(f"NOT {has(y0)} AND {has(y1)}")),
        ("none", by_city(f"NOT {has(y0)} AND NOT {has(y1)}")),
    ]
    m["cutoffs_per_year"] = q(f"""SELECT c.year, COUNT(DISTINCT c.program_id), SUM(c.combo_key != '*'), COUNT(*)
                                  FROM cutoff c JOIN program p ON p.id = c.program_id WHERE p.in_scope = 1
                                  GROUP BY c.year ORDER BY c.year""")
    m["cutoff_source"] = q("""SELECT c.year, c.source_id, COUNT(*) FROM cutoff c JOIN program p ON p.id = c.program_id
                              WHERE p.in_scope = 1 GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    m["scale"] = q("""SELECT c.scale, c.scale_basis, COUNT(DISTINCT c.program_id) FROM cutoff c JOIN program p ON p.id = c.program_id
                      WHERE p.in_scope = 1 GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    m["weights"] = one("SELECT COUNT(*) FROM program_weight")
    m["methods"] = q(f"""SELECT CASE p.is_mixed_method WHEN 1 THEN 'mixed method' WHEN 0 THEN 'exam only'
                                   ELSE 'unknown' END, COALESCE(p.mixed_method_basis, ''), COUNT(*),
                            SUM(EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id)) {ins}
                         GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    m["agreement"] = q("""SELECT source_id, SUM(status = 'agrees'), SUM(status = 'disagrees') FROM cutoff_observation
                          WHERE status IN ('agrees', 'disagrees') GROUP BY 1""")

    m["tuition"] = q(f"""SELECT p.city, SUM(p.tuition_min_vnd IS NOT NULL), SUM(p.tuition_min_vnd IS NULL),
                            SUM(p.tuition_year = {y1}), SUM(p.tuition_year = {y0}) {ins} GROUP BY p.city ORDER BY p.city""")
    m["tuition_with_cutoff"] = one(f"""SELECT COUNT(*) {ins} AND p.tuition_min_vnd IS NOT NULL
                                       AND EXISTS (SELECT 1 FROM cutoff WHERE program_id = p.id)""")
    m["with_cutoff"] = one(f"SELECT COUNT(*) {ins} AND EXISTS (SELECT 1 FROM cutoff WHERE program_id = p.id)")
    usable = conn.execute(f"SELECT p.city, COUNT(*) FROM program p "
                          f"WHERE p.id IN ({USABLE_SQL}) GROUP BY p.city ORDER BY p.city").fetchall()
    m["usable"] = usable
    m["usable_nganh"] = one(f"SELECT COUNT(DISTINCT moet_code) FROM program WHERE id IN ({USABLE_SQL})")
    m["usable_mixed"] = one(f"SELECT COUNT(*) FROM program p WHERE p.id IN ({USABLE_SQL}) AND (p.is_mixed_method = 1 "
                            f"OR EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id AND c.is_mixed_method = 1))")
    m["mixed_cutoffs"] = q("""SELECT c.year, c.scale, SUM(c.is_mixed_method), COUNT(*) FROM cutoff c
                              JOIN program p ON p.id = c.program_id WHERE p.in_scope = 1 GROUP BY 1, 2 ORDER BY 1, 2""")
    # Why in-scope programs are not usable (a program may have several blockers).
    blockers = {
        "no cutoff in either year": "NOT EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id)",
        "MOET ngành code unknown": "p.moet_code IS NULL",
        "no combination of known exam subjects": """NOT EXISTS (SELECT 1 FROM program_combo pc JOIN combo k
              ON k.code = pc.combo_code WHERE pc.program_id = p.id AND k.subjects_known = 1
              AND NOT EXISTS (SELECT 1 FROM combo_subject cs JOIN subject s ON s.code = cs.subject_code
                              WHERE cs.combo_code = k.code AND s.is_exam = 0))""",
    }
    m["blockers"] = [(label, one(f"SELECT COUNT(*) {ins} AND {cond}"),
                      one(f"SELECT COUNT(*) {ins} AND {cond} AND EXISTS (SELECT 1 FROM cutoff c WHERE c.program_id = p.id)"))
                     for label, cond in blockers.items()]
    return m


def render(m: dict, result: dict | None = None) -> str:
    y0, y1 = m["years"]
    cities = ["HN", "HCM"]
    tot = m["programs_in_scope_total"]
    lines = ["# Data coverage report", ""]
    lines += ["## 1. Inputs", "", "Cutoff observations loaded (years " + f"{y0}-{y1}; other years skipped: "
              + ", ".join(f"{k} {v}" for k, v in m["skipped_other_years"].items()) + ").", ""]
    lines.append(_table(["source", "year", "rows"], m["obs_by_source_year"]))
    lines += ["", "Each row checked against the cached page it came from (`pipelines/data/inputs/http_cache`):", ""]
    lines.append(_table(["source", "check", "rows"], m["cache_by_source"]))
    lines += ["", "What happened to each observation:", ""]
    lines.append(_table(["source", "status", "rows"], m["status_by_source"]))

    lines += ["", "## 2. Schools", "", f"{m['schools_total']} schools in the export."]
    lines.append("In scope (university or academy in Hà Nội / TP.HCM): " + ", ".join(
        f"{CITY.get(c, c)} {n}" for c, n in m["schools_in_scope"]) + f"; of which military/police: {m['schools_military_in_scope']}.")
    lines.append("With at least one cutoff: " + ", ".join(f"{CITY.get(c, c)} {n}" for c, n in m["schools_with_cutoffs"])
                 + ".")
    lines += ["", _table(["out of scope because", "schools"], m["schools_out_reason"]), "",
              _table(["in-scope city decided by", "schools"], m["schools_city_basis"])]

    lines += ["", "## 3. Programs", "", f"{m['programs_stored']} programs stored (programs of in-scope schools); "
              f"{tot} in scope: " + ", ".join(f"{CITY.get(c, c)} {n}" for c, n in m["programs_in_scope"]) + ".", ""]
    lines.append(_table(["out of scope because", "programs"], m["programs_out_reason"]))
    lines += ["", "In-scope programs:", ""]
    lines.append(_table(["fact", "programs"], [
        ["MOET ngành code: " + ", ".join(f"{b} {n}" for b, n in m["moet"]), ""],
        ["distinct ngành / nhóm ngành offered", f"{m['nganh_offered']} / {m['nhom_offered']}"],
        ["accepted combinations known", _pct(m["combos_known"], tot)],
        ["combinations taken from: " + ", ".join(f"{b} {n}" for b, n in m["combo_source"]), ""],
    ]))

    lines += ["", "Admission method (2026) of in-scope programs (`program.is_mixed_method`):", "",
              _table(["method", "evidence", "programs", "with a cutoff"], m["methods"])]
    lines += ["", "## 4. Cutoffs (THPT method, in-scope programs)", ""]
    rows = [[label] + [d.get(c, 0) for c in cities] + [_pct(sum(d.values()), tot)] for label, d in m["cutoff_rows"]]
    lines.append(_table(["cutoffs known", "Hà Nội", "TP.HCM", "total"], rows))
    lines += ["", _table(["year", "programs", "per-combination rows", "cutoff rows"], m["cutoffs_per_year"]), "",
              _table(["year", "chosen from", "rows"], m["cutoff_source"]), "",
              "Scale of the cutoffs as published (programs per scale and how it was decided). Every cutoff is also "
              "stored converted linearly to 30 points (`score_30 = score * 30 / scale`):", "",
              _table(["scale", "basis", "programs"], m["scale"]), "",
              "Cutoff rows marked mixed method (`cutoff.is_mixed_method`):", "",
              _table(["year", "scale", "mixed method", "cutoff rows"], m["mixed_cutoffs"]), "",
              f"Doubled subject named in a note (information only): {m['weights']} programs.", "",
              "Lower-priority sites compared with the chosen value:", "",
              _table(["source", "agrees", "disagrees"], m["agreement"])]

    lines += ["", "## 5. Tuition (in-scope programs)", ""]
    lines.append(_table(["city", "known", "unknown", f"from {y1}", f"from {y0}"], [[CITY.get(r[0], r[0]), *r[1:]] for r in m["tuition"]]))
    lines.append("")
    lines.append(f"Among programs with a cutoff: tuition known for {_pct(m['tuition_with_cutoff'], m['with_cutoff'])}.")

    lines += ["", "## 6. Usable for the list", "",
              "In scope, MOET code known, at least one cutoff (compared on 30 points), and at least one combination "
              "of known exam subjects:", ""]
    usable_total = sum(n for _, n in m["usable"])
    lines.append(", ".join(f"{CITY.get(c, c)} {n}" for c, n in m["usable"]) + f"; total {_pct(usable_total, tot)} of "
                 f"in-scope programs, covering {m['usable_nganh']} ngành; {m['usable_mixed']} of them are marked "
                 f"mixed method.")
    lines += ["", "Why the others are not usable (a program can have several reasons):", "",
              _table(["blocker", "in-scope programs", "of which have a cutoff"], m["blockers"])]
    if result:
        review_dir = Path(result["review_dir"]).resolve()
        try:
            review_dir = review_dir.relative_to(ROOT)
        except ValueError:
            pass
        lines += ["", "## 7. For people to review", "", f"Files in `{review_dir.as_posix()}`:", ""]
        lines.append(_table(["file", "rows"], [[f"{k}.csv", v] for k, v in result["review_counts"].items()]))
    return "\n".join(lines) + "\n"


def write_report(db_path: Path, result: dict | None, out: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        text = render(compute(conn), result)
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
