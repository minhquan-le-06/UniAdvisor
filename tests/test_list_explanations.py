"""The explanations change with the list rules of 2026-10-14 (sư phạm first, capped mixed-method programs with the an
toàn wishes, one program under two codes): the page's texts, the chat's "vì sao NV n" and the "what changed" text."""

from dataclasses import replace
from types import SimpleNamespace

from uniadvisor.chat.answers import _why_nv
from uniadvisor.chat.changes import Item
from uniadvisor.chat.diff import _entered_reason, _left_reason
from uniadvisor.planner.lists import Priority, Recommended
from uniadvisor.planner.models import Level, ShortlistItem
from uniadvisor.ui.state import PlanState
from uniadvisor.ui.texts import EXCLUDED_VI, HOW_THE_LIST_IS_BUILT, note_texts, relation_text, wish_rows
from tests.test_planner_strategy import CUTOFF, full_pool, many, prog, run


class Catalog:
    def label(self, code):
        return {"7140209": "Sư phạm Toán học", "7460101": "Toán học", "7480201": "Công nghệ thông tin"}.get(code, code)


def ctx_for(result, codes, state=None):
    ns = SimpleNamespace(result=result, wishes_by_nv={w.nv: w for w in result.wishes},
                         shortlist_codes=lambda: codes, catalog=Catalog())
    if state is not None:
        ns.state = state
    return ns


def su_pham_list():
    sp = [p for lv in Level for p in many(f"S{lv.value[:1].upper()}", lv, 3, moet="7140209")]
    other = [p for lv in (Level.THU_SUC, Level.VUA_SUC) for p in many(f"T{lv.value[:1].upper()}", lv, 4,
                                                                       moet="7460101")]
    return run(sp + other, [ShortlistItem("7140209", (), ("7460101",))])


def test_page_texts_name_the_new_rules():
    assert "sư phạm" in HOW_THE_LIST_IS_BUILT and "dấu *" in HOW_THE_LIST_IS_BUILT
    assert {"same_program_other_code", "teacher_training_limit"} <= set(EXCLUDED_VI)
    r = su_pham_list()
    notes = note_texts(r, ["7140209"], Catalog())
    assert any("5 nguyện vọng đầu" in n for n in notes)
    # A further close ngành filling a thử sức slot is not "bổ sung cho đủ nguyện vọng an toàn".
    other = next(w.candidate for w in r.wishes if w.candidate.relation == "further_close"
                 and w.candidate.level != Level.AN_TOAN)
    assert relation_text(other, ["7140209"], Catalog()) == "ngành gần của Sư phạm Toán học"


def test_why_nv_follows_the_part_of_the_list():
    r = su_pham_list()
    first = _why_nv(Item("ask_why_nv", {"nv": [1]}), ctx_for(r, ["7140209"]))
    assert "Đây là ngành em chọn" in first and "5 nguyện vọng đầu" in first
    capped = run(full_pool(n=2) + [prog("MX:1", cutoff=15.0, mixed=True)], [ShortlistItem("7480201")])
    last = len(capped.wishes)
    text = _why_nv(Item("ask_why_nv", {"nv": [last]}), ctx_for(capped, ["7480201"]))
    assert "vừa sức" in text and "xếp cùng phần cuối" in text and "xét kết hợp" in text


def test_wish_row_names_the_other_code():
    a = replace(prog("D:1", cutoff=CUTOFF[Level.VUA_SUC]), name="Kỹ thuật phần mềm")
    b = replace(prog("D:2", cutoff=CUTOFF[Level.VUA_SUC] - 0.5), name="Kỹ thuật phần mềm")
    rows = wish_rows(run([a, b], [ShortlistItem("7480201")]), ["7480201"], Catalog())
    assert rows[0]["Chương trình"].endswith("(cùng chương trình: mã 1)")


def test_what_changed_names_the_rule():
    state = PlanState()
    c = run([prog("D:1")], [ShortlistItem("7480201")]).wishes[0].candidate
    assert "5 nguyện vọng sư phạm" in _left_reason(c, None, state, "teacher_training_limit")
    assert "cùng chương trình" in _left_reason(c, None, state, "same_program_other_code")
    assert "cùng chương trình" in _entered_reason(c, c, state, "same_program_other_code")
    assert _left_reason(c, None, state) == "không còn đủ điều kiện (ngành, điểm hoặc ngưỡng đầu vào)"


def test_cost_list_says_how_many_fees_are_unknown():
    from uniadvisor.ui.list_summary import unknown_fees_text
    def cost(programs):
        return Recommended(Priority.COST, run(programs, [ShortlistItem("7480201")]), [], None, None, True)
    r = cost([prog("F:1", tuition=20_000_000), prog("F:2", cutoff=22.5)])
    assert unknown_fees_text(r).startswith("1/2 nguyện vọng chưa rõ học phí")
    assert unknown_fees_text(cost([prog("F:1", tuition=20_000_000)])) is None
