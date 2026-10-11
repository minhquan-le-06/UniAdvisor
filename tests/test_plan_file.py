"""The plan file (spec 6): round trip, damaged files, content that changed since saving."""

import json

import pytest

from uniadvisor.app.plan_file import FORMAT, SCHEMA_VERSION, Known, PlanFileError, dump, load
from uniadvisor.app.state import PlanState, ShortlistEntry

KNOWN = Known(subjects=frozenset({"TO", "LI", "HO", "N1", "VA"}), provinces=frozenset({"Nghệ An", "Hà Nội"}),
              codes=frozenset({"74801", "7480101", "7480201", "7480103"}), schools=frozenset({"HNA", "HCB"}),
              programs=frozenset({"HNA:CS1", "HCB:KTPM"}))

FULL = PlanState(scores={"TO": 8.25, "LI": 7.5, "N1": 9.0}, score_kind="real", home_province="Nghệ An",
                 area="KV2-NT", category="UT2", graduation_year=2026, budget_trieu=30.0, near_home=True,
                 favorite_school="HNA", picks=["7480201", "74801"], shortlist=[ShortlistEntry("7480201", ["7480101"]),
                                                       ShortlistEntry("74801", [])],
                 extra_points={"HNA": 1.5}, own_scores={"HCB": (85.5, 100)}, cutoff_shifts={"HNA": -0.5},
                 removed_schools=["HCB"], removed_programs=["HNA:CS1"],
                 answers={"q1": ["TO", "TI"], "q9": "alone", "q5": None}, list_choice="tiet_kiem",
                 recommended=[{"priority": "dung_nganh", "programs": ["HNA:CS1"], "values": {"hop_mon": 1.0,
                               "nghe_nghiep": None}, "no_admission": 0.01}])


def test_round_trip():
    text = dump(FULL, 2027)
    data = json.loads(text)
    assert data["format"] == FORMAT and data["schema_version"] == SCHEMA_VERSION and data["admission_year"] == 2027
    state, warnings = load(text, KNOWN)
    assert state == FULL and warnings == []
    assert load(text.encode("utf-8"), KNOWN)[0] == FULL


def test_empty_state_round_trip():
    state, warnings = load(dump(PlanState(), 2027), KNOWN)
    assert state == PlanState() and warnings == []


def test_profile_and_shortlist_conversion():
    profile = FULL.to_profile()
    assert profile.scores == {"TO": 8.25, "LI": 7.5, "N1": 9.0} and profile.area == "KV2-NT"
    assert profile.extra_points == {"HNA": 1.5} and profile.removed_schools == frozenset({"HCB"})
    items = FULL.to_shortlist()
    assert [(i.main_code, i.close_codes, i.further_close_codes) for i in items] == [
        ("7480201", ("7480101",), ()), ("74801", (), ())]
    assert PlanState().missing_for_list() == ["scores", "home_province", "shortlist"]
    assert FULL.missing_for_list() == []


def _edit(**changes):
    data = json.loads(dump(FULL, 2027))
    for path, value in changes.items():
        node = data
        *parents, last = path.split("__")
        for p in parents:
            node = node[p]
        if value is KeyError:
            del node[last]
        else:
            node[last] = value
    return json.dumps(data)


@pytest.mark.parametrize("raw, message", [
    ("not json", "Không đọc được tệp"),
    (b"\xff\xfe\x00", "Không đọc được tệp"),
    ("TOO_BIG", "Tệp quá lớn"),
    (json.dumps({"format": "other"}), "không phải tệp kế hoạch"),
    (json.dumps([1, 2]), "không phải tệp kế hoạch"),
    (_edit(schema_version=SCHEMA_VERSION + 1), "phiên bản khác"),
    (_edit(schema_version="1"), "phiên bản khác"),
    (_edit(profile__scores={"TO": 11}), "điểm môn học"),
    (_edit(profile__scores={"TO": True}), "điểm môn học"),
    (_edit(profile__scores=[8]), "điểm các môn"),
    (_edit(profile__area="KV4"), "khu vực"),
    (_edit(profile__category="UT3"), "khu vực hoặc đối tượng"),
    (_edit(profile__score_kind="guess"), "loại điểm"),
    (_edit(profile__graduation_year=2026.5), "năm tốt nghiệp"),
    (_edit(profile__budget_trieu=-1), "ngân sách"),
    (_edit(profile__near_home="yes"), "học gần nhà"),
    (_edit(profile__home_province=5), "tỉnh/thành"),
    (_edit(step1__shortlist=[{"main": "7480201"}] * 3), "danh sách ưu tiên"),
    (_edit(step1__shortlist=[{"close": []}]), "danh sách ưu tiên"),
    (_edit(step1__picks="7480201"), "danh sách ngành"),
    (_edit(adjustments__extra_points={"HNA": 20}), "điểm cộng"),
    (_edit(adjustments__removed_schools=None), "trường đã bỏ"),
    (_edit(profile__area=KeyError), "thiếu hoặc hỏng"),
    (_edit(step1=KeyError), "thiếu hoặc hỏng"),
    (_edit(adjustments=[]), "thiếu hoặc hỏng"),
])
def test_damaged_files_are_refused(raw, message):
    if raw == "TOO_BIG":
        raw = b"x" * 300_000
    with pytest.raises(PlanFileError, match=message):
        load(raw, KNOWN)


