"""Unit tests for the parsing and scope rules used by the build."""

import pandas as pd
import pytest

from uniadvisor.data import scope, sources
from pipelines.database.build import (Review, _choose_from_source, _scale, exclude_reused_codes, merge_site_duplicates,
                                    name_key, parse_tuition, reused_code, suggest_moet, to_30)
from uniadvisor.data.text import combo_key, norm_code, parse_score, same_program_name, split_combos


@pytest.mark.parametrize("address, province, expected", [
    ("Km18 Xa Lộ Hà Nội, Phường Linh Xuân, Thành phố Hồ Chí Minh.", "TP. Hồ Chí Minh", ("HCM", "address")),
    ("87 Nguyễn Chí Thanh, P. Giảng Võ, HN", "Hà Nội", ("HN", "address")),
    ("xã Thuận An - thành phố Hà Nội", "Hà Nội", ("HN", "address")),
    ("Số 80 Trương Công Định, P. Vũng Tàu, TP. Hồ Chí Minh", "Đồng Nai", ("HCM_FORMER", "address_former_province")),
    ("298 Hà Huy Tập, Phường Tân An, Tỉnh Đắk Lắk", "Đồng Nai", (None, "address_other_province")),
    ("236 phố", "Hà Nội", ("HN", "province_field")),
    ("", "TP. Hồ Chí Minh", ("HCM", "province_field")),
])
def test_school_city(address, province, expected):
    assert scope.decide_school_city(address, province) == expected


@pytest.mark.parametrize("name, expected", [
    ("Luật (dành cho Phân hiệu Đắk Lắk)", ("outside", "dak lak")),
    ("Kinh tế (Cơ sở HCM)", ("inside", "HCM")),
    ("Quản lý kinh tế - Cơ sở Hà Nội", ("inside", "HN")),
    ("Kỹ sư quân sự (đào tạo tại nước ngoài)", ("unclear", None)),
    ("Tài chính - Ngân hàng", ("none", None)),               # "tài" is not "tại"
    ("Hệ thống cơ sở dữ liệu", ("none", None)),
    ("Quản trị kinh doanh (Phân hiệu Thanh Hoá)", ("outside", "thanh hoa")),   # tone-mark variant
])
def test_campus_place(name, expected):
    assert scope.campus_place(name) == expected


@pytest.mark.parametrize("note, expected", [
    ("Xét duyệt điểm thi THPT", "thpt"),
    ("Xét kết quả thi tốt nghiệp THPT | Mã phương thức tuyển sinh: 100 | Tiêu chí phụ: NV 1", "thpt"),
    ("Xét duyệt điểm thi THPT (điểm môn Anh hệ số 2)", "thpt"),
    ("Sử dụng kết quả thi THPT (THPT; THPT+NK; THPT+HB; THPT+CC)", "other"),
    ("PT sử dụng KQ thi TN THPT 2026/KQ thi TN THPT 2026 kết hợp thi NK | Thang điểm: 30", "other"),
    ("Điểm học bạ", "other"),
    ("Điểm ĐGNL", "other"),
    ("IB", "other"),
    ("", "unknown"),
    ("Thang điểm: 40 | Tiêu chí phụ: NV1", "unknown"),
])
def test_vietnamnet_method(note, expected):
    assert sources.vietnamnet_method(note) == expected


def test_doubled_subject_and_scale_notes():
    assert sources.doubled_subject("Xét duyệt điểm thi THPT (điểm môn Anh hệ số 2)") == "N1"
    assert sources.doubled_subject("Xét duyệt điểm thi THPT (điểm môn Toán hệ số 2)") == "TO"
    assert sources.doubled_subject("Xét duyệt điểm thi THPT") is None
    assert sources.stated_scale("Thang điểm: 40 | Tiêu chí phụ: NV1") == 40
    assert sources.stated_scale("Thang điểm 100") == 100
    assert sources.stated_scale("") is None


@pytest.mark.parametrize("raw, expected", [
    ("35.000.000 - 45.000.000", (35_000_000, 45_000_000)),
    ("29.400.000", (29_400_000, 29_400_000)),
    ("--", None), ("", None), ("Đang cập nhật", None),
    ("850.000/tín chỉ", None),
    ("500.000", None),                                       # below the yearly minimum: not a yearly fee
])
def test_parse_tuition(raw, expected):
    assert parse_tuition(raw, 1_000_000, 1_000_000_000) == expected


def test_text_helpers():
    assert norm_code(" 7220201 tm ") == "7220201TM"
    assert parse_score("24,5") == 24.5 and parse_score("--") is None
    assert split_combos("A00; a01,D01 A00") == ["A00", "A01", "D01"]
    assert combo_key(["D01", "A00"]) == "A00;D01"


