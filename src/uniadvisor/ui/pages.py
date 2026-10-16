"""The Streamlit page: Về em -> Chọn ngành ("Đã có ngành quan tâm" / "Chưa xác định ngành") -> Danh sách nguyện vọng -> Lưu kế hoạch.

Privacy: the page keeps what the student enters only in the Streamlit session (memory, per browser tab). It
logs nothing, sends nothing out, and the plan file is downloaded to the student's device. Usage statistics are turned
off in .streamlit/config.toml.
"""

from __future__ import annotations

import streamlit as st

from uniadvisor.explanations import build_wish_explanation
from uniadvisor.ui import plan_file
from uniadvisor.ui.adjust import adjust_panel
from uniadvisor.ui.discover import questionnaire
from uniadvisor.ui.lists_view import chosen_header, recommendations
from uniadvisor.ui import major_info
from uniadvisor.ui.service import AppData
from uniadvisor.ui.session import PAGES, PATHS, apply_state, current_state, data, init_session
from uniadvisor.ui.state import AREAS, CATEGORIES, COMPULSORY, MAX_CLOSE
from uniadvisor.ui.texts import (
    CATEGORY_VI, EXTRA_POINTS_REMINDER, HOW_THE_LIST_IS_BUILT, LEVEL_HELP, LEVEL_VI, MIXED_METHOD_NOTE, chance_lines,
    chance_note, favorite_note, no_admission_warning, note_texts, num, wish_rows,
)
from uniadvisor.planner.models import LEVEL_ORDER

# Electives in the order students know them (the THPT exam since 2025); other exam subjects follow.
ELECTIVE_ORDER = ["N1", "LI", "HO", "SI", "SU", "DI", "GDKTPL", "TI", "CNCN", "CNNN"]
MAX_PICKS = 6
# Streamlit's upload box has fixed English text ("Upload", "1MB per file • JSON"); this swaps it for Vietnamese.
UPLOADER_VI = """<style>
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {font-size: 0;}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
  content: "Chọn tệp"; font-size: 0.875rem;}
[data-testid="stFileUploaderDropzoneInstructions"] span {font-size: 0;}
[data-testid="stFileUploaderDropzoneInstructions"] span::after {content: "Tệp .json, tối đa 1 MB"; font-size: 0.75rem;}
</style>"""


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
    st.caption("Mọi câu hỏi đều không bắt buộc, trừ điểm thi và tỉnh/thành. Thông tin em nhập chỉ nằm trong "
               "phiên làm việc này, ứng dụng không lưu lại.")
    st.radio("Điểm em nhập là", ["expected", "real"], key="score_kind", horizontal=True,
             format_func={"expected": "Điểm dự kiến (trước kỳ thi)", "real": "Điểm thi thật (sau kỳ thi)"}.get)
    st.subheader("Điểm thi (thang 10)")
    st.caption("Hai môn bắt buộc là Toán và Ngữ văn; em chọn thêm 2 môn tự chọn em đăng ký thi.")
    _score_inputs(d)

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


def _score_box(col, d: AppData, code: str, label: str | None = None):
    col.number_input(label or d.subjects[code], min_value=0.0, max_value=10.0, step=0.25, key=f"score_{code}",
                     placeholder="chưa nhập")


def _score_inputs(d: AppData):
    """Toán and Ngữ văn, then the two electives: a subject picker and its score each."""
    ss = st.session_state
    c1, c2 = st.columns(2)
    for col, code in zip((c1, c2), [c for c in COMPULSORY if c in d.subjects]):
        _score_box(col, d, code)
    electives = [c for c in ELECTIVE_ORDER if c in d.subjects and c not in COMPULSORY]
    electives += [c for c in d.subjects if c not in electives and c not in COMPULSORY]
    if ss.get("elective2") == ss.get("elective1"):
        ss["elective2"] = None
    cols = st.columns(4)
    for i in (1, 2):
        other = ss.get(f"elective{3 - i}")
        pick_col, score_col = cols[2 * i - 2], cols[2 * i - 1]
        pick_col.selectbox(f"Môn tự chọn {i}", [c for c in electives if c != other], key=f"elective{i}", index=None,
                           format_func=d.subjects.get, placeholder="Chọn môn")
        code = ss.get(f"elective{i}")
        if code:
            _score_box(score_col, d, code, f"Điểm {d.subjects[code]}")
        else:
            score_col.number_input(f"Điểm môn tự chọn {i}", value=None, disabled=True, key=f"elective{i}_empty",
                                   placeholder="chọn môn trước")


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


