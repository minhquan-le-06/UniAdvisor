"""The explanation of one wish: "Vì sao NVn ở đây?" on the list page and in the chat.

Every sentence comes from facts the planner already computed (level, gap, relation, the part of the list, the chosen
phương án); nothing is generated and nothing promises an admission.  The page and the chat use the same builder.
Layout (spec in docs/design/lists.md, "Explanations"): a one-line verdict, three number lines, why the program is on the
list, why it sits at this position, and notices.
"""

from __future__ import annotations

from dataclasses import dataclass

from uniadvisor.data.school_docs import combo_label
from uniadvisor.planner.lists import Priority
from uniadvisor.planner.models import Candidate, Level, Wish
from uniadvisor.planner.strategy import in_safe_part
from uniadvisor.ui.texts import (CITY_VI, LEVEL_VI, SOURCE_VI, cutoff_text, num, student_score_text, trieu)

TEACHER_LIMIT = 5                      # rules: application.teacher_training.max_position (2026 regulation)
SAFE_MARGIN = 2.0                      # config list.yaml levels: an toàn from this margin over the higher cutoff
TIE = 0.005                            # gaps closer than this are one gap


@dataclass(frozen=True)
class WishExplanation:
    """The pieces of one explanation, ready to show."""

    wish_no: int
    level: str
    title: str                         # "Trường · Ngành"
    verdict: str
    numbers: tuple[str, ...]           # three short lines
    why_in_list: str
    placement: str
    notices: tuple[str, ...]

    def markdown(self) -> str:
        """Structured display for the list page, not one dense paragraph."""
        parts = [f"**NV{self.wish_no} · {self.level}** — {self.title}", self.verdict,
                 "\n".join(f"- {line}" for line in self.numbers),
                 f"**Vì sao có trong danh sách:** {self.why_in_list}",
                 f"**Vì sao ở vị trí này:** {self.placement}"]
        if self.notices:
            parts.append("**Lưu ý:**\n" + "\n".join(f"- {n}" for n in self.notices))
        return "\n\n".join(parts)

    def chat_text(self) -> str:
        """The same content in a few short lines for the chat."""
        lines = [f"**NV{self.wish_no} · {self.level}** — {self.title}", self.verdict, " · ".join(self.numbers),
                 f"Có trong danh sách vì: {self.why_in_list}", f"Vị trí: {self.placement}"]
        if self.notices:
            lines.append("Lưu ý: " + " ".join(self.notices))
        return "  \n".join(lines)


# ---------------------------------------------------------------- the verdict and the numbers

def _highest_cutoff(c: Candidate) -> float:
    return max(cut.score_30 for cut in c.student.cutoffs.values()) + c.student.cutoff_shift


def _cutoff_of(c: Candidate, year: int) -> float:
    return c.student.cutoffs[year].score_30 + c.student.cutoff_shift


def verdict(c: Candidate) -> str:
    """One sentence by level and gap (gap > 0: the student is below the latest cutoff)."""
    years = sorted(c.student.cutoffs)
    latest, score, gap = years[-1], c.student.score, c.gap
    others = [y for y in years[:-1]]
    margin = score - _highest_cutoff(c)
    if c.level == Level.MO_UOC:
        text = (f"Khó đỗ: em thiếu {num(gap)} điểm so với điểm chuẩn {latest}. Đặt ở đây vì nếu đủ điểm thì đây là "
                "lựa chọn tốt nhất của em.") if gap > 0 else "Khó đỗ so với điểm chuẩn các năm trước."
    elif c.level == Level.THU_SUC:
        if gap > 0:
            text = f"Có thể đỗ nhưng chưa chắc: em thiếu {num(gap)} điểm so với điểm chuẩn {latest}."
            if any(_cutoff_of(c, y) <= score for y in others):
                year = next(y for y in reversed(others) if _cutoff_of(c, y) <= score)
                text += f" Em đã đạt điểm chuẩn năm {year}."
        else:
            year = max(others, key=lambda y: _cutoff_of(c, y)) if others else latest
            text = (f"Em đạt điểm chuẩn {latest} nhưng thấp hơn điểm chuẩn {year} ({num(_cutoff_of(c, year))}), "
                    "nên đây là nguyện vọng thử sức.")
    elif c.level == Level.VUA_SUC and c.student.capped_mixed_method:
        text = (f"Em dư {num(margin)} điểm nhưng chương trình xét kết hợp (học bạ, chứng chỉ…) nên chỉ xếp vừa sức, "
                "không xếp an toàn.")
    elif c.level == Level.VUA_SUC:
        text = f"Em đạt điểm chuẩn, dư {num(max(margin, 0))} điểm nên còn sát; điểm chuẩn thay đổi theo năm."
    else:
        text = f"Em dư {num(margin)} điểm so với điểm chuẩn nên đây là phương án dự phòng."
    extra = []
    if len(years) == 1:
        extra.append(f"Chỉ có điểm chuẩn năm {latest}.")
    for year in years:
        cut = c.student.cutoffs[year]
        if cut.scale != 30:
            extra.append(f"Điểm chuẩn {year} quy đổi từ {num(cut.score).removesuffix(',0')}/{cut.scale} sang thang 30.")
    for year, source, raw in c.program.disputes:
        if year in c.student.cutoffs:
            extra.append(f"{SOURCE_VI.get(source, source)} ghi điểm chuẩn {year} là {str(raw).replace('.', ',')}.")
    if c.student.cutoff_shift:
        extra.append(f"Em đã chỉnh điểm chuẩn trường này {'+' if c.student.cutoff_shift > 0 else ''}"
                     f"{num(c.student.cutoff_shift)} điểm.")
    return " ".join([text] + extra)


