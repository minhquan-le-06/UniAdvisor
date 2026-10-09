"""The three recommended lists on the list page: each list's pentagon (its expected outcome), a
table of the same numbers, the safety badge, and a button to choose one. After the choice the page shows the chosen
list with its live pentagon; the three lists as recommended are kept for the plan file.

Charts: one pentagon per list (small multiples, one colour each, titled, so a list is never told apart by colour
alone), drawn with Altair's identity projection; a corner without data is left out of the shape and labelled so.
Colours: the reference categorical palette, slots 1-3, light and dark steps (checked with the colour-vision validator);
the table carries every number for readers who cannot use the chart.
"""

from __future__ import annotations

import math

import altair as alt
import streamlit as st

from uniadvisor.app.service import AppData
from uniadvisor.app.state import PlanState
from uniadvisor.app.texts import chance_pct, wish_rows
from uniadvisor.plan.lists import CORNERS, Priority, Recommended, overlap

LIST_VI = {Priority.NGANH: "Đúng ngành nhất", Priority.CAREER: "Nghề nghiệp nhất", Priority.MON: "Hợp môn nhất",
           Priority.COST: "Tiết kiệm nhất"}
LIST_HELP = {
    Priority.NGANH: "ưu tiên ngành em chọn, rồi đến ngành gần nhất",
    Priority.CAREER: "ưu tiên ngành có công việc hợp với câu trả lời 12 câu hỏi của em, kể cả ngành gần khác",
    Priority.MON: "ưu tiên chương trình xét tổ hợp môn em mạnh nhất",
    Priority.COST: "ưu tiên chương trình có học phí đã biết, trong ngân sách và rẻ hơn",
}
CORNER_VI = {"hop_mon": "Hợp môn", "nguyen_vong_cao": "Nguyện vọng cao", "dung_nganh": "Đúng ngành",
             "hoc_phi": "Học phí", "nghe_nghiep": "Nghề nghiệp"}
CORNER_HELP = {
    "hop_mon": "chương trình em đỗ có xét tổ hợp môn mạnh nhất của em không",
    "nguyen_vong_cao": "khả năng em đỗ một nguyện vọng mơ ước hoặc thử sức",
    "dung_nganh": "chương trình em đỗ có đúng ngành em chọn không (ngành gần: theo độ gần)",
    "hoc_phi": "học phí của chương trình em đỗ so với ngân sách (không có ngân sách: so với các chương trình khác)",
    "nghe_nghiep": "công việc của ngành em đỗ hợp với câu trả lời 12 câu hỏi của em đến đâu",
}
COLORS = {"light": ("#2a78d6", "#eb6834", "#1baf7a"), "dark": ("#3987e5", "#d95926", "#199e70")}
GRID = "#8f8e88"
SIZE, R = 300, 95                       # chart size and pentagon radius in pixels


def _theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:                    # older Streamlit or no theme information
        return "light"


def _point(k: int, r: float) -> tuple[float, float]:
    a = math.pi / 2 - 2 * math.pi * k / len(CORNERS)
    return SIZE / 2 + r * R * math.cos(a), SIZE / 2 - r * R * math.sin(a)


def _polygon(points: list[tuple[float, float]]) -> dict:
    ring = [list(p) for p in points] + [list(points[0])]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {}}


