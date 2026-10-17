"""The Streamlit page, run headless (streamlit.testing) on the fake database."""

import re
import tomllib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from uniadvisor.ui.service import ENV_DB
from uniadvisor.paths import ROOT

APP = str(ROOT / "app.py")


@pytest.fixture
def at(fake_db_path, monkeypatch):
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception
    return app


def go(at, page):
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception


def fill_profile(at, electives=("LI", "N1")):
    at.selectbox(key="elective1").set_value(electives[0])
    at.selectbox(key="elective2").set_value(electives[1]).run()
    for key, value in {"score_TO": 8.0, "score_VA": 7.0, "score_LI": 7.0, "score_N1": 8.0}.items():
        if key[6:] in ("TO", "VA", *electives):
            at.number_input(key=key).set_value(value)
    at.selectbox(key="province").set_value("Hà Nội")
    at.run()


def pick(at, query, code):
    at.text_input(key="query").set_value(query).run()
    at.button(key=f"add_{code}").click().run()
    assert not at.exception


def test_profile_page(at):
    assert [h.value for h in at.header] == ["Về em"]
    # Toán and Ngữ văn, then two electives chosen first (fake database: 6 subjects), plus the year and the budget.
    assert {n.key for n in at.number_input} == {"score_TO", "score_VA", "elective1_empty", "elective2_empty",
                                                "grad_year", "budget"}
    assert at.number_input(key="score_VA").label == "Ngữ văn" and at.number_input(key="score_TO").value is None
    assert at.selectbox(key="elective1").options == ["Tiếng Anh", "Vật lí", "Hóa học", "Sinh học"]
    at.selectbox(key="elective1").set_value("HO").run()
    assert at.number_input(key="score_HO").label == "Điểm Hóa học"
    assert "Hóa học" not in at.selectbox(key="elective2").options
    assert at.number_input(key="grad_year").value == 2027
    assert at.selectbox(key="province").options[:2] == ["Hà Nội", "TP. Hồ Chí Minh"]
    assert len(at.selectbox(key="province").options) == 34


def test_list_needs_scores_province_and_shortlist(at):
    go(at, "3. Danh sách nguyện vọng")
    assert "điểm các môn" in at.info[0].value and "hướng học 1" in at.info[0].value


def test_whole_flow(at):
    fill_profile(at)
    go(at, "2. Chọn ngành")
    pick(at, "khmt", "7480101")
    assert at.button(key="add_7480101").label == "Đã chọn" and at.button(key="add_7480101").disabled
    pick(at, "cntt", "7480201")
    assert at.session_state["picks"] == ["7480101", "7480201"]
    texts = " ".join(m.value for m in at.markdown)
    assert "A00 (Toán - Vật lí - Hóa học): 100% chương trình" in texts            # compare: strong subjects
    assert "Kiến thức chính: Toán học, Máy tính và điện tử" in texts                # facts
    assert "Kỹ sư phát triển phần mềm" in texts
    assert any("O*NET 31.0" in c.value for c in at.caption)                        # credit line
    assert "Tóm tắt đã duyệt (fake)." in texts and "Bản nháp (fake)." not in texts  # reviewed fact sheets only
    at.selectbox(key="item1").set_value("7480101").run()
    assert at.multiselect(key="close1").value == ["7480201", "7480103"]            # proposed close ngành
    at.selectbox(key="item2").set_value("7480201").run()
    at.multiselect(key="close1").set_value(["7480103"]).run()
    assert not at.exception

    go(at, "3. Danh sách nguyện vọng")
    assert at.session_state["score_TO"] == 8.0 and at.session_state["province"] == "Hà Nội"   # kept across pages
    assert "Ba phương án gợi ý cho em" in [h.value for h in at.subheader]           # three lists first
    assert len(at.get("vega_lite_chart")) == 6 and len(at.dataframe) == 4    # 3 in the cards + 3 under Xem chi tiết; 3 lists + table
    assert any(s.value.startswith("**Gợi ý cho em: ") for s in at.success)     # one list is recommended
    assert sum("✅ Gợi ý" in m.value for m in at.markdown) == 1
    assert any("đều đủ nguyện vọng an toàn" in c.value for c in at.caption)
    choose(at)
    assert at.session_state["list_choice"] == "dung_nganh" and len(at.session_state["recommended"]) == 3
    assert any("Phương án em chọn: Đúng ngành nhất" in m.value for m in at.markdown)
    rows = at.dataframe[0].value
    assert list(rows["NV"]) == list(range(1, len(rows) + 1))
    assert set(rows["Chương trình"]) == {"Khoa học máy tính", "Kỹ thuật phần mềm", "Kỹ thuật phần mềm *",
                                         "Công nghệ thông tin"}              # the military course is over 4 points away
    assert set(rows["Hướng học"]) == {"1 · ngành chính", "1 · ngành gần của Khoa học máy tính", "2 · ngành chính"}
    assert any("Danh sách chỉ có 4 nguyện vọng" in w.value for w in at.warning)
    assert any("Có dấu *" in c.value for c in at.caption)
    assert not any("trường thích nhất" in i.value for i in at.info)             # no favorite school chosen
    chance = [m.value for m in at.markdown if "khả năng trúng tuyển" in m.value]   # expected scores: 3 lines
    assert len(chance) == 3 and chance[1].startswith("- Nếu em thi đúng như dự kiến")
    assert any(c.value.startswith("Cách tính: điểm chuẩn mỗi năm thay đổi") for c in at.caption)

    go(at, "1. Về em")
    at.selectbox(key="favorite_school").set_value("HCB").run()
    go(at, "3. Danh sách nguyện vọng")
    assert any("là trường thích nhất" in i.value for i in at.info)

    go(at, "4. Lưu kế hoạch")
    assert [h.value for h in at.header] == ["Lưu kế hoạch"]
    go(at, "2. Chọn ngành")                                                         # choices are still there
    assert at.selectbox(key="item1").value == "7480101" and at.multiselect(key="close1").value == ["7480103"]


