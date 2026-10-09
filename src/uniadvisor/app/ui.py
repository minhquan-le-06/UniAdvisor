"""The Streamlit page (spec 2): Về em -> Chọn ngành ("Em đã có vài lựa chọn") -> Danh sách nguyện vọng -> Lưu kế hoạch.

Privacy (spec 6): the page keeps what the student enters only in the Streamlit session (memory, per browser tab). It
logs nothing, sends nothing out, and the plan file is downloaded to the student's device. Usage statistics are turned
off in .streamlit/config.toml.
"""

from __future__ import annotations

import streamlit as st

from uniadvisor.app import plan_file
from uniadvisor.app.adjust import adjust_panel
from uniadvisor.app.discover import questionnaire
from uniadvisor.app.lists_view import chosen_header, recommendations
from uniadvisor.app.facts import ONET_CREDIT
from uniadvisor.app.service import AppData
from uniadvisor.app.session import PAGES, PATHS, apply_state, current_state, data, init_session
from uniadvisor.app.state import AREAS, CATEGORIES, MAX_CLOSE
from uniadvisor.app.texts import (
    INCOME_CONTEXT,
    CATEGORY_VI, EXTRA_POINTS_REMINDER, HOW_THE_LIST_IS_BUILT, LEVEL_HELP, LEVEL_VI, MIXED_METHOD_NOTE, chance_lines,
    chance_note, favorite_note, no_admission_warning, note_texts, num, wish_rows,
)
from uniadvisor.data.school_docs import combo_label
from uniadvisor.plan.models import LEVEL_ORDER

MAIN_SUBJECTS = ["TO", "VA", "N1", "LI", "HO", "SI", "SU", "DI", "GDKTPL", "TI"]
MAX_PICKS = 6


def _load_plan():
    d, ss = data(), st.session_state
    upload = ss.get("plan_upload")
    if upload is None:
        ss["load_msgs"] = ("error", ["Em chưa chọn tệp kế hoạch."])
        return
    try:
        state, warnings = plan_file.load(upload.getvalue(), d.known())
    except plan_file.PlanFileError as e:
        ss["load_msgs"] = ("error", [str(e)])
        return
    apply_state(state, d)
    ss["load_msgs"] = ("ok", ["Đã mở kế hoạch."] + warnings)


def _go(page: str):
    st.session_state["page"] = page


# ---------------------------------------------------------------- pages

def page_profile(d: AppData):
    st.header("Về em")
    st.caption("Mọi câu hỏi đều không bắt buộc, trừ điểm các môn và tỉnh/thành. Thông tin em nhập chỉ nằm trong "
               "phiên làm việc này, ứng dụng không lưu lại.")
    st.radio("Điểm em nhập là", ["expected", "real"], key="score_kind", horizontal=True,
             format_func={"expected": "Điểm dự kiến (trước kỳ thi)", "real": "Điểm thi thật (sau kỳ thi)"}.get)
    st.subheader("Điểm các môn (thang 10)")
    main = [c for c in MAIN_SUBJECTS if c in d.subjects]
    other = [c for c in d.subjects if c not in main]
    _score_inputs(d, main)
    with st.expander("Môn khác (ngoại ngữ khác, công nghệ...)"):
        _score_inputs(d, other)

    st.subheader("Nơi ở và ưu tiên")
    st.selectbox("Tỉnh/thành nơi em ở", d.provinces, key="province", index=None, placeholder="Chọn tỉnh/thành")
    c1, c2, c3 = st.columns(3)
    c1.selectbox("Khu vực ưu tiên", AREAS, key="area")
    c2.selectbox("Đối tượng ưu tiên", CATEGORIES, key="category", format_func=CATEGORY_VI.get)
    c3.number_input("Năm tốt nghiệp THPT", min_value=d.admission_year - 10, max_value=d.admission_year, step=1,
                    key="grad_year")
    st.subheader("Gia đình")
    c1, c2 = st.columns(2)
    c1.number_input("Ngân sách học phí (triệu đồng/năm)", min_value=0.0, max_value=1000.0, step=5.0, key="budget",
                    placeholder="không giới hạn")
    c2.radio("Em muốn học gần nhà?", [False, True], key="near_home", horizontal=True,
             format_func=lambda x: "Có" if x else "Không")
    st.selectbox("Trường em thích nhất (không bắt buộc)", sorted(d.school_names, key=lambda c: d.school_names[c]),
                 key="favorite_school", index=None, placeholder="Không chọn",
                 format_func=lambda c: f"{d.school_names[c]} ({c})",
                 help="Chương trình của trường này được ưu tiên ở mọi mức và có thể chiếm hết các nguyện vọng an toàn, "
                      "kể cả ngành khác ngành em chọn.")
    st.button("Tiếp: chọn ngành →", on_click=_go, args=(PAGES[1],), type="primary")


