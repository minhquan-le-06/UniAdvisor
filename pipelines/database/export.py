"""Write every table of the built database to a CSV file with exactly the table's columns.

Run: python -m pipelines.database.export [--db data/uniadvisor.db] [--out data/tables]
(`python -m pipelines.database.build` runs it at the end, into the `tables` folder next to the database.)
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from uniadvisor.data.tables import export_tables
from uniadvisor.paths import BUILD_DIR, DB_PATH


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--out", type=Path, default=BUILD_DIR / "tables")
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    counts = export_tables(conn, args.out)
    print(f"{len(counts)} tables, {sum(counts.values()):,} rows -> {args.out}")


if __name__ == "__main__":
    main()
