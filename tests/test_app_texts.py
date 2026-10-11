"""The list view's text templates (spec 4.6), on lists built from the fake database."""

import pytest

from uniadvisor.app.catalog import Catalog
from uniadvisor.app.texts import employment_text, favorite_note, note_texts, num, trieu, wish_rows
from uniadvisor.config import load_list_config, load_provinces, load_rules
from uniadvisor.plan.models import Profile, ShortlistItem
from uniadvisor.plan.repository import load_nganh_parents, load_programs
from uniadvisor.plan.strategy import build_list


@pytest.mark.parametrize("x, text", [(24.5, "24,5"), (25, "25,0"), (25.125, "25,13"), (0.43, "0,43"),
                                     (24.004, "24,0"), (23.995, "24,0"), (8.25, "8,25")])
def test_num(x, text):
    assert num(x) == text


def test_trieu():
    assert trieu(24_000_000) == "24" and trieu(25_600_000) == "25,6" and trieu(19_250_000) == "19,3"


@pytest.fixture
def setting(fake_db):
    return Catalog.load(fake_db), load_programs(fake_db), load_nganh_parents(fake_db)


def rows_for(setting, profile, shortlist):
    cat, programs, parents = setting
    result = build_list(profile, shortlist, programs, parents, load_rules(2027), load_list_config(),
                        load_provinces(), 2027)
    codes = [i.main_code for i in shortlist]
    return result, {r["Chương trình"]: r for r in wish_rows(result, codes, cat)}, note_texts(result, codes, cat)


def test_wish_rows(setting):
    profile = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội",
                      area="KV2", budget_trieu=30, near_home=True)
    result, rows, notes = rows_for(setting, profile, [ShortlistItem("74801", ("7480201",))])
    ktpm = rows["Kỹ thuật phần mềm *"]                    # HCB:KTPM, mixed method, 100-point 2026 cutoff
    assert ktpm["Trường"] == "Trường Đại học Giả TP.HCM"
    assert ktpm["Ngành (tên Bộ GD&ĐT)"] == "Kỹ thuật phần mềm"
    assert ktpm["Hướng học"] == "1 · trong nhóm ngành đã chọn"
    assert ktpm["Điểm của em · điểm chuẩn"] == (
        "23,23 (A01, đã gồm 0,23 điểm ưu tiên) · 24,5 (2025) · 24,0 (2026, quy đổi từ 80/100, xét kết hợp)")
    assert ktpm["Học phí"] == "học phí chưa rõ"
    assert ktpm["Thành phố"] == "TP.HCM · xa nhà"
    assert "Việc làm" not in ktpm                         # no school in the list states an employment rate
    cs1 = rows["Khoa học máy tính"]
    assert cs1["Học phí"] == "30-35 triệu/năm (năm 2026) · vượt ngân sách" and cs1["Thành phố"] == "Hà Nội"
    # another site gives 24.5 for 2026 (the chosen value is 24.2); 2025 agrees, so nothing is said
    assert cs1["Điểm của em · điểm chuẩn"].endswith("25,0 (2025) · 24,2 (2026, nguồn khác: Tuyensinh247 ghi 24,5)")
    assert cs1["Mức"] in {"mơ ước", "thử sức", "vừa sức", "an toàn"}
    assert rows["Công nghệ thông tin"]["Hướng học"] == "1 · ngành gần của Khoa học máy tính, Trí tuệ nhân tạo (AI), " \
                                                      "Kỹ thuật phần mềm"
    assert [r["NV"] for r in wish_rows(result, ["74801"], setting[0])] == list(range(1, len(result.wishes) + 1))
    assert notes[-1].startswith(f"Danh sách chỉ có {len(result.wishes)} nguyện vọng")
    assert any("chuyển xuống mức an toàn hơn" in n for n in notes)


