"""Build the app's database from the final tables (pipelines/data/tables).

Run: python -m pipelines.database.build [--tables DIR] [--out PATH]

Takes seconds: it creates the schema and loads one CSV per table (`uniadvisor.data.tables.load_tables`). The rules that
decide what the tables hold are in `python -m pipelines.database.prepare`, which is run by whoever changes the data.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from uniadvisor import db
from uniadvisor.data import tables
from uniadvisor.paths import DB_PATH, TABLES_DIR


def build(tables_dir: Path = TABLES_DIR, out_db: Path = DB_PATH) -> dict:
    """Create `out_db` (replacing any file there) with the schema and the rows of the tables in `tables_dir`."""
    conn = db.create(out_db)
    try:
        counts = tables.load_tables(conn, tables_dir)
        conn.execute("INSERT INTO meta (key, value) VALUES ('built_at', ?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        conn.commit()
    except Exception:
        conn.close()
        out_db.unlink(missing_ok=True)
        raise
    conn.close()
    return {"db": out_db, "table_counts": counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", type=Path, default=TABLES_DIR, help="folder with one CSV per table")
    ap.add_argument("--out", type=Path, default=DB_PATH, help="database file to create")
    args = ap.parse_args(argv)
    start = time.perf_counter()
    try:
        result = build(args.tables, args.out)
    except (tables.TableCsvError, FileNotFoundError) as err:
        print(f"Cannot build the database: {err}", file=sys.stderr)
        return 1
    n = sum(result["table_counts"].values())
    print(f"{args.out}: {len(result['table_counts'])} tables, {n:,} rows, {time.perf_counter() - start:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
