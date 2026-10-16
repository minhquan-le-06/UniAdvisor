"""Vietnamese text for the list view. Every string is a fixed template filled with data; nothing is
generated."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from uniadvisor.config import load_data_config
from uniadvisor.ui.catalog import Catalog
from uniadvisor.data.school_docs import combo_label
from uniadvisor.planner.chances import Chances
from uniadvisor.planner.models import Candidate, Level, ListResult
from uniadvisor.planner.strategy import in_safe_part

LEVEL_VI = {Level.MO_UOC: "mơ ước", Level.THU_SUC: "thử sức", Level.VUA_SUC: "vừa sức", Level.AN_TOAN: "an toàn"}
CITY_VI = {"HN": "Hà Nội", "HCM": "TP.HCM"}
AREA_VI = {"KV1": "KV1", "KV2-NT": "KV2-NT", "KV2": "KV2", "KV3": "KV3"}
CATEGORY_VI = {"none": "Không thuộc đối tượng ưu tiên", "UT1": "Ưu tiên 1 (nhóm đối tượng 01-03)",
               "UT2": "Ưu tiên 2 (nhóm đối tượng 04-06)"}

LEVEL_HELP = {
    Level.AN_TOAN: "điểm của em cao hơn điểm chuẩn cao nhất của hai năm gần nhất từ 2 điểm trở lên",
    Level.VUA_SUC: "điểm của em đạt điểm chuẩn của cả hai năm, nhưng cao hơn chưa tới 2 điểm",
    Level.THU_SUC: "điểm của em đạt điểm chuẩn của một trong hai năm, hoặc thấp hơn điểm chuẩn thấp hơn chưa tới "
                   "1,5 điểm",
    Level.MO_UOC: "điểm của em thấp hơn điểm chuẩn thấp hơn của hai năm từ 1,5 đến 4 điểm",
}

HOW_THE_LIST_IS_BUILT = (
    "Danh sách gồm tối đa 15 nguyện vọng, xếp theo một thứ tự cố định. Mỗi chương trình được xếp mức "
    "(mơ ước, thử sức, vừa sức, an toàn) bằng cách so điểm của em với điểm chuẩn phương thức điểm thi THPT của hai "
    "năm gần nhất; ứng dụng không dự đoán điểm chuẩn năm nay. Chương trình có điểm chuẩn cao hơn điểm của em quá 4 điểm bị bỏ, "
    "vì quá xa tầm với. Các nguyện vọng chưa an toàn của hướng học 1 đứng "
    "đầu, tiếp theo là của hướng học 2, các nguyện vọng an toàn luôn nằm cuối danh sách; trong mỗi phần, chương trình có điểm chuẩn cao hơn điểm "
    "của em nhiều hơn đứng trước. Lý do: em chỉ trúng tuyển "
    "nguyện vọng cao nhất mà em đạt, nên nguyện vọng an toàn đặt ở cuối để giữ chỗ chắc chắn mà không chặn các "
    "nguyện vọng em muốn hơn. Vì vậy, nếu em đạt một nguyện vọng vừa sức của hướng học 2, em sẽ trúng tuyển ở đó dù "
    "bên dưới còn nguyện vọng an toàn của hướng học 1. Chương trình xét kết hợp (dấu *) mà em vượt điểm chuẩn từ 2 "
    "điểm trở lên vẫn chỉ xếp mức vừa sức, nhưng được đặt cùng phần cuối với các nguyện vọng an toàn, theo độ khó thật. "
    "Riêng ngành sư phạm: theo quy chế tuyển sinh 2026, các ngành đào tạo giáo viên chỉ được xét ở 5 nguyện vọng đầu, "
    "nên danh sách có tối đa 5 nguyện vọng sư phạm và đặt chúng lên đầu."
)

EXTRA_POINTS_REMINDER = (
    "Ứng dụng không tự tính điểm cộng riêng của từng trường (IELTS, chứng chỉ, học sinh giỏi...). Em hãy xem quy "
    "định của từng trường trong danh sách, tự tính điểm cộng của mình và nhập ở phần Điều chỉnh → Các nút điều "
    "chỉnh → Theo từng trường (cột Điểm cộng)."
)

MIXED_METHOD_NOTE = ("Có dấu * : điểm chuẩn của chương trình này được công bố cho phương thức kết hợp điểm thi với "
                     "tiêu chí khác (học bạ, chứng chỉ...); điểm chuẩn đã được quy đổi về thang 30 để so sánh. Vì điểm "
                     "quy đổi không hoàn toàn so được với tổng điểm thi của em, các chương trình này không được xếp "
                     "mức an toàn, trừ khi em nhập điểm xét tuyển em tự tính theo cách của trường (phần Điều chỉnh, "
                     "bảng Theo từng trường).")
MIXED_METHOD_CAPPED = ("Điểm của em cao hơn điểm chuẩn từ 2 điểm trở lên, nhưng chương trình xét kết hợp (dấu *) nên "
                       "chỉ được xếp vừa sức, không xếp an toàn. Nếu em tự tính được điểm xét tuyển của mình theo cách "
                       "của trường, em nhập ở bảng Theo từng trường (phần Điều chỉnh) để so trực tiếp với điểm chuẩn.")

SOURCE_VI = {"vnexpress": "VnExpress", "tuyensinh247": "Tuyensinh247", "vietnamnet": "VietNamNet",
             "school_document": "tài liệu của trường"}


def num(x: float, max_decimals: int = 2) -> str:
    """24.5 -> '24,5'; 25 -> '25,0'; 25.125 -> '25,13' (half-up, Vietnamese decimal comma)."""
    d = Decimal(str(x)).quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_UP).normalize()
    text = format(d, "f")
    if "." not in text:
        text += ".0"
    return text.replace(".", ",")


def trieu(vnd: int) -> str:
    return num(vnd / 1_000_000, 1).removesuffix(",0")


def student_score_text(c: Candidate) -> str:
    """'24,5 (A00, đã gồm 0,5 điểm ưu tiên)'."""
    s = c.student
    if s.own_score:
        value, scale = s.own_score
        parts = [f"theo điểm em tự tính {num(value).removesuffix(',0')}/{scale}" if scale != 30 else
                 "theo điểm em tự tính"]
    else:
        parts = [combo_label(s.combo)]
        if s.priority:
            parts.append(f"đã gồm {num(s.priority)} điểm ưu tiên")
        if s.extra:
            parts.append(f"{num(s.extra)} điểm cộng")
    return f"{num(s.score)} ({', '.join(parts)})"


def cutoff_text(c: Candidate, year: int, with_year: bool = True) -> str:
    """'25,0 (2025)' or, in a column already named for the year, '25,0'; notes for converted, mixed-method and
    disputed cutoffs, and the student's own correction. '' when the program has no cutoff that year."""
    cut = c.student.cutoffs.get(year)
    if cut is None:
        return ""
    note = [str(year)] if with_year else []
    if cut.scale != 30:
        note.append(f"quy đổi từ {num(cut.score).removesuffix(',0')}/{cut.scale}")
    if cut.is_mixed_method:
        note.append("xét kết hợp")
    others = [f"{SOURCE_VI.get(src, src)} ghi {str(raw).replace('.', ',')}" for y, src, raw in c.program.disputes
              if y == year]
    if others:
        note.append("nguồn khác: " + "; ".join(others))
    if c.student.cutoff_shift and not with_year:
        note.append(f"em chỉnh {'+' if c.student.cutoff_shift > 0 else ''}{num(c.student.cutoff_shift)}")
    return f"{num(cut.score_30)}" + (f" ({', '.join(note)})" if note else "")


