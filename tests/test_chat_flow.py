"""The chat on the fake database: extraction per type, applying changes, the pipeline, answers, the list diff."""

import pytest

from uniadvisor.app.service import AppData
from uniadvisor.app.state import PlanState, ShortlistEntry
from uniadvisor.chat.changes import ChangeError, Item, apply, describe
from uniadvisor.chat.classify import RuleClassifier
from uniadvisor.chat.diff import describe_diff
from uniadvisor.chat.extract import extract, near_home_value
from uniadvisor.chat.pipeline import handle
from uniadvisor.chat.split import split_requests
from uniadvisor.data.scope import strip_accents

STATE = PlanState(scores={"TO": 8.0, "LI": 7.0, "HO": 7.0, "N1": 8.0, "VA": 7.0}, home_province="Hà Nội",
                  budget_trieu=32.0, shortlist=[ShortlistEntry("74801", ["7480201"]), ShortlistEntry("7220201")])


@pytest.fixture(scope="module")
def d(fake_db_path):
    return AppData.load(fake_db_path)


@pytest.fixture
def ctx(d):
    return d.chat_context(STATE, d.build_list(STATE))


@pytest.fixture
def rules(d):
    return RuleClassifier(d.indexes.schools, d.indexes.nganh, set(d.subjects))


def items(text, rtype, ctx):
    return [(i.kind, i.params, i.open) for i in extract(text, rtype, ctx)]


def test_extract_scores(ctx):
    assert items("Toán em được 8,5 còn văn 7", "change_score", ctx) == [
        ("set_score", {"subject": "TO", "value": 8.5}, []), ("set_score", {"subject": "VA", "value": 7.0}, [])]
    assert items("sửa điểm hóa", "change_score", ctx) == [("set_score", {"subject": "HO", "value": None}, ["value"])]
    assert items("8 điểm toán", "change_score", ctx) == [("set_score", {"subject": "TO", "value": 8.0}, [])]
    item = extract("điểm em là 9", "change_score", ctx)[0]                      # no subject: asked on the card
    assert (item.params["value"], item.open) == (9.0, ["subject"]) and len(item.options["subject"]) == 6


def test_extract_priority_budget_near_home(ctx):
    assert items("em ở kv2-nt, đối tượng 06", "change_priority", ctx) == [
        ("set_area", {"value": "KV2-NT"}, []), ("set_category", {"value": "UT2"}, [])]
    assert [i[0] for i in items("đổi ưu tiên", "change_priority", ctx)] == ["set_area", "set_category"]
    assert items("ngân sách 40tr", "change_budget", ctx) == [("set_budget", {"value": 40.0}, [])]
    assert items("học phí tối đa 25000000 đồng", "change_budget", ctx) == [("set_budget", {"value": 25.0}, [])]
    assert items("bao nhiêu cũng được", "change_budget", ctx) == [("set_budget", {"value": None}, [])]
    assert items("đổi ngân sách", "change_budget", ctx) == [("set_budget", {"value": None}, ["value"])]
    assert items("không cần học gần nhà", "change_near_home", ctx) == [("set_near_home", {"value": False}, [])]


@pytest.mark.parametrize("text, value", [
    ("em muốn học gần nhà", True), ("không cần gần nhà nữa", False), ("bố mẹ muốn em học gần nhà", True),
    ("không muốn đi xa", True), ("đi xa cũng được", False), ("xa nhà cũng được", False),
    ("gần nhà không quan trọng", False), ("tắt gần nhà", False), ("ko can hoc gan nha", False),
])
def test_near_home_value(text, value):
    assert near_home_value(strip_accents(text)) is value


def test_extract_schools(ctx):
    assert items("FHN cộng cho em 1,5 điểm", "extra_points", ctx) == [
        ("set_extra", {"school": "HNA", "value": 1.5}, [])]
    item = extract("trường Giả cộng 1 điểm", "extra_points", ctx)[0]           # two fake schools are "Giả"
    assert item.open == ["school"] and {v for v, _ in item.options["school"]} == {"HCB", "HNA"}
    assert items("Giả Sài Gòn cộng 0,5", "extra_points", ctx) == [("set_extra", {"school": "HCB", "value": 0.5}, [])]
    nv1 = ctx.result.wishes[0].candidate.program.id
    assert items("bỏ NV1", "remove", ctx) == [("remove_program", {"program": nv1}, [])]
    assert items("bỏ trường FHN", "remove", ctx) == [("remove_school", {"school": "HNA"}, [])]
    assert items("bỏ đi", "remove", ctx)[0][2] == ["school"]