def page_choose(d: AppData):
    st.header("Chọn ngành")
    st.radio("Em bắt đầu thế nào?", PATHS, key="path",
             captions=["tìm và so sánh tối đa 6 ngành", "trả lời 12 câu hỏi"])
    if st.session_state["path"] == PATHS[1]:
        questionnaire(d, st.session_state["picks"], MAX_PICKS, _add_pick)
    else:
        _search(d)
    _shortlist(d)


def _search(d: AppData):
    st.subheader("Tìm ngành")
    query = st.text_input("Gõ tên ngành, tên viết tắt hoặc từ quen thuộc (ví dụ: CNTT, KHMT, logistics, bác sĩ)",
                          key="query")
    if query:
        hits = major_info.search(d, query)
        if not hits:
            st.caption("Không tìm thấy ngành nào. Em thử cách gọi khác nhé.")
        for h in hits:
            c1, c2 = st.columns([5, 1])
            text = f"**{h['label']}** · {h['kind'].lower()}"
            if h["official"]:
                text += "  \n:gray[Tên Bộ GD&ĐT: " + h["official"] + "]"
            if h["matched"]:
                text += "  \n:gray[Khớp với tên chương trình ở trường: " + h["matched"] + "]"
            if h["children"]:
                text += "  \n:gray[Gồm: " + ", ".join(h["children"]) + (", ..." if h["more_children"] else "") + "]"
            text += "  \n:gray[" + h["where"] + "]"
            c1.markdown(text)
            picked = h["code"] in st.session_state["picks"]
            c2.button("Đã chọn" if picked else "Chọn", key="add_" + h["code"], on_click=_add_pick, args=(h["code"],),
                      disabled=picked or len(st.session_state["picks"]) >= MAX_PICKS)


def _shortlist(d: AppData):
    cat = d.catalog
    picks = st.session_state["picks"]
    st.subheader(f"Các ngành em quan tâm ({len(picks)})")
    if not picks:
        st.caption("Chưa có ngành nào. Em có thể chọn 1 ngành, hoặc từ 2 ngành trở lên để so sánh.")
        return
    for code in picks:
        c1, c2 = st.columns([5, 1])
        c1.markdown(f"**{cat.label(code)}** · {major_info.kind(d, code).lower()}")
        c2.button("Bỏ", key=f"rm_{code}", on_click=_remove_pick, args=(code,))

    if len(picks) >= 2:
        st.subheader("So sánh")
        compare(d, picks)
    else:
        st.caption("Muốn so sánh, em chọn thêm ít nhất 1 ngành nữa; hoặc xếp thứ tự ngay bên dưới.")

    st.subheader("Xếp thứ tự")
    st.caption("Em chọn tối đa 2 hướng học, theo thứ tự em thích hơn. Mỗi hướng học gồm một ngành chính và tối đa "
               "2 ngành gần. Danh sách nguyện vọng ưu tiên hướng học 1.")
    ss = st.session_state
    for key in ("item1", "item2"):
        if ss.get(key) not in picks:
            ss[key] = None
    if ss["item2"] == ss["item1"]:
        ss["item2"] = None
    st.selectbox("Hướng học 1", picks, key="item1", index=None, format_func=cat.label, placeholder="Chọn")
    st.selectbox("Hướng học 2 (không bắt buộc)", [c for c in picks if c != ss["item1"]], key="item2", index=None,
                 format_func=cat.label, placeholder="Không chọn")

    nganh = cat.nganh_codes()
    for i in (1, 2):
        main = ss.get(f"item{i}")
        if not main:
            ss[f"close{i}"] = []
            ss[f"_close_for{i}"] = None
            continue
        if ss.get(f"_close_for{i}") != main:          # a new main item: propose its closest ngành
            ss[f"close{i}"] = d.facts.proposed_close(main, MAX_CLOSE, exclude={main, ss.get("item1"), ss.get("item2")})
            ss[f"_close_for{i}"] = main
        ss[f"close{i}"] = [c for c in ss[f"close{i}"] if c in nganh and c != main]
        st.multiselect(f"Ngành gần của hướng học {i} ({cat.label(main)}), tối đa {MAX_CLOSE}",
                       [c for c in nganh if c != main], key=f"close{i}", max_selections=MAX_CLOSE,
                       format_func=cat.label, placeholder="Không có")
    st.caption("Ngành gần là ngành có công việc sau khi ra trường và kiến thức cần có giống ngành em chọn. Ứng dụng "
               "đề xuất sẵn tối đa 2 ngành gần (tính từ dữ liệu nghề nghiệp, đã rà soát); em có thể bỏ "
               "hoặc thay.")
    st.button("Tiếp: xem danh sách nguyện vọng →", on_click=_go, args=(PAGES[2],), type="primary",
              disabled=not ss.get("item1"))


