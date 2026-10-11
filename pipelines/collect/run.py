"""Collect cutoffs (2025, 2026) for schools from VnExpress and Tuyensinh247 into pipelines/data/collected/.

Run: python -m pipelines.collect.run                 # in-scope schools that have no cutoff in the database
     python -m pipelines.collect.run --schools GTA,IUH
     python -m pipelines.collect.run --offline        # rebuild the CSVs from the cache only

Every response is cached in pipelines/data/cache/http (re-runs do not fetch again). VietNamNet's API answers 403 to this
collector, so it is not used for new schools (its old rows in pipelines/data/inputs stay in use).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from uniadvisor import db
from pipelines.collect import sites
from pipelines.collect.http import PoliteClient
from uniadvisor.paths import COLLECTED_CACHE_DIR as CACHE_DIR
from uniadvisor.paths import COLLECTED_DIR


def schools_without_cutoffs() -> list[str]:
    conn = db.connect()
    rows = conn.execute(
        """SELECT s.code FROM school s WHERE s.in_scope = 1 AND NOT EXISTS
           (SELECT 1 FROM program p JOIN cutoff c ON c.program_id = p.id WHERE p.school_code = s.code)
           ORDER BY s.code"""
    ).fetchall()
    return [r[0] for r in rows]


def _merge(path: Path, columns: list[str], new_rows: list[dict], schools: set[str]):
    """Replace the rows of `schools` in the CSV at `path` with `new_rows`; keep other schools' rows."""
    rows = []
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["school_code"] not in schools]
    rows += [{k: r.get(k, "") for k in columns} for r in new_rows]
    rows.sort(key=lambda r: (r["school_code"], str(r["year"]), r["program_code"], str(r.get("url", ""))))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def collect(schools: list[str], offline: bool = False, delay: float = 2.0) -> dict:
    client = PoliteClient(CACHE_DIR, delay=delay, offline=offline)
    ts_urls = sites.tuyensinh247_urls(client)
    vne, ts, summary = [], [], {}
    for i, code in enumerate(schools, 1):
        v = sites.collect_vnexpress(client, code)
        t = sites.collect_tuyensinh247(client, code, ts_urls)
        vne += v
        ts += t
        summary[code] = (len(v), len(t))
        print(f"[{i}/{len(schools)}] {code}: vnexpress {len(v)}, tuyensinh247 {len(t)} (fetched so far {client.fetched})",
              flush=True)
    done = set(schools)
    _merge(COLLECTED_DIR / "vnexpress_cutoffs.csv", sites.VNE_COLUMNS, vne, done)
    _merge(COLLECTED_DIR / "tuyensinh247_cutoffs.csv", sites.TS_COLUMNS, ts, done)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schools", help="comma-separated school codes (default: in-scope schools without cutoffs)")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between requests to one host")
    args = parser.parse_args(argv)
    schools = args.schools.split(",") if args.schools else schools_without_cutoffs()
    summary = collect(schools, args.offline, args.delay)
    empty = [s for s, (v, t) in summary.items() if v == 0 and t == 0]
    print(f"{len(schools)} schools; nothing found for {len(empty)}: {', '.join(empty)}")


if __name__ == "__main__":
    main()
