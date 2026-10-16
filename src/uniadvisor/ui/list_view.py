"""The parts of the three-list view that need no Streamlit: the words for lists and pentagon corners, the summary
cards, the plan file's snapshot of the lists and the table of corners. The Streamlit page (lists_view.py) and the web
API (api/views.py) both use them, so the two interfaces say the same thing.
"""

from __future__ import annotations

from uniadvisor.planner.lists import CORNERS, Priority, Recommended
from uniadvisor.ui.list_summary import LIST_VI, Summary, build_summary
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import PlanState
from uniadvisor.ui.texts import chance_pct

LIST_HELP = {
    Priority.NGANH: "ưu tiên ngành em chọn, rồi đến ngành gần nhất",
    Priority.CAREER: "ưu tiên ngành hợp với sở thích và tính cách em qua 12 câu hỏi, kể cả ngành gần khác (không dựa vào tỷ lệ có việc làm)",
    Priority.MON: "ưu tiên chương trình xét tổ hợp môn em mạnh nhất",
    Priority.COST: "ưu tiên chương trình có học phí đã biết, trong ngân sách và rẻ hơn",
}
CORNER_VI = {"hop_mon": "Hợp môn", "nguyen_vong_cao": "Nguyện vọng cao", "dung_nganh": "Đúng ngành",
             "hoc_phi": "Học phí phù hợp", "nghe_nghiep": "Nghề nghiệp"}
CORNER_HELP = {
    "hop_mon": "chương trình em đỗ có xét tổ hợp môn mạnh nhất của em không",
    "nguyen_vong_cao": "khả năng em đỗ một nguyện vọng mơ ước hoặc thử sức",
    "dung_nganh": "chương trình em đỗ có đúng ngành em chọn không (ngành gần: theo độ gần)",
    "hoc_phi": "học phí của chương trình em đỗ có nằm trong ngân sách của em không (chưa nhập ngân sách: chưa tính)",
    "nghe_nghiep": "công việc của ngành em đỗ hợp với câu trả lời 12 câu hỏi của em đến đâu",
}
PENTAGON_NOTE = ("Mỗi hình năm góc cho biết điều em có thể chờ đợi ở chương trình em sẽ đỗ (tính trên 20.000 lần giả "
                 "lập điểm chuẩn năm sau); góc càng xa tâm càng tốt, trừ “Nguyện vọng cao” là nhắm cao hơn chứ không "
                 "phải an toàn hơn.")
NO_ANSWERS_NOTE = ("Em chưa trả lời 12 câu hỏi (Chọn ngành → Chưa xác định ngành), nên ứng dụng gợi ý phương án “Hợp môn "
                   "học nhất” thay cho “Hợp sở thích nhất”.")
CAREER_FALLBACK_NOTE = ("Phương án Hợp sở thích nhất cần câu trả lời 12 câu hỏi (Chọn ngành → Chưa xác định ngành). Em "
                        "chưa trả lời nên ứng dụng dùng phương án Hợp môn học nhất thay thế.")
UNKNOWN_NOTE = ("“chưa rõ”: phần khả năng em đỗ vào chương trình chưa có số liệu cho góc đó (ví dụ học phí chưa công "
                "bố); con số tính trên phần còn lại.")


def snapshot(recs: list[Recommended]) -> list[dict]:
    """The three lists as recommended, for the plan file."""
    return [{"priority": r.priority.value, "programs": [w.candidate.program.id for w in r.result.wishes],
             "values": {c: (round(v, 4) if v is not None else None) for c, v in r.pentagon.values.items()}
             if r.pentagon else {}, "no_admission": round(r.chances.none, 4) if r.chances else 0.0} for r in recs]


def summary(d: AppData, state: PlanState, recs: list[Recommended]) -> Summary:
    cfg = d.list_cfg
    favorite = d.school_names.get(state.favorite_school) if state.favorite_school else None
    return build_summary(recs, budget_trieu=state.budget_trieu, floor=cfg["three_lists"]["max_no_admission"],
                         cap=cfg["chances"]["display_cap"], similar=cfg["three_lists"]["similar_overlap"],
                         tie_margin=cfg["three_lists"]["pick_tie_margin"], label=d.catalog.label, favorite=favorite,
                         item_labels=tuple(d.catalog.label(e.main) for e in state.shortlist))


def corner_rows(recs: list[Recommended]) -> list[dict]:
    """One row per pentagon corner with the value of every list as text (the table under the charts)."""
    table = []
    for c in CORNERS:
        row = {"Góc": CORNER_VI[c], "Ý nghĩa": CORNER_HELP[c]}
        for r in recs:
            v = r.pentagon.values.get(c) if r.pentagon else None
            unknown = r.pentagon.unknown.get(c, 0.0) if r.pentagon else 0.0
            row[LIST_VI[r.priority]] = ("chưa có dữ liệu" if v is None else f"{round(v * 100)}%") + (
                f" (chưa rõ {round(unknown * 100)}%)" if v is not None and unknown >= 0.05 else "")
        table.append(row)
    return table


def at_least_one_text(recs: list[Recommended], cap: float) -> str:
    """The chance of at least one admission of every list, as the caption under the table."""
    return (UNKNOWN_NOTE + " Khả năng đỗ ít nhất 1 nguyện vọng của từng phương án: "
            + "; ".join(f"{LIST_VI[r.priority]} {chance_pct(1 - r.chances.none, cap)}" for r in recs if r.chances)
            + ".")


def has_career(recs: list[Recommended]) -> bool:
    """False when no list has a career corner (the student did not answer the 12 questions)."""
    return not all(r.pentagon is None or r.pentagon.values["nghe_nghiep"] is None for r in recs)