def pentagon_chart(values: dict, color: str, title: str) -> alt.Chart:
    proj = {"type": "identity"}
    grid = [_polygon([_point(k, r) for k in range(len(CORNERS))]) for r in (0.25, 0.5, 0.75, 1.0)]
    rings = alt.Chart(alt.Data(values=grid)).mark_geoshape(filled=False, stroke=GRID, strokeOpacity=0.35,
                                                           strokeWidth=1).project(**proj)
    spokes = alt.Chart(alt.Data(values=[
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [list(_point(k, 0)), list(_point(k, 1))]},
         "properties": {}} for k in range(len(CORNERS))])).mark_geoshape(
        filled=False, stroke=GRID, strokeOpacity=0.35, strokeWidth=1).project(**proj)
    known = [(k, c) for k, c in enumerate(CORNERS) if values.get(c) is not None]
    layers = [rings, spokes]
    if len(known) >= 3:
        shape = _polygon([_point(k, values[c]) for k, c in known])
        layers.append(alt.Chart(alt.Data(values=[shape])).mark_geoshape(
            fill=color, fillOpacity=0.25, stroke=color, strokeWidth=2).project(**proj))
    pts = [{"x": _point(k, values[c])[0], "y": _point(k, values[c])[1], "corner": CORNER_VI[c],
            "value": f"{round(values[c] * 100)}%"} for k, c in known]
    if pts:
        layers.append(alt.Chart(alt.Data(values=pts)).mark_circle(size=70, color=color, opacity=1).encode(
            longitude="x:Q", latitude="y:Q", tooltip=[alt.Tooltip("corner:N", title="Góc"),
                                                     alt.Tooltip("value:N", title="Giá trị")]).project(**proj))
    labels = []
    for k, c in enumerate(CORNERS):
        x, y = _point(k, 1.28)
        v = values.get(c)
        labels.append({"x": x, "y": y, "text": f"{CORNER_VI[c]} {round(v * 100)}%" if v is not None
                       else f"{CORNER_VI[c]}: chưa có"})
    layers.append(alt.Chart(alt.Data(values=labels)).mark_text(fontSize=11).encode(
        longitude="x:Q", latitude="y:Q", text="text:N").project(**proj))
    return alt.layer(*layers).properties(width=SIZE, height=SIZE, title=title)


def snapshot(recs: list[Recommended]) -> list[dict]:
    """The three lists as recommended, for the plan file."""
    return [{"priority": r.priority.value, "programs": [w.candidate.program.id for w in r.result.wishes],
             "values": {c: (round(v, 4) if v is not None else None) for c, v in r.pentagon.values.items()}
             if r.pentagon else {}, "no_admission": round(r.chances.none, 4) if r.chances else 0.0} for r in recs]


def _choose(priority: str, d: AppData, state: PlanState):
    ss = st.session_state
    ss["recommended"] = snapshot(d.recommend(state))
    ss["list_choice"] = priority


def _unchoose():
    st.session_state["list_choice"] = None


def _best(recs: list[Recommended]) -> dict[Priority, list[str]]:
    """Corners where a list is ahead of both others by at least 2 points (of 100)."""
    out = {r.priority: [] for r in recs}
    for c in CORNERS:
        vals = [(r.pentagon.values.get(c) if r.pentagon else None, r.priority) for r in recs]
        known = sorted((v, p) for v, p in vals if v is not None)
        if len(known) >= 2 and known[-1][0] - known[-2][0] >= 0.02:
            out[known[-1][1]].append(CORNER_VI[c])
    return out