def score_text(c: Candidate) -> str:
    """'24,5 (A00, đã gồm 0,5 điểm ưu tiên) · 25,0 (2025) · 24,2 (2026)'."""
    out = [student_score_text(c)] + [cutoff_text(c, year) for year in sorted(c.student.cutoffs)]
    if c.student.cutoff_shift:
        out.append(cutoff_shift_text(c.student.cutoff_shift))
    return " · ".join(out)


def cutoff_shift_text(shift: float) -> str:
    return (f"em đã điều chỉnh điểm chuẩn của trường này {'cao' if shift > 0 else 'thấp'} hơn "
            f"{num(abs(shift)).removesuffix(',0')} điểm so với điểm công bố")


# No per-ngành income: national context only. Source: GSO labour-force survey,
# press release on Q4 and year 2024 (published 2025-01-06).
INCOME_CONTEXT = ("chưa có số liệu theo ngành; để tham khảo, thu nhập bình quân của lao động làm công hưởng lương "
                  "cả nước năm 2024 là 8,7 triệu đồng/tháng (Tổng cục Thống kê)")


# How a yearly amount was converted from the school's own unit (school_docs.FACTOR_BASES).
TUITION_BASIS_VI = {
    "semesters_per_year_stated": "quy đổi từ học phí mỗi học kỳ",
    "semesters_per_year_owner_rule": "ước tính từ học phí mỗi học kỳ, 2 học kỳ/năm",
    "course_years_stated": "quy đổi từ học phí toàn khóa",
    "months_per_year_stated": "quy đổi từ học phí mỗi tháng, 10 tháng/năm",
    "months_per_year_assumed": "ước tính từ học phí mỗi tháng, 10 tháng/năm",
    "credits_per_year_owner_rule": "ước tính từ học phí mỗi tín chỉ, 35 tín chỉ/năm",
}


