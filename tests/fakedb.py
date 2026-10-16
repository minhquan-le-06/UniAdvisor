"""A small, hand-written fake database with the real schema, for testing rules without real data.

Schools and programs are invented; the cases are chosen to exercise every rule: two years of cutoffs,
one year, none, per-combination cutoffs, a 40-point scale, a mixed-method program with a 100-point cutoff
(all cutoffs also stored converted to 30 points, as the build does), ministry-floor
programs (medicine, other health, teacher training), known and unknown tuition, both cities, and an
out-of-scope school. MOET codes and names are real (Thông tư 09/2022) so floors can be tested.
"""

from __future__ import annotations

from pathlib import Path

from uniadvisor import db

SOURCES = [
    ("fake", "Fake test data", "curated", None, None, "invented for tests"),
    ("moet_tt09_2022", "MOET catalog", "regulation", None, None, None),
    ("tuyensinh247", "Tuyensinh247 (fake rows)", "website", None, None, None),
]
# source, program, year, raw score, status: another site's value for a chosen cutoff
OBSERVATIONS = [
    ("tuyensinh247", "HNA:CS1", 2026, "24.5", "disagrees"),
    ("tuyensinh247", "HNA:CS1", 2025, "25.0", "agrees"),
]

MOET = [
    ("714", "linh_vuc", "Khoa học giáo dục và đào tạo giáo viên", None),
    ("71402", "nhom_nganh", "Đào tạo giáo viên", "714"),
    ("7140209", "nganh", "Sư phạm Toán học", "71402"),
    ("722", "linh_vuc", "Nhân văn", None),
    ("72202", "nhom_nganh", "Ngôn ngữ, văn học và văn hóa nước ngoài", "722"),
    ("7220201", "nganh", "Ngôn ngữ Anh", "72202"),
    ("748", "linh_vuc", "Máy tính và công nghệ thông tin", None),
    ("74801", "nhom_nganh", "Máy tính", "748"),
    ("7480101", "nganh", "Khoa học máy tính", "74801"),
    ("7480103", "nganh", "Kỹ thuật phần mềm", "74801"),
    ("7480107", "nganh", "Trí tuệ nhân tạo", "74801"),
    ("74802", "nhom_nganh", "Công nghệ thông tin", "748"),
    ("7480201", "nganh", "Công nghệ thông tin", "74802"),
    ("772", "linh_vuc", "Sức khoẻ", None),
    ("77201", "nhom_nganh", "Y học", "772"),
    ("7720101", "nganh", "Y khoa", "77201"),
    ("77203", "nhom_nganh", "Điều dưỡng - hộ sinh", "772"),
    ("7720301", "nganh", "Điều dưỡng", "77203"),
]

# code, display name (None: official), aliases, status, origin
DISPLAY = [
    ("74801", "Khoa học máy tính, Trí tuệ nhân tạo (AI), Kỹ thuật phần mềm", "KHMT; AI; computer science", "draft",
     "group_labels_old_repo"),
    ("74802", "Công nghệ thông tin, An toàn thông tin", "IT", "draft", "group_labels_old_repo"),
    ("77201", "Y khoa (bác sĩ), Y học cổ truyền", "bác sĩ", "reviewed", "group_labels_old_repo"),
    ("7480107", None, "AI; artificial intelligence", "draft", "agent_draft"),
]

SUBJECTS = [("TO", "Toán"), ("LI", "Vật lí"), ("HO", "Hóa học"), ("SI", "Sinh học"),
            ("VA", "Ngữ văn"), ("N1", "Tiếng Anh")]

COMBOS = {"A00": ["TO", "LI", "HO"], "A01": ["TO", "LI", "N1"], "B00": ["TO", "HO", "SI"],
          "D01": ["VA", "TO", "N1"]}

# code, name, type, military/police, city, in_scope, scope_reason
SCHOOLS = [
    ("HNA", "Trường Đại học Giả Hà Nội", "university", 0, "HN", 1, None),
    ("HCB", "Trường Đại học Giả TP.HCM", "university", 0, "HCM", 1, None),
    ("MIL", "Học viện Giả Quân sự", "academy", 1, "HN", 1, None),
    ("OUT", "Trường Đại học Giả Đà Nẵng", "university", 0, None, 0, "city_not_hn_hcm"),
]