def _score_inputs(d: AppData, codes: list[str], per_row: int = 4):
    """One row of columns per `per_row` subjects, so the keyboard moves along a row (Toán -> Ngữ văn -> ...)."""
    for start in range(0, len(codes), per_row):
        for col, code in zip(st.columns(per_row), codes[start:start + per_row]):
            col.number_input(d.subjects[code], min_value=0.0, max_value=10.0, step=0.25, key=f"score_{code}",
                             placeholder="chưa nhập")


def _add_pick(code: str):
    picks = st.session_state["picks"]
    if code not in picks and len(picks) < MAX_PICKS:
        picks.append(code)


def _remove_pick(code: str):
    ss = st.session_state
    ss["picks"] = [c for c in ss["picks"] if c != code]
    for i in (1, 2):
        if ss.get(f"item{i}") == code:
            ss[f"item{i}"], ss[f"close{i}"] = None, []


def _kind(d: AppData, code: str) -> str:
    return "Nhóm ngành" if d.catalog.majors[code].level == "nhom_nganh" else "Ngành"


def _where(d: AppData, code: str) -> str:
    m = d.catalog.majors[code]
    return f"{m.n_programs_hn} chương trình ở Hà Nội, {m.n_programs_hcm} ở TP.HCM"


def page_choose(d: AppData):
    st.header("Chọn ngành")
    st.radio("Em bắt đầu thế nào?", PATHS, key="path", captions=["", "sắp có", "trả lời 12 câu hỏi"])
    if st.session_state["path"] == PATHS[1]:
        st.info("Cách này đang được xây dựng. Em dùng “Em đã có vài lựa chọn” hoặc “Em chưa biết gì” nhé.")
        return
    if st.session_state["path"] == PATHS[2]:
        questionnaire(d, st.session_state["picks"], MAX_PICKS, _add_pick)
    else:
        _search(d)
    _shortlist(d)


def _search(d: AppData):
    cat = d.catalog
    st.subheader("Tìm ngành")
    query = st.text_input("Gõ tên ngành, tên viết tắt hoặc từ quen thuộc (ví dụ: CNTT, KHMT, logistics, bác sĩ)",
                          key="query")
    if query:
        hits = cat.search(query, limit=12)
        if not hits:
            st.caption("Không tìm thấy ngành nào. Em thử cách gọi khác nhé.")
        for h in hits:
            m = cat.majors[h.code]
            c1, c2 = st.columns([5, 1])
            text = f"**{m.label}** · {_kind(d, h.code).lower()}"
            if m.display and m.display != m.official:
                text += f"  \n:gray[Tên Bộ GD&ĐT: {m.official}]"
            if h.tier == 3:
                text += f"  \n:gray[Khớp với tên chương trình ở trường: {h.matched}]"
            if m.level == "nhom_nganh":
                text += "  \n:gray[Gồm: " + ", ".join(cat.label(c) for c in m.children[:4]) + \
                        (", ..." if len(m.children) > 4 else "") + "]"
            text += f"  \n:gray[{_where(d, h.code)}]"
            c1.markdown(text)
            picked = h.code in st.session_state["picks"]
            c2.button("Đã chọn" if picked else "Chọn", key=f"add_{h.code}", on_click=_add_pick, args=(h.code,),
                      disabled=picked or len(st.session_state["picks"]) >= MAX_PICKS)


