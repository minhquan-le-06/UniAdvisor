"""What the three lists give and cost, in words (docs/design/lists.md, "Explaining the three lists"): one test per case."""

from dataclasses import replace
from types import SimpleNamespace

from uniadvisor.planner.lists import Priority, Recommended
from uniadvisor.planner.models import Level, ShortlistItem
from uniadvisor.planner.models import Level
from uniadvisor.ui.list_summary import build_summary, choose_best, metrics
from tests.test_planner_strategy import STUDENT, full_pool, many, prog, run

ITEM = [ShortlistItem("7480201", close_codes=("7480101",))]
LABEL = {"7480101": "Khoa học máy tính", "7480201": "Công nghệ thông tin"}.get


def rec(priority, programs, shortlist=ITEM, profile=STUDENT, none=0.0, floor_met=True, chances=True):
    result = run(programs, shortlist, profile)
    ch = SimpleNamespace(none=none) if chances else None
    return Recommended(priority, result, [], ch, None, floor_met)


def summary(recs, **kw):
    args = dict(budget_trieu=None, floor=0.05, cap=0.99, similar=0.7, label=lambda c: LABEL(c, c))
    args.update(kw)
    return build_summary(recs, **args)


def three(own=None, cheap=None, aim=None):
    """Three lists that differ: the chosen ngành with dear fees, close ngành, and the same ngành with cheap fees."""
    dear = rec(Priority.NGANH, full_pool(n=5, tuition=50_000_000))
    near = rec(Priority.CAREER, full_pool(n=5, moet="7480101", tuition=30_000_000))
    cheap_ = rec(Priority.COST, [replace(p, id=p.id.replace(":", "z:"), school_code=p.school_code + "z")
                                 for p in full_pool(n=5, tuition=20_000_000)])
    return [dear, near, cheap_]


# ---------------------------------------------------------------- the metrics

def test_metrics_count_the_wishes_of_the_chosen_ngành_the_usual_fee_and_the_aim():
    m = metrics(rec(Priority.NGANH, full_pool(n=5, tuition=50_000_000)))
    assert (m.n, m.in_group, m.fee_median, m.fee_known, m.fee_unknown, m.fee_free) == (15, 15, 50.0, 15, 0, 0)
    assert m.aim_low <= m.aim_high and m.reach == 24.0
    assert metrics(rec(Priority.NGANH, [])) is None


def test_free_programs_are_counted_apart_from_the_usual_fee():
    free = [replace(p, tuition_basis="free", tuition_max_vnd=0) for p in many("F", Level.VUA_SUC, 2)]
    m = metrics(rec(Priority.COST, full_pool(n=3, tuition=40_000_000) + free))
    assert m.fee_free >= 1 and m.fee_median == 40.0


# ---------------------------------------------------------------- cards: Được / Đổi lại

def test_each_list_gets_good_and_bad_lines_where_it_is_best_and_worst():
    cards = {c.priority: c for c in summary(three()).cards}
    assert any("15/15 nguyện vọng đúng ngành" in s for s in cards[Priority.NGANH].good)
    assert any("Chỉ 0/15 nguyện vọng đúng ngành" in s for s in cards[Priority.CAREER].bad)
    assert any("Học phí thường ~20 triệu/năm, thấp hơn ~30 triệu so với phương án đắt nhất" in s
               for s in cards[Priority.COST].good)
    assert any("Học phí thường ~50 triệu/năm, cao hơn ~30 triệu so với phương án rẻ nhất" in s
               for s in cards[Priority.NGANH].bad)
    assert all(len(c.good) <= 2 and len(c.bad) <= 2 for c in cards.values())


def test_small_differences_make_no_good_or_bad_line():
    a = rec(Priority.NGANH, full_pool(n=5, tuition=30_000_000))
    b = rec(Priority.COST, full_pool(n=5, tuition=31_000_000))
    cards = summary([a, b]).cards
    assert not any("Học phí" in s for c in cards for s in c.good + c.bad)


def test_fee_lines_need_enough_known_fees():
    a = rec(Priority.NGANH, full_pool(n=1, tuition=50_000_000)[:4])
    b = rec(Priority.COST, full_pool(n=1, tuition=10_000_000)[:4])
    assert not any("Học phí" in s for c in summary([a, b]).cards for s in c.good + c.bad)


