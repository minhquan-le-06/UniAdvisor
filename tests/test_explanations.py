"""The explanation of a wish is a fixed template: a verdict by level, three number lines, why it is on the list, why it
sits at this position, notices.  Every case of docs/design/lists.md ("Explanations") has a test here."""

from dataclasses import replace
from types import SimpleNamespace

from uniadvisor.explanations import build_wish_explanation, verdict
from uniadvisor.planner.models import Cutoff, Level, Profile, ShortlistItem
from tests.test_list_explanations import Catalog, ctx_for, su_pham_list
from tests.test_planner_strategy import CUTOFF, STUDENT, full_pool, prog, run

ITEM = [ShortlistItem("7480201")]
FORBIDDEN = ("chắc đỗ", "chắc chắn", "chắc rớt", "hướng học 1", "tham chiếu", "điểm trường")


def explain(result, nv, codes=("7480201",), **state):
    ctx = ctx_for(result, list(codes), state=SimpleNamespace(**state) if state else None)
    return build_wish_explanation(next(w for w in result.wishes if w.nv == nv), ctx)


def one(program, profile=STUDENT, **state):
    result = run([program], ITEM, profile)
    return explain(result, 1, **state)


def years(a, b):
    return (Cutoff(2025, None, a, a, 30, False), Cutoff(2026, None, b, b, 30, False))


# ---------------------------------------------------------------- the verdict, by level and gap

def test_mo_uoc_says_how_many_points_are_missing():
    e = one(prog("A:1", cutoff=CUTOFF[Level.MO_UOC]))
    assert e.level == "mơ ước" and e.verdict.startswith("Khó đỗ: em thiếu 2,0 điểm so với điểm chuẩn 2026")
    assert e.numbers[2] == "Thiếu 2,0 điểm so với 2026"


def test_thu_suc_below_the_latest_cutoff_but_reached_the_year_before():
    e = one(prog("A:1", cutoffs=years(24.0, 25.0)))
    assert e.level == "thử sức"
    assert "Có thể đỗ nhưng chưa chắc: em thiếu 1,0 điểm so với điểm chuẩn 2026" in e.verdict
    assert "Em đã đạt điểm chuẩn năm 2025." in e.verdict


def test_thu_suc_reaching_the_latest_cutoff_but_not_the_higher_one_of_the_year_before():
    e = one(prog("A:1", cutoffs=years(25.0, 23.8)))
    assert e.level == "thử sức" and e.numbers[2] == "Dư 0,2 điểm so với 2026"
    assert "Em đạt điểm chuẩn 2026 nhưng thấp hơn điểm chuẩn 2025 (25,0)" in e.verdict


def test_vua_suc_and_an_toan_say_the_margin():
    close = one(prog("A:1", cutoff=CUTOFF[Level.VUA_SUC]))
    assert close.level == "vừa sức" and "dư 1,0 điểm nên còn sát" in close.verdict
    safe = one(prog("A:1", cutoff=CUTOFF[Level.AN_TOAN]))
    assert safe.level == "an toàn" and "Em dư 3,0 điểm" in safe.verdict and "dự phòng" in safe.verdict


def test_capped_mixed_method_keeps_vua_suc_and_says_why():
    e = one(prog("M:1", cutoff=21.0, mixed=True, tuition=30_000_000))
    assert e.level == "vừa sức" and "xét kết hợp" in e.verdict and "không xếp an toàn" in e.verdict
    assert e.notices == ()                                              # the cap is the verdict, not a second notice


def test_uncapped_mixed_method_gets_a_notice():
    e = one(prog("M:1", cutoff=24.5, mixed=True))
    assert any("xét kết hợp" in n for n in e.notices)


def test_one_year_converted_and_disputed_cutoffs_are_named():
    one_year = one(prog("A:1", cutoffs=(Cutoff(2026, None, 23.0, 23.0, 30, False),)))
    assert "Chỉ có điểm chuẩn năm 2026." in one_year.verdict
    converted = one(prog("A:1", cutoffs=(Cutoff(2025, None, 23.0, 23.0, 30, False),
                                         Cutoff(2026, None, 23.0, 76.67, 100, False))))
    assert "quy đổi từ 76,67/100 sang thang 30" in converted.verdict
    disputed = one(replace(prog("A:1", cutoff=23.0), disputes=((2026, "tuyensinh247", "24.5"),)))
    assert "Tuyensinh247 ghi điểm chuẩn 2026 là 24,5" in disputed.verdict