def test_removing_a_pick_clears_its_rank(at):
    go(at, "2. Chọn ngành")
    pick(at, "khmt", "7480101")
    pick(at, "cntt", "7480201")
    at.selectbox(key="item1").set_value("7480201").run()
    at.button(key="rm_7480201").click().run()
    assert at.session_state["picks"] == ["7480101"] and at.session_state["item1"] is None
    assert not at.exception


def test_two_paths_only(at):
    go(at, "2. Chọn ngành")
    assert at.radio(key="path").options == ["Đã có ngành quan tâm", "Chưa xác định ngành"]


def test_questionnaire_path_suggests_groups(at):
    go(at, "2. Chọn ngành")
    at.radio(key="path").set_value("Chưa xác định ngành").run()
    assert not at.exception and len([w for w in at.multiselect if w.key.startswith("quiz_")]) == 8      # the capped questions with long lists are dropdowns
    at.multiselect(key="quiz_q1").set_value(["Toán", "Tin học"])
    at.multiselect(key="quiz_q2").set_value(["Toán"])                         # also liked: not counted
    at.multiselect(key="quiz_q6").set_value(["Máy tính"])
    at.pills(key="quiz_q11").set_value("Hiểu vì sao mọi thứ xảy ra")
    next(b for b in at.button if b.label == "Xem gợi ý").click().run()
    assert not at.exception
    assert "Nhóm ngành có thể hợp với em" in [h.value for h in at.subheader]
    assert any("bỏ lựa chọn trùng với câu 1" in c.value for c in at.caption)
    assert at.session_state["quiz_answers"]["q2"] is None
    assert any("Vì em chọn" in m.value and "Máy tính" in m.value for m in at.markdown)
    at.button(key="quiz_add_74801").click().run()
    assert "74801" in at.session_state["picks"]
    assert "Các ngành em quan tâm (1)" in [h.value for h in at.subheader]
    go(at, "1. Về em")                                                     # answers kept across pages
    go(at, "2. Chọn ngành")
    assert at.multiselect(key="quiz_q1").value == ["Toán", "Tin học"]


def test_privacy_settings():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False
    # The app code sends nothing out and logs nothing.
    for path in (ROOT / "src" / "uniadvisor" / "ui").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(requests|urllib|http|socket|logging)\b", source, re.M), path
        assert "print(" not in source, path


def choose(at, which="dung_nganh"):
    at.button(key=f"choose_{which}").click().run()
    assert not at.exception


def ready_list(at):
    fill_profile(at)
    at.session_state["picks"] = ["74801"]
    at.session_state["item1"] = "74801"
    go(at, "3. Danh sách nguyện vọng")
    choose(at)
    assert len(at.dataframe[0].value) >= 3


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_chat_card_confirm_and_undo(at):
    ready_list(at)
    at.chat_input[0].set_value("bỏ trường FHN và ngân sách 40 triệu").run()
    assert not at.exception
    assert [c.label for c in at.checkbox] == ["Bỏ Trường Đại học Giả Hà Nội (mọi chương trình của trường)",
                                              "Ngân sách học phí: 40 triệu/năm"]
    assert at.session_state["removed_schools"] == []                    # nothing changes before Xác nhận
    at.checkbox[1].uncheck()                                            # [Sửa]-style: untick one change
    button(at, "Xác nhận").click().run()
    assert at.session_state["removed_schools"] == ["HNA"] and at.session_state["budget"] is None
    assert "Trường Đại học Giả Hà Nội" in at.success[0].value
    button(at, "Hoàn tác thay đổi gần nhất").click().run()
    assert at.session_state["removed_schools"] == [] and not at.exception