def _shortlist(d: AppData):
    cat = d.catalog
    picks = st.session_state["picks"]
    st.subheader(f"Các lựa chọn của em ({len(picks)})")
    if not picks:
        st.caption("Chưa có lựa chọn nào. Em có thể chọn 1 ngành, hoặc từ 2 ngành trở lên để so sánh.")
        return
    for code in picks:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"**{cat.label(code)}** · {_kind(d, code).lower()}")
        c2.button("Bỏ", key=f"rm_{code}", on_click=_remove_pick, args=(code,))

    if len(picks) >= 2:
        st.subheader("So sánh")
        compare(d, picks)
    else:
        st.caption("Muốn so sánh, em chọn thêm ít nhất 1 ngành nữa; hoặc xếp thứ tự ngay bên dưới.")

    st.subheader("Xếp thứ tự")
    st.caption("Em chọn tối đa 2 lựa chọn, theo thứ tự em thích hơn. Danh sách nguyện vọng ưu tiên lựa chọn 1.")
    ss = st.session_state
    for key in ("item1", "item2"):
        if ss.get(key) not in picks:
            ss[key] = None
    if ss["item2"] == ss["item1"]:
        ss["item2"] = None
    st.selectbox("Lựa chọn 1", picks, key="item1", index=None, format_func=cat.label, placeholder="Chọn")
    st.selectbox("Lựa chọn 2 (không bắt buộc)", [c for c in picks if c != ss["item1"]], key="item2", index=None,
                 format_func=cat.label, placeholder="Không chọn")

    nganh = cat.nganh_codes()
    for i in (1, 2):
        main = ss.get(f"item{i}")
        if not main:
            ss[f"close{i}"] = []
            ss[f"_close_for{i}"] = None
            continue
        if ss.get(f"_close_for{i}") != main:          # a new main item: propose its closest ngành (spec 3.3)
            ss[f"close{i}"] = d.facts.proposed_close(main, MAX_CLOSE, exclude={main, ss.get("item1"), ss.get("item2")})
            ss[f"_close_for{i}"] = main
        ss[f"close{i}"] = [c for c in ss[f"close{i}"] if c in nganh and c != main]
        st.multiselect(f"Ngành gần của lựa chọn {i} ({cat.label(main)}), tối đa {MAX_CLOSE}",
                       [c for c in nganh if c != main], key=f"close{i}", max_selections=MAX_CLOSE,
                       format_func=cat.label, placeholder="Không có")
    st.caption("Ngành gần là ngành có công việc sau khi ra trường và kiến thức cần có giống ngành em chọn. Ứng dụng "
               "đề xuất sẵn tối đa 2 ngành gần (tính từ dữ liệu nghề nghiệp, bản nháp đang được duyệt); em có thể bỏ "
               "hoặc thay.")
    st.button("Tiếp: xem danh sách nguyện vọng →", on_click=_go, args=(PAGES[2],), type="primary",
              disabled=not ss.get("item1"))


def compare(d: AppData, picks: list[str]):
    """Side by side on the four facts (spec 3.1): content and jobs and interests from step 6 (O*NET), strong subjects
    from the accepted combinations; income not yet."""
    cat = d.catalog
    pending = ":gray[Chưa có dữ liệu.]"
    any_facts = False
    for start in range(0, len(picks), 3):
        cols = st.columns(3)
        for col, code in zip(cols, picks[start:start + 3]):
            m = cat.majors[code]
            f = d.facts.get(code)
            any_facts |= not f.empty
            with col.container(border=True):
                st.markdown(f"**{m.label}**")
                if m.display and m.display != m.official:
                    st.caption(f"Tên Bộ GD&ĐT: {m.official}")
                st.markdown("**Học gì**")
                st.markdown("Kiến thức chính: " + ", ".join(f.knowledge) if f.knowledge else pending)
                st.markdown("**Cần mạnh môn nào**")
                shares = cat.combo_shares(code, top=4)
                if shares:
                    st.markdown("Tổ hợp hay gặp:  \n" + "  \n".join(
                        f"{combo_label(s.combo)} ({' - '.join(s.subjects)}): {round(s.share * 100)}% chương trình"
                        for s in shares))
                else:
                    st.markdown(pending)
                st.markdown("**Việc làm sau khi ra trường**")
                st.markdown("; ".join(f.jobs) if f.jobs else pending)
                st.caption(f"Thu nhập: {INCOME_CONTEXT}.")
                st.markdown("**Có hợp với em không**")
                if f.interests:
                    st.markdown("Hợp với người thích: " + "; ".join(f"{name.lower()} ({desc})" if desc else name
                                                                    for name, desc in f.interests))
                else:
                    st.markdown(pending)
                if f.close:
                    st.caption("Ngành gần: " + ", ".join(cat.label(c) for c in f.close[:3]))
                if m.level == "nhom_nganh":
                    st.caption("Gồm: " + ", ".join(cat.label(c) for c in m.children))
                st.caption(_where(d, code))
                sheet = (d.sheets or {}).get(code)
                if sheet:
                    with st.expander("Bản tóm tắt nhóm ngành"):
                        st.markdown(sheet.split("\n", 1)[1] if sheet.startswith("# ") else sheet)
    if any_facts:
        st.caption(ONET_CREDIT + (" Tên tiếng Việt và cách ghép ngành với nghề đang là bản nháp, chưa duyệt."
                                  if any(d.facts.get(c).draft for c in picks) else ""))