@pytest.mark.parametrize("a, b, same", [
    ("Hoá học", "Hóa học", True),                                            # old and new tone placement
    ("SP Hóa học", "Sư phạm Hoá học", True),                                 # abbreviation
    ("Phân tích dữ liệu", "Toán kinh tế (Chuyên ngành Phân tích dữ liệu)", True),   # specialisation in brackets
    ("Kinh tế - CLC", "Kinh tế (Chương trình chất lượng cao)", True),        # how it is taught is not the name
    ("Thủy văn học", "Tài nguyên nước và môi trường (Thủy văn học)", True),
    ("CNKT cơ khí - Cơ sở Hà Nội", "Công nghệ kỹ thuật cơ khí (Chuyên ngành Công nghệ chế tạo máy)", True),
    ("Marketing - Chương trình đại học bằng tiếng Anh", "Marketing - Chất lượng cao giảng dạy 100% tiếng Anh", True),
    ("Kế toán", "Kỹ thuật phần mềm", False),
    ("Quản trị kinh doanh - CLC", "Khoa học máy tính chương trình tiên tiến", False),
    ("Chương trình chất lượng cao", "Ngôn ngữ Anh", True),                   # nothing specific to compare
])
def test_same_program_name(a, b, same):
    assert same_program_name(a, b) is same


_CATALOG = {name_key(n): c for c, n in [("7310608", "Đông phương học"), ("7310620", "Đông Nam Á học"),
                                        ("7220201", "Ngôn ngữ Anh"), ("7220209", "Ngôn ngữ Nhật"),
                                        ("7340301", "Kế toán"), ("7480103", "Kỹ thuật phần mềm")]}


@pytest.mark.parametrize("then, now, moet_now, reused", [
    ("Đông phương học", "Đông Nam Á học", "7310620", True),     # QHX05: names share "Đông", ngành differ
    ("Ngôn ngữ Anh", "Ngôn ngữ Nhật", "7220209", True),
    ("Kế toán", "Kỹ thuật phần mềm", "7480103", True),           # names share nothing
    ("Ngôn ngữ Anh", "Tiếng Anh thương mại", "7220201", False),  # a specialisation of the same ngành
    ("Hoá học", "Hóa học", None, False),
    ("Đông phương học", "Đông Nam Á học", None, False),          # no current code: the names alone are too close
])
def test_reused_code(then, now, moet_now, reused):
    assert reused_code(then, now, moet_now, _CATALOG) is reused


def _rows(*items):
    return pd.DataFrame([{"combo_key": k, "score": s, "raw_score": str(s)} for k, s in items],
                        index=range(10, 10 + len(items)))


def test_choose_single_and_duplicate_rows():
    picked, conflict = _choose_from_source(_rows(("A00;A01", 24.0), ("A00;A01", 24.0)))
    assert conflict is None and picked == [("*", 24.0, 10)]


def test_choose_same_score_with_and_without_combinations_is_one_cutoff():
    picked, conflict = _choose_from_source(_rows(("A01;D01", 15.0), ("", 15.0), ("A01;D01", 15.0)))
    assert conflict is None and picked == [("*", 15.0, 10)]


def test_choose_per_combination():
    picked, conflict = _choose_from_source(_rows(("A00", 23.0), ("A01;D01", 24.0)))
    assert conflict is None and [(k, s) for k, s, _ in picked] == [("A00", 23.0), ("A01;D01", 24.0)]


@pytest.mark.parametrize("rows, reason", [
    ((("A00;A01", 18.75), ("A00;A01", 20.0)), "different_scores_same_combinations"),
    ((("A00", 25.35), ("X06;X26", 25.5), ("A01;X26", 25.1)), "overlapping_combinations"),
    ((("", 21.31), ("", 20.0)), "rows_without_combinations"),
])
def test_choose_conflicts(rows, reason):
    picked, conflict = _choose_from_source(_rows(*rows))
    assert picked == [] and conflict == reason


def _obs(*items):
    return pd.DataFrame([{"score": s, "note": n} for s, n in items])


@pytest.mark.parametrize("rows, expected", [
    ([(24.0, "")], (30, "assumed_max_score_le_30")),
    ([(24.0, "Thang điểm: 30")], (30, "stated_in_note")),
    ([(33.5, "")], (40, "score_above_30")),
    ([(24.13, "Thang điểm: 40")], (40, "stated_in_note")),
    ([(24.0, "điểm môn Anh hệ số 2")], (40, "stated_in_note")),
    ([(85.4, "")], (100, "score_above_40_assumed_100")),
    ([(24.0, "Thang điểm 100")], (100, "stated_in_note")),
])
def test_scale(rows, expected):
    assert _scale(_obs(*rows), [], 40.0) == expected


