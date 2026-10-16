"""Answers to the five question types: fixed templates filled from the list, the rules and the catalog. No
generated prose."""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

from uniadvisor.ui.texts import (EXCLUDED_VI, INCOME_CONTEXT, LEVEL_HELP, LEVEL_VI,
                                  num, relation_text, score_text, tuition_text)
from uniadvisor.chat.changes import Item
from uniadvisor.chat.context import ChatContext
from uniadvisor.data.school_docs import combo_label
from uniadvisor.explanations import build_wish_explanation
from uniadvisor.planner.models import Level

PENDING = "chưa có dữ liệu trong ứng dụng (đang bổ sung)"


def answer(item: Item, ctx: ChatContext) -> str:
    return {"ask_why_nv": _why_nv, "ask_why_not": _why_not, "ask_compare": _compare, "ask_what_is": _what_is,
            "ask_level": _level, "ask_tuition": _tuition, "ask_cutoff": _cutoff, "ask_combos": _combos,
            "ask_employment": _employment, "ask_extra_policy": _extra_policy, "out_procedure": _procedure,
            "out_admission_method": _admission_method, "out_forecast": _forecast, "out_advice": _advice}[item.kind](item, ctx)


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
    for nv in nvs[:3]:
        w = ctx.wishes_by_nv.get(nv)
        if w is None:
            out.append(f"Danh sách hiện có {len(ctx.result.wishes)} nguyện vọng, không có NV{nv}.")
            continue
        out.append(build_wish_explanation(w, ctx).chat_text())
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


# ---------------------------------------------------------------- questions about one program's published data

def _program_label(program, nv: int | None = None) -> str:
    label = f"{program.school_name} · {program.name}"
    return f"NV{nv}: {label}" if nv is not None else label


def _same_major(program, code: str) -> bool:
    """A five-digit nhóm ngành query includes its seven-digit child ngành."""
    return bool(program.moet_code) and (program.moet_code == code or
                                        (len(code) == 5 and program.moet_code.startswith(code)))


def _data_targets(item: Item, ctx: ChatContext, noun: str) -> tuple[list[tuple[object, int | None]], str | None]:
    """Resolve a data question conservatively: an NV, or one school plus one ngành.

    Program names are not a separate search index yet.  Requiring a school and ngành outside a list avoids silently
    selecting one of several similarly named programmes.
    """
    nvs = item.params.get("nv") or []
    if nvs:
        if (msg := _need_list(ctx)):
            return [], msg
        targets = [(ctx.wishes_by_nv[n].candidate.program, n) for n in nvs[:3] if n in ctx.wishes_by_nv]
        if targets:
            return targets, None
        return [], f"Danh sách hiện có {len(ctx.result.wishes)} nguyện vọng, không có nguyện vọng em hỏi."

    school_groups = item.params.get("schools") or []
    if any(len(values) != 1 for values in school_groups):
        return [], "Có nhiều trường khớp với tên em viết. Em nói rõ tên trường hoặc hỏi theo số nguyện vọng nhé."
    schools = list(dict.fromkeys(values[0] for values in school_groups if values))
    codes = list(dict.fromkeys(item.params.get("codes") or []))
    if not schools and not codes:
        return [], f"Em muốn hỏi {noun} của nguyện vọng nào, hoặc của trường và ngành nào?"
    if not schools:
        return [], f"Em cho mình biết trường nào, hoặc hỏi theo số nguyện vọng, để xem {noun} nhé."
    if not codes:
        return [], f"Em cho mình biết ngành hoặc số nguyện vọng ở {ctx.school_label(schools[0])} nhé."
    targets = [(p, None) for p in ctx.programs.values()
               if p.school_code in schools and any(_same_major(p, code) for code in codes)]
    if not targets:
        return [], (f"Ứng dụng chưa có chương trình khớp với trường và ngành em hỏi. Em thử nêu số nguyện vọng "
                    "hoặc kiểm tra lại tên ngành nhé.")
    return targets[:3], None


def _tuition(item: Item, ctx: ChatContext) -> str:
    targets, message = _data_targets(item, ctx, "học phí")
    if message:
        return message
    out = []
    for program, nv in targets:
        over_budget = bool(nv and ctx.wishes_by_nv[nv].candidate.over_budget)
        text = tuition_text(SimpleNamespace(program=program, over_budget=over_budget))
        if program.tuition_max_vnd is None:
            text = "Học phí: Ứng dụng chưa có học phí công bố theo năm cho chương trình này."
        else:
            text = "Học phí: " + text + "."
        out.append(f"{_program_label(program, nv)} — {text}")
    return "\n\n".join(out)


def _cutoff_line(cutoff) -> str:
    notes = []
    if cutoff.scale != 30:
        notes.append(f"quy đổi từ {num(cutoff.score).removesuffix(',0')}/{cutoff.scale}")
    if cutoff.is_mixed_method:
        notes.append("xét kết hợp")
    if cutoff.combos:
        notes.append("tổ hợp " + ", ".join(combo_label(c) for c in sorted(cutoff.combos)))
    return f"{num(cutoff.score_30)}" + (f" ({'; '.join(notes)})" if notes else "")


