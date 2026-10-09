"""Sanity checks that the fake database is consistent with the schema's rules."""


def test_foreign_keys_hold(fake_db):
    assert fake_db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_fake_db_covers_rule_cases(fake_db):
    years = dict(fake_db.execute(
        "SELECT p.id, COUNT(DISTINCT c.year) FROM program p LEFT JOIN cutoff c ON c.program_id = p.id GROUP BY p.id"
    ).fetchall())
    assert years["HNA:CS1"] == 2 and years["HNA:SE"] == 1 and years["HNA:AI"] == 0
    per_combo = fake_db.execute("SELECT COUNT(*) FROM cutoff WHERE combo_key != '*'").fetchone()[0]
    assert per_combo >= 2
    assert fake_db.execute("SELECT COUNT(*) FROM program WHERE tuition_min_vnd IS NULL").fetchone()[0] >= 1
    assert {r[0] for r in fake_db.execute("SELECT DISTINCT city FROM school WHERE in_scope = 1")} == {"HN", "HCM"}
    assert fake_db.execute("SELECT weight FROM program_weight WHERE program_id = 'HCB:NNA'").fetchone()[0] == 2.0
    assert fake_db.execute("SELECT score_30 FROM cutoff WHERE program_id = 'HCB:NNA' AND year = 2025").fetchone()[0]         == 25.5
    assert tuple(fake_db.execute("SELECT score_30, is_mixed_method FROM cutoff WHERE program_id = 'HCB:KTPM' AND year = 2026"
                           ).fetchone()) == (24.0, 1)


def test_connection_is_read_only(fake_db):
    import sqlite3

    import pytest

    with pytest.raises(sqlite3.OperationalError):
        fake_db.execute("DELETE FROM program")