def test_the_students_own_corrections_are_named():
    shifted = one(prog("A:1", cutoff=23.0), replace(STUDENT, cutoff_shifts={"A": 1.0}))
    assert "Em đã chỉnh điểm chuẩn trường này +1,0 điểm." in shifted.verdict
    own = one(prog("A:1", cutoff=23.0), replace(STUDENT, own_scores={"A": (25.0, 30)}))
    assert "theo điểm em tự tính" in own.numbers[0]


def test_numbers_name_the_combination_and_the_extra_points():
    profile = replace(STUDENT, area="KV1", extra_points={"A": 0.5})
    e = one(prog("A:1", cutoff=23.0), profile)
    assert e.numbers[0].startswith("Điểm của em: 25,1 (A00") and "0,6 điểm ưu tiên" in e.numbers[0]
    assert "0,5 điểm cộng" in e.numbers[0]


def test_no_text_promises_an_admission():
    result = run(full_pool(n=4) + [prog("MX:1", cutoff=15.0, mixed=True)], ITEM)
    for w in result.wishes:
        text = explain(result, w.nv).markdown().casefold()
        assert not any(bad in text for bad in FORBIDDEN), (w.nv, text)


# ---------------------------------------------------------------- why it sits here

def test_first_wish_stands_first_because_it_is_harder_than_the_next():
    result = run(full_pool(n=4), ITEM)
    e = explain(result, 1)
    assert e.placement.startswith("Hệ thống xét từ NV1 xuống") and "Đứng đầu danh sách" in e.placement
    assert "trước NV2" in e.placement and "khó hơn" in e.placement


def test_a_middle_wish_names_its_neighbour_school():
    result = run(full_pool(n=4), ITEM)
    e = explain(result, 5)
    nxt = result.wishes[5].candidate.program.school_name
    assert f"trước NV6 ({nxt})" in e.placement


def test_two_equal_wishes_are_said_to_be_equal():
    a, b = prog("A:1", cutoff=24.5), prog("B:1", cutoff=24.5)
    result = run([a, b], ITEM)
    assert "Ngang độ khó với NV2" in explain(result, 1).placement


def test_last_unsafe_wish_points_to_the_safe_part_and_the_safe_wish_says_what_it_does_not_block():
    result = run(full_pool(n=4), ITEM)
    last_unsafe = max(w.nv for w in result.wishes if w.candidate.level != Level.AN_TOAN)
    assert f"Từ NV{last_unsafe + 1} trở đi là các nguyện vọng an toàn" in explain(result, last_unsafe).placement
    safe = explain(result, last_unsafe + 1).placement
    assert f"nếu không đạt {last_unsafe} nguyện vọng phía trên" in safe and "không chặn" in safe


def test_the_last_wish_of_a_list_without_safe_wishes():
    result = run(many_levels := [prog("A:1", cutoff=26.0), prog("B:1", cutoff=25.0)], ITEM)
    assert "Đây là nguyện vọng cuối danh sách." in explain(result, len(result.wishes)).placement


def test_teacher_training_first_names_the_regulation():
    result = su_pham_list()
    e = explain(result, 1, codes=("7140209",))
    assert "Quy chế chỉ cho xét ngành sư phạm ở 5 nguyện vọng đầu" in e.placement


def test_capped_mixed_method_sits_with_the_safe_part_by_real_difficulty():
    result = run(full_pool(n=2) + [prog("MX:1", cutoff=15.0, mixed=True)], ITEM)
    e = explain(result, len(result.wishes))
    assert e.level == "vừa sức" and "xếp cùng phần cuối" in e.placement


def test_top_up_safe_wish_says_it_was_added_for_safety():
    near = [p for lv in (Level.MO_UOC, Level.THU_SUC, Level.VUA_SUC) for p in full_pool(n=4)
            if lv.value[:2].upper() in p.id]
    top = prog("FC:7480101", moet="7480101", cutoff=CUTOFF[Level.AN_TOAN])
    result = run(near + [top], [ShortlistItem("7480201", (), ("7480101",))])
    w = next(w for w in result.wishes if w.candidate.relation == "further_close")
    e = explain(result, w.nv)
    assert "Được thêm vào cuối để danh sách đủ lựa chọn an toàn." in e.placement
    assert "thêm vào để đủ lựa chọn an toàn" in e.why_in_list