@pytest.mark.parametrize("text, rtype, expected", [
    ("trường em thích nhất là FHN", "favorite_school", ("set_favorite", {"school": "HNA"}, [])),
    ("em muốn vào FHN nhất", "favorite_school", ("set_favorite", {"school": "HNA"}, [])),
    ("bỏ trường yêu thích đi", "favorite_school", ("set_favorite", {"school": None}, [])),
    ("điểm xét tuyển của em ở FHN là 82", "own_score", ("set_own_score", {"school": "HNA", "value": 82.0}, [])),
    ("điểm của em tại FHN là 90 trên thang 100", "own_score",
     ("set_own_score", {"school": "HNA", "value": 90.0}, [])),
    ("bỏ điểm xét tuyển em tự tính ở FHN", "own_score", ("set_own_score", {"school": "HNA", "value": None}, [])),
    ("điểm chuẩn FHN nhiều điểm cộng, thực ra thấp hơn 1 điểm", "cutoff_shift",
     ("set_cutoff_shift", {"school": "HNA", "value": -1.0}, [])),
    ("điểm chuẩn FHN thực ra cao hơn 0,5", "cutoff_shift", ("set_cutoff_shift", {"school": "HNA", "value": 0.5}, [])),
    ("30 điểm của FHN không cao bằng 29 của trường khác", "cutoff_shift",
     ("set_cutoff_shift", {"school": "HNA", "value": -1.0}, [])),
    ("điểm chuẩn FHN với em thấp hơn", "cutoff_shift",
     ("set_cutoff_shift", {"school": "HNA", "value": None}, ["value"])),
    ("bỏ điều chỉnh điểm chuẩn của FHN", "cutoff_shift", ("set_cutoff_shift", {"school": "HNA", "value": 0.0}, [])),
])
def test_extract_corrections(text, rtype, expected, ctx, rules):
    assert rules.classify(text)[0] == rtype
    assert items(text, rtype, ctx) == [expected]


def test_extract_restore(d):
    state = PlanState(**{**STATE.__dict__, "removed_schools": ["HNA"], "removed_programs": ["HCB:NNA"]})
    ctx = d.chat_context(state, d.build_list(state))
    assert items("đưa FHN trở lại", "restore", ctx) == [("restore_school", {"school": "HNA"}, [])]
    item = extract("lấy lại cái em vừa bỏ", "restore", ctx)[0]
    assert item.kind == "restore_any" and [v for v, _ in item.options["target"]] == [("school", "HNA"),
                                                                                       ("program", "HCB:NNA")]


def test_extract_nganh_changes(ctx):
    assert items("thay ngành gần Công nghệ thông tin bằng Trí tuệ nhân tạo", "replace_nganh", ctx) == [
        ("set_close", {"index": 0, "old": "7480201", "new": "7480107"}, [])]
    assert items("thay Ngôn ngữ Anh bằng Y khoa", "replace_nganh", ctx) == [
        ("replace_item", {"index": 1, "code": "7720101"}, [])]
    item = extract("chọn Điều dưỡng", "replace_nganh", ctx)[0]                    # which item? asked on the card
    assert item.kind == "replace_item" and item.open == ["index"] and item.params["code"] == "7720301"


def test_apply_every_change(ctx):
    s = STATE
    s = apply(s, Item("set_score", {"subject": "SI", "value": 6.5}), ctx)
    s = apply(s, Item("set_area", {"value": "KV1"}), ctx)
    s = apply(s, Item("set_category", {"value": "UT2"}), ctx)
    s = apply(s, Item("set_budget", {"value": None}), ctx)
    s = apply(s, Item("set_near_home", {"value": True}), ctx)
    s = apply(s, Item("set_extra", {"school": "HNA", "value": 1.0}), ctx)
    s = apply(s, Item("remove_school", {"school": "HCB"}), ctx)
    s = apply(s, Item("remove_program", {"program": "HNA:SE"}), ctx)
    assert (s.scores["SI"], s.area, s.category, s.budget_trieu, s.near_home, s.extra_points) == (
        6.5, "KV1", "UT2", None, True, {"HNA": 1.0})
    assert (s.removed_schools, s.removed_programs) == (["HCB"], ["HNA:SE"])
    s = apply(s, Item("restore_any", {"target": ("school", "HCB")}), ctx)
    s = apply(s, Item("restore_program", {"program": "HNA:SE"}), ctx)
    assert (s.removed_schools, s.removed_programs) == ([], [])
    s = apply(s, Item("swap_items"), ctx)
    assert [e.main for e in s.shortlist] == ["7220201", "74801"]
    s = apply(s, Item("replace_item", {"index": 0, "code": "7720101"}), ctx)
    s = apply(s, Item("set_close", {"index": 1, "old": "7480201", "new": "7480107"}), ctx)
    assert [(e.main, e.close) for e in s.shortlist] == [("7720101", []), ("74801", ["7480107"])]
    s = apply(s, Item("set_extra", {"school": "HNA", "value": 0}), ctx)
    assert s.extra_points == {}
    assert STATE.budget_trieu == 32.0 and STATE.removed_schools == []           # the original is not changed


