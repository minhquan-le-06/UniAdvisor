"""Tables as CSV files: the columns of a CSV are the columns of its database table, in the same order.

- `read_table_csv` reads a CSV for a table and refuses it when its header differs from the table's columns.
- `insert_rows` writes rows into a table by column name.
- `export_tables` writes every table of a built database to `<out_dir>/<table>.csv` (UTF-8 with BOM, so Excel opens it),
  one row per row of the table, in the order the build inserted them. An empty cell is NULL.
- `load_tables` is the reverse: it fills an empty database from such a folder, casting each cell to its column's type.

The export of a whole database is `python -m pipelines.database.export`; `pipelines.database.prepare` writes the
final tables with it and `pipelines.database.build` loads them.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from uniadvisor.data.text import nfc

# Tables that are filled from a CSV in pipelines/data/curated: table -> file name.
CURATED_TABLES = {
    "display_name": "display_names.csv",
    "school_alias": "school_aliases.csv",
    "school_employment": "school_employment.csv",
    "nganh_cip": "nganh_cip.csv",
    "name_vi": "names_vi.csv",
}

# meta rows that differ on every build; they are not written to meta.csv (the loader sets them).
VOLATILE_META_KEYS = ("built_at", "schema_version")


class TableCsvError(ValueError):
    """A CSV does not have the columns of its table, or a cell does not fit its column."""


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                       "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def read_table_csv(path: Path, table: str, columns: list[str], normalize: bool = True) -> list[dict[str, str]]:
    """Rows of the file as dicts of strings (NFC-normalised unless `normalize` is False); [] when the file does not
    exist. The header must be exactly `columns` (the table's columns, in order)."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return []
        if header != columns:
            missing = [c for c in columns if c not in header]
            extra = [c for c in header if c not in columns]
            detail = "; ".join(x for x in (f"missing {missing}" if missing else "", f"unknown {extra}" if extra else "",
                                           "wrong order" if not missing and not extra else "") if x)
            raise TableCsvError(f"{path.name} must have the columns of table {table}, in this order: "
                                f"{','.join(columns)} ({detail})")
        rows = []
        for n, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(values) != len(columns):
                raise TableCsvError(f"{path.name} line {n}: {len(values)} cells, expected {len(columns)}")
            rows.append({c: (nfc(v) if normalize else v) for c, v in zip(columns, values)})
        return rows


def insert_rows(conn: sqlite3.Connection, table: str, rows: list[dict], columns: list[str] | None = None) -> None:
    """INSERT the rows by column name; '' and None become NULL for columns that allow it and are kept as '' otherwise."""
    columns = columns or table_columns(conn, table)
    not_null = {r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[3]}
    conn.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})",
        [tuple(("" if c in not_null else None) if row.get(c) in ("", None) else row[c] for c in columns)
         for row in rows])


def export_tables(conn: sqlite3.Connection, out_dir: Path, skip_meta_keys: tuple[str, ...] = ()) -> dict[str, int]:
    """Write every table to <out_dir>/<table>.csv in insertion order; return table -> number of rows.
    `skip_meta_keys`: meta rows left out (the ones that change on every build).

    A CSV cannot tell NULL from an empty string, so a nullable column that holds '' is refused."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.csv"):
        old.unlink()
    counts = {}
    for table in table_names(conn):
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        for _, name, _, notnull, _, pk in info:
            if not notnull and not pk and conn.execute(f"SELECT 1 FROM {table} WHERE {name} = '' LIMIT 1").fetchone():
                raise TableCsvError(f"{table}.{name} allows NULL but holds an empty string: a CSV cannot tell them "
                                    "apart; make the column NOT NULL or store NULL")
        columns = [r[1] for r in info]
        where = f" WHERE key NOT IN ({','.join('?' * len(skip_meta_keys))})" if table == "meta" and skip_meta_keys else ""
        params = skip_meta_keys if where else ()
        n = 0
        with open(out_dir / f"{table}.csv", "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(columns)
            for row in conn.execute(f"SELECT {','.join(columns)} FROM {table}{where} ORDER BY rowid", params):
                writer.writerow(["" if v is None else v for v in row])
                n += 1
        counts[table] = n
    return counts


def _cell(value: str, sql_type: str, nullable: bool, column: str, path: str, line: int):
    """One CSV cell as the Python value for its column: NULL for an empty cell of a nullable column, a number for an
    INTEGER or REAL column, the text otherwise."""
    t = sql_type.upper()
    numeric = t.startswith("INT") or t in ("REAL", "FLOAT", "DOUBLE", "NUMERIC")
    if value == "":
        if nullable:
            return None
        if numeric:
            raise TableCsvError(f"{path} line {line}: column {column} ({t}) may not be empty")
        return ""
    try:
        if t.startswith("INT"):
            return int(value)
        if numeric:
            return float(value)
    except ValueError:
        raise TableCsvError(f"{path} line {line}: {value!r} is not a valid {t} for column {column}") from None
    return value


def load_tables(conn: sqlite3.Connection, tables_dir: Path) -> dict[str, int]:
    """Fill the (empty) tables of `conn` from `<tables_dir>/<table>.csv`; return table -> rows loaded.

    Every table must have its file with exactly the table's columns. Cells are cast by the column's declared type; an
    empty cell is NULL when the column allows it. Foreign keys are checked at the end and the first violations are
    listed. `meta.csv` lacks the volatile keys; the rows `db.create` already put in `meta` are kept."""
    conn.commit()                                   # PRAGMA foreign_keys does nothing inside a transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    counts = {}
    for table in table_names(conn):
        path = tables_dir / f"{table}.csv"
        if not path.exists():
            raise TableCsvError(f"{path} is missing: every table of the schema needs its CSV")
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = [r[1] for r in info]
        rows = read_table_csv(path, table, columns, normalize=False)
        kinds = {r[1]: r[2] for r in info}
        nullable = {r[1] for r in info if not r[3] and not r[5]}
        data = []
        for n, row in enumerate(rows, start=2):
            data.append(tuple(_cell(row[c], kinds[c], c in nullable, c, path.name, n) for c in columns))
        conn.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' * len(columns))})", data)
        counts[table] = len(data)
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.execute("PRAGMA foreign_keys = ON")
    if violations:
        shown = "; ".join(f"{t} row {rowid} -> {parent}" for t, rowid, parent, _ in violations[:8])
        raise TableCsvError(f"{len(violations)} foreign key violations: {shown}")
    return counts