def compare(d: AppData, picks: list[str]):
    """One row per ngành: a one-line summary, and the four facts (content, strong subjects, jobs, who it suits; O*NET
    and the accepted combinations) behind "Xem chi tiết"; income not yet."""
    pending = ":gray[Chưa có dữ liệu.]"
    details = [major_info.detail(d, code) for code in picks]
    for x in details:
        with st.container(border=True):
            st.markdown(f"**{x['label']}** · {x['kind'].lower()}"
                        + (f"  \n:gray[Tên Bộ GD&ĐT: {x['official']}]" if x["official"] else ""))
            summary = [x["where"]]
            if x["top_combos"]:
                summary.append("tổ hợp hay gặp: " + ", ".join(x["top_combos"]))
            if x["interest_names"]:
                summary.append("hợp với người thích " + ", ".join(x["interest_names"]))
            st.caption(" · ".join(summary))
            with st.expander("Xem chi tiết"):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.markdown("**Học gì**")
                    st.markdown("Kiến thức chính: " + ", ".join(x["knowledge"]) if x["knowledge"] else pending)
                    if x["children"]:
                        st.caption("Gồm: " + ", ".join(x["children"]))
                with c2:
                    st.markdown("**Cần mạnh môn nào**")
                    if x["combos"]:
                        st.markdown("Tổ hợp hay gặp:  \n" + "  \n".join(
                            f"{s['label']} ({' - '.join(s['subjects'])}): {s['share_pct']}% chương trình"
                            for s in x["combos"]))
                    else:
                        st.markdown(pending)
                with c3:
                    st.markdown("**Việc làm sau khi ra trường**")
                    st.markdown("; ".join(x["jobs"]) if x["jobs"] else pending)
                    st.caption(f"Thu nhập: {x['income']}.")
                with c4:
                    st.markdown("**Có hợp với em không**")
                    if x["interests"]:
                        st.markdown("Hợp với người thích: " + "; ".join(
                            f"{i['name'].lower()} ({i['description']})" if i["description"] else i["name"]
                            for i in x["interests"]))
                    else:
                        st.markdown(pending)
                    if x["close"]:
                        st.caption("Ngành gần: " + ", ".join(x["close"]))
            if x["sheet"]:
                with st.expander("Bản tóm tắt nhóm ngành"):
                    st.markdown(x["sheet"])
    if credit := major_info.credit(details):
        st.caption(credit)


def page_list(d: AppData):
    st.header("Danh sách nguyện vọng")
    state = current_state(d)
    missing = state.missing_for_list()
    if missing:
        what = {"scores": "điểm các môn (trang Về em)", "home_province": "tỉnh/thành nơi em ở (trang Về em)",
                "shortlist": "hướng học 1 (trang Chọn ngành)"}
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
    _wish_reasons(d, state, result)
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


def _wish_reasons(d: AppData, state, result):
    """A visible route to the same fixed explanation as “Vì sao NVn ở đó?” in chat.

    This is deliberately not generated prose (a fixed template, `explanations.py`) and does not add an item to the chat
    history.  A keyed toggle keeps one explanation open while the student reads it; it is rebuilt from the current list
    after every confirmed change.
    """
    st.subheader("Vì sao từng nguyện vọng ở đây?")
    st.caption("Chọn một nguyện vọng để xem lý do có mặt và thứ tự của nó trong danh sách.")
    context = d.chat_context(state, result)
    cols = st.columns(3)
    for index, wish in enumerate(result.wishes):
        key = f"why_wish_{wish.nv}"
        with cols[index % len(cols)]:
            if st.button(f"Vì sao ở đây? · NV{wish.nv}", key=f"why_wish_button_{wish.nv}"):
                st.session_state[key] = not st.session_state.get(key, False)
            if st.session_state.get(key, False):
                explanation = build_wish_explanation(wish, context)
                st.markdown(explanation.markdown())


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
        st.markdown(UPLOADER_VI, unsafe_allow_html=True)
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
