"""Load what the list rules need from the database."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from uniadvisor.plan.models import Cutoff, ProgramFacts


def load_programs(conn: sqlite3.Connection) -> list[ProgramFacts]:
    """In-scope programs with a MOET code, taught in Hà Nội or TP.HCM.

    Combinations are kept only when their three subjects are known exam subjects (no talent test).
    """
    combos: dict[str, dict[str, tuple[str, ...]]] = defaultdict(dict)
    rows = conn.execute(
        """SELECT pc.program_id, pc.combo_code, group_concat(cs.subject_code, ',')
           FROM program_combo pc JOIN combo k ON k.code = pc.combo_code AND k.subjects_known = 1
           JOIN combo_subject cs ON cs.combo_code = k.code
           WHERE NOT EXISTS (SELECT 1 FROM combo_subject x JOIN subject s ON s.code = x.subject_code
                             WHERE x.combo_code = k.code AND s.is_exam = 0)
           GROUP BY pc.program_id, pc.combo_code"""
    ).fetchall()
    for pid, combo, subjects in rows:
        combos[pid][combo] = tuple(sorted(subjects.split(",")))

    cutoffs: dict[str, list[Cutoff]] = defaultdict(list)
    for pid, year, key, score, scale, score_30, mixed in conn.execute(
        "SELECT program_id, year, combo_key, score, scale, score_30, is_mixed_method FROM cutoff "
        "ORDER BY program_id, year, combo_key"
    ):
        cutoffs[pid].append(Cutoff(year, None if key == "*" else frozenset(key.split(";")), score_30, score, scale,
                                   bool(mixed)))

    # Values another source gives for a chosen cutoff's program and year that do not agree with it (build: status
    # 'disagrees'), shown so the student knows the published figures differ.
    disputes: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for pid, year, source, raw in conn.execute(
        """SELECT DISTINCT program_id, year, source_id, raw_score FROM cutoff_observation
           WHERE status = 'disagrees' ORDER BY program_id, year, source_id, raw_score"""
    ):
        disputes[pid].append((year, source, raw))

    # The share of the school's graduates of the ngành who have a job, latest graduation year (school_employment;
    # absent in a database built before the table existed).
    employment: dict[tuple[str, str], tuple[float, int]] = {}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'school_employment'").fetchone():
        for school, moet, year, rate in conn.execute(
            "SELECT school_code, moet_code, graduation_year, rate FROM school_employment ORDER BY graduation_year"
        ):
            employment[(school, moet)] = (rate, year)

    programs = []
    for (pid, school, school_name, name, moet, city, tmin, tmax, tyear, mixed, tbasis) in conn.execute(
        """SELECT p.id, p.school_code, s.name, p.name, p.moet_code, p.city, p.tuition_min_vnd, p.tuition_max_vnd,
                  p.tuition_year, p.is_mixed_method, p.tuition_basis
           FROM program p JOIN school s ON s.code = p.school_code
           WHERE p.in_scope = 1 AND p.moet_code IS NOT NULL AND p.city IN ('HN', 'HCM')
           ORDER BY p.id"""
    ):
        programs.append(ProgramFacts(pid, school, school_name, name, moet, city, dict(combos.get(pid, {})),
                                     tuple(cutoffs.get(pid, [])), tmax, tmin, tyear, bool(mixed), tbasis,
                                     tuple(disputes.get(pid, [])), employment.get((school, moet))))
    return programs


def load_nganh_parents(conn: sqlite3.Connection) -> dict[str, str]:
    """ngành code -> nhóm ngành code (MOET catalog)."""
    return dict(conn.execute("SELECT code, parent_code FROM moet_major WHERE level = 'nganh'").fetchall())
