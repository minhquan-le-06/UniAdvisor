"""Adjusting the list: a chat box and visible controls, both producing the same changes. The chat never
edits the list: it proposes changes on one card, the student confirms, the inputs change and the list is rebuilt.
"""

from __future__ import annotations

import copy

import streamlit as st

from uniadvisor.ui.change_card import DEFAULT_RANGE, NUMBER_RANGES, param_label
from uniadvisor.ui.service import AppData
from uniadvisor.ui.session import commit, data
from uniadvisor.ui.state import AREAS, CATEGORIES, COMPULSORY, MAX_CLOSE, MAX_CUTOFF_SHIFT, MAX_ELECTIVES, PlanState
from uniadvisor.ui.texts import CATEGORY_VI, num
from uniadvisor.chat.changes import Item, describe
from uniadvisor.chat.pipeline import handle
from uniadvisor.planner.models import ListResult

CHAT_PLACEHOLDER = "Ví dụ: Toán em được 8,5 · bỏ trường Bách khoa Hà Nội · vì sao NV3 ở đó?"
# Columns of the per-school table (adjust panel).
COL_SCHOOL, COL_EXTRA, COL_OWN, COL_SCALE, COL_SHIFT = (
    "Trường", "Điểm cộng", "Điểm xét tuyển em tự tính", "Thang điểm của trường", "Điểm chuẩn cao hơn (+) hoặc thấp hơn (-)")


def adjust_panel(d: AppData, state: PlanState, result: ListResult | None):
    st.subheader("Điều chỉnh")
    chat_tab, controls_tab = st.tabs(["Nhắn yêu cầu hoặc câu hỏi", "Các nút điều chỉnh"])
    with chat_tab:
        chat(d, state, result)
    with controls_tab:
        controls(d, state, result)


# ---------------------------------------------------------------- chat + change card

def _log(role: str, text: str):
    st.session_state["chat_log"].append((role, text))


def chat(d: AppData, state: PlanState, result: ListResult | None):
    ss = st.session_state
    st.caption("Chat chỉ đổi thông tin em đã nhập (rồi danh sách được lập lại theo cách cố định) hoặc trả lời câu hỏi "
               "từ dữ liệu của ứng dụng. Mọi thay đổi đều cần em bấm Xác nhận. Tin nhắn không được lưu lại.")
    log_box, card_box = st.container(), st.container()
    message = st.chat_input(CHAT_PLACEHOLDER, key="chat_msg")
    if message:
        ctx = d.chat_context(state, result)
        reply = handle(message, ctx, d.classifier)
        _log("user", message)
        for text in reply.answers:
            _log("assistant", text)
        if reply.help:
            _log("assistant", reply.help)
        if reply.items:
            ss["card"] = {"id": ss.get("card_seq", 0) + 1, "items": reply.items, "edit": False}
            ss["card_seq"] = ss["card"]["id"]
            _log("assistant", "Mình hiểu em muốn thay đổi những điều dưới đây. Em kiểm tra rồi bấm **Xác nhận** nhé.")
    with log_box:
        for role, text in ss["chat_log"][-30:]:
            with st.chat_message(role):
                st.markdown(text)
    if ss.get("card"):
        with card_box:
            change_card(d, state, result)


def _input_key(cid: int, i: int, param: str) -> str:
    return f"card{cid}_{i}_{param}"


