import pytest

from uniadvisor.config import load_data_config, load_rules


def test_2026_rules_match_spec_section_8():
    rules = load_rules(2026)
    assert rules["priority"]["area"] == {"KV1": 0.75, "KV2-NT": 0.5, "KV2": 0.25, "KV3": 0.0}
    assert rules["priority"]["category"] == {"none": 0.0, "UT1": 2.0, "UT2": 1.0}
    assert rules["priority"]["taper_from"] == 22.5
    assert rules["priority"]["taper_denominator"] == 7.5
    assert rules["priority"]["area_valid_years_after_graduation"] == 1
    floors = {tuple(f["prefixes"]): f["min_total"] for f in rules["floors"]}
    assert floors == {("772010", "772020", "772050"): 20.5, ("7720",): 17.0, ("71402",): 19.0}
    assert rules["application"]["max_wishes"] == 15


def test_2027_inherits_2026_except_year():
    r26, r27 = load_rules(2026), load_rules(2027)
    assert r27["admission_year"] == 2027
    assert {k: v for k, v in r27.items() if k != "admission_year"} == {
        k: v for k, v in r26.items() if k != "admission_year"
    }


def test_unknown_year_raises():
    with pytest.raises(FileNotFoundError):
        load_rules(1999)


def test_data_config_has_two_cutoff_years():
    cfg = load_data_config()
    assert cfg["cutoff_years"] == [2025, 2026]
    assert cfg["cutoff_source_priority"][:2] == ["school_document", "vnexpress"]