def test_main_relation_and_no_priority(setting):
    profile = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0}, home_province="Hà Nội")
    _, rows, _ = rows_for(setting, profile, [ShortlistItem("7480101")])
    assert rows["Khoa học máy tính"]["Hướng học"] == "1 · ngành chính"
    assert rows["Khoa học máy tính"]["Điểm của em · điểm chuẩn"].startswith("23,0 (A01) · ")


def test_tuition_text_marks_converted_and_free():
    from dataclasses import replace
    from types import SimpleNamespace

    from uniadvisor.app.texts import tuition_text
    from uniadvisor.plan.models import ProgramFacts

    p = ProgramFacts("X:1", "X", "Trường X", "Ngành", "7480201", "HN", {}, (), 27_000_000, 27_000_000, 2026)
    c = SimpleNamespace(program=p, over_budget=False)
    assert tuition_text(c) == "27 triệu/năm (năm 2026)"
    c.program = replace(p, tuition_basis="semesters_per_year_owner_rule")
    assert tuition_text(c) == "khoảng 27 triệu/năm (năm 2026, ước tính từ học phí mỗi học kỳ, 2 học kỳ/năm)"
    c.program = replace(p, tuition_min_vnd=0, tuition_max_vnd=0, tuition_year=None, tuition_basis="free")
    assert tuition_text(c) == "miễn học phí"


def test_favorite_school_texts(setting):
    # HCB's Điều dưỡng (B00, cutoffs 19 / 18) is an toàn for this student: another ngành, taken for the safe slots
    profile = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "SI": 8.0, "N1": 8.0, "VA": 7.0},
                      home_province="Hà Nội", favorite_school="HCB")
    result, rows, _ = rows_for(setting, profile, [ShortlistItem("7480101")])
    fav = [w for w in result.wishes if w.candidate.favorite]
    assert [w.candidate.program.id for w in fav if w.candidate.relation == "favorite_school"] == ["HCB:DD"]
    assert rows["Điều dưỡng"]["Hướng học"] == "1 · trường yêu thích · ngành khác"
    note = favorite_note("Trường Đại học Giả TP.HCM", result)
    assert note.startswith("Vì em chọn Trường Đại học Giả TP.HCM là trường thích nhất")
    assert "là ngành khác ngành em chọn" in note
    nothing = favorite_note("X", type(result)([], [], []))
    assert nothing == "X (trường em thích nhất) không có chương trình nào phù hợp với hướng học và điểm của em để đưa "                       "vào danh sách."


def test_correction_texts(setting):
    profile = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội",
                      area="KV2", own_scores={"HCB": (90.0, 100)}, cutoff_shifts={"HCB": 0.5})
    _, rows, _ = rows_for(setting, profile, [ShortlistItem("74801", ("7480201",))])
    assert rows["Kỹ thuật phần mềm *"]["Điểm của em · điểm chuẩn"] == (
        "27,0 (theo điểm em tự tính 90/100) · 24,0 (2026, quy đổi từ 80/100, xét kết hợp) · em đã điều chỉnh điểm "
        "chuẩn của trường này cao hơn 0,5 điểm so với điểm công bố")


def test_employment_text(setting):
    from dataclasses import replace
    _, programs, _ = setting
    profile = Profile(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội")
    result, _, _ = rows_for(setting, profile, [ShortlistItem("74801", ("7480201",))])
    c = result.wishes[0].candidate
    assert employment_text(c) == "chưa rõ"
    c = replace(c, program=replace(c.program, employment=(0.952, 2024)))
    assert employment_text(c) == "95% có việc làm (khóa tốt nghiệp 2024)"


def test_disliked_answers_read_as_dislikes_in_reasons():
    from uniadvisor.app.discover import _reason_label
    from uniadvisor.suggest.questions import load_questionnaire
    qn = load_questionnaire()
    label = {(q.id, o.code): _reason_label(q, o) for q in qn.questions for o in q.options}
    assert label[("q1", "TO")] == "Toán" and label[("q2", "SU")] == "không thích Lịch sử"
    assert label[("q7", "health")].startswith("không muốn học ")
    assert label[("q12", "night_shift")] == "không muốn làm ca đêm"