SCHOOL_ALIASES = [("HNA", "FHN"), ("HCB", "Giả Sài Gòn")]

# id, school, code, name, moet, latest cutoff scale, tuition (min, max, year) or None, combos
PROGRAMS = [
    ("HNA:CS1", "HNA", "CS1", "Khoa học máy tính", "7480101", 30, (30_000_000, 35_000_000, 2026), ["A00", "A01"]),
    ("HNA:IT2", "HNA", "IT2", "Công nghệ thông tin", "7480201", 30, None, ["A00", "D01"]),
    ("HNA:AI", "HNA", "AI", "Trí tuệ nhân tạo", "7480107", 30, (40_000_000, 40_000_000, 2026), ["A00", "A01"]),
    ("HNA:SE", "HNA", "SE", "Kỹ thuật phần mềm", "7480103", 30, (25_000_000, 28_000_000, 2025), ["A00", "A01", "D01"]),
    ("HCB:YK", "HCB", "YK", "Y khoa", "7720101", 30, (80_000_000, 80_000_000, 2026), ["B00"]),
    ("HCB:DD", "HCB", "DD", "Điều dưỡng", "7720301", 30, (30_000_000, 30_000_000, 2026), ["B00"]),
    ("HCB:SPT", "HCB", "SPT", "Sư phạm Toán học", "7140209", 30, None, ["A00", "A01"]),
    ("HCB:NNA", "HCB", "NNA", "Ngôn ngữ Anh", "7220201", 40, (32_000_000, 32_000_000, 2026), ["D01"]),
    ("HCB:KTPM", "HCB", "KTPM", "Kỹ thuật phần mềm", "7480103", 100, None, ["A00", "A01"]),   # mixed method
    ("MIL:CS", "MIL", "CS", "Khoa học máy tính (hệ quân sự)", "7480101", 30, None, ["A00", "A01"]),
    ("OUT:CS", "OUT", "CS", "Khoa học máy tính", "7480101", 30, None, ["A00"]),
]

# program, year, combo_key, score, scale, mixed method
CUTOFFS = [
    ("HNA:CS1", 2025, "*", 25.0, 30, 0), ("HNA:CS1", 2026, "*", 24.2, 30, 0),
    ("HNA:IT2", 2025, "*", 23.5, 30, 0),
    ("HNA:IT2", 2026, "A00", 23.0, 30, 0), ("HNA:IT2", 2026, "D01", 24.0, 30, 0),
    ("HNA:SE", 2026, "*", 22.0, 30, 0),                       # one year only
    ("HCB:YK", 2025, "*", 27.0, 30, 0), ("HCB:YK", 2026, "*", 26.5, 30, 0),
    ("HCB:DD", 2025, "*", 19.0, 30, 0), ("HCB:DD", 2026, "*", 18.0, 30, 0),
    ("HCB:SPT", 2025, "*", 26.0, 30, 0), ("HCB:SPT", 2026, "*", 25.0, 30, 0),
    ("HCB:NNA", 2025, "*", 34.0, 40, 0), ("HCB:NNA", 2026, "*", 33.5, 40, 0),    # 25.5 / 25.125 on 30
    ("HCB:KTPM", 2025, "*", 24.5, 30, 0), ("HCB:KTPM", 2026, "*", 80.0, 100, 1),  # 2026: 24.0 on 30
    ("MIL:CS", 2025, "*", 27.5, 30, 0), ("MIL:CS", 2026, "*", 27.9, 30, 0),
    ("OUT:CS", 2026, "*", 20.0, 30, 0),
    # HNA:AI has no cutoff (new program)
]

WEIGHTS = [("HCB:NNA", "N1", 2.0)]