def recommendations(d: AppData, state: PlanState):
    """Before the choice: the three lists side by side."""
    recs = d.recommend(state)
    cap = d.list_cfg["chances"]["display_cap"]
    floor = d.list_cfg["three_lists"]["max_no_admission"]
    colors = COLORS[_theme()]
    st.subheader("Ba danh sách gợi ý cho em")
    st.caption("Ba danh sách cùng quy tắc xếp nguyện vọng, chỉ khác điều được ưu tiên khi chọn chương trình. Mỗi hình "
               "năm góc cho biết điều em có thể chờ đợi ở chương trình em sẽ đỗ (tính trên 20.000 lần giả lập điểm "
               "chuẩn năm sau); góc càng xa tâm càng tốt. Em chọn một danh sách để xem chi tiết và điều chỉnh.")
    best = _best(recs)
    cols = st.columns(3)
    for col, r, color in zip(cols, recs, colors):
        with col.container(border=True):
            name = LIST_VI[r.priority]
            if r.pentagon:
                st.altair_chart(pentagon_chart(r.pentagon.values, color, name), width="content")
            else:
                st.markdown(f"**{name}**")
            st.caption(LIST_HELP[r.priority])
            if r.chances:
                safe = 1 - r.chances.none
                badge = f"Khả năng đỗ ít nhất 1 nguyện vọng: {chance_pct(safe, cap)}"
                (st.markdown if r.floor_met else st.warning)(
                    badge if r.floor_met else badge + f" (dưới mức an toàn {round((1 - floor) * 100)}%: không còn "
                                                      "chương trình an toàn nào để thêm)")
            if best[r.priority]:
                st.markdown("Tốt nhất về: " + ", ".join(best[r.priority]))
            if any(w.candidate.relation == "wider" for w in r.result.wishes):
                st.caption("Đã thêm nguyện vọng an toàn của ngành khác cùng nhóm ngành hoặc cùng lĩnh vực, vì ngành "
                           "em chọn không còn chương trình an toàn nào.")
            with st.expander(f"Xem {len(r.result.wishes)} nguyện vọng"):
                rows = wish_rows(r.result, [e.main for e in state.shortlist], d.catalog)
                st.dataframe(rows, hide_index=True, width="stretch")
            st.button("Chọn danh sách này", key=f"choose_{r.priority.value}", on_click=_choose,
                      args=(r.priority.value, d, state), type="primary", width="stretch")
    if all(r.pentagon is None or r.pentagon.values["nghe_nghiep"] is None for r in recs):
        st.caption("Em chưa trả lời 12 câu hỏi (Chọn ngành → Em chưa biết gì), nên ứng dụng gợi ý danh sách “Hợp môn "
                   "nhất” thay cho “Nghề nghiệp nhất”, và góc Nghề nghiệp chưa có số liệu.")
    similar = d.list_cfg["three_lists"]["similar_overlap"]
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            o = overlap(recs[i].result, recs[j].result)
            if o >= similar:
                st.caption(f"“{LIST_VI[recs[i].priority]}” và “{LIST_VI[recs[j].priority]}” gần giống nhau "
                           f"({round(o * 100)}% chương trình chung).")
    table = []
    for c in CORNERS:
        row = {"Góc": CORNER_VI[c], "Ý nghĩa": CORNER_HELP[c]}
        for r in recs:
            v = r.pentagon.values.get(c) if r.pentagon else None
            unknown = r.pentagon.unknown.get(c, 0.0) if r.pentagon else 0.0
            row[LIST_VI[r.priority]] = ("chưa có" if v is None else f"{round(v * 100)}%") + (
                f" (chưa rõ {round(unknown * 100)}%)" if v is not None and unknown >= 0.05 else "")
        table.append(row)
    with st.expander("Bảng so sánh", expanded=False):
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("“chưa rõ”: phần khả năng em đỗ vào chương trình chưa có số liệu cho góc đó (ví dụ học phí chưa "
                   "công bố); con số tính trên phần còn lại.")


def chosen_header(d: AppData, state: PlanState):
    """After the choice: the chosen list's name, its live pentagon and a way back to the three lists."""
    rec = d.chosen(state)
    if rec is None:
        return
    slot = {Priority.NGANH: 0, Priority.CAREER: 1, Priority.MON: 1, Priority.COST: 2}[rec.priority]
    color = COLORS[_theme()][slot]
    c1, c2 = st.columns([2, 3])
    with c1:
        if rec.pentagon:
            st.altair_chart(pentagon_chart(rec.pentagon.values, color, LIST_VI[rec.priority]), width="content")
    with c2:
        st.markdown(f"**Danh sách em chọn: {LIST_VI[rec.priority]}** ({LIST_HELP[rec.priority]}).")
        if state.list_choice == Priority.CAREER.value and rec.priority is Priority.MON:
            st.caption("Danh sách Nghề nghiệp nhất cần câu trả lời 12 câu hỏi (Chọn ngành → Em chưa biết gì). Em chưa "
                       "trả lời nên ứng dụng dùng danh sách Hợp môn nhất thay thế.")
        st.caption("Các điều chỉnh bên dưới chỉ thay đổi danh sách này; hình năm góc cập nhật theo. Ba danh sách gợi ý "
                   "ban đầu vẫn được lưu trong tệp kế hoạch.")
        st.button("Xem lại ba danh sách gợi ý", on_click=_unchoose, key="unchoose")
