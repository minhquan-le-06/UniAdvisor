"""Write the list of in-scope programs still without tuition, one row per program, for the team.

    python -m pipelines.database.missing_tuition        # -> docs/team/teammate_lists/hoc_phi_con_thieu.csv

Reads the final tables (pipelines/data/tables/program.csv, school.csv) and, for each school, why it is still missing
(pipelines/data/manual_sources/teammate_returns/not_entered_hoc_phi_*.csv, the latest one). Rerun after every prepare;
the file is committed so the team always sees what is left. The status text is Vietnamese (teammate document).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from uniadvisor.paths import PIPELINE_DATA, ROOT, TABLES_DIR

OUT = ROOT / "docs" / "team" / "teammate_lists" / "hoc_phi_con_thieu.csv"
RETURNS = PIPELINE_DATA / "manual_sources" / "teammate_returns"
HIGH = ROOT / "docs" / "team" / "teammate_lists" / "drive_dot_4" / "1_hoc_phi.csv"
COLUMNS = ["ma_truong", "ten_truong", "thanh_pho", "uu_tien", "ma_chuong_trinh", "ten_chuong_trinh", "ma_nganh",
           "nhom_ly_do", "tinh_trang", "tai_lieu_da_co"]
NO_FILE = ("Chưa có tài liệu học phí: tìm đề án tuyển sinh hoặc thông báo học phí 2026-2027 của trường "
           "(ghi rõ năm học và đơn vị: năm / học kỳ / tín chỉ)")


# Schools whose file needs an answer or a rule (round of 2026-10-13): what to ask, in Vietnamese.
ASK = {
    "DKK": "File ghi học phí theo ngành nhưng không ghi theo năm hay theo học kỳ: xác định đơn vị",
    "HHK": "File ghi tổng học phí + bảo hiểm + lệ phí, không ghi theo năm hay học kỳ: xác định đơn vị và tách "
           "riêng học phí",
    "DQH": "Hệ dân sự đóng 1,85 triệu/tháng: một năm học bao nhiêu tháng?",
    "KQH": "Hệ dân sự đóng 2,09 triệu/tháng: một năm học bao nhiêu tháng?",
    "HTA": "Một mức 7,95 triệu kèm chi phí nội trú, không ghi theo năm hay kỳ: xác định đơn vị",
    "QHE": "File chỉ có chương trình chuẩn; tìm học phí 2 chương trình liên kết (Troy, St. Francis)",
    "MHN": "Tìm học phí ngành Kỹ thuật máy tính (không có trong file)",
    "PCH": "File là học phí hệ dân sự; tìm học phí của 4 chương trình chỉ tiêu (học viên công an)",
    "HFH": "Chỉ có một con số khoảng 18,5 triệu, không ghi theo năm, kỳ hay khóa: xác định đơn vị",
    "SPS": "Học phí cả khóa, 140 tín chỉ, không ghi khóa học mấy năm: tìm số năm hoặc học phí theo năm",
    "NTH": "Một mã dùng chung cho chương trình chuẩn, CLC, quốc tế có học phí khác nhau: tìm học phí theo năm "
           "của từng chương trình, ghi đúng tên chương trình (D10)",
}


D8 = ("Trường chỉ ghi giá mỗi tín chỉ (D8): tìm học phí theo năm học, hoặc tổng số tín chỉ toàn khóa và số năm "
      "học của từng ngành (chương trình đào tạo / đề án tuyển sinh)")


def status(reason: str, school: str = "") -> str:
    """Vietnamese status from the reason recorded when the school's file was not entered."""
    if school in ASK:
        return ASK[school]
    r = reason.lower()
    if "chờ d8" in r:                          # Vietnamese reasons of later rounds (2026-10-15)
        return D8
    if "cần hỏi lại" in r:
        return "Cần hỏi lại: " + reason.replace(" (cần hỏi lại)", "")
    if "không có trong bảng" in r or "không có mức" in r or "không có" in r:
        return "File chưa có học phí của chương trình này: tìm thêm (" + reason + ")"
    if "excel" in r:
        return "Đã có file Excel, chưa đọc"
    if "price per credit" in r or "per credit" in r:
        return D8
    if "not entered yet" in r:
        return "Đã có file, chưa nhập vào hệ thống"
    if "empty" in r:
        return "File gửi về trống hoặc chỉ có tiêu đề / link: cần tìm lại tài liệu"
    if "only some" in r:
        return "File chỉ có một số chương trình: tìm học phí các chương trình còn lại"
    return f"Cần hỏi lại: {reason}"


def category(text: str) -> str:
    """The short reason: blocked by an owner decision, not found yet, or the file needs an answer."""
    if "(D8)" in text:
        return "Chỉ có giá theo tín chỉ (D8)"
    if "(D10)" in text:
        return "Mã dùng chung nhiều chương trình (D10)"
    if text.startswith("Chưa có tài liệu") or text.startswith("File gửi về trống") or text.startswith("File chỉ có")             or text.startswith("File chưa có học phí"):
        return "Chưa tìm được học phí"
    if text.startswith("Cần hỏi lại") or text in ASK.values():
        return "Cần hỏi lại (file thiếu đơn vị hoặc thông tin)"
    return "Đã có file, chưa nhập"


def latest_reasons() -> dict[str, tuple[str, str]]:
    files = sorted(RETURNS.glob("not_entered_hoc_phi_*.csv"))
    if not files:
        return {}
    with open(files[-1], encoding="utf-8-sig", newline="") as fh:
        return {r["ma_truong"]: (r["ly_do_chua_nhap"], r["tep"]) for r in csv.DictReader(fh)}


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build() -> list[dict]:
    schools = {s["code"]: s for s in read(TABLES_DIR / "school.csv")}
    reasons = latest_reasons()
    high = {r["ma_truong"] for r in read(HIGH) if r.get("uu_tien") == "cao"} if HIGH.exists() else set()
    rows = []
    for p in read(TABLES_DIR / "program.csv"):
        if p["in_scope"] != "1" or p["tuition_max_vnd"]:
            continue
        school = p["school_code"]
        reason, files = reasons.get(school, ("", ""))
        text = status(reason, school) if reason else NO_FILE
        rows.append({"ma_truong": school, "ten_truong": schools.get(school, {}).get("name", ""),
                     "thanh_pho": {"HN": "Hà Nội", "HCM": "TP.HCM"}.get(p["city"], p["city"]),
                     "uu_tien": "cao" if school in high else "", "ma_chuong_trinh": p["program_code"],
                     "ten_chuong_trinh": p["name"], "ma_nganh": p["moet_code"], "nhom_ly_do": category(text),
                     "tinh_trang": text,
                     "tai_lieu_da_co": files})
    rows.sort(key=lambda r: (r["nhom_ly_do"], r["uu_tien"] != "cao", r["ma_truong"], r["ma_chuong_trinh"]))
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = build()
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT}: {len(rows)} programs at {len({r['ma_truong'] for r in rows})} schools without tuition")


if __name__ == "__main__":
    main()