@pytest.mark.parametrize("score, scale, expected", [(24.2, 30, 24.2), (34.0, 40, 25.5), (80.0, 100, 24.0),
                                                     (85.41, 100, 25.623)])
def test_linear_conversion_to_30(score, scale, expected):
    assert to_30(score, scale) == expected


def test_suggest_moet():
    by_name = {"khoa học máy tính": "7480101", "kinh tế đầu tư": "7310104"}
    assert suggest_moet("(1) Kinh tế Đầu tư", by_name) == "7310104"
    assert suggest_moet("Khoa học máy tính (Chương trình tiên tiến)", by_name) == "7480101"
    assert suggest_moet("CNTT: Khoa học Máy tính", by_name) == "7480101"
    assert suggest_moet("Robot", by_name) == ""
    by_name = {name_key("Kỹ thuật điện tử - viễn thông"): "7520207", name_key("Tài chính - Ngân hàng"): "7340201",
               name_key("Kỹ thuật điều khiển và tự động hóa"): "7520216"}
    assert suggest_moet("Kỹ thuật Điện tử-Viễn thông", by_name) == "7520207"
    assert suggest_moet("Tài chính-Ngân hàng", by_name) == "7340201"
    assert suggest_moet("Kỹ thuật điều khiển & Tự động hóa", by_name) == "7520216"


def _site_rows(*rows):
    return pd.DataFrame([{"program_id": pid, "year": year, "source_id": src, "program_name": name, "status": None,
                          "score": row[4] if len(row) > 4 else 20.0, "raw_score": "20", "url": ""}
                         for row in rows for pid, year, src, name in [row[:4]]])


def _program(school, name, moet=None, sources=("unipilot",)):
    return {"school_code": school, "name": name, "moet": moet, "in_scope": True, "sources": set(sources)}


def test_reused_code_row_moves_to_the_program_that_has_its_name_now():
    # QHX shifted its codes in 2026: QHX05's 2025 row is Đông phương học, which is QHX06 now
    programs = {"QHX:QHX05": _program("QHX", "Đông Nam Á học", "7310620"),
                "QHX:QHX06": _program("QHX", "Đông phương học", "7310608"),
                "QHX:QHX19": _program("QHX", "Quản trị văn phòng", "7340406")}
    obs = _site_rows(("QHX:QHX05", 2025, "vnexpress", "Đông phương học"),
               ("QHX:QHX05", 2026, "vnexpress", "Đông Nam Á học"),
               ("QHX:QHX06", 2026, "vnexpress", "Đông phương học"),
               ("QHX:QHX19", 2025, "vnexpress", "Tâm lý học"),                 # no program is Tâm lý học now
               ("QHX:QHX06", 2025, "vnexpress", "Hán Nôm"))                    # QHX06's own 2025 row leaves too
    review = Review()
    catalog = {"7310620": "Đông Nam Á học", "7310608": "Đông phương học", "7340406": "Quản trị văn phòng",
               "7310401": "Tâm lý học"}
    n = exclude_reused_codes(obs, programs, {"latest_program_year": 2026}, review, catalog)
    assert obs.at[0, "program_id"] == "QHX:QHX06" and obs.at[0, "status"] is None      # moved, still usable
    assert obs.at[3, "status"] == "excluded:name_differs_from_latest_year"
    assert obs.at[4, "status"] == "excluded:name_differs_from_latest_year" and n == 2      # it does not block
    assert [r["moved_to"] for r in review.rows["cutoff_relinked"]] == ["QHX:QHX06"]


def test_a_name_that_lives_elsewhere_now_moves_even_if_it_half_matches():
    # QHX17's 2025 row "Quản tri văn phòng" (typo) shares "quản trị" with QHX17's current name, but is QHX19 now
    programs = {"QHX:QHX17": _program("QHX", "Quản trị dịch vụ du lịch và lữ hành", "7810103"),
                "QHX:QHX19": _program("QHX", "Quản trị văn phòng", "7340406")}
    obs = _site_rows(("QHX:QHX17", 2025, "vnexpress", "Quản tri văn phòng"),
                     ("QHX:QHX17", 2025, "vnexpress", "Quản trị dịch vụ du lịch và lữ hành - CLC"))   # its own row
    exclude_reused_codes(obs, programs, {"latest_program_year": 2026}, Review(), {})
    assert list(obs["program_id"]) == ["QHX:QHX19", "QHX:QHX17"] and obs["status"].isna().all()