def test_career_list_names_the_close_ngành_it_adds():
    near = rec(Priority.CAREER, full_pool(n=5) + full_pool(n=5, moet="7480101"))
    card = summary([rec(Priority.NGANH, full_pool(n=5)), near, rec(Priority.COST, full_pool(n=5))]).cards[1]
    assert card.name == "Hợp sở thích nhất" and "Có thêm ngành gần hợp câu trả lời của em" in card.good[0]


def test_subject_list_names_the_combination():
    card = summary([rec(Priority.NGANH, full_pool(n=5)), rec(Priority.MON, full_pool(n=5))]).cards[1]
    assert card.name == "Hợp môn học nhất" and "tổ hợp" in card.good[0]


# ---------------------------------------------------------------- nearly the same lists

def test_a_list_that_repeats_another_is_said_so_without_good_and_bad_lines():
    a = rec(Priority.NGANH, full_pool(n=5, tuition=40_000_000))
    b = rec(Priority.COST, full_pool(n=5, tuition=40_000_000))
    s = summary([a, b])
    assert s.cards[1].same_as == "Giống “Đúng ngành nhất”: cùng các chương trình."
    assert summary([a, b, rec(Priority.MON, full_pool(n=5, tuition=40_000_000))]).notes      # all three alike


def test_a_list_that_nearly_repeats_another_names_the_difference():
    base = full_pool(n=5, tuition=40_000_000)
    a = rec(Priority.NGANH, base)
    swapped = [replace(p, tuition_max_vnd=10_000_000) if i < 5 else p for i, p in enumerate(base)]
    b = rec(Priority.COST, swapped)
    text = summary([a, b], similar=0.6).cards[1].same_as
    assert text is None or text.startswith(("Giống", "Gần giống"))


# ---------------------------------------------------------------- budget and fees

def test_cost_list_without_a_budget_says_how_it_ranks():
    notes = summary(three()).cards[2].notes
    assert any("chưa đặt ngân sách" in n for n in notes)


def test_cost_list_with_a_budget_counts_what_it_dropped():
    programs = full_pool(n=5, tuition=20_000_000) + [prog("X:1", cutoff=24.5, tuition=90_000_000)]
    profile = replace(STUDENT, budget_trieu=30.0)
    r = rec(Priority.COST, programs, profile=profile)
    r = replace(r, result=replace(r.result, excluded=list(r.result.excluded) + [
        SimpleNamespace(reason="over_budget"), SimpleNamespace(reason="over_budget")]))
    notes = summary([rec(Priority.NGANH, programs, profile=profile), r], budget_trieu=30.0).cards[1].notes
    assert any("Đã bỏ 2 chương trình có học phí cao hơn ngân sách 30 triệu/năm" in n for n in notes)


def test_other_lists_count_wishes_over_the_budget_but_keep_them():
    programs = full_pool(n=2, tuition=20_000_000) + [prog("X:1", cutoff=24.5, tuition=90_000_000)]
    r = rec(Priority.NGANH, programs, profile=replace(STUDENT, budget_trieu=30.0))
    note = next(n for n in summary([r], budget_trieu=30.0).cards[0].notes if "cao hơn ngân sách" in n)
    assert note.startswith("1 nguyện vọng có học phí cao hơn ngân sách 30 triệu/năm")


def test_a_budget_that_fits_nothing_blocks_the_cost_card():
    empty = rec(Priority.COST, [])
    card = summary([rec(Priority.NGANH, full_pool(n=5)), empty], budget_trieu=10.0).cards[1]
    assert "Không có chương trình nào trong ngân sách 10 triệu/năm" in card.blocked
    assert summary([empty]).cards[0].blocked == "Chưa có nguyện vọng nào phù hợp với phương án này."


def test_short_lists_say_how_many_wishes_there_are():
    r = rec(Priority.COST, full_pool(n=1)[:4])
    notes = summary([r], budget_trieu=30.0).cards[0].notes
    assert "Chỉ có 4/15 nguyện vọng." in notes and "Ít lựa chọn nên danh sách chưa đủ rộng." in notes
    assert any("Chỉ tìm được 4 nguyện vọng trong ngân sách 30 triệu/năm" in n for n in notes)