def test_chat_card_asks_what_is_unclear(at):
    ready_list(at)
    at.chat_input[0].set_value("trường Giả cộng 1 điểm").run()
    button(at, "Xác nhận").click().run()
    assert "Em chọn giúp mình: trường nào" in at.error[0].value         # the card stays and asks
    at.selectbox(key=next(s.key for s in at.selectbox if s.label == "Trường nào?")).set_value("HCB").run()
    button(at, "Xác nhận").click().run()
    assert at.session_state["extra_points"] == {"HCB": 1.0}


def test_chat_answers_and_help(at):
    ready_list(at)
    at.chat_input[0].set_value("vì sao NV1 lại ở đó?").run()
    assert at.chat_message[-1].markdown[0].value.startswith("**NV1 · ")
    at.chat_input[0].set_value("trời đẹp quá").run()
    assert at.chat_message[-1].markdown[0].value.startswith("Mình chưa hiểu ý em")
    assert not at.checkbox                                               # no card for questions or chit-chat


def test_wish_reason_button_uses_the_current_wish(at):
    ready_list(at)
    button(at, "Vì sao ở đây? · NV1").click().run()
    assert not at.exception
    assert any("**Vì sao có trong danh sách:**" in markdown.value for markdown in at.markdown)


def test_controls(at):
    ready_list(at)
    at.number_input(key="adj_budget").set_value(20.0)
    button(at, "Đổi ngân sách").click().run()
    assert at.session_state["budget"] == 20.0
    button(at, "Bật “muốn học gần nhà”").click().run()
    assert at.session_state["near_home"] is True
    assert "SI" not in at.selectbox(key="adj_subject").options      # Toán, Văn and the two electives only
    at.selectbox(key="adj_subject").set_value("N1")
    at.number_input(key="adj_score").set_value(9.0)
    button(at, "Đổi điểm").click().run()
    assert at.session_state["score_N1"] == 9.0
    at.selectbox(key="adj_rm_school").set_value("HNA").run()
    button(at, "Bỏ trường").click().run()
    assert at.session_state["removed_schools"] == ["HNA"]
    button(at, "Đưa lại Trường Đại học Giả Hà Nội").click().run()
    assert at.session_state["removed_schools"] == []
    at.selectbox(key="adj_close_new_0").set_value("7480201").run()
    button(at, "Thêm").click().run()
    assert at.session_state["close1"] == ["7480201"] and not at.exception


def test_second_list_follows_the_answers(at):
    fill_profile(at)
    at.session_state["picks"] = ["74801"]
    at.session_state["item1"] = "74801"
    go(at, "3. Danh sách nguyện vọng")                                   # no answers: Hợp môn học nhất
    keys = {b.key for b in at.button if (b.key or "").startswith("choose_")}
    assert keys == {"choose_dung_nganh", "choose_hop_mon", "choose_tiet_kiem"}
    assert any("thay cho “Hợp sở thích nhất”" in c.value for c in at.caption)

    go(at, "2. Chọn ngành")                                                 # answer the questions
    at.radio(key="path").set_value("Chưa xác định ngành").run()
    at.multiselect(key="quiz_q6").set_value(["Máy tính"])
    next(b for b in at.button if b.label == "Xem gợi ý").click().run()
    go(at, "3. Danh sách nguyện vọng")
    keys = {b.key for b in at.button if (b.key or "").startswith("choose_")}
    assert keys == {"choose_dung_nganh", "choose_nghe_nghiep", "choose_tiet_kiem"}
    choose(at, "nghe_nghiep")
    assert any("Phương án em chọn: Hợp sở thích nhất" in m.value for m in at.markdown)

    at.session_state["quiz_answers"] = None                                   # answers cleared: Hợp môn instead
    at.run()
    assert any("Phương án em chọn: Hợp môn học nhất" in m.value for m in at.markdown)
    assert any("dùng phương án Hợp môn học nhất thay thế" in c.value for c in at.caption)


def test_free_text_guesses_are_confirmed_first(at):
    go(at, "2. Chọn ngành")
    at.radio(key="path").set_value("Chưa xác định ngành").run()
    at.text_area(key="quiz_text").set_value("em thích vẽ nhưng sợ máu")
    next(b for b in at.button if b.label == "Xem gợi ý").click().run()
    assert not at.exception
    assert at.session_state["quiz_answers"]["q4"] is None                     # not an answer until confirmed
    keep = at.pills(key="quiz_guess_keep")
    assert len(keep.options) == 2 and set(keep.value) == set(keep.options)
    keep.set_value([o for o in keep.options if "Vẽ" in o])                 # the student drops one guess
    at.button(key="quiz_guess_apply").click().run()
    assert at.session_state["quiz_answers"]["q4"] == ["drawing"] and at.session_state["quiz_answers"]["q12"] is None
    assert at.multiselect(key="quiz_q4").value == ["Vẽ"]
