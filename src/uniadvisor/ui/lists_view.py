"""The three recommended lists on the list page: one card per list saying what it is good for, what it gives and what
it costs (`list_summary.py`), and a button to choose one; the pentagons and the table of the same numbers are under
"Xem chi tiết". After the choice the page shows the chosen list with its live pentagon; the three lists as
recommended are kept for the plan file.

Charts: one pentagon per list (small multiples, one colour each, titled, so a list is never told apart by colour
alone), drawn with Altair's identity projection; a corner without data is left out of the shape and labelled so.
Colours: the reference categorical palette, slots 1-3, light and dark steps (checked with the colour-vision validator);
the table carries every number for readers who cannot use the chart.
"""

from __future__ import annotations

import math

import altair as alt
import streamlit as st

from uniadvisor.ui import list_view
from uniadvisor.ui.list_summary import LIST_VI, unknown_fees_text
from uniadvisor.ui.list_view import (CAREER_FALLBACK_NOTE, CORNER_VI, LIST_HELP, NO_ANSWERS_NOTE, PENTAGON_NOTE,
                                     at_least_one_text, corner_rows, has_career, snapshot)
from uniadvisor.ui.service import AppData
from uniadvisor.ui.state import PlanState
from uniadvisor.ui.texts import wish_rows
from uniadvisor.planner.lists import CORNERS, Priority, Recommended

COLORS = {"light": ("#2a78d6", "#eb6834", "#1baf7a"), "dark": ("#3987e5", "#d95926", "#199e70")}
GRID = "#8f8e88"
W, H, R = 420, 260, 85                  # chart width and height, pentagon radius, in pixels
CX, CY = W / 2, 128                     # pentagon centre


def slot_color(priority: Priority) -> str:
    """One colour per phương án everywhere (cards, chosen header): Đúng ngành 0, Hợp sở thích / Hợp môn 1, Tiết kiệm 2."""
    return COLORS[_theme()][{Priority.NGANH: 0, Priority.CAREER: 1, Priority.MON: 1, Priority.COST: 2}[priority]]


def _theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:                    # older Streamlit or no theme information
        return "light"


def _point(k: int, r: float) -> tuple[float, float]:
    a = math.pi / 2 - 2 * math.pi * k / len(CORNERS)
    return CX + r * R * math.cos(a), CY - r * R * math.sin(a)


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
    # Labels just outside each corner, anchored away from the shape so they never cross it: left corners end at
    # the corner, right corners start there, top and bottom ones are centred above / below.
    sides = {"left": [], "right": [], "top": [], "bottom": []}
    for k, c in enumerate(CORNERS):
        x, y = _point(k, 1.08)
        v = values.get(c)
        text = f"{CORNER_VI[c]} {round(v * 100)}%" if v is not None else f"{CORNER_VI[c]}: chưa có dữ liệu"
        side = "top" if abs(x - CX) < 1 else ("bottom" if y > CY + 0.5 * R else ("left" if x < CX else "right"))
        sides[side].append({"x": x, "y": y, "text": text})
    style = {"left": {"align": "right", "dx": -6}, "right": {"align": "left", "dx": 6},
             "top": {"baseline": "bottom", "dy": -4}, "bottom": {"baseline": "top", "dy": 4}}
    for side, rows in sides.items():
        if rows:
            layers.append(alt.Chart(alt.Data(values=rows)).mark_text(fontSize=11, **style[side]).encode(
                longitude="x:Q", latitude="y:Q", text="text:N").project(**proj))
    return alt.layer(*layers).properties(width=W, height=H, title=title)


def _summary(d: AppData, state: PlanState, recs: list[Recommended]):
    return list_view.summary(d, state, recs)


def _choose(priority: str, d: AppData, state: PlanState):
    ss = st.session_state
    recs = d.recommend(state)
    ss["recommended"] = snapshot(recs)
    ss["list_choice"] = priority
    card = next((c for c in _summary(d, state, recs).cards if c.priority.value == priority), None)
    ss["chosen_card"] = {"good": card.good[:1], "bad": card.bad[:1]} if card else {}


