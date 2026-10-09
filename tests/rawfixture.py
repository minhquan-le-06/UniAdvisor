"""A tiny set of raw inputs in the exact formats of data/inputs, written to a temp dir, for testing the build.

Cached pages are generated from the same rows, so each CSV row can be checked against "its" page.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

VNE_URL = "https://diemthi.vnexpress.net/tra-cuu-dai-hoc/loadbenchmark/id/{id}/year/{year}/sortby/1/block_name/-1"
TS_URL = "https://diemthi.tuyensinh247.com/diem-chuan/{school}.html"
VNN_URL = "https://vietnamnet.vn/newsapi-edu/UniversityDetail/GetDetail?keyword={school}&year={year}"

MOET = [
    ("748", "linh_vuc", "Máy tính và công nghệ thông tin", ""),
    ("74801", "nhom_nganh", "Máy tính", "748"),
    ("7480101", "nganh", "Khoa học máy tính", "74801"),
    ("74802", "nhom_nganh", "Công nghệ thông tin", "748"),
    ("7480201", "nganh", "Công nghệ thông tin", "74802"),
    ("772", "linh_vuc", "Sức khoẻ", ""),
    ("77201", "nhom_nganh", "Y học", "772"),
    ("7720101", "nganh", "Y khoa", "77201"),
    ("721", "linh_vuc", "Nghệ thuật", ""),
    ("72104", "nhom_nganh", "Mỹ thuật ứng dụng", "721"),
    ("7210403", "nganh", "Thiết kế đồ họa", "72104"),
]

# id, name, type, military, province, address
SCHOOLS = [
    ("HNA", "Trường Đại học A Hà Nội", "university", "False", "Hà Nội", "1 Đường X, Cầu Giấy, Hà Nội"),
    ("HCB", "Trường Đại học B", "university", "False", "Đồng Nai", "2 Đường Y, Quận 1, TP. Hồ Chí Minh"),
    ("BDU", "Trường Đại học Bình Dương Giả", "university", "False", "Đồng Nai", "3 Đại lộ, Thủ Dầu Một, Bình Dương"),
    ("DNG", "Trường Đại học Đà Nẵng Giả", "university", "False", "Đà Nẵng", "4 Đường Z, Hải Châu, Đà Nẵng"),
    ("COL", "Trường Cao đẳng Giả", "college", "False", "Hà Nội", "5 Đường W, Hà Nội"),
    ("NOA", "Trường Đại học Không Địa Chỉ", "university", "True", "Hà Nội", ""),
    ("MXS", "Trường Đại học Kết Hợp Giả", "university", "False", "TP. Hồ Chí Minh", "9 Đường Q, Quận 3, TP. Hồ Chí Minh"),
]

# program_code, school, name, major_code, exam method (True: exam only "ĐT THPT"; False: none; a label: that
# combined method only), combos
PROGRAMS = [
    ("CS1", "HNA", "Khoa học máy tính", "7480101", True, ["A00", "A01"]),
    ("IT1", "HNA", "Công nghệ thông tin", "7480201", True, ["A00", "D01"]),
    ("X9", "HNA", "Khoa học máy tính", "", True, ["A00"]),                  # no major code: name-match suggestion
    ("BR1", "HNA", "Khoa học máy tính (Phân hiệu Thanh Hóa)", "7480101", True, ["A00"]),
    ("TK1", "HNA", "Thiết kế đồ họa", "7210403", True, ["H00"]),          # talent test only
    ("HB1", "HNA", "Công nghệ thông tin (học bạ)", "7480201", False, []),  # no THPT method
    ("KT1", "HNA", "Kinh tế (Cơ sở HCM)", "", True, ["A00"]),              # taught in TP.HCM
    ("YK", "HCB", "Y khoa", "7720101", True, ["B00"]),
    ("F7480201", "HCB", "Công nghệ thông tin", "", True, ["A00"]),          # MOET code embedded in program code
    ("CS1", "DNG", "Khoa học máy tính", "7480101", True, ["A00"]),
    ("AR1", "HNA", "Kiến trúc", "", "THPT + NK", ["H00"]),                   # exam + talent test only
    ("MX1", "MXS", "Công nghệ thông tin", "7480201", "THPT + Học bạ", ["A00"]),  # combined only, has a cutoff
    ("IU1", "MXS", "Khoa học máy tính", "7480101", "THPT + Học bạ", ["A00"]),    # combined only, no cutoff
    ("401", "HCB", "Kinh tế học", "7310101", True, ["A00"]),               # site writes '7310101_401'
    ("DS_01", "HCB", "Khoa học dữ liệu", "", True, ["A00"]),               # site writes 'DS01'
    ("SH7", "HCB", "Sinh học", "", True, ["B00"]),                         # one code, two programs;
    ("SH7", "HCB", "Sinh học (tăng cường tiếng Anh)", "", True, ["B00"]),  # site writes 'SH7_TA'
]

SUBJECTS = [("VA", "Ngữ văn"), ("TO", "Toán"), ("LI", "Vật lí"), ("HO", "Hóa học"), ("SI", "Sinh học"),
            ("N1", "Tiếng Anh"), ("NK", "Năng khiếu (bài thi do trường tổ chức)"),
            ("GDKTPL", "Giáo dục kinh tế và pháp luật")]
# Subject names VnExpress shows for a combination (title attribute); X99 and C14 are not defined by the export.
VNE_TITLES = {"A00": "Toán, Vật lí, Hóa Học", "X99": "Toán, Vật lí, Giáo dục kinh tế và pháp luật",
              "C14": "Ngữ văn, Toán, Giáo dục công dân"}
COMBO_PARTS = {"A00": ["TO", "LI", "HO"], "A01": ["TO", "LI", "N1"], "B00": ["TO", "HO", "SI"],
               "D01": ["VA", "TO", "N1"], "H00": ["VA", "NK", "NK"]}

# school, vne_id, year, name, code, combos, thpt, tuition
VNEXPRESS = [
    ("HNA", 1, 2025, "Khoa học máy tính", "CS1", "A00;A01", "25.0", "30.000.000 - 35.000.000"),
    ("HNA", 1, 2026, "Khoa học máy tính", "CS1", "A00;A01;X99;C14", "24.2", "32.000.000 - 36.000.000"),
    ("HNA", 1, 2026, "Công nghệ thông tin", "IT1", "A00;D01", "23.0", ""),
    ("HNA", 1, 2025, "Hệ thống cũ", "OLD9", "A00", "20.0", ""),             # only 2025 -> not offered 2026
    ("HNA", 1, 2025, "Kinh tế (Cơ sở HCM)", "KT0", "A00", "21.0", ""),     # KT1's old code: linked by name
    ("HNA", 1, 2026, "Kinh tế (Cơ sở HCM)", "KT1", "A00", "21.5", "25.000.000"),
    ("HCB", 2, 2025, "Y khoa", "YK", "B00", "85.5", "80.000.000"),        # mixed-method / 100-point score
    ("HCB", 2, 2026, "Y khoa", "YK", "B00", "27.0", "Đang cập nhật"),       # tuition text not a number
    ("DNG", 3, 2026, "Khoa học máy tính", "CS1", "A00", "22.0", ""),
    ("MXS", 4, 2026, "Công nghệ thông tin", "MX1", "A00", "24.0", ""),       # on 30 points, but a combined score
    ("MXS", 4, 2025, "Ngôn ngữ Anh", "MX1", "D01", "20.0", ""),              # code reused: another program in 2025
    ("MXS", 4, 2026, "Kỹ thuật phần mềm", "MX2", "A00", "23.0", ""),         # not in the export: school rule
    ("HCB", 2, 2026, "Kinh tế học", "7310101_401", "A00", "25.5", ""),
    ("HCB", 2, 2026, "Khoa học dữ liệu", "DS01", "A00", "26.0", ""),
    ("HCB", 2, 2026, "Sinh học (tăng cường tiếng Anh)", "SH7_TA", "B00", "21.0", ""),
]
VNE_NOT_ON_PAGE = ("HNA", 1, 2025, "Công nghệ thông tin", "IT1", "A00;D01", "99.0", "")  # cache mismatch

# school, year, code, name, combos, mark, method
TS247 = [
    ("HNA", 2026, "IT1", "Công nghệ thông tin", "A00", 23.0, "Điểm thi THPT"),
    ("HNA", 2026, "IT1", "Công nghệ thông tin", "D01", 24.0, "Điểm thi THPT"),
    ("HNA", 2026, "CS1", "Khoa học máy tính", "A00;A01", 24.5, "Điểm thi THPT"),   # disagrees with VnExpress
]

# school, year, code, name, score, combos, note
VIETNAMNET = [
    ("HNA", 2026, "X9", "Khoa học máy tính", "21.0", "A00", "Xét tuyển bằng điểm thi tốt nghiệp THPT"),
    ("HNA", 2026, "X9", "Khoa học máy tính", "27.5", "A00", "Điểm học bạ"),
    ("HNA", 2025, "X9", "Khoa học máy tính", "20.5", "", ""),
    ("HCB", 2026, "F7480201", "Công nghệ thông tin", "33.0", "A00", "Điểm thi THPT (điểm môn Toán hệ số 2)"),
    ("HNA", 2024, "CS1", "Khoa học máy tính", "26.0", "A00", "Điểm thi THPT"),   # other year: skipped
]


def _write_csv(path: Path, header: list[str], rows: list[list], bom: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig" if bom else "utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _cache(root: Path, url: str, body: str):
    name = hashlib.sha1(url.encode()).hexdigest()[:20]
    d = root / url.split("/")[2]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.body").write_text(body, encoding="utf-8")
    (d / f"{name}.meta.json").write_text(json.dumps({"url": url, "status": 200, "fetched_at": "2026-09-29"}))


def _vne_page(rows) -> str:
    trs = []
    for r in rows:
        combos = "".join(f'<a title="{VNE_TITLES.get(c, "")}">{c}</a>' for c in r[5].split(";"))
        trs.append(
            f'<tr class="university__benchmark  odd"><td style="width:150px"><strong><a href="#">{r[3]}</a></strong>'
            f'<span style="display: block;">{r[4]}</span></td><td>{combos}</td><td><span>{r[6]}</span></td>'
            f"<td>--</td><td>{r[7]}</td></tr>"
        )
    return json.dumps({"html": '<table class="university__table"><tbody>' + "".join(trs) + "</tbody></table>"})


def _ts_page(rows) -> str:
    objs = "\n".join(
        json.dumps({"id": i, "school_id": 1, "code": r[2], "name": r[3], "block": r[4].replace(";", "; "),
                    "mark": r[5], "year": r[1], "is_converted_score": 0, "admission_name": r[6]},
                   ensure_ascii=False)
        for i, r in enumerate(rows))
    half = len(objs) // 2      # data is split across two push chunks, as on the real site
    push = lambda s: "<script>self.__next_f.push([1," + json.dumps(s, ensure_ascii=False) + "])</script>"  # noqa
    return "<html>" + push(objs[:half]) + push(objs[half:]) + "</html>"


def _vnn_page(rows) -> str:
    scores = [{"code": r[2], "name": r[3], "score": r[4], "type": 2, "subjectGroup": r[5], "note": r[6]}
              for r in rows]
    return json.dumps({"status": True, "data": {"model": {"schoolScores": scores}}}, ensure_ascii=False)


def write_raw_inputs(root: Path) -> Path:
    """Write the fixture inputs under `root` (same layout as data/inputs) and return `root`."""
    _write_csv(root / "manual" / "moet_majors.csv", ["code", "level", "name", "parent", "former_code", "note",
               "source", "url"], [[c, lv, n, p, "", "", "moet_tt09_2022", ""] for c, lv, n, p in MOET])
    u = root / "unipilot"
    _write_csv(u / "school.csv", ["id", "name_vi", "name_en", "short_name", "school_type", "ownership", "managed_by",
               "parent_school_id", "parent_school_name", "is_military_or_police", "province", "region", "address",
               "website", "status", "chosen_fact_id"],
               [[i, n, "", "", t, "", "", "", "", m, p, "", a, "", "unconfirmed", ""] for i, n, t, m, p, a in SCHOOLS],
               bom=True)
    prog_rows, meth_rows, combo_rows = [], [], []
    for code, school, name, major, thpt, combos in PROGRAMS:
        pid = f"{school}:{code}@2026" if sum(1 for x in PROGRAMS if x[:2] == (code, school)) == 1 or             name == next(x[2] for x in PROGRAMS if x[:2] == (code, school)) else f"{school}:{code}~2@2026"
        prog_rows.append([pid, school, "2026", code, name, major, "", "", "", "unconfirmed", ""])
        meth_rows.append([pid, "Học Bạ", "200"])
        if thpt is True:
            meth_rows.append([pid, "ĐT THPT", "100"])
            combo_rows += [[pid, "ĐT THPT", c] for c in combos]
        elif thpt:
            meth_rows.append([pid, thpt, ""])
            combo_rows += [[pid, thpt, c] for c in combos]
        combo_rows.append([pid, "Học Bạ", "D01"])
    _write_csv(u / "program.csv", ["id", "school_code", "year", "program_code", "name_vi", "major_code",
               "program_kind", "program_group", "quota", "status", "chosen_fact_id"], prog_rows, bom=True)
    _write_csv(u / "program_admission_method.csv", ["program_id", "method_label", "method_code"], meth_rows, bom=True)
    _write_csv(u / "program_subject_combo.csv", ["program_id", "method_label", "combo_code"], combo_rows, bom=True)
    _write_csv(u / "subject.csv", ["code", "name_vi", "name_en", "first_year", "last_year", "status",
               "chosen_fact_id"], [[c, n, "", "", "", "unconfirmed", ""] for c, n in SUBJECTS], bom=True)
    _write_csv(u / "subject_combo_part.csv", ["combo_code", "year", "position", "subject_code", "weight"],
               [[c, "2026", i + 1, s, "1.0"] for c, ss in COMBO_PARTS.items() for i, s in enumerate(ss)], bom=True)

    cache = root / "http_cache"
    col = root / "collected"
    vne_rows = []
    pages: dict[str, list] = {}
    for r in VNEXPRESS:
        url = VNE_URL.format(id=r[1], year=r[2])
        pages.setdefault(url, []).append(r)
    for r in VNEXPRESS + [VNE_NOT_ON_PAGE]:
        url = VNE_URL.format(id=r[1], year=r[2])
        vne_rows.append(["vnexpress_cutoffs", r[0], r[1], r[2], r[3], r[4], r[5], r[6], "--", r[7], url, "2026-09-29"])
    for url, rows in pages.items():
        _cache(cache, url, _vne_page(rows))
    _write_csv(col / "vnexpress_cutoffs.csv", ["source", "school_code", "vne_id", "year", "program_name",
               "program_code", "combos", "thpt_score_raw", "other_methods", "tuition_raw", "url", "fetched_at"],
               vne_rows)

    ts_rows, pages = [], {}
    for r in TS247:
        url = TS_URL.format(school=r[0])
        pages.setdefault(url, []).append(r)
        ts_rows.append(["tuyensinh247_cutoffs", r[0], r[1], r[2], r[3], r[4], r[5], url, "2026-09-29"])
    for url, rows in pages.items():
        _cache(cache, url, _ts_page(rows))
    _write_csv(col / "tuyensinh247_cutoffs.csv", ["source", "school_code", "year", "program_code", "program_name",
               "combos", "score_raw", "url", "fetched_at"], ts_rows)

    vnn_rows, pages = [], {}
    for r in VIETNAMNET:
        url = VNN_URL.format(school=r[0], year=r[1])
        pages.setdefault(url, []).append(r)
        vnn_rows.append(["vietnamnet_cutoffs", r[0], "", "", r[1], r[2], r[3], r[4], r[5], r[6], "2", url,
                         "2026-09-29"])
    for url, rows in pages.items():
        _cache(cache, url, _vnn_page(rows))
    _write_csv(col / "vietnamnet_cutoffs.csv", ["source", "school_code", "school_name_src", "province_src", "year",
               "program_code", "program_name", "score_raw", "combos_raw", "note", "training_type", "url",
               "fetched_at"], vnn_rows)
    return root