def test_apply_corrections(ctx):
    assert ctx.scales["HCB"] == (30, 40, 100)                                   # KTPM 2026 is on 100
    assert [ctx.scale_for("HCB", v) for v in (27, 35, 85)] == [30, 40, 100]
    s = apply(STATE, Item("set_favorite", {"school": "HCB"}), ctx)
    s = apply(s, Item("set_own_score", {"school": "HCB", "value": 85}), ctx)
    s = apply(s, Item("set_cutoff_shift", {"school": "HNA", "value": -1.0}), ctx)
    assert (s.favorite_school, s.own_scores, s.cutoff_shifts) == ("HCB", {"HCB": (85.0, 100)}, {"HNA": -1.0})
    s = apply(s, Item("set_own_score", {"school": "HCB", "value": None}), ctx)
    s = apply(s, Item("set_cutoff_shift", {"school": "HNA", "value": 0}), ctx)
    s = apply(s, Item("set_favorite", {"school": None}), ctx)
    assert (s.favorite_school, s.own_scores, s.cutoff_shifts) == (None, {}, {})
    assert describe(Item("set_own_score", {"school": "HCB", "value": 85}), ctx) == \
        "Điểm xét tuyển em tự tính ở Trường Đại học Giả TP.HCM: 85/100"
    assert describe(Item("set_cutoff_shift", {"school": "HNA", "value": -1.0}), ctx) == \
        "Với em, điểm chuẩn của Trường Đại học Giả Hà Nội thấp hơn 1 điểm so với điểm công bố (thang 30)"
    assert describe(Item("set_cutoff_shift", {"school": "HNA", "value": 0}), ctx) == \
        "Bỏ điều chỉnh điểm chuẩn của Trường Đại học Giả Hà Nội"
    assert describe(Item("set_favorite", {"school": "HCB"}), ctx) == \
        "Trường yêu thích nhất: Trường Đại học Giả TP.HCM"


def test_own_score_changes_the_list(d):
    # HCB:KTPM's 2026 cutoff is 80/100 (mixed): with 90/100 at HCB it is compared on the school's own scale
    base = PlanState(**{**STATE.__dict__, "shortlist": [ShortlistEntry("74801")]})
    own = PlanState(**{**base.__dict__, "own_scores": {"HCB": (90.0, 100)}})
    before = {c.program.id: c for c in d.build_list(base).candidates}
    after = {c.program.id: c for c in d.build_list(own).candidates}
    assert before["HCB:KTPM"].student.own_score is None
    assert after["HCB:KTPM"].student.own_score == (90.0, 100) and list(after["HCB:KTPM"].student.cutoffs) == [2026]
    assert not after["HCB:KTPM"].student.capped_mixed_method


@pytest.mark.parametrize("item, message", [
    (Item("set_own_score", {"school": "HCB", "value": 120}), "không quá 100"),
    (Item("set_own_score", {"school": "HCB", "value": 0}), "lớn hơn 0"),
    (Item("set_cutoff_shift", {"school": "HNA", "value": 6}), "tối đa 5"),
    (Item("set_favorite", {"school": "XYZ"}), "không có trong dữ liệu"),
    (Item("set_score", {"subject": "TO", "value": 11}), "từ 0 đến 10"),
    (Item("set_budget", {"value": 0}), "triệu đồng"),
    (Item("set_area", {"value": "KV4"}), "Khu vực"),
    (Item("set_close", {"index": 0, "old": None, "new": "74802"}), "ngành cụ thể"),
    (Item("set_close", {"index": 1, "old": None, "new": "7220201"}), "khác ngành chính"),
    (Item("replace_item", {"index": 5, "code": "7720101"}), "Không có lựa chọn"),
    (Item("set_score", {"subject": None, "value": 8}, open=["subject"]), "chưa đủ thông tin"),
])
def test_bad_changes_are_refused(item, message, ctx):
    with pytest.raises(ChangeError, match=message):
        apply(STATE, item, ctx)