def _unchoose():
    st.session_state["list_choice"] = None


def recommendations(d: AppData, state: PlanState):
    """Before the choice: the three lists as cards, with the pentagons and the table under "Xem chi tiết"."""
    recs = d.recommend(state)
    cap = d.list_cfg["chances"]["display_cap"]
    summary = _summary(d, state, recs)
    pick = summary.pick
    st.subheader("Ba phương án gợi ý cho em")
    st.markdown(summary.intro)
    if summary.safe_line:
        st.caption(summary.safe_line)
    for note in summary.notes:
        st.info(note)
    if pick:
        st.success(f"**Gợi ý cho em: {pick.name}.** {pick.reason}")
        st.caption("Đây chỉ là gợi ý rút ra từ ba biểu đồ; em vẫn là người chọn.")
    for r, card in zip(recs, summary.cards):
        with st.container(border=True):
            badge = " · ✅ Gợi ý" if pick and pick.priority is r.priority else ""
            chart, text = st.columns([1, 1], vertical_alignment="center")
            with chart:
                if r.pentagon and not card.blocked:
                    st.altair_chart(pentagon_chart(r.pentagon.values, slot_color(r.priority), card.name),
                                    width="content")
            with text:
                st.markdown(f"**{card.name}**{badge}")
                st.markdown(f"*Hợp nếu {card.fit}.*")
                if card.blocked:
                    st.warning(card.blocked)
                else:
                    if card.same_as:
                        st.markdown(card.same_as)
                    else:
                        for line in card.good:
                            st.markdown(f"✔ **Được:** {line}")
                        for line in card.bad:
                            st.markdown(f"✘ **Đổi lại:** {line}")
                    if card.warning:
                        st.warning(card.warning)
                    for note in card.notes:
                        st.caption(note)
                    st.button("Chọn phương án này", key=f"choose_{r.priority.value}", on_click=_choose,
                              args=(r.priority.value, d, state), type="primary")
            if card.blocked:
                continue
            with st.expander(f"Xem {len(r.result.wishes)} nguyện vọng"):
                rows = wish_rows(r.result, [e.main for e in state.shortlist], d.catalog)
                st.dataframe(rows, hide_index=True, width="stretch")
    if not has_career(recs):
        st.caption(NO_ANSWERS_NOTE)
    with st.expander("Xem chi tiết: biểu đồ năm góc và bảng so sánh"):
        st.caption(PENTAGON_NOTE)
        for r in recs:
            if r.pentagon:
                st.altair_chart(pentagon_chart(r.pentagon.values, slot_color(r.priority), LIST_VI[r.priority]),
                                width="content")
        st.dataframe(corner_rows(recs), hide_index=True, width="stretch")
        st.caption(at_least_one_text(recs, cap))


def chosen_header(d: AppData, state: PlanState):
    """After the choice: the chosen list's name, its live pentagon and a way back to the three lists."""
    rec = d.chosen(state)
    if rec is None:
        return
    color = slot_color(rec.priority)
    c1, c2 = st.columns([2, 3])
    with c1:
        if rec.pentagon:
            st.altair_chart(pentagon_chart(rec.pentagon.values, color, LIST_VI[rec.priority]), width="content")
    with c2:
        st.markdown(f"**Phương án em chọn: {LIST_VI[rec.priority]}** ({LIST_HELP[rec.priority]}).")
        words = st.session_state.get("chosen_card") or {}
        for line in words.get("good", []):
            st.markdown(f"✔ **Được:** {line}")
        for line in words.get("bad", []):
            st.markdown(f"✘ **Đổi lại:** {line}")
        if state.list_choice == Priority.CAREER.value and rec.priority is Priority.MON:
            st.caption(CAREER_FALLBACK_NOTE)
        if note := unknown_fees_text(rec):
            st.caption(note)
        st.caption("Các điều chỉnh bên dưới chỉ thay đổi phương án này; hình năm góc cập nhật theo. Ba phương án gợi ý "
                   "ban đầu vẫn được lưu trong tệp kế hoạch.")
        st.button("Xem lại ba phương án gợi ý", on_click=_unchoose, key="unchoose")