def change_card(d: AppData, state: PlanState, result: ListResult | None):
    ss = st.session_state
    card = ss["card"]
    cid, items = card["id"], card["items"]
    ctx = d.chat_context(state, result)
    cat = d.catalog
    with st.container(border=True):
        st.markdown("**Các thay đổi sẽ áp dụng**")
        for i, item in enumerate(items):
            st.checkbox(describe(item, ctx), value=True, key=f"card{cid}_on_{i}")
            for param in item.open:
                key = _input_key(cid, i, param)
                if item.options.get(param):
                    labels = dict(item.options[param])
                    st.selectbox(param_label(item, param), list(labels), key=key, index=None,
                                 format_func=lambda v, labels=labels: labels[v], placeholder="Chọn")
                elif param in ("code", "new"):
                    codes = cat.nganh_codes() if param == "new" else sorted(cat.majors)
                    st.selectbox(param_label(item, param), codes, key=key, index=None, format_func=cat.label,
                                 placeholder="Chọn ngành")
                elif param == "value":
                    lo, hi, step = NUMBER_RANGES.get(item.kind, DEFAULT_RANGE)
                    st.number_input(param_label(item, param), min_value=lo, max_value=hi, step=step, value=None,
                                    key=key, placeholder="nhập số")
            if card["edit"] and item.complete and isinstance(item.params.get("value"), (int, float)) \
                    and not isinstance(item.params.get("value"), bool):
                lo, hi, step = NUMBER_RANGES.get(item.kind, DEFAULT_RANGE)
                st.number_input("Sửa giá trị", min_value=lo, max_value=hi, step=step,
                                value=float(item.params["value"]), key=_input_key(cid, i, "fix"))
        if ss.get("card_error"):
            st.error(ss.pop("card_error"))
        c1, c2, c3 = st.columns([1, 1, 4], vertical_alignment="bottom")
        c1.button("Xác nhận", type="primary", key=f"card{cid}_ok", on_click=_confirm_card, args=(cid,))
        c2.button("Sửa", key=f"card{cid}_edit", on_click=_toggle_edit)
        c3.button("Huỷ", key=f"card{cid}_cancel", on_click=_cancel_card)


def _toggle_edit():
    card = st.session_state.get("card")
    if card:
        card["edit"] = not card["edit"]


def _cancel_card():
    st.session_state["card"] = None
    _log("assistant", "Đã huỷ, danh sách giữ nguyên.")


def _confirm_card(cid: int):
    ss = st.session_state
    card = ss.get("card")
    if not card or card["id"] != cid:
        return
    chosen, missing = [], []
    for i, item in enumerate(card["items"]):
        if not ss.get(f"card{cid}_on_{i}", True):
            continue
        item = copy.deepcopy(item)
        for param in list(item.open):
            value = ss.get(_input_key(cid, i, param))
            if value is None:
                missing.append(param_label(item, param).rstrip("?").lower())
            else:
                item.choose(param, value)
        fix = ss.get(_input_key(cid, i, "fix"))
        if fix is not None and card["edit"]:
            item.params["value"] = fix
        if item.complete:
            chosen.append(item)
    if missing:
        ss["card_error"] = "Em chọn giúp mình: " + ", ".join(dict.fromkeys(missing)) + "."
        return
    ss["card"] = None
    if not chosen:
        _log("assistant", "Không có thay đổi nào được chọn.")
        return
    res = commit(data(), chosen)
    text = ("Đã áp dụng: " + "; ".join(res["done"]) + "." if res["done"] else "") + \
           (f" {res['diff']}" if res["diff"] else "") + \
           "".join(f"\n\n{e}" for e in res["errors"])
    _log("assistant", text.strip())


# ---------------------------------------------------------------- visible controls

def _do(items: list[Item]):
    commit(data(), items)


def _ctl_score():
    ss = st.session_state
    if ss.get("adj_subject") and ss.get("adj_score") is not None:
        _do([Item("set_score", {"subject": ss["adj_subject"], "value": ss["adj_score"]})])


def _ctl_priority():
    ss = st.session_state
    _do([Item("set_area", {"value": ss["adj_area"]}), Item("set_category", {"value": ss["adj_cat"]})])


def _ctl_budget(clear: bool = False):
    ss = st.session_state
    if clear or ss.get("adj_budget"):
        _do([Item("set_budget", {"value": None if clear else ss["adj_budget"]})])


def _ctl_schools():
    """The per-school table: extra points, the student's own score at the school, a correction of its cutoffs."""
    ss = st.session_state
    codes = ss.get("adj_extra_codes", [])
    edits = (ss.get("adj_extra") or {}).get("edited_rows", {})
    items = []
    for row, change in edits.items():
        if int(row) >= len(codes):
            continue
        school = codes[int(row)]
        if COL_EXTRA in change:
            items.append(Item("set_extra", {"school": school, "value": float(change[COL_EXTRA] or 0)}))
        if COL_OWN in change:
            items.append(Item("set_own_score", {"school": school, "value": change[COL_OWN] or None}))
        if COL_SHIFT in change:
            items.append(Item("set_cutoff_shift", {"school": school, "value": float(change[COL_SHIFT] or 0)}))
    if items:
        _do(items)


def _selected(key: str):
    return st.session_state.get(key)