def tuition_text(c: Candidate) -> str:
    p = c.program
    if p.tuition_max_vnd is None:
        return "học phí chưa rõ"
    note = [f"năm {p.tuition_year}"] if p.tuition_year else []
    if p.tuition_max_vnd == 0:
        text = "miễn học phí"
    else:
        amount = (trieu(p.tuition_max_vnd) if p.tuition_min_vnd in (None, p.tuition_max_vnd)
                  else f"{trieu(p.tuition_min_vnd)}-{trieu(p.tuition_max_vnd)}")
        text = f"{amount} triệu/năm"
        if p.tuition_basis in TUITION_BASIS_VI:
            text = "khoảng " + text
            note.append(TUITION_BASIS_VI[p.tuition_basis])
    text += f" ({', '.join(note)})" if note else ""
    return text + (" · vượt ngân sách" if c.over_budget else "")


def employment_text(c: Candidate) -> str:
    job = c.program.employment
    return f"{round(job[0] * 100)}% có việc làm (khóa tốt nghiệp {job[1]})" if job else "chưa rõ"


def city_text(c: Candidate) -> str:
    return CITY_VI.get(c.program.city, c.program.city or "") + (" · xa nhà" if c.far_from_home else "")


def relation_text(c: Candidate, item_codes: list[str], catalog: Catalog) -> str:
    """'ngành chính', 'trong nhóm ngành đã chọn', 'ngành gần của Công nghệ thông tin'."""
    if c.relation == "main":
        return "ngành chính"
    if c.relation == "group":
        return "trong nhóm ngành đã chọn"
    main = catalog.label(item_codes[c.item_index])
    if c.relation == "favorite_school":
        return {1: f"trường yêu thích · cùng nhóm ngành với {main}",
                2: f"trường yêu thích · cùng lĩnh vực với {main}"}.get(c.closeness_rank,
                                                                         "trường yêu thích · ngành khác")
    if c.relation == "close":
        return f"ngành gần của {main}"
    if c.relation == "wider":
        same_group = (c.program.moet_code or "")[:5] == item_codes[c.item_index][:5]
        return (f"cùng {'nhóm ngành' if same_group else 'lĩnh vực'} với {main} "
                "(bổ sung để danh sách đủ an toàn)")
    if not in_safe_part(c):                   # a further close ngành at another level (sư phạm limit, career list)
        return f"ngành gần của {main}"
    return f"ngành gần của {main} (bổ sung cho đủ nguyện vọng an toàn)"


