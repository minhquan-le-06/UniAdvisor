"""Changes to the student's inputs. Both the visible controls and the chat produce Items; applying an Item
returns a new PlanState and the fixed strategy rebuilds the list. The chat never edits the list itself.

An Item may be incomplete (a school name that fits two schools, a score without a subject): its `open` parameters
are asked on the change card with buttons or a number box, and it is applied only when complete.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from uniadvisor.ui.state import (AREAS, CATEGORIES, COMPULSORY, MAX_CLOSE, MAX_CUTOFF_SHIFT, MAX_ELECTIVES, SCALES,
                                  PlanState, ShortlistEntry, on_step, score_step)
from uniadvisor.ui.texts import CATEGORY_VI, num
from uniadvisor.chat.context import ChatContext

CHANGE_KINDS = ["set_score", "set_area", "set_category", "set_budget", "set_near_home", "set_extra",
                "set_favorite", "set_own_score", "set_cutoff_shift",
                "remove_school", "remove_program", "restore_school", "restore_program", "restore_any", "swap_items",
                "replace_item",
                "set_close", "undo"]


@dataclass
class Item:
    kind: str                                         # a CHANGE_KINDS value, or a question type (ask_*)
    params: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)       # param -> [(value, label)] to choose from
    open: list[str] = field(default_factory=list)     # params still to be given by the student
    text: str = ""                                    # the request it came from

    @property
    def complete(self) -> bool:
        return not self.open

    def choose(self, param: str, value) -> None:
        self.params[param] = value
        if param in self.open:
            self.open.remove(param)


class ChangeError(ValueError):
    """The change cannot be applied (message in Vietnamese)."""


def apply(state: PlanState, item: Item, ctx: ChatContext) -> PlanState:
    """A new PlanState with the change applied. Raises ChangeError when it does not make sense."""
    if not item.complete:
        raise ChangeError("Thay đổi chưa đủ thông tin.")
    s = copy.deepcopy(state)
    p = item.params
    k = item.kind
    if k == "restore_any":                           # chosen on the card: ('school', code) or ('program', id)
        kind, value = p["target"]
        return apply(state, Item(f"restore_{kind}", {kind: value}), ctx)
    if k == "set_score":
        if p["subject"] not in ctx.subjects or not 0 <= p["value"] <= 10:
            raise ChangeError("Điểm môn phải từ 0 đến 10.")
        step = score_step(p["subject"])
        if not on_step(p["value"], step):
            raise ChangeError(f"Điểm {ctx.subjects.get(p['subject'], p['subject'])} chỉ nhận bước {num(step)} điểm "
                              f"(ví dụ {num(8 + step * 3)}); em nhập lại giúp mình.")
        electives = [c for c in s.scores if c not in COMPULSORY]
        if p["subject"] not in COMPULSORY and p["subject"] not in electives and len(electives) >= MAX_ELECTIVES:
            raise ChangeError(f"Em đã có {MAX_ELECTIVES} môn tự chọn ("
                              + ", ".join(ctx.subjects.get(c, c) for c in electives)
                              + "). Muốn đổi môn tự chọn, em vào trang Về em.")
        s.scores[p["subject"]] = float(p["value"])
    elif k == "set_area":
        if p["value"] not in AREAS:
            raise ChangeError("Khu vực không hợp lệ.")
        s.area = p["value"]
    elif k == "set_category":
        if p["value"] not in CATEGORIES:
            raise ChangeError("Đối tượng ưu tiên không hợp lệ.")
        s.category = p["value"]
    elif k == "set_budget":
        if p["value"] is not None and not 0 < p["value"] <= 1000:
            raise ChangeError("Ngân sách tính theo triệu đồng một năm, từ 1 đến 1000.")
        s.budget_trieu = None if p["value"] is None else float(p["value"])
    elif k == "set_near_home":
        s.near_home = bool(p["value"])
    elif k == "set_extra":
        if p["school"] not in ctx.school_names or not 0 <= p["value"] <= 10:
            raise ChangeError("Điểm cộng phải từ 0 đến 10.")
        if p["value"]:
            s.extra_points[p["school"]] = float(p["value"])
        else:
            s.extra_points.pop(p["school"], None)
    elif k == "set_favorite":
        if p["school"] is not None and p["school"] not in ctx.school_names:
            raise ChangeError("Trường này không có trong dữ liệu của ứng dụng.")
        s.favorite_school = p["school"]
    elif k == "set_own_score":
        if p["school"] not in ctx.school_names:
            raise ChangeError("Trường này không có trong dữ liệu của ứng dụng.")
        if p["value"] is None:
            s.own_scores.pop(p["school"], None)
        else:
            scale = p.get("scale") or ctx.scale_for(p["school"], p["value"])
            if scale not in SCALES or not 0 < p["value"] <= scale:
                raise ChangeError(f"Điểm xét tuyển phải lớn hơn 0 và không quá {max(SCALES)}.")
            s.own_scores[p["school"]] = (float(p["value"]), scale)
    elif k == "set_cutoff_shift":
        if p["school"] not in ctx.school_names:
            raise ChangeError("Trường này không có trong dữ liệu của ứng dụng.")
        if p["value"] is not None and not -MAX_CUTOFF_SHIFT <= p["value"] <= MAX_CUTOFF_SHIFT:
            raise ChangeError(f"Điều chỉnh điểm chuẩn tối đa {num(MAX_CUTOFF_SHIFT).removesuffix(',0')} điểm.")
        if p["value"]:
            s.cutoff_shifts[p["school"]] = float(p["value"])
        else:
            s.cutoff_shifts.pop(p["school"], None)
    elif k == "remove_school":
        if p["school"] not in s.removed_schools:
            s.removed_schools.append(p["school"])
    elif k == "remove_program":
        if p["program"] not in s.removed_programs:
            s.removed_programs.append(p["program"])
    elif k == "restore_school":
        s.removed_schools = [x for x in s.removed_schools if x != p["school"]]
    elif k == "restore_program":
        s.removed_programs = [x for x in s.removed_programs if x != p["program"]]
    elif k == "swap_items":
        if len(s.shortlist) != 2:
            raise ChangeError("Em mới có một hướng học, chưa có gì để đổi thứ tự.")
        s.shortlist.reverse()
    elif k == "replace_item":
        i, code = p["index"], p["code"]
        if code not in ctx.catalog.majors:
            raise ChangeError("Ngành này không có chương trình nào ở Hà Nội, TP.HCM.")
        if i == len(s.shortlist) and i < 2:
            s.shortlist.append(ShortlistEntry(code))
        elif 0 <= i < len(s.shortlist):
            s.shortlist[i] = ShortlistEntry(code, [c for c in s.shortlist[i].close if c != code])
        else:
            raise ChangeError("Không có hướng học này.")
        if code not in s.picks:
            s.picks.append(code)
    elif k == "set_close":
        i, old, new = p["index"], p.get("old"), p.get("new")
        if not 0 <= i < len(s.shortlist):
            raise ChangeError("Không có hướng học này.")
        entry = s.shortlist[i]
        close = [c for c in entry.close if c != old]
        if new is not None:
            if new not in ctx.catalog.majors or ctx.catalog.majors[new].level != "nganh":
                raise ChangeError("Ngành gần phải là một ngành cụ thể có chương trình ở Hà Nội, TP.HCM.")
            if new == entry.main:
                raise ChangeError("Ngành gần phải khác ngành chính.")
            if new not in close:
                if len(close) >= MAX_CLOSE:
                    raise ChangeError(f"Mỗi hướng học có tối đa {MAX_CLOSE} ngành gần; em bỏ bớt một ngành trước.")
                close.append(new)
        entry.close = close
    else:
        raise ChangeError(f"Không áp dụng được thay đổi loại {k}.")
    return s


def describe(item: Item, ctx: ChatContext) -> str:
    """One line for the change card."""
    p, k = item.params, item.kind
    cat = ctx.catalog

    def school(code):
        return ctx.school_label(code) if code else "trường nào?"

    def nganh(code):
        return cat.label(code) if code else "ngành nào?"

    if k == "set_score":
        subject = ctx.subjects.get(p.get("subject"), "môn nào?")
        return f"Đổi điểm {subject} thành {num(p['value']) if p.get('value') is not None else '...'}"
    if k == "set_area":
        return f"Khu vực ưu tiên: {p['value']}"
    if k == "set_category":
        return f"Đối tượng ưu tiên: {CATEGORY_VI[p['value']]}"
    if k == "set_budget":
        if "value" in item.open:
            return "Đổi ngân sách học phí thành ... triệu/năm"
        return "Bỏ giới hạn ngân sách học phí" if p["value"] is None else \
            f"Ngân sách học phí: {num(p['value']).removesuffix(',0')} triệu/năm"
    if k == "set_near_home":
        return "Muốn học gần nhà: có" if p["value"] else "Muốn học gần nhà: không"
    if k == "set_extra":
        value = num(p["value"]) if p.get("value") is not None else "..."
        return f"Điểm cộng ở {school(p.get('school'))}: {value}"
    if k == "set_favorite":
        if "school" not in item.open and p.get("school") is None:
            return "Bỏ trường yêu thích nhất"
        return f"Trường yêu thích nhất: {school(p.get('school'))}"
    if k == "set_own_score":
        if "value" not in item.open and p.get("value") is None:
            return f"Bỏ điểm xét tuyển em tự tính ở {school(p.get('school'))}"
        value = "..."
        if p.get("value") is not None:
            scale = p.get("scale") or (ctx.scale_for(p["school"], p["value"]) if p.get("school") else None)
            value = num(p["value"]).removesuffix(",0") + (f"/{scale}" if scale else "")
        return f"Điểm xét tuyển em tự tính ở {school(p.get('school'))}: {value}"
    if k == "set_cutoff_shift":
        if "value" not in item.open and not p.get("value"):
            return f"Bỏ điều chỉnh điểm chuẩn của {school(p.get('school'))}"
        value = p.get("value")
        how = "cao hơn ... điểm" if value is None else             f"{'cao' if value > 0 else 'thấp'} hơn {num(abs(value)).removesuffix(',0')} điểm"
        return f"Với em, điểm chuẩn của {school(p.get('school'))} {how} so với điểm công bố (thang 30)"
    if k == "remove_school":
        return f"Bỏ {school(p.get('school'))} (mọi chương trình của trường)"
    if k == "remove_program":
        return f"Bỏ nguyện vọng {ctx.program_label(p['program'])}" if p.get("program") else "Bỏ nguyện vọng nào?"
    if k == "restore_school":
        return f"Đưa lại {school(p.get('school'))}"
    if k == "restore_program":
        return f"Đưa lại nguyện vọng {ctx.program_label(p['program'])}" if p.get("program") else \
            "Đưa lại nguyện vọng nào?"
    if k == "swap_items":
        return "Đổi thứ tự hai hướng học (hướng học 2 lên trước)"
    if k == "replace_item":
        i = p.get("index")
        old = ctx.shortlist_codes()[i] if i is not None and i < len(ctx.shortlist_codes()) else None
        head = f"Hướng học {i + 1}" if i is not None else "Hướng học nào?"
        return f"{head}: {nganh(old) + ' → ' if old else ''}{nganh(p.get('code'))}"
    if k == "set_close":
        i = p.get("index")
        head = f"Ngành gần của hướng học {i + 1}" if i is not None else "Ngành gần của hướng học nào?"
        parts = ([f"bỏ {nganh(p['old'])}"] if p.get("old") else []) + \
                ([f"thêm {nganh(p['new'])}"] if p.get("new") or "new" in item.open else [])
        return f"{head}: {', '.join(parts)}"
    if k == "restore_any":
        return "Đưa lại trường / nguyện vọng nào?"
    if k == "undo":
        return "Hoàn tác thay đổi gần nhất"
    return k