def build_fake_db(path: Path | str):
    conn = db.create(path)
    conn.executemany("INSERT INTO source VALUES (?,?,?,?,?,?)", SOURCES)
    conn.executemany(
        "INSERT INTO moet_major (code, level, name, parent_code, source_id) VALUES (?,?,?,?, 'moet_tt09_2022')", MOET
    )
    conn.executemany("INSERT INTO display_name (code, display_name, aliases, status, origin, source_id) "
                     "VALUES (?,?,?,?,?, 'fake')", DISPLAY)
    conn.executemany("INSERT INTO subject VALUES (?,?,1,'fake')", SUBJECTS)
    for code, subjects in COMBOS.items():
        conn.execute("INSERT INTO combo VALUES (?,1,'fake')", (code,))
        conn.executemany(
            "INSERT INTO combo_subject VALUES (?,?,?)", [(code, i + 1, s) for i, s in enumerate(subjects)]
        )
    conn.executemany(
        "INSERT INTO school VALUES (?,?,?,?,?,'fake',?,?,'fake')", SCHOOLS
    )
    conn.executemany("INSERT INTO school_alias (school_code, alias, status, origin, source_id) "
                     "VALUES (?,?,'draft','agent_draft','fake')", SCHOOL_ALIASES)
    for pid, school, code, name, moet, scale, tuition, combos in PROGRAMS:
        tmin, tmax, tyear = tuition or (None, None, None)
        in_scope = 0 if school == "OUT" else 1
        city = {"HNA": "HN", "HCB": "HCM", "MIL": "HN"}.get(school)
        conn.execute(
            """INSERT INTO program (id, school_code, program_code, name, city, moet_code, moet_code_basis,
                   is_mixed_method, mixed_method_basis, score_scale, scale_basis, in_scope, scope_reason,
                   tuition_min_vnd, tuition_max_vnd, tuition_year, tuition_source_id, tuition_basis, source_ids)
               VALUES (?,?,?,?,?,?,'fake',?,'fake',?,'fake',?,?,?,?,?,?,NULL,'fake')""",
            (pid, school, code, name, city, moet, int(scale == 100), scale, in_scope,
             None if in_scope else "school_out_of_scope",
             tmin, tmax, tyear, "fake" if tuition else None),
        )
        conn.executemany("INSERT INTO program_combo VALUES (?,?,'fake')", [(pid, c) for c in combos])
    conn.executemany(
        "INSERT INTO cutoff VALUES (?,?,?,?,?,'fake',?,?,?,'fake',NULL)",
        [(pid, year, key, score, scale, round(score * 30 / scale, 4), mixed, "fake" if mixed else None)
         for pid, year, key, score, scale, mixed in CUTOFFS],
    )
    conn.executemany(
        "INSERT INTO program_weight VALUES (?,?,?,'fake',NULL)", WEIGHTS
    )
    conn.executemany(
        """INSERT INTO cutoff_observation (source_id, school_code, program_code, program_id, year, combos, score,
               raw_score, note, status, cache_check, source_url) VALUES (?,?,?,?,?,'A00',?,?,NULL,?,'verified',NULL)""",
        [(src, pid.split(":")[0], pid.split(":")[1], pid, year, float(raw), raw, status)
         for src, pid, year, raw, status in OBSERVATIONS],
    )
    add_facts(conn)
    conn.commit()
    return conn


# Facts (invented, shaped like O*NET): two computing ngành and medicine.
OCCUPATIONS = [("15-1252.00", "Software Developers", "Kỹ sư phát triển phần mềm"),
               ("15-1221.00", "Computer and Information Research Scientists", "Nhà nghiên cứu khoa học máy tính"),
               ("15-1211.00", "Computer Systems Analysts", "Chuyên viên phân tích hệ thống"),
               ("29-1216.00", "General Internal Medicine Physicians", "Bác sĩ nội khoa")]
NGANH_OCC = [("7480101", "15-1221.00", 0.5, 0.5, 1), ("7480101", "15-1252.00", 0.5, 0.5, 2),
             ("7480103", "15-1252.00", 1.0, 1.0, 1), ("7480201", "15-1211.00", 0.6, 0.6, 1),
             ("7480201", "15-1252.00", 0.4, 0.4, 2), ("7720101", "29-1216.00", 1.0, 1.0, 1)]
KNOWLEDGE = {"7480101": {"Computers and Electronics": 4.8, "Mathematics": 4.5, "English Language": 3.5},
             "7480103": {"Computers and Electronics": 4.9, "Mathematics": 3.9, "English Language": 3.4},
             "7480201": {"Computers and Electronics": 4.6, "Mathematics": 3.5, "English Language": 3.8},
             "7720101": {"Medicine and Dentistry": 4.9, "Biology": 4.2, "Psychology": 3.6}}
