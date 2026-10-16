"""prepare writes the final tables, build loads them: the loaded database is the prepared one."""

from __future__ import annotations

import filecmp
import sqlite3

import pytest

from pipelines.database.build import build
from pipelines.database.compare import compare_databases
from pipelines.database.prepare import prepare
from tests.rawfixture import write_raw_inputs
from uniadvisor import db
from uniadvisor.config import load_data_config
from uniadvisor.data import tables
from uniadvisor.paths import TABLES_DIR


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("loader")
    inputs = write_raw_inputs(root / "inputs")
    curated = root / "curated"
    curated.mkdir()
    (curated / "display_names.csv").write_text(
        "code,display_name,aliases,status,origin,source_id,note\n"
        "74801,\"Khoa học máy tính, Trí tuệ nhân tạo\",KHMT; AI,draft,group_labels_old_repo,curated,a note\n",
        encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=root / "p1" / "prepare.db", cfg=load_data_config())
    return root, inputs, curated, result


def test_the_loaded_database_is_the_prepared_one(prepared):
    root, _, _, result = prepared
    loaded = build(tables_dir=root / "p1" / "tables", out_db=root / "loaded" / "app.db")
    report = compare_databases(result["db"], loaded["db"])
    assert [r["table"] for r in report if not r["same"]] == []
    assert loaded["table_counts"]["program"] == result["table_counts"]["program"] > 0


def test_prepare_twice_writes_identical_tables(prepared):
    root, inputs, curated, _ = prepared
    prepare(inputs=inputs, curated=curated, out_db=root / "p2" / "prepare.db", cfg=load_data_config())
    a, b = root / "p1" / "tables", root / "p2" / "tables"
    names = sorted(p.name for p in a.glob("*.csv"))
    assert names == sorted(p.name for p in b.glob("*.csv")) and len(names) == 30
    assert [n for n in names if not filecmp.cmp(a / n, b / n, shallow=False)] == []


def test_meta_csv_has_no_volatile_rows_but_the_loaded_database_does(prepared):
    root, _, _, _ = prepared
    keys = [line.split(",")[0] for line in (root / "p1" / "tables" / "meta.csv").read_text(encoding="utf-8-sig").splitlines()[1:]]
    assert "built_at" not in keys and "schema_version" not in keys
    conn = sqlite3.connect(build(tables_dir=root / "p1" / "tables", out_db=root / "loaded2" / "app.db")["db"])
    stored = dict(conn.execute("SELECT key, value FROM meta"))
    conn.close()
    assert stored["schema_version"] == db.SCHEMA_VERSION and stored["built_at"]


def test_types_round_trip(tmp_path):
    """Numbers stay numbers, NULL stays NULL, a leading zero in text is kept."""
    conn = db.create(tmp_path / "t.db")
    conn.execute("INSERT INTO source VALUES ('s', 'S', 'curated', NULL, NULL, NULL)")
    conn.execute("INSERT INTO moet_major (code, level, name, source_id) VALUES ('748', 'linh_vuc', 'M', 's')")
    conn.execute("INSERT INTO school (code, name, city, city_basis, in_scope, source_id) VALUES ('0123', 'A', NULL, 'x', 1, 's')")
    conn.execute("INSERT INTO school_employment VALUES ('0123', '748', 2024, 0.1, 'f', NULL, NULL, NULL, 's')")
    conn.commit()
    out = tmp_path / "tables"
    tables.export_tables(conn, out, skip_meta_keys=tables.VOLATILE_META_KEYS)
    conn.close()
    fresh = db.create(tmp_path / "fresh.db")
    tables.load_tables(fresh, out)
    row = fresh.execute("SELECT typeof(code), code, typeof(city), typeof(in_scope) FROM school").fetchone()
    assert row == ("text", "0123", "null", "integer")
    assert fresh.execute("SELECT typeof(rate), rate, typeof(graduation_year), typeof(reviewed_by) "
                         "FROM school_employment").fetchone() == ("real", 0.1, "integer", "null")


def test_a_foreign_key_violation_is_reported_with_the_table(tmp_path, prepared):
    root, *_ = prepared
    broken = tmp_path / "tables"
    broken.mkdir()
    for p in (root / "p1" / "tables").glob("*.csv"):
        (broken / p.name).write_bytes(p.read_bytes())
    path = broken / "school_alias.csv"
    path.write_text(path.read_text(encoding="utf-8-sig") + "NOPE,x,draft,t,curated,\n", encoding="utf-8")
    with pytest.raises(tables.TableCsvError, match="foreign key violations.*school_alias"):
        build(tables_dir=broken, out_db=tmp_path / "x.db")
    assert not (tmp_path / "x.db").exists()                       # a failed build leaves no half-built database


def test_a_missing_or_wrong_table_file_is_refused(tmp_path, prepared):
    root, *_ = prepared
    folder = tmp_path / "tables"
    folder.mkdir()
    with pytest.raises(tables.TableCsvError, match="is missing"):
        build(tables_dir=folder, out_db=tmp_path / "x.db")
    for p in (root / "p1" / "tables").glob("*.csv"):
        (folder / p.name).write_bytes(p.read_bytes())
    (folder / "subject.csv").write_text("code,name\nTO,Toán\n", encoding="utf-8")
    with pytest.raises(tables.TableCsvError, match="subject.csv must have the columns of table subject"):
        build(tables_dir=folder, out_db=tmp_path / "x.db")


def test_the_nullable_empty_string_trap_is_refused(tmp_path):
    conn = db.create(tmp_path / "t.db")
    conn.execute("INSERT INTO source VALUES ('s', 'S', 'curated', ?, NULL, NULL)", ("",))
    with pytest.raises(tables.TableCsvError, match="source.location allows NULL but holds an empty string"):
        tables.export_tables(conn, tmp_path / "out")
    conn.close()


@pytest.mark.skipif(not TABLES_DIR.exists(), reason="the final tables are not published with the public repository")
def test_the_committed_final_tables_load_into_the_schema(tmp_path):
    result = build(tables_dir=TABLES_DIR, out_db=tmp_path / "app.db")
    assert result["table_counts"]["program"] > 3000
    assert result["table_counts"]["cutoff"] > 4000