def _keep_valid(key: str, options: list):
    if st.session_state.get(key) not in options:
        st.session_state[key] = None


def controls(d: AppData, state: PlanState, result: ListResult | None):
    ss = st.session_state
    cat = d.catalog
    st.button("Hoàn tác thay đổi gần nhất", on_click=_do, args=([Item("undo")],), disabled=not ss["history"])

    st.markdown("**Điểm và ưu tiên**")
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    electives = [c for c in state.scores if c not in COMPULSORY]
    subjects = [c for c in d.subjects if c in COMPULSORY or c in electives or len(electives) < MAX_ELECTIVES]
    _keep_valid("adj_subject", subjects)
    c1.selectbox("Môn", subjects, key="adj_subject", format_func=d.subjects.get, index=None, placeholder="Chọn môn")
    c2.number_input("Điểm mới", min_value=0.0, max_value=10.0, step=0.25, value=None, key="adj_score")
    c3.button("Đổi điểm", on_click=_ctl_score, key="adj_score_btn")
    ss.setdefault("adj_area", state.area)
    ss.setdefault("adj_cat", state.category)
    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="bottom")
    c1.selectbox("Khu vực", AREAS, key="adj_area")
    c2.selectbox("Đối tượng", CATEGORIES, key="adj_cat", format_func=CATEGORY_VI.get)
    c3.button("Đổi ưu tiên", on_click=_ctl_priority, key="adj_prio_btn")

    st.markdown("**Ngân sách và nơi học**")
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    current = f"{num(state.budget_trieu).removesuffix(',0')} triệu/năm" if state.budget_trieu else "không giới hạn"
    c1.number_input(f"Ngân sách (hiện tại: {current})", min_value=1.0, max_value=1000.0, step=5.0, value=None,
                    key="adj_budget", placeholder="triệu/năm")
    c2.button("Đổi ngân sách", on_click=_ctl_budget, key="adj_budget_btn")
    c3.button("Bỏ giới hạn", on_click=_ctl_budget, args=(True,), key="adj_budget_clear",
              disabled=state.budget_trieu is None)
    st.button("Tắt “muốn học gần nhà”" if state.near_home else "Bật “muốn học gần nhà”", key="adj_near",
              on_click=_do, args=([Item("set_near_home", {"value": not state.near_home})],))

    if result and result.wishes:
        st.markdown("**Theo từng trường**")
        st.caption(f"{COL_EXTRA}: ứng dụng không biết quy định điểm cộng của từng trường (IELTS, chứng chỉ, học sinh "
                   "giỏi...); em xem quy định của trường, tự tính rồi nhập một số. "
                   f"{COL_OWN}: nếu em biết điểm xét tuyển của mình theo cách tính của trường (ví dụ trường xét kết "
                   "hợp điểm thi với học bạ hoặc điểm đánh giá năng lực), em nhập theo thang điểm của trường; ứng dụng "
                   "sẽ dùng điểm này thay cho tổng điểm thi, điểm ưu tiên và điểm cộng ở trường đó. "
                   f"{COL_SHIFT}: nếu em thấy điểm chuẩn của trường thực ra cao hơn hoặc thấp hơn so với các trường "
                   "khác (ví dụ trường có nhiều điểm cộng nên điểm chuẩn cao), em nhập số điểm chênh, thang 30. "
                   "Các điều chỉnh này chỉ áp dụng cho em.")
        schools = []
        for w in result.wishes:
            code = w.candidate.program.school_code
            if code not in schools:
                schools.append(code)
        schools += [s for s in [*state.extra_points, *state.own_scores, *state.cutoff_shifts] if s not in schools]
        schools = list(dict.fromkeys(schools))
        ss["adj_extra_codes"] = schools
        scales = d.chat_context(state, result).scales
        st.data_editor([{COL_SCHOOL: d.all_school_names.get(s, s), COL_EXTRA: state.extra_points.get(s, 0.0),
                         COL_OWN: state.own_scores[s][0] if s in state.own_scores else None,
                         COL_SCALE: ", ".join(str(k) for k in scales.get(s, ())),
                         COL_SHIFT: state.cutoff_shifts.get(s, 0.0)}
                        for s in schools], key="adj_extra", hide_index=True, disabled=[COL_SCHOOL, COL_SCALE],
                       column_config={
                           COL_EXTRA: st.column_config.NumberColumn(min_value=0.0, max_value=10.0, step=0.25),
                           COL_OWN: st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.05),
                           COL_SHIFT: st.column_config.NumberColumn(min_value=-MAX_CUTOFF_SHIFT,
                                                                    max_value=MAX_CUTOFF_SHIFT, step=0.25)})
        st.button("Lưu", on_click=_ctl_schools, key="adj_extra_btn")

        st.markdown("**Bỏ trường hoặc nguyện vọng**")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        _keep_valid("adj_rm_school", schools)
        c1.selectbox("Trường", schools, key="adj_rm_school", index=None, format_func=d.all_school_names.get,
                     placeholder="Chọn trường")
        c2.button("Bỏ trường", key="adj_rm_school_btn", disabled=not _selected("adj_rm_school"), on_click=_do,
                  args=([Item("remove_school", {"school": _selected("adj_rm_school")})],))
        programs = {w.candidate.program.id: f"NV{w.nv} · {w.candidate.program.school_name} · "
                                            f"{w.candidate.program.name}" for w in result.wishes}
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        _keep_valid("adj_rm_program", list(programs))
        c1.selectbox("Nguyện vọng", list(programs), key="adj_rm_program", index=None, format_func=programs.get,
                     placeholder="Chọn nguyện vọng")
        c2.button("Bỏ nguyện vọng", key="adj_rm_program_btn", disabled=not _selected("adj_rm_program"), on_click=_do,
                  args=([Item("remove_program", {"program": _selected("adj_rm_program")})],))

    if state.removed_schools or state.removed_programs:
        st.markdown("**Đã bỏ**")
        for s in state.removed_schools:
            st.button(f"Đưa lại {d.all_school_names.get(s, s)}", key=f"adj_rs_{s}", on_click=_do,
                      args=([Item("restore_school", {"school": s})],))
        for p in state.removed_programs:
            prog = d.programs_by_id.get(p)
            label = f"{prog.school_name} · {prog.name}" if prog else p
            st.button(f"Đưa lại {label}", key=f"adj_rp_{p}", on_click=_do,
                      args=([Item("restore_program", {"program": p})],))

    st.markdown("**Hướng học**")
    if len(state.shortlist) == 2:
        st.button("Đổi thứ tự hai hướng học", key="adj_swap", on_click=_do, args=([Item("swap_items")],))
    indexes = list(range(len(state.shortlist))) + ([len(state.shortlist)] if len(state.shortlist) < 2 else [])

    def item_label(i):
        return f"Hướng học {i + 1}: {cat.label(state.shortlist[i].main)}" if i < len(state.shortlist) else \
            "Thêm làm hướng học 2"

    c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    _keep_valid("adj_rep_idx", indexes)
    c1.selectbox("Thay", indexes, key="adj_rep_idx", index=None, format_func=item_label, placeholder="Chọn hướng học")
    c2.selectbox("bằng ngành", sorted(cat.majors), key="adj_rep_code", index=None, format_func=cat.label,
                 placeholder="Chọn ngành")
    c3.button("Thay", key="adj_rep_btn", disabled=_selected("adj_rep_idx") is None or not _selected("adj_rep_code"),
              on_click=_do, args=([Item("replace_item", {"index": _selected("adj_rep_idx"),
                                                         "code": _selected("adj_rep_code")})],))
    for i, entry in enumerate(state.shortlist):
        st.caption(f"Ngành gần của hướng học {i + 1} ({cat.label(entry.main)}), tối đa {MAX_CLOSE}")
        for code in entry.close:
            st.button(f"Bỏ ngành gần {cat.label(code)}", key=f"adj_close_rm_{i}_{code}", on_click=_do,
                      args=([Item("set_close", {"index": i, "old": code, "new": None})],))
        if len(entry.close) < MAX_CLOSE:
            c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
            options = [c for c in cat.nganh_codes() if c != entry.main and c not in entry.close]
            c1.selectbox("Thêm ngành gần", options, key=f"adj_close_new_{i}", index=None, format_func=cat.label,
                         placeholder="Chọn ngành", label_visibility="collapsed")
            c2.button("Thêm", key=f"adj_close_add_{i}", disabled=not _selected(f"adj_close_new_{i}"), on_click=_do,
                      args=([Item("set_close", {"index": i, "old": None, "new": _selected(f"adj_close_new_{i}")})],))