INTERESTS = {"7480101": {"Investigative": 6.5, "Realistic": 4.0, "Conventional": 3.5},
             "7480103": {"Investigative": 6.0, "Realistic": 4.2, "Conventional": 4.0},
             "7480201": {"Investigative": 5.5, "Conventional": 5.0, "Realistic": 4.0},
             "7720101": {"Investigative": 6.0, "Social": 5.5, "Realistic": 4.0}}
# Work Context (element id -> value): sitting and indoor offices for computing, disease exposure for medicine.
WORK_CONTEXT = {"7480101": {"4.C.2.d.1.a": 4.6, "4.C.2.c.1.b": 1.1, "4.C.2.a.1.a": 4.9},
                "7480103": {"4.C.2.d.1.a": 4.7, "4.C.2.c.1.b": 1.0, "4.C.2.a.1.a": 4.9},
                "7480201": {"4.C.2.d.1.a": 4.4, "4.C.2.c.1.b": 1.2, "4.C.2.a.1.a": 4.8},
                "7720101": {"4.C.2.d.1.a": 2.9, "4.C.2.c.1.b": 4.8, "4.C.2.a.1.a": 4.6}}
CLOSE = [("7480101", "7480201", 1, 0.8), ("7480101", "7480103", 2, 0.7), ("7480101", "7480107", 3, 0.6),
         ("7480201", "7480101", 1, 0.8), ("7480201", "7480103", 2, 0.75), ("7480201", "7480107", 3, 0.5),
         ("7720101", "7720301", 1, 0.5)]
NAMES = [("knowledge", "Computers and Electronics", "Máy tính và điện tử", None),
         ("knowledge", "Mathematics", "Toán học", None), ("knowledge", "English Language", "Ngôn ngữ và viết", None),
         ("knowledge", "Medicine and Dentistry", "Y khoa và nha khoa", None), ("knowledge", "Biology", "Sinh học", None),
         ("knowledge", "Psychology", "Tâm lý học", None),
         ("riasec", "Investigative", "Nghiên cứu", "thích tìm hiểu, phân tích"),
         ("riasec", "Realistic", "Kỹ thuật (thực tế)", "thích máy móc, công cụ"),
         ("riasec", "Conventional", "Nghiệp vụ (văn phòng)", "thích quy trình rõ ràng"),
         ("riasec", "Social", "Xã hội", "thích giúp đỡ con người")]


def add_facts(conn):
    conn.execute("INSERT INTO source VALUES ('onet_31_0', 'O*NET (fake)', 'export', NULL, NULL, NULL)")
    conn.executemany("INSERT INTO occupation VALUES (?,?,NULL,4,'onet_31_0')", [(c, t) for c, t, _ in OCCUPATIONS])
    conn.executemany("INSERT INTO nganh_occupation VALUES (?,?,?,?,?)", NGANH_OCC)
    conn.executemany("INSERT INTO fact_sheet VALUES (?,?,?,'fake','fake')",      # only reviewed sheets are shown
                     [("7480101", "# KHMT\n\n## Học gì\n\nTóm tắt đã duyệt (fake).", "reviewed"),
                      ("7480201", "# CNTT\n\n## Học gì\n\nBản nháp (fake).", "draft")])
    conn.executemany("INSERT INTO nganh_knowledge VALUES (?,?,?)",
                     [(n, k, v) for n, d in KNOWLEDGE.items() for k, v in d.items()])
    conn.executemany("INSERT INTO nganh_interest VALUES (?,?,?)",
                     [(n, k, v) for n, d in INTERESTS.items() for k, v in d.items()])
    conn.executemany("INSERT INTO nganh_work_context VALUES (?,?,?,?,?)",
                     [(n, e, e, "CX", v) for n, d in WORK_CONTEXT.items() for e, v in d.items()])
    conn.executemany("INSERT INTO nganh_close VALUES (?,?,?,?,0,0)", CLOSE)
    conn.executemany("INSERT INTO name_vi (kind, key, name_vi, description, status, origin) "
                     "VALUES (?,?,?,?,'draft','test')",
                     [("occupation", c, vi, None) for c, _, vi in OCCUPATIONS] + NAMES)