def number_lines(c: Candidate) -> tuple[str, ...]:
    years = sorted(c.student.cutoffs, reverse=True)
    cutoffs = " · ".join(f"{year}: {cutoff_text(c, year, with_year=False)}" for year in years)
    gap = c.gap
    if gap > 0:
        diff = f"Thiếu {num(gap)} điểm so với {years[0]}"
    elif gap < 0:
        diff = f"Dư {num(-gap)} điểm so với {years[0]}"
    else:
        diff = f"Bằng điểm chuẩn {years[0]}"
    return f"Điểm của em: {student_score_text(c)}", f"Điểm chuẩn {cutoffs}", diff


# ---------------------------------------------------------------- why it is on the list

def _priority(ctx) -> str | None:
    """The chosen phương án; a chosen 'Hợp sở thích nhất' without answers is built as 'Hợp môn học nhất'."""
    state = getattr(ctx, "state", None)
    choice = getattr(state, "list_choice", None)
    if choice == Priority.CAREER.value and not getattr(state, "answers", None):
        return Priority.MON.value
    return choice


def _label(ctx, code: str) -> str:
    return ctx.catalog.label(code)


def relation_sentence(c: Candidate, ctx) -> str:
    codes = ctx.shortlist_codes()
    main = _label(ctx, codes[c.item_index])
    safe_top_up = in_safe_part(c) and c.level == Level.AN_TOAN
    if c.relation == "main":
        return f"Đây là ngành em chọn: {main}."
    if c.relation == "group":
        return f"Ngành này thuộc nhóm ngành em chọn: {main}."
    if c.relation == "close":
        return f"Đây là ngành gần với {main}."
    if c.relation == "further_close":
        why = ("thêm vào để đủ lựa chọn an toàn" if safe_top_up else
               "thêm vào vì hợp với câu trả lời của em" if _priority(ctx) == Priority.CAREER.value else
               "thêm vào để danh sách có thêm lựa chọn")
        return f"Đây là ngành gần với {main}, {why}."
    if c.relation == "favorite_school":
        tier = {1: f"cùng nhóm ngành với {main}", 2: f"cùng lĩnh vực với {main}"}.get(c.closeness_rank, "ngành khác")
        return (f"Em chọn {c.program.school_name} là trường thích nhất, nên chương trình này được thêm vào "
                f"({tier}).")
    same_group = (c.program.moet_code or "")[:5] == codes[c.item_index][:5]
    return (f"Thêm làm nguyện vọng an toàn vì ngành em chọn không còn đủ chương trình an toàn "
            f"(cùng {'nhóm ngành' if same_group else 'lĩnh vực'} với {main}).")


def _fee_sentence(c: Candidate) -> str:
    fee = c.program.tuition_max_vnd
    if c.program.tuition_basis == "free":
        return "Miễn học phí (trường tuyển riêng, điều kiện xét khác)."
    if fee is None:
        return "Chưa rõ học phí."
    return f"Học phí khoảng {trieu(fee)} triệu/năm; phương án này ưu tiên chương trình rẻ hơn ở cùng mức."


def priority_sentence(c: Candidate, ctx) -> str:
    priority = _priority(ctx)
    if priority == Priority.NGANH.value and c.relation in ("main", "group"):
        return "Được ưu tiên vì đúng ngành hơn các lựa chọn khác ở cùng mức."
    if priority == Priority.CAREER.value:
        return "Ngành này hợp với câu trả lời 12 câu hỏi của em."
    if priority == Priority.MON.value:
        return f"Chương trình xét tổ hợp {combo_label(c.student.combo)} em mạnh nhất ({num(c.student.exam_total)}/30)."
    if priority == Priority.COST.value:
        return _fee_sentence(c)
    return ""


def why_in_list(c: Candidate, ctx) -> str:
    return " ".join(s for s in (relation_sentence(c, ctx), priority_sentence(c, ctx)) if s)


# ---------------------------------------------------------------- why it sits here

def _teacher_count(result) -> int:
    for note in result.notes:
        if note.startswith("teacher_training_first:"):
            return int(note.split(":", 1)[1])
    return 0


def _school(w: Wish, other: Wish | None = None) -> str:
    if other is not None and other.candidate.program.school_code == w.candidate.program.school_code:
        return "cùng trường"
    return w.candidate.program.school_name