def test_changed_content_is_dropped_with_warnings():
    text = _edit(profile__scores={"TO": 8, "KHTN": 7}, profile__home_province="Hà Tây",
                 step1__picks=["7480201", "7999999", "7480201"],
                 step1__shortlist=[{"main": "7999999", "close": []},
                                   {"main": "74801", "close": ["7480101", "7888888", "7480103", "7480201"]}],
                 adjustments__extra_points={"HNA": 1, "ZZZ": 2}, adjustments__removed_programs=["ZZZ:1"])
    state, warnings = load(text, KNOWN)
    assert state.scores == {"TO": 8.0} and state.home_province is None
    assert state.picks == ["7480201"]
    assert state.shortlist == [ShortlistEntry("74801", ["7480101", "7480103"])]   # unknown dropped, at most 2 kept
    assert state.extra_points == {"HNA": 1.0} and state.removed_programs == []
    assert len(warnings) == 5          # score, province, pick, shortlist item, close ngành
    assert any("KHTN" in w for w in warnings) and any("Hà Tây" in w for w in warnings)


def test_former_province_opens_on_its_new_unit():
    """A plan saved with a province merged in 2025 (config/provinces.yaml aliases) opens on the new unit, silently."""
    known = Known(KNOWN.subjects, KNOWN.provinces | {"Ninh Bình"}, KNOWN.codes, KNOWN.schools, KNOWN.programs,
                  {"Nam Định": "Ninh Bình", "Ninh Bình": "Ninh Bình"})
    state, warnings = load(_edit(profile__home_province="Nam Định"), known)
    assert state.home_province == "Ninh Bình" and warnings == []


def test_favorite_school():
    assert FULL.to_profile().favorite_school == "HNA"
    data = json.loads(dump(FULL, 2027))
    del data["profile"]["favorite_school"]                       # a file saved before the field existed
    assert load(json.dumps(data), KNOWN)[0].favorite_school is None
    data["profile"]["favorite_school"] = "GONE"
    state, warnings = load(json.dumps(data), KNOWN)
    assert state.favorite_school is None and warnings == ["Trường yêu thích mã GONE không còn trong danh sách trường; "
                                                          "em chọn lại nhé."]
    data["profile"]["favorite_school"] = 5
    with pytest.raises(PlanFileError, match="trường yêu thích"):
        load(json.dumps(data), KNOWN)


def test_corrections():
    profile = FULL.to_profile()
    assert (profile.own_scores, profile.cutoff_shifts) == ({"HCB": (85.5, 100)}, {"HNA": -0.5})
    data = json.loads(dump(FULL, 2027))
    assert data["adjustments"]["own_scores"] == {"HCB": {"score": 85.5, "scale": 100}}
    del data["adjustments"]["own_scores"], data["adjustments"]["cutoff_shifts"]   # saved before the fields existed
    state = load(json.dumps(data), KNOWN)[0]
    assert (state.own_scores, state.cutoff_shifts) == ({}, {})
    for bad in ({"HCB": {"score": 85.5, "scale": 50}}, {"HCB": {"score": 120, "scale": 100}}, {"HCB": 85}):
        data["adjustments"]["own_scores"] = bad
        with pytest.raises(PlanFileError, match="điểm xét tuyển tự tính"):
            load(json.dumps(data), KNOWN)
    data["adjustments"]["own_scores"] = {}
    data["adjustments"]["cutoff_shifts"] = {"HNA": 9}
    with pytest.raises(PlanFileError, match="điều chỉnh điểm chuẩn"):
        load(json.dumps(data), KNOWN)


def test_three_lists():
    data = json.loads(dump(FULL, 2027))
    assert data["lists"]["chosen"] == "tiet_kiem" and data["step1"]["answers"]["q9"] == "alone"
    del data["lists"], data["step1"]["answers"]                          # schema 1 files have neither
    data["schema_version"] = 1
    state = load(json.dumps(data), KNOWN)[0]
    assert (state.answers, state.list_choice, state.recommended) == ({}, None, [])
    data = json.loads(dump(FULL, 2027))
    data["lists"]["recommended"][0]["programs"].append("GONE:X")         # a program no longer offered is dropped
    assert load(json.dumps(data), KNOWN)[0].recommended[0]["programs"] == ["HNA:CS1"]
    for bad in ({"chosen": "best"}, {"recommended": [{"priority": "x"}]},
                {"recommended": [{"priority": "dung_nganh", "values": {"hop_mon": 2}}]}):
        data = json.loads(dump(FULL, 2027))
        data["lists"].update(bad)
        with pytest.raises(PlanFileError, match="danh sách"):
            load(json.dumps(data), KNOWN)
