"""Step 1's catalog: what can be picked, display names, search, strong-subject facts (on the fake database)."""

import pytest

from uniadvisor.app.catalog import Catalog, initials, search_key


@pytest.fixture
def cat(fake_db):
    return Catalog.load(fake_db)


def test_search_key_and_initials():
    assert search_key("Tài chính - Ngân hàng") == "tai chinh ngan hang"
    assert search_key("  Đại  học ") == "dai hoc"
    assert initials("Công nghệ thông tin") == "cntt"
    assert initials("Kỹ thuật điện tử - viễn thông") == "ktdtvt"
    assert initials("Luật") is None                                   # one word: no abbreviation
    assert initials("Một hai ba bốn năm sáu bảy") is None              # too long to have one


def test_only_codes_with_in_scope_programs(cat):
    assert set(cat.majors) == {"71402", "7140209", "72202", "7220201", "74801", "7480101", "7480103", "7480107",
                               "74802", "7480201", "77201", "7720101", "77203", "7720301"}
    cs = cat.majors["7480101"]
    assert (cs.n_programs, cs.n_programs_hn, cs.n_programs_hcm) == (2, 2, 0)   # OUT:CS is out of scope
    group = cat.majors["74801"]
    assert (group.n_programs, group.n_programs_hn, group.n_programs_hcm, group.n_with_cutoff) == (5, 4, 1, 4)
    assert group.children == ["7480101", "7480103", "7480107"]          # most programs first, then code


def test_labels(cat):
    assert cat.label("74801") == "Khoa học máy tính, Trí tuệ nhân tạo (AI), Kỹ thuật phần mềm"
    assert cat.official("74801") == "Máy tính"
    assert cat.label("7480107") == "Trí tuệ nhân tạo"                  # alias row without a display name
    assert cat.majors["77201"].display_status == "reviewed"
    assert cat.majors["7480201"].display_status is None
    assert cat.nganh_parents()["7480103"] == "74801"


def codes(hits):
    return [(h.code, h.tier) for h in hits]


def test_search_abbreviations_and_aliases(cat):
    assert codes(cat.search("KHMT")) == [("74801", 0), ("7480101", 0)]  # alias of the group, initials of the ngành
    assert codes(cat.search("cntt")) == [("7480201", 0), ("74802", 0)]  # same count: ngành first
    assert codes(cat.search("AI")) == [("74801", 0), ("7480107", 0)]
    assert codes(cat.search("bác sĩ")) == [("77201", 0)]
    assert codes(cat.search("bac si")) == [("77201", 0)]               # accents are optional


def test_search_prefix_words_and_program_names(cat):
    assert codes(cat.search("ky thuat phan")) == [("74801", 1), ("7480103", 1)]
    assert codes(cat.search("ngôn ngữ")) == [("72202", 0), ("7220201", 1)]   # a part of the official name
    assert codes(cat.search("tri tue")) == [("74801", 1), ("7480107", 1)]     # the group has more programs
    hits = cat.search("hệ quân sự")                                    # only in a school's program name
    assert codes(hits) == [("7480101", 3)] and hits[0].matched == "Khoa học máy tính (hệ quân sự)"
    assert cat.search("x") == [] and cat.search("   ") == []
    assert cat.search("không có ngành này") == []


def test_strong_subject_facts(cat):
    shares = cat.combo_shares("7480101")
    assert [(s.combo, s.subjects, s.n_programs, s.share) for s in shares] == [
        ("A00", ("Toán", "Vật lí", "Hóa học"), 2, 1.0), ("A01", ("Toán", "Vật lí", "Tiếng Anh"), 2, 1.0)]
    group = {s.combo: s.share for s in cat.combo_shares("74801")}
    assert group == {"A00": 1.0, "A01": 1.0, "D01": 0.2}               # SE accepts D01; 5 programs
    assert cat.subject_shares("7480201") == [("Hóa học", 1.0), ("Ngữ văn", 1.0), ("Tiếng Anh", 1.0),
                                             ("Toán", 1.0), ("Vật lí", 1.0)]
    assert cat.combo_shares("7140209")[0].combo == "A00"
