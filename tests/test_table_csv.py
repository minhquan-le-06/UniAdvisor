"""Curated CSVs hold exactly the columns of their database table, and every table can be written back out as a CSV."""

from __future__ import annotations

import csv
import sqlite3

import pytest

from pipelines.database.prepare import prepare
from tests.rawfixture import write_raw_inputs
from uniadvisor import db
from uniadvisor.config import load_data_config
from uniadvisor.data import tables
from uniadvisor.paths import CURATED_DIR


def _header(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return next(csv.reader(fh))


@pytest.mark.parametrize("table, file", sorted(tables.CURATED_TABLES.items()))
def test_committed_curated_files_have_the_columns_of_their_table(tmp_path, table, file):
    conn = db.create(tmp_path / "t.db")
    assert _header(CURATED_DIR / file) == tables.table_columns(conn, table)
    conn.close()


def test_a_file_with_other_columns_is_refused_with_the_difference(tmp_path):
    path = tmp_path / "school_aliases.csv"
    path.write_text("school_code,alias,status,source,note\nHNA,FHN,draft,x,\n", encoding="utf-8")
    columns = ["school_code", "alias", "status", "origin", "source_id", "note"]
    with pytest.raises(tables.TableCsvError) as err:
        tables.read_table_csv(path, "school_alias", columns)
    assert "missing ['origin', 'source_id']" in str(err.value) and "unknown ['source']" in str(err.value)
    path.write_text("alias,school_code,status,origin,source_id,note\n", encoding="utf-8")
    with pytest.raises(tables.TableCsvError, match="wrong order"):
        tables.read_table_csv(path, "school_alias", columns)
    path.write_text("school_code,alias,status,origin,source_id,note\nHNA,FHN\n", encoding="utf-8")
    with pytest.raises(tables.TableCsvError, match="line 2"):
        tables.read_table_csv(path, "school_alias", columns)


def test_a_missing_file_is_no_rows(tmp_path):
    assert tables.read_table_csv(tmp_path / "none.csv", "school_alias", ["school_code"]) == []


def test_empty_cells_are_null_unless_the_column_is_required(tmp_path):
    conn = db.create(tmp_path / "t.db")
    conn.execute("INSERT INTO source VALUES ('curated', 'c', 'curated', NULL, NULL, NULL)")
    conn.execute("INSERT INTO school (code, name, city_basis, in_scope, source_id) VALUES ('HNA', 'A', 'x', 1, 'curated')")
    tables.insert_rows(conn, "school_alias", [{"school_code": "HNA", "alias": "FHN", "status": "draft", "origin": "t",
                                               "source_id": "curated", "note": ""}])
    assert conn.execute("SELECT note, origin FROM school_alias").fetchone() == (None, "t")
    conn.close()


def test_every_table_is_exported_with_its_columns_and_a_curated_file_comes_back_unchanged(tmp_path):
    inputs = write_raw_inputs(tmp_path / "inputs")
    curated = tmp_path / "curated"
    curated.mkdir()
    names = ("code,display_name,aliases,status,origin,source_id,note\n"
             "74801,\"Khoa học máy tính, Trí tuệ nhân tạo\",KHMT; AI,draft,group_labels_old_repo,curated,a note\n"
             "7480201,,IT,reviewed,tester,curated,\n")
    (curated / "display_names.csv").write_text(names, encoding="utf-8")
    result = prepare(inputs=inputs, curated=curated, out_db=tmp_path / "o" / "x.db", cfg=load_data_config())
    out = tmp_path / "o" / "tables"
    conn = sqlite3.connect(result["db"])
    for table in (r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")):
        assert _header(out / f"{table}.csv") == tables.table_columns(conn, table)
        with open(out / f"{table}.csv", encoding="utf-8-sig", newline="") as fh:
            volatile = len(tables.VOLATILE_META_KEYS) if table == "meta" else 0     # meta.csv lacks built_at, schema_version
            assert len(list(csv.reader(fh))) - 1 == conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] - volatile
    conn.close()
    assert result["table_counts"]["display_name"] == 2
    with open(out / "display_name.csv", encoding="utf-8-sig", newline="") as fh:
        exported = list(csv.reader(fh))
    assert exported == list(csv.reader(names.splitlines()))                          # the same rows, sorted by code