def wish_rows(result: ListResult, item_codes: list[str], catalog: Catalog) -> list[dict]:
    """One row per wish; the Việc làm column only when a school states an employment rate for one of them."""
    rows = []
    jobs = any(w.candidate.program.employment for w in result.wishes)
    years = load_data_config()["cutoff_years"]
    for w in result.wishes:
        c = w.candidate
        rows.append({
            "NV": w.nv,
            "Mức": LEVEL_VI[c.level],
            "Trường": c.program.school_name,
            "Chương trình": c.program.name + (" *" if c.is_mixed_method else "") + (
                " (cùng chương trình: mã " + ", ".join(pid.split(":", 1)[-1] for pid in c.other_codes) + ")"
                if c.other_codes else ""),
            "Hướng học": f"{c.item_index + 1} · {relation_text(c, item_codes, catalog)}",
            "Điểm của em": student_score_text(c),
            **{f"Điểm chuẩn {year}": cutoff_text(c, year, with_year=False) or "chưa có" for year in years},
            "Học phí": tuition_text(c),
            **({"Việc làm": employment_text(c)} if jobs else {}),
            "Thành phố": city_text(c),
        })
    return rows


def note_texts(result: ListResult, item_codes: list[str], catalog: Catalog) -> list[str]:
    """Plain-word explanations of the notes the strategy left (short list, shift-down, top-up)."""
    out = []
    for note in result.notes:
        kind, *rest = note.split(":")
        if kind == "shifted_down":
            item, level, n = int(rest[0]), Level(rest[1]), int(rest[2])
            out.append(f"Hướng học {item} ({catalog.label(item_codes[item - 1])}): không đủ chương trình ở mức "
                       f"{LEVEL_VI[level]}, {n} chỗ còn trống được chuyển xuống mức an toàn hơn.")
        elif kind == "topped_up":
            item, n = int(rest[0]), int(rest[1])
            out.append(f"Hướng học {item}: thêm {n} nguyện vọng an toàn từ các ngành gần khác.")
        elif kind == "short":
            item, n = int(rest[0]), int(rest[1])
            out.append(f"Hướng học {item} ({catalog.label(item_codes[item - 1])}): thiếu {n} nguyện vọng vì không "
                       "còn chương trình phù hợp có điểm chuẩn.")
        elif kind == "teacher_training_first":
            out.append(f"Theo quy chế tuyển sinh 2026, ngành sư phạm chỉ được xét ở 5 nguyện vọng đầu, nên {rest[0]} "
                       "nguyện vọng sư phạm được đặt lên đầu danh sách. Các nguyện vọng sau chỉ được xét khi em không "
                       "đỗ các nguyện vọng sư phạm này.")
        elif kind == "short_list":
            out.append(f"Danh sách chỉ có {rest[0]} nguyện vọng (tối đa 15). Em có thể thêm ngành gần hoặc chọn "
                       "nhóm ngành rộng hơn để có thêm chương trình.")
    return out


EXCLUDED_VI = {
    "no_cutoff": "chưa có điểm chuẩn",
    "below_floor": "điểm của em chưa đạt ngưỡng đầu vào của Bộ GD&ĐT cho ngành này",
    "no_usable_combination": "em chưa nhập đủ điểm các môn của tổ hợp xét tuyển",
    "weak_combination": "chương trình chỉ xét tổ hợp em có điểm thấp hơn hẳn tổ hợp mạnh nhất của em",
    "removed_school": "em đã bỏ trường này",
    "removed_program": "em đã bỏ nguyện vọng này",
    "not_selected": "đã đủ số nguyện vọng ở mức này",
    "taken_by_item1": "đã có trong hướng học 1",
    "taken_by_item2": "đã có trong hướng học 2",
    "not_in_hn_hcm": "không học ở Hà Nội hoặc TP.HCM",
    "too_hard": "điểm của em thấp hơn điểm chuẩn thấp hơn của hai năm quá 4 điểm, nên không xếp vào danh sách",
    "over_budget": "học phí công bố cao hơn ngân sách em đặt (phương án Tiết kiệm nhất không chọn)",
    "same_program_other_code": "cùng chương trình với một mã khác đã có trong danh sách",
    "teacher_training_limit": "quy chế chỉ cho xét ngành sư phạm ở 5 nguyện vọng đầu, và danh sách đã đủ 5 nguyện vọng "
                              "sư phạm",
}