def _cutoff(item: Item, ctx: ChatContext) -> str:
    targets, message = _data_targets(item, ctx, "điểm chuẩn")
    if message:
        return message
    wanted_years = set(item.params.get("years") or [])
    out = []
    for program, nv in targets:
        by_year: dict[int, list[object]] = {}
        for cutoff in program.cutoffs:
            if wanted_years and cutoff.year not in wanted_years:
                continue
            by_year.setdefault(cutoff.year, []).append(cutoff)
        if not by_year:
            suffix = " năm " + ", ".join(str(y) for y in sorted(wanted_years)) if wanted_years else ""
            text = "Ứng dụng chưa có điểm chuẩn phương thức điểm thi THPT" + suffix + " cho chương trình này."
        else:
            years = [f"{year}: " + "; ".join(_cutoff_line(c) for c in cuts)
                     for year, cuts in sorted(by_year.items())]
            text = "Điểm chuẩn đã công bố (phương thức điểm thi THPT, thang 30): " + " · ".join(years) + "."
        out.append(f"{_program_label(program, nv)} — {text}")
    return "\n\n".join(out)


def _combos(item: Item, ctx: ChatContext) -> str:
    targets, message = _data_targets(item, ctx, "tổ hợp xét tuyển")
    if message:
        return message
    out = []
    for program, nv in targets:
        if not program.combos:
            text = "Ứng dụng chưa biết đủ ba môn của tổ hợp xét tuyển cho chương trình này."
        else:
            values = [f"{combo_label(code)} ({' - '.join(subjects)})"
                      for code, subjects in sorted(program.combos.items())]
            text = "Tổ hợp xét tuyển: " + "; ".join(values) + "."
        out.append(f"{_program_label(program, nv)} — {text}")
    return "\n\n".join(out)


def _employment(item: Item, ctx: ChatContext) -> str:
    targets, message = _data_targets(item, ctx, "tỷ lệ có việc làm")
    if message:
        return message
    out = []
    for program, nv in targets:
        if program.employment is None:
            text = "Ứng dụng chưa có tỷ lệ có việc làm do trường công bố cho ngành này."
        else:
            rate, year = program.employment
            text = f"Trường công bố {round(rate * 100)}% sinh viên có việc làm, khóa tốt nghiệp {year}."
        out.append(f"{_program_label(program, nv)} — {text}")
    return "\n\n".join(out)


def _extra_policy(item: Item, ctx: ChatContext) -> str:
    groups = item.params.get("schools") or []
    if any(len(values) != 1 for values in groups):
        return "Có nhiều trường khớp với tên em viết. Em nói rõ tên trường hoặc hỏi theo số nguyện vọng nhé."
    schools = list(dict.fromkeys(values[0] for values in groups if values))
    nvs = item.params.get("nv") or []
    if nvs and ctx.result:
        schools += [ctx.wishes_by_nv[n].candidate.program.school_code for n in nvs if n in ctx.wishes_by_nv]
        schools = list(dict.fromkeys(schools))
    if not schools:
        return "Em muốn hỏi quy định điểm cộng của trường nào? Ví dụ: “Bách khoa cộng IELTS thế nào?”"
    labels = ", ".join(ctx.school_label(code) for code in schools[:3])
    return (f"Ứng dụng chưa lưu quy định điểm cộng riêng của {labels} (IELTS, chứng chỉ, giải thưởng...). "
            "Em xem đề án tuyển sinh chính thức của trường; sau khi tự tính được điểm của mình, em có thể nhập ở "
            "Điều chỉnh → Các nút điều chỉnh → Theo từng trường.")


# ---------------------------------------------------------------- questions deliberately outside the app's data scope

def _procedure(item: Item, ctx: ChatContext) -> str:
    return ("Ứng dụng không theo dõi thủ tục hay lịch tuyển sinh. Em xem cổng thông tin tuyển sinh chính thức của Bộ "
            "GD&ĐT và thông báo của trường để biết mốc áp dụng cho mình nhé.")


def _admission_method(item: Item, ctx: ChatContext) -> str:
    return ("UniAdvisor hiện chỉ lập danh sách theo điểm thi tốt nghiệp THPT. Với học bạ, chứng chỉ, đánh giá năng lực "
            "hoặc phương thức khác, em xem đề án tuyển sinh chính thức của trường nhé.")


def _forecast(item: Item, ctx: ChatContext) -> str:
    return ("Ứng dụng không dự báo điểm chuẩn năm nay. Ứng dụng chỉ so sánh điểm của em với điểm chuẩn đã công bố của "
            "hai năm gần nhất; em có thể hỏi điểm chuẩn của một nguyện vọng cụ thể.")


def _advice(item: Item, ctx: ChatContext) -> str:
    return ("Mình không thể quyết định thay em nên chọn trường nào. Em nhập điểm, chọn ngành em quan tâm rồi xem ba "
            "phương án; hoặc hỏi để so sánh hai ngành/trường cụ thể nhé.")


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
