"""Answers to the five question types: fixed templates filled from the list, the rules and the catalog. No
generated prose."""

from __future__ import annotations

from collections import Counter

from uniadvisor.ui.texts import (EXCLUDED_VI, INCOME_CONTEXT, LEVEL_HELP, LEVEL_VI, MIXED_METHOD_CAPPED,
                                  relation_text, score_text)
from uniadvisor.chat.changes import Item
from uniadvisor.chat.context import ChatContext
from uniadvisor.data.school_docs import combo_label
from uniadvisor.planner.models import Level

PENDING = "chưa có dữ liệu (đang được biên soạn)"


def answer(item: Item, ctx: ChatContext) -> str:
    return {"ask_why_nv": _why_nv, "ask_why_not": _why_not, "ask_compare": _compare, "ask_what_is": _what_is,
            "ask_level": _level}[item.kind](item, ctx)


def _need_list(ctx: ChatContext) -> str | None:
    if ctx.result is None or not ctx.result.wishes:
        return "Em chưa có danh sách nguyện vọng. Em nhập điểm, tỉnh/thành và chọn ngành trước nhé."
    return None


def _why_nv(item: Item, ctx: ChatContext) -> str:
    if (msg := _need_list(ctx)):
        return msg
    nvs = item.params.get("nv") or []
    if not nvs:
        return "Em hỏi về nguyện vọng số mấy? Ví dụ: “Vì sao NV3 lại ở đó?”"
    out = []
    codes = ctx.shortlist_codes()
    for nv in nvs[:3]:
        w = ctx.wishes_by_nv.get(nv)
        if w is None:
            out.append(f"Danh sách hiện có {len(ctx.result.wishes)} nguyện vọng, không có NV{nv}.")
            continue
        c = w.candidate
        part = ("Các nguyện vọng an toàn luôn nằm cuối danh sách (hướng học 1 trước) để giữ chỗ chắc chắn mà không chặn "
                "các nguyện vọng em muốn hơn; trong phần này, chương trình có điểm chuẩn năm gần nhất cao hơn điểm của em "
                "nhiều hơn đứng trước."
                if c.level == Level.AN_TOAN else
                f"Các nguyện vọng chưa an toàn của hướng học {c.item_index + 1} xếp theo khoảng cách giữa điểm chuẩn "
                "năm gần nhất và điểm của em (cách xa hơn đứng trước), rồi theo điểm trường.")
        penalties = []
        if c.over_budget:
            penalties.append("học phí vượt ngân sách")
        if c.far_from_home:
            penalties.append("xa nhà")
        school = f"Điểm trường của chương trình này là {c.school_score}%" + \
                 (f" (bị trừ vì {' và '.join(penalties)})." if penalties else ".")
        capped = f" {MIXED_METHOD_CAPPED}" if c.student.capped_mixed_method else ""
        out.append(f"NV{nv}: {c.program.school_name} · {c.program.name} ({relation_text(c, codes, ctx.catalog)}), "
                   f"mức {LEVEL_VI[c.level]}.{capped} Điểm của em và điểm chuẩn: {score_text(c)}. {school} {part}")
    return "\n\n".join(out)


def _why_not(item: Item, ctx: ChatContext) -> str:
    groups = item.params.get("schools") or []
    if not groups:
        return "Em hỏi về trường nào? Ví dụ: “Sao không có trường Kinh tế Quốc dân?”"
    out = []
    for values in groups[:3]:
        for code in values[:3]:
            out.append(_why_not_school(code, ctx))
    return "\n\n".join(out)