def page_list(d: AppData):
    st.header("Danh sách nguyện vọng")
    state = current_state(d)
    missing = state.missing_for_list()
    if missing:
        what = {"scores": "điểm các môn (trang Về em)", "home_province": "tỉnh/thành nơi em ở (trang Về em)",
                "shortlist": "lựa chọn 1 (trang Chọn ngành)"}
        st.info("Để lập danh sách, em cần nhập: " + "; ".join(what[m] for m in missing) + ".")
        return
    if state.list_choice is None:                 # three recommended lists first
        recommendations(d, state)
        return
    chosen_header(d, state)
    result = d.build_list(state)
    last = st.session_state.pop("last_change", None)
    if last:
        if last["done"]:
            st.success("Đã áp dụng: " + "; ".join(last["done"]) + (f". {last['diff']}" if last["diff"] else ""))
        for err in last["errors"]:
            st.error(err)
    with st.expander("Danh sách được lập thế nào?", expanded=False):
        st.write(HOW_THE_LIST_IS_BUILT)
        for lv in reversed(LEVEL_ORDER):
            st.markdown(f"- **{LEVEL_VI[lv]}**: {LEVEL_HELP[lv]}.")
    st.info(EXTRA_POINTS_REMINDER)
    if state.score_kind == "expected":
        st.caption("Em đang dùng điểm dự kiến. Sau kỳ thi, em mở lại kế hoạch và thay bằng điểm thật.")
    for text in note_texts(result, [e.main for e in state.shortlist], d.catalog):
        st.warning(text)
    if state.favorite_school in d.school_names:
        st.info(favorite_note(d.school_names[state.favorite_school], result))
    if not result.wishes:
        st.error("Chưa lập được nguyện vọng nào: không có chương trình nào của ngành em chọn có điểm chuẩn mà em có "
                 "đủ điểm các môn trong tổ hợp xét tuyển.")
        adjust_panel(d, state, result)
        return
    rows = wish_rows(result, [e.main for e in state.shortlist], d.catalog)
    st.dataframe(rows, hide_index=True, width="stretch", height=36 * (len(rows) + 1) + 3)   # every row visible
    if any(w.candidate.is_mixed_method for w in result.wishes):
        st.caption(MIXED_METHOD_NOTE)
    chs = d.chances(state, result)
    cc = d.list_cfg["chances"]
    at_entered = next((c for c in chs if c.score_shift == 0.0), None)
    if at_entered and at_entered.none > cc["warn_no_admission_above"]:
        st.warning(no_admission_warning(at_entered.none, cc["display_cap"]))
    if chs:
        st.markdown("**Khả năng trúng tuyển**")
        for line in chance_lines(chs, cc["display_cap"], state.score_kind == "expected"):
            st.markdown(f"- {line}")
        st.caption(chance_note(d.change_model.years))
    st.caption("Điểm chuẩn là của phương thức xét điểm thi THPT, quy đổi về thang 30. "
               f"Điểm của em gồm tổng 3 môn của tổ hợp có lợi nhất và điểm ưu tiên "
               f"({state.area}, {CATEGORY_VI[state.category].lower()}).")
    adjust_panel(d, state, result)


def page_save(d: AppData):
    st.header("Lưu kế hoạch")
    state = current_state(d)
    st.write("Tải kế hoạch về máy để lần sau mở lại, ví dụ sau kỳ thi để thay điểm dự kiến bằng điểm thật. Tệp gồm "
             "mọi thứ em đã nhập; ứng dụng không lưu bản nào ở phía mình.")
    st.download_button("Tải kế hoạch", plan_file.dump(state, d.admission_year), file_name="ke-hoach-uniadvisor.json",
                       mime="application/json", type="primary")
    if state.scores:
        st.caption("Điểm đã nhập: " + ", ".join(f"{d.subjects[c]} {num(v)}" for c, v in state.scores.items()))


def sidebar(d: AppData):
    with st.sidebar:
        st.title("UniAdvisor")
        st.radio("Các bước", PAGES, key="page", label_visibility="collapsed")
        st.divider()
        st.markdown("**Mở kế hoạch đã lưu**")
        st.file_uploader("Tệp kế hoạch (.json)", type=["json"], key="plan_upload", label_visibility="collapsed")
        st.button("Mở kế hoạch", on_click=_load_plan)
        msgs = st.session_state.pop("load_msgs", None)
        if msgs:
            kind, texts = msgs
            (st.error if kind == "error" else st.success)(texts[0])
            for t in texts[1:]:
                st.warning(t)


def main():
    st.set_page_config(page_title="UniAdvisor", layout="wide")
    d = data()
    init_session(d)
    sidebar(d)
    {PAGES[0]: page_profile, PAGES[1]: page_choose, PAGES[2]: page_list, PAGES[3]: page_save}[
        st.session_state["page"]](d)
