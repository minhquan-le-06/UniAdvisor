"""Fact sheets (src/uniadvisor/facts/sheets.py): drafts say only what the pack says; the automatic checks catch the rest."""

import sqlite3

from uniadvisor import db
from uniadvisor.facts.sheets import (HEADINGS, SOURCES, check_sheet, draft_sheet, insert_sheets, read_sheet,
                                     write_drafts)

PACK = {
    "code": "74802", "name": "Công nghệ thông tin", "official_name": "Công nghệ thông tin",
    "programs": {"total": 167, "ha_noi": 92, "tp_hcm": 75, "schools": 78},
    "nganh": [{"code": "7480201", "name": "Công nghệ thông tin", "programs": 134},
              {"code": "7480202", "name": "An toàn thông tin", "programs": 33}],
    "knowledge": ["Máy tính và điện tử", "Toán học"],
    "jobs": ["Kỹ sư phát triển phần mềm", "Kiến trúc sư mạng máy tính"],
    "interests": [{"type": "Nghiên cứu", "meaning": "thích tìm hiểu, phân tích"}],
    "combos": [{"code": "A01", "subjects": ["Toán", "Vật lí", "Tiếng Anh"], "share_pct": 92},
               {"code": "A00", "subjects": ["Toán", "Vật lí", "Hóa học"], "share_pct": 90}],
    "close_nganh": ["Khoa học máy tính"],
    "income": "để tham khảo, 8,7 triệu đồng/tháng năm 2024",
    "sources": SOURCES, "facts_reviewed": False,
}


def test_draft_passes_its_checks(tmp_path):
    path = tmp_path / "74802.md"
    path.write_text(draft_sheet(PACK), encoding="utf-8")
    meta, body = read_sheet(path)
    assert meta["status"] == "draft" and meta["code"] == "74802"
    assert check_sheet(meta, body, PACK) == []
    assert "A01 (Toán, Vật lí, Tiếng Anh) ở 92% chương trình" in body
    assert "Môn có trong tất cả các tổ hợp trên: Toán và Vật lí." in body
    assert "máy tính và điện tử; toán học" in body          # items with their own 'và' joined by semicolons


def test_checks_catch_invented_numbers_and_headings():
    meta = {"code": "74802"}
    body = "\n".join(f"## {h}\nO*NET" for h in HEADINGS) + "\nLương khởi điểm 15 triệu."
    assert check_sheet(meta, body, PACK) == ["numbers_not_in_pack:15"]
    body2 = body.replace("## Ngành gần\n", "")
    assert any(i.startswith("headings:") for i in check_sheet(meta, body2, PACK))
    assert check_sheet(meta, body, None) == ["no_facts_pack"]


def test_missing_data_and_files(tmp_path):
    empty = {**PACK, "knowledge": [], "jobs": [], "interests": [], "combos": [], "close_nganh": [],
             "nganh": PACK["nganh"][:1], "programs": {"total": 4, "ha_noi": 0, "tp_hcm": 4, "schools": 3}}
    text = draft_sheet(empty)
    assert "Chưa có dữ liệu việc làm" in text and "tất cả ở TP.HCM" in text and "Nhóm có một ngành" in text
    folder = tmp_path / "sheets"
    assert write_drafts({"74802": PACK}, folder) == 1
    (folder / "74802.md").write_text(draft_sheet(PACK).replace("status: draft", "status: reviewed"), encoding="utf-8")
    assert write_drafts({"74802": PACK}, folder) == 0                   # never overwrites
    conn = db.create(tmp_path / "x.db")
    conn.execute("INSERT INTO source VALUES ('moet', 'moet', 'export', NULL, NULL, NULL)")
    conn.execute("INSERT INTO moet_major (code, level, name, parent_code, source_id) VALUES "
                 "('74802', 'nhom_nganh', 'CNTT', NULL, 'moet')")
    assert insert_sheets(conn, folder) == 1
    assert conn.execute("SELECT status FROM fact_sheet").fetchone() == ("reviewed",)