def _why_not_school(code: str, ctx: ChatContext) -> str:
    name = ctx.school_label(code)
    if code not in ctx.school_names:
        return (f"{name}: trường này nằm ngoài phạm vi của ứng dụng (chỉ gồm các trường đại học có chương trình học ở "
                "Hà Nội và TP.HCM), hoặc chưa được kiểm tra dữ liệu.")
    if code in ctx.state.removed_schools:
        return f"{name}: em đã bỏ trường này. Em có thể nói “đưa lại {name}”."
    if ctx.result is None:
        return f"{name}: em chưa có danh sách nguyện vọng."
    on_list = [w.nv for w in ctx.result.wishes if w.candidate.program.school_code == code]
    if on_list:
        return f"{name} đang có trong danh sách: " + ", ".join(f"NV{n}" for n in on_list) + "."
    reasons = Counter()
    for e in ctx.result.excluded:
        p = ctx.programs.get(e.program_id)
        if p and p.school_code == code:
            reasons[e.reason] += 1
    if not reasons:
        return (f"{name} không có chương trình nào thuộc ngành em chọn (hoặc ngành gần) ở Hà Nội, TP.HCM có dữ liệu "
                "đủ để xếp vào danh sách.")
    parts = [f"{n} chương trình: {EXCLUDED_VI.get(r, r)}" for r, n in reasons.most_common()]
    return f"{name} có chương trình thuộc ngành em chọn nhưng không vào danh sách: " + "; ".join(parts) + "."


def _facts(code: str, ctx: ChatContext) -> str:
    cat = ctx.catalog
    m = cat.majors[code]
    lines = [f"**{m.label}**" + (f" (tên Bộ GD&ĐT: {m.official})" if m.display and m.display != m.official else "")]
    f = ctx.facts.get(code) if ctx.facts else None
    lines.append("- Học gì: kiến thức chính " + ", ".join(f.knowledge) + "." if f and f.knowledge
                 else f"- Học gì: {PENDING}.")
    shares = cat.combo_shares(code, top=3)
    if shares:
        lines.append("- Cần mạnh môn nào: tổ hợp hay gặp " + "; ".join(
            f"{combo_label(s.combo)} ({' - '.join(s.subjects)}) ở {round(s.share * 100)}% chương trình" for s in shares) + ".")
    lines.append("- Việc làm sau khi ra trường: " + "; ".join(f.jobs) + f". Thu nhập: {INCOME_CONTEXT}."
                 if f and f.jobs else f"- Việc làm và thu nhập: {PENDING}.")
    lines.append("- Có hợp với em không: hợp với người thích " + "; ".join(n.lower() for n, _ in f.interests) + "."
                 if f and f.interests else f"- Có hợp với em không: {PENDING}.")
    if f and f.close:
        lines.append("- Ngành gần: " + ", ".join(cat.label(c) for c in f.close[:3]) + ".")
    if m.level == "nhom_nganh":
        lines.append("- Gồm các ngành: " + ", ".join(cat.label(c) for c in m.children) + ".")
    lines.append(f"- Có {m.n_programs_hn} chương trình ở Hà Nội, {m.n_programs_hcm} ở TP.HCM.")
    return "\n".join(lines)


def _compare(item: Item, ctx: ChatContext) -> str:
    codes = item.params.get("codes") or []
    if len(codes) < 2:
        return "Em muốn so sánh hai ngành nào? Ví dụ: “Khoa học máy tính với Công nghệ thông tin khác gì nhau?”"
    return "\n\n".join(_facts(c, ctx) for c in codes[:3]) + _credit(ctx, codes[:3])


def _what_is(item: Item, ctx: ChatContext) -> str:
    codes = item.params.get("codes") or []
    if not codes:
        return "Em hỏi về ngành nào? Ví dụ: “Ngành Logistics học gì?”"
    return "\n\n".join(_facts(c, ctx) for c in codes[:2]) + _credit(ctx, codes[:2])


def _level(item: Item, ctx: ChatContext) -> str:
    levels = [Level(v) for v in item.params.get("levels") or []] or list(reversed(list(Level)))
    lines = [f"- **{LEVEL_VI[lv]}**: {LEVEL_HELP[lv]}." for lv in levels]
    return "\n".join(lines) + "\n\nỨng dụng chỉ so với điểm chuẩn đã công bố của hai năm gần nhất, không dự đoán điểm " \
                              "chuẩn năm nay."



def _credit(ctx: ChatContext, codes: list[str]) -> str:
    if ctx.facts and any(not ctx.facts.get(c).empty for c in codes):
        from uniadvisor.ui.facts import ONET_CREDIT
        return "\n\n_" + ONET_CREDIT + "_"
    return ""