# Chances (planner/chances.py): historical, never a forecast, never 100%.
CHANCE_LEVEL_VI = {Level.MO_UOC: "một nguyện vọng mơ ước", Level.THU_SUC: "thử sức trở lên",
                   Level.VUA_SUC: "vừa sức trở lên", Level.AN_TOAN: "một nguyện vọng bất kỳ trong danh sách"}
CHANCE_SHIFT_VI = {-1.0: "Nếu điểm thật thấp hơn dự kiến 1 điểm", 0.0: "Nếu em thi đúng như dự kiến",
                   1.0: "Nếu điểm thật cao hơn dự kiến 1 điểm"}


def chance_pct(p: float, cap: float) -> str:
    """0.98 -> '98%'; above the cap '≥ 99%', below 1 - cap '< 1%' (never 100% or 0%)."""
    if p >= cap:
        return f"≥ {round(cap * 100)}%"
    if p <= 1 - cap:
        return f"< {round((1 - cap) * 100)}%"
    return f"{min(round(p * 100), round(cap * 100) - 1)}%"


def chance_lines(chs: list[Chances], cap: float, expected: bool) -> list[str]:
    """One line per score shift: 'Nếu em thi đúng như dự kiến: một nguyện vọng mơ ước 6% · thử sức trở lên 33% · ...'."""
    out = []
    for ch in chs:
        label = CHANCE_SHIFT_VI.get(ch.score_shift, f"Với điểm {num(ch.score_shift)}") if expected else "Với điểm của em"
        parts = [f"{CHANCE_LEVEL_VI[lv]}: {chance_pct(p, cap)}" for lv, p in ch.at_least.items()]
        out.append(f"{label}, khả năng trúng tuyển " + " · ".join(parts))
    return out


def chance_note(years: tuple[int, int]) -> str:
    return (f"Cách tính: điểm chuẩn mỗi năm thay đổi, các chương trình cùng trường thường lên xuống cùng nhau. Ứng dụng "
            f"mô phỏng nhiều năm, với mức thay đổi giống như giữa {years[0]} và {years[1]}, và đếm số lần em trúng tuyển "
            "ở từng mức. Đây không phải dự báo điểm chuẩn, và không tính trường hợp điểm chuẩn cả nước cùng tăng hay "
            "giảm mạnh như năm có thay đổi kỳ thi.")


def no_admission_warning(none: float, cap: float) -> str:
    return (f"Với danh sách này, khả năng em không trúng tuyển nguyện vọng nào là khoảng {chance_pct(none, cap)}, vì "
            "danh sách thiếu nguyện vọng chắc chắn. Em có thể thêm ngành gần hoặc hướng học 2 có điểm chuẩn thấp hơn, "
            "hoặc bỏ bớt trường đã loại, để có thêm nguyện vọng an toàn.")


def favorite_note(school_name: str, result: ListResult) -> str | None:
    """Why the favorite school is everywhere on the list, and what to do about it."""
    on_list = [w for w in result.wishes if w.candidate.favorite]
    if not on_list:
        return (f"{school_name} (trường em thích nhất) không có chương trình nào phù hợp với hướng học và điểm của em "
                "để đưa vào danh sách.")
    other = [w.nv for w in on_list if w.candidate.relation == "favorite_school"]
    text = (f"Vì em chọn {school_name} là trường thích nhất, chương trình của trường được ưu tiên ở mọi mức "
            f"({len(on_list)} nguyện vọng).")
    if other:
        text += (" " + ", ".join(f"NV{n}" for n in other) + " là ngành khác ngành em chọn, được đưa vào để em có "
                 "nguyện vọng an toàn ở trường này; em có thể bỏ ở phần Điều chỉnh.")
    return text