def test_a_variants_row_stays_with_the_variant():
    # the plain program has the row's name, but the row is the English-taught variant's own (its name contains it)
    programs = {"SPH:7140211": _program("SPH", "Sư phạm Vật lí", "7140211"),
                "SPH:7140211K": _program("SPH", "Sư phạm Vật lí (dạy Toán bằng tiếng Anh)", "7140211")}
    obs = _site_rows(("SPH:7140211K", 2025, "vnexpress", "Sư phạm Vật lí (học bằng tiếng Anh)"))
    exclude_reused_codes(obs, programs, {"latest_program_year": 2026}, Review(), {})
    assert obs.at[0, "program_id"] == "SPH:7140211K" and obs.at[0, "status"] is None


def test_reused_code_row_is_not_moved_onto_a_program_with_its_own_row():
    programs = {"A:1": _program("A", "Kỹ thuật phần mềm", "7480103"), "A:2": _program("A", "Kế toán", "7340301")}
    obs = _site_rows(("A:1", 2025, "vnexpress", "Kế toán"), ("A:2", 2025, "vnexpress", "Kế toán"))
    exclude_reused_codes(obs, programs, {"latest_program_year": 2026}, Review(),
                         {"7480103": "Kỹ thuật phần mềm", "7340301": "Kế toán"})
    assert obs.at[0, "status"] == "excluded:name_differs_from_latest_year" and obs.at[0, "program_id"] == "A:1"


def test_site_duplicates_are_merged_into_the_export_program():
    programs = {"DKK:7340101DKK": _program("DKK", "Quản trị Kinh doanh", "7340101"),
                "DKK:7340101": _program("DKK", "Quản trị kinh doanh", "7340101", sources=("vnexpress",)),
                "DKK:7480201": _program("DKK", "Công nghệ thông tin", None, sources=("vnexpress",)),   # no export twin
                "HBT:616": _program("HBT", "Ngành Triết học", "7229001", sources=("vietnamnet",)),
                "HBT:TM7229001": _program("HBT", "Triết học", "7229001"),
                "HBT:9": _program("HBT", "Triết học", "7310101", sources=("vietnamnet",))}         # other ngành
    obs = _site_rows(("DKK:7340101", 2026, "vnexpress", "Quản trị kinh doanh"),
               ("HBT:616", 2026, "vietnamnet", "Ngành Triết học"))
    review = Review()
    assert merge_site_duplicates(obs, programs, review) == 2
    assert list(obs["program_id"]) == ["DKK:7340101DKK", "HBT:TM7229001"]
    assert programs["DKK:7340101"]["in_scope"] is False and programs["DKK:7340101"]["reason"] == \
        "duplicate_of:DKK:7340101DKK"
    assert programs["DKK:7480201"]["in_scope"] and programs["HBT:9"]["in_scope"]
    assert "vnexpress" in programs["DKK:7340101DKK"]["sources"]


def test_reviewer_can_keep_a_site_program_apart():
    programs = {"NTT:7340101": _program("NTT", "Quản trị kinh doanh", "7340101"),
                "NTT:7340101DN": _program("NTT", "Quản trị kinh doanh", "7340101", sources=("vnexpress",))}
    obs = _site_rows(("NTT:7340101DN", 2026, "vnexpress", "Quản trị kinh doanh"))
    assert merge_site_duplicates(obs, programs, Review(), keep_apart=frozenset({"NTT:7340101DN"})) == 0
    assert programs["NTT:7340101DN"]["in_scope"] and obs.at[0, "program_id"] == "NTT:7340101DN"


def test_variants_and_differing_cutoffs_are_not_merged():
    programs = {"KHA:7340101": _program("KHA", "Quản trị kinh doanh", "7340101"),
                "KHA:CLC2-03": _program("KHA", "Quản trị kinh doanh (CLC)", "7340101", sources=("tuyensinh247",)),
                "GSA:GSA18DS": _program("GSA", "Kỹ thuật xây dựng công trình giao thông", "7580205"),
                "GSA:GHA32DS": _program("GSA", "Kỹ thuật xây dựng công trình giao thông", "7580205",
                                        sources=("vnexpress",))}
    obs = _site_rows(("GSA:GSA18DS", 2026, "vnexpress", "Kỹ thuật xây dựng công trình giao thông", 21.94),
                     ("GSA:GHA32DS", 2026, "vnexpress", "Kỹ thuật xây dựng công trình giao thông", 23.96))
    review = Review()
    assert merge_site_duplicates(obs, programs, review) == 0
    assert programs["KHA:CLC2-03"]["in_scope"]                                  # CLC is another program
    assert [r["program_id"] for r in review.rows["site_duplicates_not_merged"]] == ["GSA:GHA32DS"]  # 21.94 vs 23.96