def test_second_hướng_sits_after_the_first_ones_unsafe_wishes():
    a = [p for p in full_pool(n=3)]
    b = [prog(f"B{i}:7220201", "7220201", 25.0 - i * 0.2) for i in range(3)]
    result = run(a + b, [ShortlistItem("7480201"), ShortlistItem("7220201")])
    second = next(w for w in result.wishes if w.candidate.item_index == 1 and w.candidate.level != Level.AN_TOAN)
    e = explain(result, second.nv, codes=("7480201", "7220201"))
    assert "nằm sau các nguyện vọng chưa an toàn của hướng 7480201" in e.placement or \
           "nằm sau các nguyện vọng chưa an toàn của hướng" in e.placement


# ---------------------------------------------------------------- why it is on the list

def test_relation_sentences():
    result = run(full_pool(n=2), ITEM)
    main = explain(result, 1)
    assert main.why_in_list.startswith("Đây là ngành em chọn: 7480201.") or "Đây là ngành em chọn" in main.why_in_list


def test_each_phuong_an_adds_its_own_sentence():
    result = run([prog("A:1", cutoff=24.5, tuition=30_000_000)], ITEM)
    nganh = explain(result, 1, list_choice="dung_nganh").why_in_list
    assert "đúng ngành hơn các lựa chọn khác ở cùng mức" in nganh
    career = explain(result, 1, list_choice="nghe_nghiep", answers={"q1": 1}).why_in_list
    assert "hợp với câu trả lời 12 câu hỏi" in career
    cleared = explain(result, 1, list_choice="nghe_nghiep", answers={}).why_in_list      # built as Hợp môn học nhất
    assert "xét tổ hợp" in cleared and "24,0/30" in cleared
    cost = explain(result, 1, list_choice="tiet_kiem").why_in_list
    assert "Học phí khoảng 30 triệu/năm" in cost
    assert "đúng ngành hơn" not in explain(result, 1).why_in_list                        # no phương án chosen yet


def test_cost_phuong_an_names_unknown_and_free_fees():
    unknown = explain(run([prog("A:1", cutoff=24.5)], ITEM), 1, list_choice="tiet_kiem")
    assert "Chưa rõ học phí." in unknown.why_in_list and not unknown.notices
    free = replace(prog("A:1", cutoff=24.5, tuition=0), tuition_basis="free")
    e = explain(run([free], ITEM), 1, list_choice="tiet_kiem")
    assert "Miễn học phí (trường tuyển riêng" in e.why_in_list


# ---------------------------------------------------------------- notices

def test_notices_for_budget_distance_fee_codes_and_rate():
    far = prog("A:1", cutoff=24.5, city="HCM", tuition=60_000_000)
    far = replace(far, employment=(0.952, 2024))
    profile = replace(STUDENT, budget_trieu=40.0, near_home=True)
    e = one(far, profile, budget_trieu=40.0)
    assert "Học phí 60 triệu/năm cao hơn ngân sách 40 triệu em đặt." in e.notices
    assert any("xa nhà" in n for n in e.notices)
    assert "Trường công bố tỷ lệ có việc làm 95% (khóa tốt nghiệp 2024)." in e.notices
    assert any("Chưa có học phí" in n for n in one(prog("B:1", cutoff=24.5)).notices)
    a = replace(prog("D:1", cutoff=23.0), name="Kỹ thuật phần mềm")
    b = replace(prog("D:2", cutoff=22.5), name="Kỹ thuật phần mềm")
    merged = explain(run([a, b], ITEM), 1)
    assert any("Cùng chương trình với mã 1" in n for n in merged.notices)


def test_the_two_surfaces_share_one_text():
    result = run(full_pool(n=2), ITEM)
    e = explain(result, 3, list_choice="dung_nganh")
    page, chat = e.markdown(), e.chat_text()
    for piece in (e.verdict, e.why_in_list, e.placement):
        assert piece in page and piece in chat
    assert page.startswith("**NV3 · ") and "- Điểm của em:" in page and "**Vì sao ở vị trí này:**" in page