def test_unknown_and_free_fees_are_named():
    unknown = rec(Priority.NGANH, full_pool(n=5))                              # no fee at all: every wish unknown
    assert any("15/15 nguyện vọng chưa rõ học phí" in n for n in summary([unknown]).cards[0].notes)
    free = [replace(p, tuition_basis="free", tuition_max_vnd=0) for p in full_pool(n=5)]
    assert any("miễn học phí (trường tuyển riêng" in n for n in summary([rec(Priority.COST, free)]).cards[0].notes)


# ---------------------------------------------------------------- the first wishes

def test_programs_over_four_points_away_are_not_in_the_cards_wishes():
    far = [prog(f"H{i}:7480201", cutoff=30.0 - i * 0.1) for i in range(6)] + [prog("N:7480201", cutoff=26.0)]
    r = rec(Priority.NGANH, far)
    assert [w.candidate.program.id for w in r.result.wishes] == ["N:7480201"]
    assert {e.reason for e in r.result.excluded} == {"too_hard"}
    assert not any("rất khó" in n for n in summary([r]).cards[0].notes)


def test_a_student_who_reaches_the_first_three_wishes_is_told():
    easy = [prog(f"E{i}:7480201", cutoff=20.0 - i * 0.1) for i in range(6)]
    assert any("Em đạt điểm chuẩn cả 3 nguyện vọng đầu" in n for n in summary([rec(Priority.NGANH, easy)]).cards[0].notes)


# ---------------------------------------------------------------- the structure of a list

def test_top_up_shift_down_teacher_and_two_hướng_and_favorite_notes():
    wide = rec(Priority.NGANH, full_pool(n=5) + [prog("W:7480101", "7480101", 20.0)])
    r = replace(wide, result=replace(wide.result, notes=["shifted_down:1:mo_uoc:2", "shifted_down:1:thu_suc:1",
                                                         "topped_up:1:1", "teacher_training_first:3"]))
    notes = summary([r], favorite="Trường A", item_labels=("Công nghệ thông tin", "Y khoa")).cards[0].notes
    assert any("Thiếu chương trình ở mức mơ ước và thử sức nên 3 chỗ được chuyển xuống mức an toàn hơn" in n for n in notes)
    assert any("Đã thêm nguyện vọng an toàn của ngành gần" in n for n in notes)
    assert any("3 nguyện vọng sư phạm đặt đầu danh sách" in n for n in notes)
    assert any("tính cả hai hướng: Công nghệ thông tin và Y khoa" in n for n in notes)
    assert any("Trường Trường A đứng đầu mỗi mức" in n for n in notes)


# ---------------------------------------------------------------- the safety line

def test_safe_line_only_when_every_list_meets_the_floor_with_a_model():
    ok = three()
    assert summary(ok).safe_line == "Cả 3 phương án đều đủ nguyện vọng an toàn (khả năng đỗ ít nhất 1 nguyện vọng ≥ 95%)."
    risky = [replace(ok[0], chances=SimpleNamespace(none=0.3), floor_met=False)] + ok[1:]
    s = summary(risky)
    assert s.safe_line is None
    assert "chỉ 70%, dưới mức an toàn 95%: không còn chương trình an toàn nào để thêm" in s.cards[0].warning
    assert s.cards[1].warning is None
    no_model = [replace(r, chances=None) for r in ok]
    assert summary(no_model).safe_line is None and summary(no_model).cards[0].warning is None


def test_the_safe_percentage_is_capped():
    ok = three()
    risky = [replace(ok[0], chances=SimpleNamespace(none=0.003), floor_met=False)] + ok[1:]
    assert "≥ 99%" in summary(risky).cards[0].warning


# ---------------------------------------------------------------- the list the pentagons favour

def with_pentagon(priority, values, floor_met=True, programs=None):
    base = rec(priority, programs or full_pool(n=5), floor_met=floor_met)
    return replace(base, pentagon=SimpleNamespace(values=values, unknown={}, none=0.0))


def corners(hop=1.0, cao=0.5, nganh=1.0, phi=0.5, nghe=None):
    return {"hop_mon": hop, "nguyen_vong_cao": cao, "dung_nganh": nganh, "hoc_phi": phi, "nghe_nghiep": nghe}


def test_the_fee_corner_counts_only_when_a_budget_was_given():
    dear = with_pentagon(Priority.NGANH, corners(phi=0.2, cao=0.5))
    cheap = with_pentagon(Priority.COST, corners(phi=0.9, cao=0.4))
    assert choose_best([dear, cheap], budget_trieu=None).priority is Priority.NGANH     # fees do not decide
    best = choose_best([dear, cheap], budget_trieu=30.0)
    assert best.priority is Priority.COST and "Học phí thấp hơn (trong ngân sách 30 triệu)" in best.reason


