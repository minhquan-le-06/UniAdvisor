"""The school -> khu vực file the input page reads (tools/build_school_areas.py, web/public/data/school-areas.json)."""

import importlib.util
import json
from pathlib import Path

import pytest

from uniadvisor.config import province_names

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "public" / "data" / "school-areas.json"


def _tool():
    spec = importlib.util.spec_from_file_location("build_school_areas", ROOT / "tools" / "build_school_areas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shipped_file_covers_every_province_with_valid_areas():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert set(data) == set(province_names())
    for rows in data.values():
        assert rows and rows == sorted(rows)
        assert {area for _, area in rows} <= {"KV1", "KV2-NT", "KV2", "KV3"}
        assert not any("trước" in school.lower() for school, _ in rows)


def _csv(tmp_path, rows):
    head = '"Mã Tỉnh/TP","Tên Tỉnh/TP","Mã Trường","Tên Trường","Khu Vực"\n'
    path = tmp_path / "schools.csv"
    path.write_text(head + "".join(f'"1","{p}","1","{s}","{a}"\n' for p, s, a in rows), encoding="utf-8")
    return path


def test_build_maps_spellings_drops_old_rows_and_renames_areas(tmp_path):
    tool = _tool()
    names = province_names()
    rows = [(p, "THPT A", "KV2_NT") for p in names]
    rows[names.index("Huế")] = ("Thành phố Huế", "THPT A", "KV1")
    rows[names.index("TP. Hồ Chí Minh")] = ("Tp. Hồ Chí Minh", "THPT A", "KV3")
    rows += [("Hà Nội", "THPT B (trước 01/7/2025)", "KV1"), ("Hà Nội", "THPT  C", "KV2")]
    data = tool.build(_csv(tmp_path, rows))
    assert data["Huế"] == [["THPT A", "KV1"]] and data["TP. Hồ Chí Minh"] == [["THPT A", "KV3"]]
    assert data["Hà Nội"] == [["THPT A", "KV2-NT"], ["THPT C", "KV2"]]


def test_build_refuses_an_unknown_province_or_area(tmp_path):
    tool = _tool()
    with pytest.raises(SystemExit):
        tool.build(_csv(tmp_path, [("Nước khác", "THPT A", "KV1")]))
    with pytest.raises(SystemExit):
        tool.build(_csv(tmp_path, [("Hà Nội", "THPT A", "KV9")]))
