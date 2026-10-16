"""Part 4 chat questions: published program data, clear scope limits, and natural multi-request messages."""

from dataclasses import replace

import pytest

from uniadvisor.chat.classify import RuleClassifier
from uniadvisor.chat.pipeline import handle
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import PlanState, ShortlistEntry


STATE = PlanState(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội",
                  budget_trieu=32.0, shortlist=[ShortlistEntry("74801"), ShortlistEntry("7220201")])


@pytest.fixture(scope="module")
def data(fake_db_path):
    return AppData.load(fake_db_path)


@pytest.fixture
def ctx(data):
    return data.chat_context(STATE, data.build_list(STATE))


@pytest.fixture
def rules(data):
    return RuleClassifier(data.indexes.schools, data.indexes.nganh, set(data.subjects))


@pytest.mark.parametrize(("text", "kind"), [
    ("Học phí NV1 bao nhiêu?", "ask_tuition"),
    ("Điểm chuẩn NV1 là bao nhiêu?", "ask_cutoff"),
    ("NV1 xét tổ hợp nào?", "ask_combos"),
    ("Tỷ lệ có việc làm NV1 bao nhiêu?", "ask_employment"),
    ("FHN cộng IELTS thế nào?", "ask_extra_policy"),
    ("Khi nào đăng ký nguyện vọng?", "out_procedure"),
    ("FHN xét học bạ ra sao?", "out_admission_method"),
    ("Dự báo điểm chuẩn CNTT năm nay?", "out_forecast"),
    ("Em nên chọn trường nào?", "out_advice"),
])
def test_part4_rules_choose_the_right_read_only_or_scope_type(text, kind, rules):
    assert rules.classify(text)[0] == kind


def test_published_data_answers_by_wish(ctx, rules):
    tuition = handle("Học phí NV1 bao nhiêu?", ctx, rules).answers[0]
    cutoff = handle("Điểm chuẩn NV1 là bao nhiêu?", ctx, rules).answers[0]
    combos = handle("NV1 xét tổ hợp nào?", ctx, rules).answers[0]
    employment = handle("Tỷ lệ có việc làm NV1 bao nhiêu?", ctx, rules).answers[0]
    assert tuition.startswith("NV1:") and "Học phí:" in tuition
    assert cutoff.startswith("NV1:") and "phương thức điểm thi THPT" in cutoff and "2025:" in cutoff
    assert combos.startswith("NV1:") and "Tổ hợp xét tuyển:" in combos
    assert employment.startswith("NV1:") and "chưa có tỷ lệ có việc làm" in employment


def test_cutoff_question_honours_a_year_when_the_student_names_one(ctx, rules):
    answer = handle("Điểm chuẩn NV1 năm 2026 là bao nhiêu?", ctx, rules).answers[0]
    assert "2026:" in answer and "2025:" not in answer


def test_published_data_answers_by_school_and_major(ctx, rules):
    reply = handle("Học phí ngành Khoa học máy tính ở FHN bao nhiêu?", ctx, rules)
    assert reply.requests == [("Học phí ngành Khoa học máy tính ở FHN bao nhiêu?", "ask_tuition")]
    assert "Trường Đại học Giả Hà Nội · Khoa học máy tính" in reply.answers[0]
    assert "30-35 triệu/năm" in reply.answers[0]
    missing_school = handle("Tỷ lệ có việc làm ngành Khoa học máy tính bao nhiêu?", ctx, rules).answers[0]
    assert "trường nào" in missing_school


def test_employment_answer_never_infers_a_rate(ctx, rules):
    program = ctx.programs["HNA:CS1"]
    ctx.programs = {**ctx.programs, program.id: replace(program, employment=(0.952, 2024))}
    answer = handle("Tỷ lệ có việc làm ngành Khoa học máy tính ở FHN bao nhiêu?", ctx, rules).answers[0]
    assert "95% sinh viên có việc làm, khóa tốt nghiệp 2024" in answer


def test_extra_points_and_out_of_scope_answers_are_clear(ctx, rules):
    extra = handle("FHN cộng IELTS thế nào?", ctx, rules).answers[0]
    procedure = handle("Khi nào đăng ký nguyện vọng?", ctx, rules).answers[0]
    other_method = handle("FHN xét học bạ ra sao?", ctx, rules).answers[0]
    forecast = handle("Dự báo điểm chuẩn CNTT năm nay?", ctx, rules).answers[0]
    advice = handle("Em nên chọn trường nào?", ctx, rules).answers[0]
    assert "chưa lưu quy định điểm cộng" in extra and "đề án tuyển sinh chính thức" in extra
    assert "không theo dõi thủ tục hay lịch tuyển sinh" in procedure
    assert "chỉ lập danh sách theo điểm thi tốt nghiệp THPT" in other_method
    assert "không dự báo điểm chuẩn năm nay" in forecast
    assert "không thể quyết định thay em" in advice


def test_natural_multi_request_keeps_values_and_data_question_separate(ctx, rules):
    reply = handle("Toán em được tám phẩy hai lăm, ngân sách 35tr rồi học phí NV1 bao nhiêu?", ctx, rules)
    assert reply.requests == [
        ("Toán em được tám phẩy hai lăm", "change_score"),
        ("ngân sách 35tr", "change_budget"),
        ("học phí NV1 bao nhiêu?", "ask_tuition"),
    ]
    assert [(item.kind, item.params) for item in reply.items] == [
        ("set_score", {"subject": "TO", "value": 8.25}), ("set_budget", {"value": 35.0}),
    ]
    assert len(reply.answers) == 1 and "Học phí:" in reply.answers[0]