def placement_sentence(wish: Wish, ctx) -> str:
    c = wish.candidate
    wishes = ctx.result.wishes
    by_nv = {w.nv: w for w in wishes}
    if wish.nv <= _teacher_count(ctx.result):
        return (f"Quy chế chỉ cho xét ngành sư phạm ở {TEACHER_LIMIT} nguyện vọng đầu nên nguyện vọng này nằm đầu "
                "danh sách. Trong nhóm sư phạm, nguyện vọng khó hơn xếp trước.")
    if in_safe_part(c):
        parts = ["Hệ thống xét từ NV1 xuống và em vào nguyện vọng đầu tiên đủ điểm."]
        if c.level != Level.AN_TOAN:
            parts.append("Chương trình xét kết hợp nên xếp cùng phần cuối với các nguyện vọng an toàn, theo độ khó thật.")
        elif wish.nv > 1:
            parts.append(f"Nguyện vọng an toàn để ở cuối: em chỉ vào đây nếu không đạt {wish.nv - 1} nguyện vọng phía "
                         "trên, nên nó không chặn các nguyện vọng em muốn hơn.")
        else:
            parts.append("Đây là nguyện vọng đầu danh sách nên em vào đây nếu đủ điểm.")
        if c.relation in ("further_close", "wider"):
            parts.append("Được thêm vào cuối để danh sách đủ lựa chọn an toàn.")
        return " ".join(parts)
    parts = ["Hệ thống xét từ NV1 xuống và em vào nguyện vọng đầu tiên đủ điểm."]
    nxt = by_nv.get(wish.nv + 1)
    codes = ctx.shortlist_codes()
    if c.item_index == 1 and len(codes) == 2:
        parts.append(f"Nguyện vọng của hướng {_label(ctx, codes[1])} nằm sau các nguyện vọng chưa an toàn của hướng "
                     f"{_label(ctx, codes[0])}.")
    if nxt is None:
        parts.append("Đây là nguyện vọng cuối danh sách.")
    elif in_safe_part(nxt.candidate):
        parts.append(f"Từ NV{nxt.nv} trở đi là các nguyện vọng an toàn.")
    elif nxt.candidate.item_index != c.item_index:
        pass
    elif c.gap - nxt.candidate.gap > TIE:
        lead = "Đứng đầu danh sách và xếp" if wish.nv == 1 else "Xếp"
        parts.append(f"{lead} trước NV{nxt.nv} ({_school(nxt, wish)}) vì khó hơn: nếu đủ điểm em vào ngay trường này, "
                     "nếu không vẫn còn các nguyện vọng phía sau.")
    elif abs(c.gap - nxt.candidate.gap) <= TIE:
        parts.append(f"Ngang độ khó với NV{nxt.nv} ({_school(nxt, wish)}); khi bằng nhau, ứng dụng xếp theo thứ tự cố định.")
    return " ".join(parts)


# ---------------------------------------------------------------- notices

def notice_lines(c: Candidate, ctx) -> tuple[str, ...]:
    out: list[str] = []
    priority = _priority(ctx)
    state = getattr(ctx, "state", None)
    budget = getattr(state, "budget_trieu", None)
    fee = c.program.tuition_max_vnd
    if c.over_budget:
        cap = f"ngân sách {num(budget).removesuffix(',0')} triệu em đặt" if budget is not None else "ngân sách em đặt"
        out.append(f"Học phí {trieu(fee)} triệu/năm cao hơn {cap}.")
    if c.far_from_home:
        out.append(f"Trường ở {CITY_VI.get(c.program.city, c.program.city)}, xa nhà theo lựa chọn của em.")
    if priority != Priority.COST.value:                       # the cost phương án already said it
        if c.program.tuition_basis == "free":
            out.append("Miễn học phí; trường tuyển riêng, em kiểm tra điều kiện xét tuyển.")
        elif c.tuition_unknown:
            out.append("Chưa có học phí đã công bố.")
    if c.is_mixed_method and not c.student.capped_mixed_method:
        out.append("Điểm chuẩn thuộc phương thức xét kết hợp; số đã quy đổi chỉ để tham khảo.")
    if c.other_codes:
        out.append("Cùng chương trình với mã " + ", ".join(pid.split(":", 1)[-1] for pid in c.other_codes)
                   + "; đã gộp thành một nguyện vọng.")
    if c.program.employment:
        rate, year = c.program.employment
        out.append(f"Trường công bố tỷ lệ có việc làm {round(rate * 100)}% (khóa tốt nghiệp {year}).")
    return tuple(out)


def build_wish_explanation(wish: Wish, ctx) -> WishExplanation:
    """`ctx` is duck-typed (result, shortlist_codes(), catalog and, when present, state) so the chat and list-page
    tests can supply small read-only contexts."""
    c = wish.candidate
    return WishExplanation(wish.nv, LEVEL_VI[c.level], f"{c.program.school_name} · {c.program.name}", verdict(c),
                           number_lines(c), why_in_list(c, ctx), placement_sentence(wish, ctx), notice_lines(c, ctx))
