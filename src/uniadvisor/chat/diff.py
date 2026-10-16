"""What changed in the list after a change: "NV6, NV9 mới vào vì không còn vượt ngân sách; NV12 ra"."""

from __future__ import annotations

from collections import defaultdict

from uniadvisor.ui.state import PlanState
from uniadvisor.ui.texts import LEVEL_VI
from uniadvisor.planner.models import Candidate, ListResult


def _join(nvs: list[int]) -> str:
    return ", ".join(f"NV{n}" for n in sorted(nvs))


def _entered_reason(old: Candidate | None, new: Candidate, old_state: PlanState) -> str:
    p = new.program
    if p.school_code in old_state.removed_schools or p.id in old_state.removed_programs:
        return "em đã đưa lại"
    if old is None:
        return "giờ mới đủ điều kiện (ngành, điểm hoặc ngưỡng đầu vào)"
    if old.over_budget and not new.over_budget:
        return "không còn vượt ngân sách"
    if old.far_from_home and not new.far_from_home:
        return "không còn bị tính là xa nhà"
    if old.level != new.level:
        return f"đổi mức từ {LEVEL_VI[old.level]} sang {LEVEL_VI[new.level]}"
    if new.school_score > old.school_score:
        return "điểm trường tăng"
    return "có chỗ trống sau thay đổi"


def _left_reason(old: Candidate, new: Candidate | None, new_state: PlanState) -> str:
    p = old.program
    if p.school_code in new_state.removed_schools:
        return "em đã bỏ trường"
    if p.id in new_state.removed_programs:
        return "em đã bỏ nguyện vọng này"
    if new is None:
        return "không còn đủ điều kiện (ngành, điểm hoặc ngưỡng đầu vào)"
    if new.over_budget and not old.over_budget:
        return "vượt ngân sách"
    if new.far_from_home and not old.far_from_home:
        return "xa nhà"
    if old.level != new.level:
        return f"đổi mức từ {LEVEL_VI[old.level]} sang {LEVEL_VI[new.level]}"
    return "nhường chỗ cho chương trình xếp trên"


def describe_diff(old: ListResult | None, new: ListResult | None, old_state: PlanState, new_state: PlanState) -> str:
    if old is None or new is None:
        return "Đã cập nhật."
    old_nv = {w.candidate.program.id: w for w in old.wishes}
    new_nv = {w.candidate.program.id: w for w in new.wishes}
    old_c = {c.program.id: c for c in old.candidates}
    new_c = {c.program.id: c for c in new.candidates}
    entered, left, moved = defaultdict(list), defaultdict(list), []
    for pid, w in new_nv.items():
        if pid not in old_nv:
            entered[_entered_reason(old_c.get(pid), w.candidate, old_state)].append(w.nv)
        elif old_nv[pid].candidate.level != w.candidate.level:
            moved.append(f"NV{w.nv} đổi mức từ {LEVEL_VI[old_nv[pid].candidate.level]} sang "
                         f"{LEVEL_VI[w.candidate.level]}")
    for pid, w in old_nv.items():
        if pid not in new_nv:
            left[_left_reason(w.candidate, new_c.get(pid), new_state)].append(w.nv)
    parts = [f"{_join(nvs)} mới vào vì {why}" for why, nvs in entered.items()]
    parts += [f"{_join(nvs)} (danh sách cũ) ra vì {why}" for why, nvs in left.items()]
    parts += moved
    if not parts:
        order_changed = [w.candidate.program.id for w in old.wishes] != [w.candidate.program.id for w in new.wishes]
        return "Thứ tự danh sách thay đổi; các chương trình vẫn như cũ." if order_changed else "Danh sách không đổi."
    return "; ".join(parts) + "."
