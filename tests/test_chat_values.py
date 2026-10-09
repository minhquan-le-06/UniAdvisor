"""The chat's value extraction (spec 9: "the chat's value extraction has unit tests"): numbers and names."""

import pytest

from uniadvisor.chat.mentions import (
    SchoolIndex, find_area, find_category, find_levels, find_nv, find_subjects, prefer_nganh,
)
from uniadvisor.chat.numbers import find_numbers, normalise


def nums(text):
    return [(n.value, n.unit, n.weak) for n in find_numbers(normalise(text))]


@pytest.mark.parametrize("text, expected", [
    ("Toán em được 8,5", [(8.5, None, False)]),
    ("toán 8.25", [(8.25, None, False)]),
    ("ngân sách 40tr", [(40.0, "trieu", False)]),
    ("1tr5 thôi", [(1.5, "trieu", False)]),
    ("ba mươi củ", [(30, "trieu", False)]),
    ("bốn mươi triệu", [(40, "trieu", False)]),
    ("hai mươi lăm điểm", [(25, "diem", False)]),
    ("mười lăm triệu", [(15, "trieu", False)]),
    ("hai mươi mốt", [(21, None, False)]),
    ("một trăm linh năm", [(105, None, False)]),
    ("tám phẩy hai lăm", [(8.25, None, False)]),
    ("toan tam phay nam", [(8.5, None, False)]),
    ("văn tám rưỡi", [(8.5, None, False)]),
    ("cộng 1.5 điểm", [(1.5, "diem", False)]),
    ("40 k", [(40.0, "nghin", False)]),
    ("40 triệu một năm", [(40.0, "trieu", False), (1, None, True), (5, None, True)]),   # weak: 'một', 'năm'
    ("NV12", []),                                            # wish numbers are found by find_nv, not here
    ("kv2", []),
    ("không có gì", [(0, None, False)]),
])
def test_numbers(text, expected):
    assert nums(text) == expected


def subjects(text):
    return [(m.values[0], m.text) for m in find_subjects(text)]


def test_subjects_need_a_score_when_the_word_is_ambiguous():
    assert subjects("Toán em được 8,5 còn văn 7") == [("TO", "Toán"), ("VA", "văn")]
    assert subjects("toan tam phay nam, ly 7") == [("TO", "toan"), ("LI", "ly")]
    assert subjects("Tiếng Anh 9 điểm") == [("N1", "Tiếng Anh")]
    assert subjects("em thích văn học") == []                 # 'văn' without a score is not a subject
    assert subjects("em học tốt môn Hóa học") == [("HO", "Hóa học")]
    assert find_subjects("toán 8", known={"VA"}) == []         # only the app's subjects


def test_area_category_nv_level():
    assert [m.values[0] for m in find_area("em ở kv2-nt")] == ["KV2-NT"]
    assert [m.values[0] for m in find_area("Khu vực 2 nông thôn")] == ["KV2-NT"]
    assert [m.values[0] for m in find_area("KV1 và kv3")] == ["KV1", "KV3"]
    assert find_area("kv1-nt") == []                          # only KV2 has a nông thôn variant
    assert [m.values[0] for m in find_category("đối tượng 06")] == ["UT2"]
    assert [m.values[0] for m in find_category("nhóm đối tượng 04")] == ["UT1"]
    assert [m.values[0] for m in find_category("UT1")] == ["UT1"]
    assert [m.values[0] for m in find_category("ưu tiên 2")] == ["UT2"]
    assert [m.values[0] for m in find_category("em không thuộc diện ưu tiên")] == ["none"]
    assert [m.values[0] for m in find_nv("vì sao NV3 ở đó, còn nguyện vọng số 12")] == ["3", "12"]
    assert [m.values[0] for m in find_levels("thử sức với an toan khác gì")] == ["thu_suc", "an_toan"]


SCHOOLS = {"BKA": "Trường Đại học Bách Khoa Hà Nội", "QSB": "Trường Đại học Bách Khoa - Đại học Quốc gia TP.HCM",
           "KHA": "Trường Đại học Kinh tế Quốc dân", "KSA": "Trường Đại học Kinh tế tp. Hồ Chí Minh",
           "NHF": "Trường Đại học Hà Nội", "NHH": "Học viện Ngân hàng (Cơ sở Hà Nội)"}


@pytest.fixture
def schools():
    return SchoolIndex(SCHOOLS, {"ha noi", "nghe an"}, {"KHA": ["NEU"], "QSB": ["Bách khoa TP.HCM", "HCMUT"]})


def found(index, text):
    return [(m.values, m.text) for m in index.find(text)]


def test_school_names(schools):
    assert found(schools, "bỏ Bách khoa Hà Nội") == [(("BKA",), "Bách khoa Hà Nội")]
    assert found(schools, "bỏ trường Bách khoa") == [(("BKA", "QSB"), "Bách khoa")]      # ambiguous: asked on the card
    assert found(schools, "sao không có Kinh tế Quốc dân") == [(("KHA",), "Kinh tế Quốc dân")]
    assert found(schools, "đại học ktqd") == [(("KHA",), "ktqd")]                       # first letters
    assert found(schools, "Kinh tế tp HCM") == [(("KSA",), "Kinh tế tp HCM")]
    assert found(schools, "Kinh tế Sài Gòn") == [(("KSA",), "Kinh tế Sài Gòn")]         # another way to write the city
    assert found(schools, "Học viện Ngân hàng") == [(("NHH",), "Ngân hàng")]


def test_school_aliases_and_codes(schools):
    assert found(schools, "NEU cộng 1 điểm") == [(("KHA",), "NEU")]
    assert found(schools, "neu em được cộng") == []                                     # 'neu' = 'nếu' without accents
    assert found(schools, "Bách khoa TP.HCM") == [(("QSB",), "Bách khoa TP HCM")]
    assert found(schools, "bỏ BKA") == [(("BKA",), "BKA")]
    assert found(schools, "bka") == []                                                  # codes only in capitals


def test_place_names_are_not_schools(schools):
    assert found(schools, "em ở Hà Nội") == []                                          # NHF's short name is a city
    assert found(schools, "trường Hà Nội") == [(("NHF",), "Hà Nội")]


def test_nganh_names(fake_db):
    from uniadvisor.app.catalog import Catalog
    from uniadvisor.chat.mentions import NganhIndex
    cat = Catalog.load(fake_db)
    index = NganhIndex(cat)
    hits = index.find("thay KHMT bằng AI")
    assert [(m.values, m.text) for m in hits] == [(("74801", "7480101"), "KHMT"), (("74801", "7480107"), "AI")]
    assert prefer_nganh(hits[0].values, cat) == ("7480101",)
    assert [m.values for m in index.find("ai học được")] == []                          # 'ai' = "who"
    assert [m.values for m in index.find("ngành Kỹ thuật phần mềm học gì")] == [("74801", "7480103")]
    assert prefer_nganh(("7480101", "7480103"), cat) == ("7480101", "7480103")         # two ngành stay ambiguous
