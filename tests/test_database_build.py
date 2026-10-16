"""The whole build, run on the tiny raw-input fixture (tests/rawfixture.py)."""

import sqlite3

import pandas as pd
import pytest

from tests.rawfixture import write_raw_inputs
from uniadvisor.config import load_data_config
from pipelines.database.prepare import prepare
from pipelines.database.coverage import compute, render
from uniadvisor.data.school_docs import ANY_TWO_SUBJECTS, any_two


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("build")
    inputs = write_raw_inputs(root / "inputs")
    curated = root / "curated"
    curated.mkdir()
    result = prepare(inputs=inputs, curated=curated, out_db=root / "out" / "test.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    yield conn, result
    conn.close()


def one(conn, sql, *args):
    row = conn.execute(sql, args).fetchone()
    return row[0] if row and len(row) == 1 else row


def test_foreign_keys(built):
    conn, _ = built
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_school_scope(built):
    conn, _ = built
    rows = {r[0]: r[1:] for r in conn.execute("SELECT code, city, in_scope, scope_reason, city_basis FROM school")}
    assert rows["HNA"][:2] == ("HN", 1)
    assert rows["HCB"][:2] == ("HCM", 1)               # address wins over the junk province field
    # Former Bình Dương / Bà Rịa - Vũng Tàu count as TP.HCM
    assert rows["BDU"] == ("HCM", 1, None, "address_former_province")
    assert rows["DNG"][1:3] == (0, "city_not_hn_hcm")
    assert rows["COL"][1:3] == (0, "not_university")
    assert rows["NOA"][0] == "HN" and rows["NOA"][3] == "province_field"


def test_program_scope(built):
    conn, _ = built
    reason = dict(conn.execute("SELECT id, scope_reason FROM program"))
    assert reason["HNA:CS1"] is None
    assert reason["HNA:BR1"].startswith("campus_outside_hn_hcm")
    assert reason["HNA:TK1"] == "talent_test_required"
    assert reason["HNA:HB1"] == "no_thpt_method"
    assert reason["HNA:OLD9"] == "not_seen_in_2026"
    assert "DNG:CS1" not in reason                       # programs of out-of-scope schools are not stored


def test_program_city_follows_named_campus(built):
    conn, _ = built
    assert one(conn, "SELECT city FROM program WHERE id = 'HNA:KT1'") == "HCM"
    assert one(conn, "SELECT city FROM program WHERE id = 'HNA:CS1'") == "HN"


def test_moet_codes(built):
    conn, result = built
    assert one(conn, "SELECT moet_code, moet_code_basis FROM program WHERE id = 'HNA:CS1'") == ("7480101", "unipilot")
    assert one(conn, "SELECT moet_code, moet_code_basis FROM program WHERE id = 'HCB:F7480201'") == (
        "7480201", "program_code_contains")
    # X9 has no major code, but its name equals an official ngành name: applied, marked unreviewed
    assert one(conn, "SELECT moet_code, moet_code_basis FROM program WHERE id = 'HNA:X9'") == (
        "7480101", "name_match_unreviewed")
    assert one(conn, "SELECT moet_code FROM program WHERE id = 'HNA:KT1'") is None     # "Kinh tế": not in catalog
    review = (result["review_dir"] / "program_moet_code.csv").read_text(encoding="utf-8-sig")
    assert "HNA:X9" in review and "name_match_unreviewed" in review   # listed for a person to confirm


def test_cutoffs_two_years_and_disagreement(built):
    conn, _ = built
    rows = conn.execute("SELECT year, combo_key, score, source_id FROM cutoff WHERE program_id = 'HNA:CS1' "
                        "ORDER BY year").fetchall()
    assert rows == [(2025, "*", 25.0, "vnexpress"), (2026, "*", 24.2, "vnexpress")]
    assert one(conn, "SELECT status FROM cutoff_observation WHERE source_id = 'tuyensinh247' "
                     "AND program_code = 'CS1'") == "disagrees"


def test_per_combination_refinement(built):
    conn, _ = built
    rows = conn.execute("SELECT combo_key, score, source_id FROM cutoff WHERE program_id = 'HNA:IT1' AND year = 2026 "
                        "ORDER BY combo_key").fetchall()
    assert rows == [("A00", 23.0, "tuyensinh247"), ("D01", 24.0, "tuyensinh247")]
    assert one(conn, "SELECT status FROM cutoff_observation WHERE source_id = 'vnexpress' AND program_code = 'IT1' "
                     "AND year = 2026") == "agrees"


def test_reused_code_earlier_year_is_excluded(built):
    conn, result = built
    # MX1 is "Công nghệ thông tin" in 2026; the 2025 row with that code is "Ngôn ngữ Anh": another program
    assert one(conn, "SELECT status FROM cutoff_observation WHERE program_code = 'MX1' AND year = 2025") == \
        "excluded:name_differs_from_latest_year"
    assert one(conn, "SELECT COUNT(*) FROM cutoff WHERE program_id = 'MXS:MX1' AND year = 2025") == 0
    assert result["review_counts"]["cutoff_name_changed"] == 1
    # the same name in both years is kept
    assert one(conn, "SELECT COUNT(*) FROM cutoff WHERE program_id = 'HNA:CS1' AND year = 2025") == 1


def test_confirmed_same_program_keeps_the_earlier_year(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "same_program.csv").write_text(
        "program_id,year,note,reviewed_by,reviewed_on\nMXS:MX1,2025,renamed,tester,2026-10-07\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    assert one(conn, "SELECT score FROM cutoff WHERE program_id = 'MXS:MX1' AND year = 2025") == 20.0
    assert "cutoff_name_changed" not in result["review_counts"]


def test_cache_mismatch_is_excluded(built):
    conn, _ = built
    assert one(conn, "SELECT status, cache_check FROM cutoff_observation WHERE program_code = 'IT1' AND year = 2025") \
        == ("excluded:cache_mismatch", "mismatch")
    assert one(conn, "SELECT COUNT(*) FROM cutoff WHERE program_id = 'HNA:IT1' AND year = 2025") == 0


def test_vietnamnet_method_picking(built):
    conn, _ = built
    statuses = dict(conn.execute("SELECT raw_score, status FROM cutoff_observation WHERE program_code = 'X9'"))
    assert statuses == {"21.0": "chosen", "27.5": "excluded:not_thpt_method", "20.5": "excluded:method_unknown"}
    assert one(conn, "SELECT COUNT(*) FROM cutoff_observation WHERE year = 2024") == 0


def test_scales_and_conversion_to_30(built):
    conn, _ = built
    # 2025 cutoff 85.5 on a 100-point scale: converted linearly and marked mixed method
    assert one(conn, "SELECT scale, score_30, is_mixed_method, mixed_method_basis FROM cutoff "
                     "WHERE program_id = 'HCB:YK' AND year = 2025") == (100, 25.65, 1, "score_on_100_point_scale")
    assert one(conn, "SELECT scale, score_30, is_mixed_method FROM cutoff "
                     "WHERE program_id = 'HCB:YK' AND year = 2026") == (30, 27.0, 0)
    assert one(conn, "SELECT score_scale FROM program WHERE id = 'HCB:YK'") == 30        # latest year decides
    assert one(conn, "SELECT score_scale, scale_basis FROM program WHERE id = 'HCB:F7480201'") == (
        40, "cutoff_2026_on_40")
    assert one(conn, "SELECT score_30 FROM cutoff WHERE program_id = 'HCB:F7480201'") == 24.75     # 33.0 * 30 / 40
    assert one(conn, "SELECT subject_code, weight FROM program_weight WHERE program_id = 'HCB:F7480201'") == ("TO", 2.0)


def test_tuition(built):
    conn, result = built
    assert one(conn, "SELECT tuition_min_vnd, tuition_max_vnd, tuition_year FROM program WHERE id = 'HNA:CS1'") == (
        32_000_000, 36_000_000, 2026)
    # 2026 text is not an amount -> the 2025 amount is used and the text is listed for review
    assert one(conn, "SELECT tuition_min_vnd, tuition_year FROM program WHERE id = 'HCB:YK'") == (80_000_000, 2025)
    assert "Đang cập nhật" in (result["review_dir"] / "tuition_unparsed.csv").read_text(encoding="utf-8-sig")
    assert one(conn, "SELECT tuition_min_vnd FROM program WHERE id = 'HNA:IT1'") is None


def test_coverage_report_renders(built):
    conn, result = built
    text = render(compute(conn), result)
    assert "## 6. Usable for the list" in text
    m = compute(conn)
    assert m["programs_in_scope_total"] == one(conn, "SELECT COUNT(*) FROM program WHERE in_scope = 1")
    # Usable: CS1, IT1, X9 (name match), YK, F7480201 (40 points), MX1 (mixed method, marked).
    # Not usable: KT1, MX2 and the linkage fixtures (no MOET code), IU1 (no cutoff).
    assert sum(n for _, n in m["usable"]) == 6
    assert m["usable_mixed"] == 2                               # MX1, and YK for its 2025 100-point cutoff
    blockers = {label: n for label, n, _ in m["blockers"]}
    # KT1, MX2, and the linkage fixtures 401 (7310101 is not in the fixture catalog), DS_01, SH7, SH7~2
    assert blockers["MOET ngành code unknown"] == 6


def _dump(path):
    conn = sqlite3.connect(path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    dump = {t: sorted(map(repr, conn.execute(f"SELECT * FROM {t}"))) for t in tables if t != "meta"}
    conn.close()
    return dump


def test_build_is_deterministic(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    (tmp_path / "curated").mkdir()
    a = prepare(inputs=inputs, curated=tmp_path / "curated", out_db=tmp_path / "a" / "x.db", cfg=load_data_config())
    b = prepare(inputs=inputs, curated=tmp_path / "curated", out_db=tmp_path / "b" / "x.db", cfg=load_data_config())
    assert _dump(a["db"]) == _dump(b["db"])


def test_curated_overrides_are_applied(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "program_overrides.csv").write_text(
        "program_id,moet_code,in_scope,reason,reviewed_by,reviewed_on\nHNA:X9,7480101,,,tester,2026-10-06\n",
        encoding="utf-8")
    (curated / "school_overrides.csv").write_text(
        "school_code,city,in_scope,reason,reviewed_by,reviewed_on\nDNG,,0,checked_da_nang,tester,2026-10-06\n",
        encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    assert one(conn, "SELECT moet_code, moet_code_basis FROM program WHERE id = 'HNA:X9'") == ("7480101", "override")
    assert one(conn, "SELECT scope_reason, city_basis FROM school WHERE code = 'DNG'") == ("checked_da_nang", "override")
    conn.close()


def test_display_names_are_loaded(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "display_names.csv").write_text(
        "code,display_name,aliases,status,origin,source_id,note\n"
        "74801,\"Khoa học máy tính, Trí tuệ nhân tạo\",KHMT;  AI ;,draft,group_labels_old_repo,curated,\n"
        "7480201,,IT,reviewed,tester,curated,\n"
        "99999,Không có,,draft,agent_draft,curated,\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    rows = conn.execute("SELECT code, display_name, aliases, status, origin FROM display_name ORDER BY code").fetchall()
    assert rows == [("74801", "Khoa học máy tính, Trí tuệ nhân tạo", "KHMT; AI", "draft", "group_labels_old_repo"),
                    ("7480201", None, "IT", "reviewed", "tester")]
    conn.close()
    assert result["review_counts"]["display_names"] == 1            # 99999 is not in the catalog


def test_former_hcm_provinces_can_be_switched_off(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    (tmp_path / "curated").mkdir()
    cfg = dict(load_data_config(), include_former_provinces_merged_into_hcm=False)
    result = prepare(inputs=inputs, curated=tmp_path / "curated", out_db=tmp_path / "o" / "x.db", cfg=cfg)
    conn = sqlite3.connect(result["db"])
    assert one(conn, "SELECT in_scope, scope_reason FROM school WHERE code = 'BDU'") == (
        0, "former_province_merged_into_hcm")
    conn.close()


def test_mixed_method_list(built):
    _, result = built
    import pandas as pd

    mixed = pd.read_csv(result["review_dir"] / "mixed_method_programs.csv", encoding="utf-8-sig",
                        keep_default_na=False, dtype=str)
    assert list(mixed["program_id"]) == ["HCB:YK", "MXS:IU1", "MXS:MX1", "MXS:MX2"]
    row = mixed.set_index("program_id").loc["HCB:YK"]          # 2025 cutoff above 40; 2026 exam only
    assert (row["scale_2025"], row["cutoff_2025_on_30"], row["mixed_2025"], row["mixed_2026"]) == (
        "100", "25.65", "1", "0")
    assert row["is_mixed_method_2026"] == "0"


def test_mixed_method_marks(built):
    conn, _ = built
    flags = {r[0]: r[1:] for r in conn.execute("SELECT id, is_mixed_method, mixed_method_basis, in_scope FROM program")}
    assert flags["HNA:CS1"] == (0, "export_lists_exam_only_method", 1)
    # A 30-point cutoff whose program lists only "THPT + Học bạ" is a combined score: kept on 30, marked
    assert flags["MXS:MX1"] == (1, "export_lists_only_combined_methods", 1)
    assert one(conn, "SELECT scale, score_30, is_mixed_method, mixed_method_basis FROM cutoff "
                     "WHERE program_id = 'MXS:MX1'") == (30, 24.0, 1, "export_lists_only_combined_methods")
    assert flags["MXS:MX2"] == (1, "school_lists_no_exam_only_method", 1)
    assert flags["MXS:IU1"] == (1, "export_lists_only_combined_methods", 1)   # kept, marked
    assert one(conn, "SELECT scope_reason FROM program WHERE id = 'HNA:AR1'") == "talent_test_required"


def test_site_codes_link_to_export_programs(built):
    conn, _ = built
    linked = dict(conn.execute("SELECT program_code, program_id FROM cutoff_observation WHERE school_code = 'HCB'"))
    assert linked["7310101_401"] == "HCB:401"          # MOET code + '_' + export code
    assert linked["DS01"] == "HCB:DS_01"               # punctuation ignored
    assert linked["SH7_TA"] == "HCB:SH7~2"             # shared code + suffix, linked by exact name
    assert one(conn, "SELECT COUNT(*) FROM program WHERE id IN ('HCB:7310101_401', 'HCB:DS01', 'HCB:SH7_TA')") == 0


def test_renamed_code_is_linked_by_exact_name(built):
    conn, result = built
    # KT0 (2025 only) and KT1 (2026, in the export) have the same name at the same school
    assert one(conn, "SELECT program_id FROM cutoff_observation WHERE program_code = 'KT0'") == "HNA:KT1"
    assert one(conn, "SELECT COUNT(*) FROM program WHERE id = 'HNA:KT0'") == 0
    assert [r[0] for r in conn.execute("SELECT year FROM cutoff WHERE program_id = 'HNA:KT1' ORDER BY year")] == [
        2025, 2026]
    assert "KT0" in (result["review_dir"] / "renamed_code_links.csv").read_text(encoding="utf-8-sig")
    # OLD9 has no same-name program: still a program not offered in 2026
    assert one(conn, "SELECT scope_reason FROM program WHERE id = 'HNA:OLD9'") == "not_seen_in_2026"


def test_combinations_defined_from_vnexpress_titles(built):
    conn, result = built
    assert one(conn, "SELECT subjects_known, source_id FROM combo WHERE code = 'X99'") == (1, "vnexpress")
    assert [r[0] for r in conn.execute("SELECT subject_code FROM combo_subject WHERE combo_code = 'X99' "
                                       "ORDER BY position")] == ["TO", "LI", "GDKTPL"]
    # "Giáo dục công dân" is not an exam subject since 2025: C14 is not defined, and is listed for review
    assert one(conn, "SELECT COUNT(*) FROM combo_subject WHERE combo_code = 'C14'") == 0
    text = (result["review_dir"] / "combo_definitions.csv").read_text(encoding="utf-8-sig")
    assert "C14" in text and "vnexpress_names_not_all_exam_subjects" in text


def test_program_name_vs_moet_review(fake_db):
    from pipelines.database.prepare import Review, _name_vs_moet
    review = Review()
    _name_vs_moet(fake_db, review)                     # every fake program is named like its ngành
    assert review.rows.get("program_name_vs_moet", []) == []


def test_program_name_vs_moet_flags_unrelated_names(tmp_path):
    from uniadvisor import db
    from pipelines.database.prepare import Review, _name_vs_moet
    conn = db.create(tmp_path / "x.db")
    conn.execute("INSERT INTO source VALUES ('s', 's', 'curated', NULL, NULL, NULL)")
    conn.executemany("INSERT INTO moet_major (code, level, name, parent_code, source_id) VALUES (?,?,?,?, 's')",
                     [("731", "linh_vuc", "Khoa học xã hội", None), ("73104", "nhom_nganh", "Tâm lý học", "731"),
                      ("7310401", "nganh", "Tâm lý học", "73104")])
    conn.execute("INSERT INTO school (code, name, city_basis, in_scope, source_id) VALUES ('S', 'S', 'x', 1, 's')")
    conn.executemany(
        "INSERT INTO program (id, school_code, program_code, name, moet_code, moet_code_basis, scale_basis, in_scope, "
        "source_ids) "
        "VALUES (?, 'S', ?, ?, '7310401', 'unipilot', 'no_cutoff', 1, 's')",
        [("S:1", "1", "Luật Kinh tế"), ("S:2", "2", "Tâm lý học giáo dục"), ("S:3", "3", "Chương trình tiên tiến")])
    review = Review()
    _name_vs_moet(conn, review)
    assert [r["program_id"] for r in review.rows["program_name_vs_moet"]] == ["S:1"]   # S:3 has only noise words


def test_school_documents(tmp_path):
    """Values entered from schools' own documents: cutoffs, school-specific combinations, tuition."""
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "school_cutoffs.csv").write_text(
        "school_code,program_code,program_name,year,combos,score,scale,method,source_file,note\n"
        "MXS,IU1,Khoa học máy tính,2026,A00,22.5,30,thpt_mixed,Viec2/MXS/MXS26.png,\n"
        "HNA,NEW1,Ngành mới,2026,*,20,,thpt,Viec2/HNA/HNA26.png,\n", encoding="utf-8")
    (curated / "school_combos.csv").write_text(
        "school_code,combo_code,subjects,source_file,note\n"
        "HNA,C14,VA;TO;GDKTPL,Viec3/HNA/HNA.png,\n"
        "HNA,X99,TO;LI;GDKTPL,Viec3/HNA/HNA.png,same as the shared definition\n"
        "HNA,Z01,VA;Giáo dục công dân;TO,Viec3/HNA/HNA.png,\n", encoding="utf-8")
    (curated / "school_tuition.csv").write_text(
        "school_code,program_pattern,min_vnd,max_vnd,unit,school_year,source_file,note,per_year_factor,factor_basis\n"
        "HNA,.*,500000,500000,per_credit,2026-2027,Viec4/HNA/HNA.png,no credits per year stated,,\n"
        "HNA,IT1,30000000,32000000,per_year,2026-2027,Viec4/HNA/HNA.png,,,\n"
        "HNA,CS1,10000000,10000000,per_year,2025-2026,Viec4/HNA/HNA.png,older than VnExpress 2026,,\n"
        "HNA,NEW1,14250000,14250000,per_semester,2026-2027,Viec4/HNA/HNA.png,3 hoc ky/nam,3,"
        "semesters_per_year_stated\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    assert one(conn, """SELECT score, source_id, is_mixed_method, mixed_method_basis FROM cutoff
                        WHERE program_id = 'MXS:IU1'""") == (22.5, "school_document", 1,
        "school_document_states_combined_method;export_lists_only_combined_methods")
    assert one(conn, "SELECT score FROM cutoff WHERE program_id = 'HNA:NEW1'") == 20.0
    assert one(conn, "SELECT combos FROM cutoff_observation WHERE program_code = 'CS1' AND year = 2026 "
                     "AND source_id = 'vnexpress'") == "A00;A01;X99;C14@HNA"
    assert conn.execute("SELECT subject_code FROM combo_subject WHERE combo_code = 'C14@HNA' ORDER BY position"
                        ).fetchall() == [("VA",), ("TO",), ("GDKTPL",)]
    assert one(conn, "SELECT count(*) FROM combo WHERE code LIKE 'X99@%'") == 0      # same as shared: not scoped
    assert one(conn, "SELECT tuition_min_vnd, tuition_year, tuition_source_id FROM program WHERE id = 'HNA:IT1'") == (
        30_000_000, 2026, "school_document")
    assert one(conn, "SELECT tuition_min_vnd, tuition_source_id FROM program WHERE id = 'HNA:CS1'") == (
        32_000_000, "vnexpress")
    assert one(conn, "SELECT tuition_min_vnd, tuition_basis, tuition_raw FROM program WHERE id = 'HNA:NEW1'") == (
        42_750_000, "semesters_per_year_stated",
        "14.250.000/học kỳ x 3 (semesters_per_year_stated) (2026-2027, Viec4/HNA/HNA.png)")
    assert one(conn, "SELECT tuition_basis FROM program WHERE id = 'HNA:IT1'") is None
    conn.close()
    assert result["review_counts"]["school_combos_unusable"] == 1
    assert result["review_counts"]["school_tuition_not_per_year"] == 1


def test_school_stated_scale(tmp_path):
    """A school's own document states the scale of a year's cutoffs that the sites give without one."""
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "school_scales.csv").write_text(
        "school_code,year,program_pattern,scale,source_file,note\nHNA,2025,,40,Viec2/HNA/HNA25.pdf,thang 40\n"
        "HNA,2025,CS1,30,Viec2/HNA/HNA25.pdf,CS1 on 30\nHNA,2026,,,Viec2/HNA/HNA26.pdf,no scale\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    assert one(conn, "SELECT scale, scale_basis, score_30 FROM cutoff WHERE program_id = 'HNA:CS1' AND year = 2025"
               ) == (30, "school_document_states_scale", 25.0)              # the program's own row wins
    assert one(conn, "SELECT scale, scale_basis FROM cutoff WHERE program_id = 'HNA:KT1' AND year = 2025") == (
        40, "school_document_states_scale")                                  # the school-wide row
    assert one(conn, "SELECT scale FROM cutoff WHERE program_id = 'HNA:CS1' AND year = 2026") == 30
    conn.close()
    assert result["review_counts"]["school_document_rows"] == 1

def test_catalog_extension(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "moet_extra.csv").write_text(
        "code,name,source_file,status,note\n"
        "7480118,Hệ thống nhúng và IoT,Viec1/X/X.pdf p.1,school_document,\n"
        "8480101,Khoa học máy tính,Viec1/X/X.pdf p.2,school_document,master's code\n"
        "7999901,Không có nhóm,Viec1/X/X.pdf p.3,school_document,\n", encoding="utf-8")
    (curated / "program_overrides.csv").write_text(
        "program_id,moet_code,in_scope,reason,reviewed_by,reviewed_on,source_file\n"
        "HNA:X9,7480118,,,tester,2026-10-07,Viec1/X/X.pdf p.1\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    assert one(conn, "SELECT parent_code, source_id FROM moet_major WHERE code = '7480118'") == (
        "74801", "school_document")
    assert one(conn, "SELECT moet_code FROM program WHERE id = 'HNA:X9'") == "7480118"
    assert one(conn, "SELECT count(*) FROM moet_major WHERE code IN ('8480101', '7999901')") == 0
    conn.close()
    assert result["review_counts"]["moet_extra"] == 2


def test_school_employment(tmp_path):
    """Employment rates from schools' own documents: kept when usable, the others listed for review."""
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (tmp_path / "manual_sources").mkdir()
    (tmp_path / "manual_sources" / "HNA_viec_lam_1.pdf").write_bytes(b"%PDF")
    (curated / "school_employment.csv").write_text(
        "school_code,moet_code,graduation_year,rate,source_file,reviewed_by,reviewed_on,note,source_id\n"
        "HNA,7480101,2024,0.952,HNA_viec_lam_1.pdf p.12,Quan,2026-10-10,survey 12 months after graduation,school_document\n"
        "hna,7480201,2024,0.9,HNA_viec_lam_2.pdf,,,,\n"                 # file not captured: kept, listed
        "HNA,7480201,2023,95.2,HNA_viec_lam_1.pdf,,,,\n"                # a percentage, not 0-1
        "HNA,7210403,,0.8,HNA_viec_lam_1.pdf,,,,\n"                     # no year
        "DNG,7480201,2024,0.8,HNA_viec_lam_1.pdf,,,,\n"                 # DNG offers no Công nghệ thông tin
        "HNA,7480101,2024,0.9,HNA_viec_lam_1.pdf,,,,\n", encoding="utf-8")   # duplicate
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    rows = conn.execute("SELECT school_code, moet_code, graduation_year, rate, reviewed_by, source_id "
                        "FROM school_employment ORDER BY moet_code").fetchall()
    conn.close()
    assert rows == [("HNA", "7480101", 2024, 0.952, "Quan", "school_document"),
                    ("HNA", "7480201", 2024, 0.9, None, "school_document")]
    issues = pd.read_csv(result["review_dir"] / "school_employment_rows.csv")["issue"].tolist()
    assert sorted(issues) == sorted([
        "source file not found (row kept)", "rate is not a number from 0 to 1", "graduation_year missing",
        "the school offers no program of this ngành", "same school, ngành and year as an earlier row"])


def test_program_combos_and_any_two_rule(tmp_path):
    """program_combos.csv replaces a program's combinations; 'TO+2' becomes every set of Toán and two other exam
    subjects, scored like any combination; unknown programs go to review."""
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "program_combos.csv").write_text(
        "school_code,program_code,combos,source_file,note\n"
        "HNA,X9,TO+2,list.csv,\n"
        "HNA,NOPE,A00,list.csv,\n", encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    conn = sqlite3.connect(result["db"])
    combos = [c for (c,) in conn.execute("SELECT combo_code FROM program_combo WHERE program_id = 'HNA:X9'")]
    exam = {c for (c,) in conn.execute("SELECT code FROM subject WHERE is_exam = 1")} & set(ANY_TWO_SUBJECTS)
    subjects = conn.execute("SELECT group_concat(subject_code, ',') FROM combo_subject "
                            "WHERE combo_code = 'Toán+Lí+Hóa' ORDER BY position").fetchone()[0]
    conn.close()
    n = len(exam) - 1                                                   # the other subjects, 2 of them
    assert len(combos) == n * (n - 1) // 2 and "Toán+Lí+Hóa" in combos
    assert all(c.startswith("Toán+") for c in combos) and subjects == "TO,LI,HO"
    unmatched = pd.read_csv(result["review_dir"] / "program_combos_unmatched.csv")
    assert unmatched["program_code"].tolist() == ["NOPE"]


def test_anchor_fixed_subject_and_any_one_is_a_subset_of_anchor_and_any_two():
    """'Văn, Anh, 1 môn bất kì' (VA+N1+1): the sets of VA+2 that contain Anh, with the same codes."""
    from uniadvisor.data.school_docs import ANY_ONE, ANY_TWO
    assert ANY_ONE.match("VA+N1+1") and ANY_ONE.match("TO+N4+1") and not ANY_ONE.match("VA+2")
    assert ANY_TWO.match("VA+2") and not ANY_TWO.match("VA+N1+1") and not ANY_ONE.match("LI+N1+1")
    from uniadvisor.data.school_docs import any_one
    some = any_one("VA", "N1")
    assert len(some) == 16 and all(v[0] == "VA" and "N1" in v for v in some.values())    # 16 other subjects besides Anh
    assert set(some) <= set(any_two("VA")) and "Văn+Lí+Anh" in some
    assert any_one("VA", "VA") == {}


def test_any_two_covers_the_real_exam():
    sets = any_two("TO")
    assert len(sets) == 136 and sets["Toán+Văn+Anh"] == ["TO", "VA", "N1"]   # 17 other subjects, 2 of them
    assert all(len(set(v)) == 3 and v[0] == "TO" for v in sets.values())


def test_tuition_per_credit_x35_and_repeated_code(tmp_path):
    """Per credit x 35 (owner rule) and two programs sharing a code, told apart by the id suffix; a later row wins."""
    from uniadvisor.data.school_docs import load_tuition

    class Review:
        def __init__(self):
            self.rows = []

        def add(self, name, **kw):
            self.rows.append(name)

    (tmp_path / "school_tuition.csv").write_text(
        "school_code,program_pattern,min_vnd,max_vnd,unit,school_year,source_file,note,per_year_factor,factor_basis\n"
        "XX,^(108)$,31500000,31500000,per_year,2026-2027,f.md,,,\n"
        "XX,^(108~2)$,63000000,63000000,per_year,2026-2027,f.md,,,\n"
        "XX,^(200)$,1000000,1000000,per_credit,2026,f.md,,35,credits_per_year_owner_rule\n", encoding="utf-8")
    programs = {"XX:108": {"school_code": "XX", "program_code": "108"}, "XX:108~2": {"school_code": "XX", "program_code": "108"},
                "XX:200": {"school_code": "XX", "program_code": "200"}}
    review = Review()
    out = load_tuition(tmp_path, programs, review)
    assert out["XX:108"][:2] == (31_500_000, 31_500_000) and out["XX:108~2"][:2] == (63_000_000, 63_000_000)
    assert out["XX:200"][0] == 35_000_000 and out["XX:200"][5] == "credits_per_year_owner_rule"
    assert review.rows == []
