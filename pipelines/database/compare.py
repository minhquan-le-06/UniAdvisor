"""Compare two built databases table by table: every value and its SQLite type (integer, real, text, null).

Run: python -m pipelines.database.compare OLD.db NEW.db

Rows are compared in insertion (rowid) order, because the app may read unordered queries in that order. Columns that
only one database has are listed but not compared; `meta.built_at` is ignored. Exit code 1 when any table differs.
Used to prove that a change to the build or the loader leaves the database unchanged.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

IGNORED_META_KEYS = ("built_at",)


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _rows(conn: sqlite3.Connection, table: str, columns: list[str]) -> list[tuple]:
    select = ", ".join(f"{c}, typeof({c})" for c in columns)
    where = " WHERE key NOT IN (%s)" % ",".join(repr(k) for k in IGNORED_META_KEYS) if table == "meta" else ""
    return conn.execute(f"SELECT {select} FROM {table}{where} ORDER BY rowid").fetchall()


def compare_databases(old: Path | str, new: Path | str) -> list[dict]:
    """One dict per table: name, rows in each, columns only in one of them, whether values and types match, and a few
    examples of the rows that differ."""
    a, b = sqlite3.connect(old), sqlite3.connect(new)
    try:
        ta, tb = _tables(a), _tables(b)
        report = []
        for table in sorted(set(ta) | set(tb)):
            if table not in ta or table not in tb:
                report.append({"table": table, "same": False, "only_in": "old" if table in ta else "new"})
                continue
            ca, cb = _columns(a, table), _columns(b, table)
            common = [c for c in ca if c in cb]
            ra, rb = _rows(a, table, common), _rows(b, table, common)
            sa, sb = set(ra), set(rb)
            report.append({
                "table": table, "same": ra == rb, "same_rows_other_order": ra != rb and sorted(ra, key=repr) == sorted(rb, key=repr),
                "rows_old": len(ra), "rows_new": len(rb),
                "columns_only_old": [c for c in ca if c not in cb], "columns_only_new": [c for c in cb if c not in ca],
                "only_old": sorted(sa - sb, key=repr)[:3], "only_new": sorted(sb - sa, key=repr)[:3]})
        return report
    finally:
        a.close()
        b.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")        # example rows contain Vietnamese text
    report = compare_databases(args.old, args.new)
    for r in report:
        if "only_in" in r:
            print(f"DIFF {r['table']:26} only in the {r['only_in']} database")
            continue
        extra = f"  columns only in new: {r['columns_only_new']}" if r["columns_only_new"] else ""
        extra += f"  columns only in old: {r['columns_only_old']}" if r["columns_only_old"] else ""
        label = "OK  " if r["same"] else "ORDR" if r["same_rows_other_order"] else "DIFF"
        print(f"{label} {r['table']:26} rows {r['rows_old']:>7} / {r['rows_new']:>7}{extra}")
        if not r["same"] and not r["same_rows_other_order"]:
            print("     only in old:", r["only_old"])
            print("     only in new:", r["only_new"])
    bad = sum(not r["same"] for r in report)
    print(f"{len(report)} tables, {bad} differing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