def test_too_many_close_nganh(ctx):
    s = apply(STATE, Item("set_close", {"index": 0, "old": None, "new": "7480107"}), ctx)
    with pytest.raises(ChangeError, match="tối đa 2"):
        apply(s, Item("set_close", {"index": 0, "old": None, "new": "7480103"}), ctx)
    one = PlanState(**{**STATE.__dict__, "shortlist": [ShortlistEntry("74801")]})
    with pytest.raises(ChangeError, match="một lựa chọn"):
        apply(one, Item("swap_items"), ctx)


def test_describe(ctx):
    assert describe(Item("set_score", {"subject": "TO", "value": 8.5}), ctx) == "Đổi điểm Toán thành 8,5"
    assert describe(Item("set_budget", {"value": 40.0}), ctx) == "Ngân sách học phí: 40 triệu/năm"
    assert describe(Item("set_budget", {"value": None}), ctx) == "Bỏ giới hạn ngân sách học phí"
    assert describe(Item("remove_school", {"school": "HNA"}), ctx) == \
        "Bỏ Trường Đại học Giả Hà Nội (mọi chương trình của trường)"
    assert describe(Item("replace_item", {"index": 1, "code": "7720101"}), ctx) == "Lựa chọn 2: Ngôn ngữ Anh → Y khoa"


def test_split(rules):
    assert split_requests("Toán 8, văn 7", rules) == [("Toán 8, văn 7", "change_score")]
    assert split_requests("ngân sách 40tr và bỏ trường FHN", rules) == [
        ("ngân sách 40tr", "change_budget"), ("bỏ trường FHN", "remove")]
    assert split_requests("toán 8.5 rồi hoàn tác", rules) == [("toán 8.5", "change_score"), ("hoàn tác", "undo")]
    assert split_requests("Khoa học máy tính và Công nghệ thông tin khác gì?", rules) == [
        ("Khoa học máy tính và Công nghệ thông tin khác gì?", "ask_compare")]
    assert split_requests("", rules) == []


def test_pipeline(ctx, rules):
    r = handle("toán 8,5 và bỏ trường Giả. Thử sức là gì?", ctx, rules)
    assert [(i.kind, i.open) for i in r.items] == [("set_score", []), ("remove_school", ["school"])]
    assert len(r.answers) == 1 and "thử sức" in r.answers[0] and r.help is None
    r = handle("hôm nay trời đẹp", ctx, rules)
    assert r.items == [] and r.answers == [] and r.help.startswith("Mình chưa hiểu")
    r = handle("toán 9. trời đẹp quá", ctx, rules)
    assert len(r.items) == 1 and r.answers[-1].startswith("Phần này mình chưa hiểu")


def test_answers(ctx, rules):
    nv1 = ctx.result.wishes[0]
    answer = handle("vì sao NV1 lại ở đó?", ctx, rules).answers[0]
    assert answer.startswith(f"NV1: {nv1.candidate.program.school_name} · {nv1.candidate.program.name}")
    assert "Danh sách hiện có" in handle("vì sao NV15 ở đó?", ctx, rules).answers[0]
    assert "ngoài phạm vi" in handle("sao không có trường Giả Đà Nẵng?", ctx, rules).answers[0]
    compare = handle("Khoa học máy tính và Công nghệ thông tin khác gì?", ctx, rules).answers[0]
    assert "**Khoa học máy tính**" in compare and "**Công nghệ thông tin**" in compare
    assert "A00 (Toán - Vật lí - Hóa học)" in compare
    what = handle("ngành Y khoa học gì", ctx, rules).answers[0]
    assert what.startswith("**Y khoa**") and "8,7 triệu đồng/tháng (Tổng cục Thống kê)" in what
    level = handle("an toàn nghĩa là gì", ctx, rules).answers[0]
    assert level.startswith("- **an toàn**") and "thử sức" not in level


def test_why_not_reasons(d, rules):
    state = PlanState(**{**STATE.__dict__, "removed_schools": ["HCB"]})
    ctx = d.chat_context(state, d.build_list(state))
    assert "em đã bỏ trường này" in handle("sao không có trường Giả Sài Gòn?", ctx, rules).answers[0]


def test_diff(d, ctx):
    old = STATE
    new = apply(old, Item("remove_school", {"school": "HNA"}), ctx)
    text = describe_diff(ctx.result, d.build_list(new), old, new)
    assert "(danh sách cũ) ra vì em đã bỏ trường" in text
    assert describe_diff(ctx.result, ctx.result, old, old) == "Danh sách không đổi."
    back = describe_diff(d.build_list(new), ctx.result, new, old)
    assert "mới vào vì em đã đưa lại" in back