def test_the_career_corner_counts_double_when_the_questions_were_answered():
    a = with_pentagon(Priority.NGANH, corners(nghe=0.2))
    b = with_pentagon(Priority.CAREER, corners(cao=0.45, nghe=0.9))
    best = choose_best([a, b], budget_trieu=None)
    assert best.priority is Priority.CAREER and best.reason == "Hợp câu trả lời của em hơn so với các phương án còn lại."


def test_a_list_below_the_safety_floor_is_passed_over_while_another_is_fit():
    risky = with_pentagon(Priority.NGANH, corners(cao=1.0), floor_met=False)
    safe = with_pentagon(Priority.COST, corners(cao=0.3))
    assert choose_best([risky, safe], budget_trieu=None).priority is Priority.COST
    assert choose_best([risky], budget_trieu=None).priority is Priority.NGANH               # the only one there is


def test_tied_lists_go_by_the_fixed_order_and_the_sentence_says_so():
    a = with_pentagon(Priority.COST, corners())
    b = with_pentagon(Priority.NGANH, corners(cao=0.51))
    best = choose_best([a, b], budget_trieu=None)
    assert best.priority is Priority.NGANH
    assert best.reason == "Các phương án gần như ngang nhau, nên ưu tiên phương án bám sát ngành em chọn nhất."
    base, spread = corners(hop=0.9, cao=0.5, nganh=0.9), corners(hop=0.94, cao=0.54, nganh=0.94)   # +0.04 in each: no lead of 0.05
    ahead = choose_best([with_pentagon(Priority.NGANH, base), with_pentagon(Priority.COST, spread)], budget_trieu=None)
    assert ahead.priority is Priority.COST and ahead.reason.startswith("Phương án có điểm tổng hợp cao nhất")


def test_the_sentence_names_up_to_two_corners_the_pick_leads_in():
    a = with_pentagon(Priority.NGANH, corners(hop=1.0, cao=0.9, nganh=1.0, phi=0.9))
    b = with_pentagon(Priority.COST, corners(hop=0.7, cao=0.3, nganh=0.6, phi=0.9))
    best = choose_best([a, b], budget_trieu=None)
    assert best.priority is Priority.NGANH
    assert best.reason.count(" và ") == 1 and best.reason.endswith("so với các phương án còn lại.")
    assert "đúng ngành em chọn hơn" in best.reason.casefold() and "hợp tổ hợp môn mạnh nhất của em hơn" in best.reason
    assert "cao hơn mức điểm" not in best.reason                    # the ambition corner weighs 0.25, so it ranks last


def test_a_modest_lead_in_the_ambition_corner_no_longer_decides():
    cheap_but_ambitious = with_pentagon(Priority.COST, corners(cao=0.96))
    right_ngành = with_pentagon(Priority.NGANH, corners(cao=0.80))      # at weight 1 this 0.16 would have decided it
    assert choose_best([right_ngành, cheap_but_ambitious], budget_trieu=None).priority is Priority.NGANH


def test_a_single_fit_list_and_no_list_at_all():
    only = with_pentagon(Priority.NGANH, corners())
    assert choose_best([only, with_pentagon(Priority.COST, corners(), floor_met=False)],
                       budget_trieu=None).reason == "Đây là phương án duy nhất đủ nguyện vọng an toàn."
    assert choose_best([rec(Priority.NGANH, [])], budget_trieu=None) is None
    assert choose_best([], budget_trieu=None) is None


def test_the_summary_carries_the_pick():
    ok = [with_pentagon(Priority.NGANH, corners(cao=0.9)), with_pentagon(Priority.COST, corners(cao=0.2))]
    assert summary(ok).pick.name == "Đúng ngành nhất"


def test_the_ambition_corner_does_not_count_at_all():
    most_ambitious = with_pentagon(Priority.COST, corners(cao=1.0))
    other = with_pentagon(Priority.NGANH, corners(cao=0.0))
    best = choose_best([other, most_ambitious], budget_trieu=None)      # same everywhere else: a tie, the fixed order wins
    assert best.priority is Priority.NGANH and best.scores[Priority.COST] == best.scores[Priority.NGANH]
