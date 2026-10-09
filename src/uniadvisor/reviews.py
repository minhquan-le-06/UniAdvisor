"""The review archive (data/reviews/): every review file returned by reviewers (people or an LLM), kept as received,
one CSV per kind of review with a `round` column instead of one folder per round.

A new round still arrives as a folder (`data/reviews/<round>/`, e.g. `step6_llm_round5_2026-10-09`) and is applied from
there (`python -m uniadvisor.facts.apply_review`, or by hand for the data reviews). Afterwards:

    python -m uniadvisor.reviews data/reviews/<round>        # append its files to the archive, remove the folder

`<kind>_done.csv` / `<kind>_reviewed.csv` / `<kind>.csv` -> `data/reviews/<kind>.csv` (rows prefixed with `round`);
the three Vietnamese-name kinds go to one `names_vi_review.csv` with a `kind` column; Markdown notes -> `summaries/<round>.md`.
Columns differ between rounds of a kind (the review files changed); the archive keeps their union, in order.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from uniadvisor.paths import ROOT

REVIEWS = ROOT / "data" / "reviews"
NAME_KINDS = {"occupation_names_vi": "occupation", "knowledge_names_vi": "knowledge", "riasec_names_vi": "riasec"}


def kind_of(path: Path) -> str:
    stem = path.stem
    for suffix in ("_done", "_reviewed"):
        stem = stem.removesuffix(suffix)
    return stem


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def archive_round(folder: Path, reviews: Path = REVIEWS, remove: bool = True) -> dict[str, int]:
    """Append a round folder's files to the archive; returns rows added per archive file."""
    rnd = folder.name
    added: dict[str, int] = {}
    for path in sorted(folder.glob("*.csv")):
        kind = kind_of(path)
        df = _read(path)
        lead = {"round": rnd}
        if kind in NAME_KINDS:
            lead["kind"] = NAME_KINDS[kind]
            kind = "names_vi_review"
        df = pd.concat([pd.DataFrame({k: [v] * len(df) for k, v in lead.items()}), df], axis=1)
        added[f"{kind}.csv"] = added.get(f"{kind}.csv", 0) + len(df)
        target = reviews / f"{kind}.csv"
        if target.exists():
            old = _read(target)
            have = set(zip(old["round"], old["kind"])) if "kind" in old else set(old["round"])
            assert (tuple(lead.values()) if "kind" in lead else rnd) not in have, f"{rnd} is already in {target.name}"
            df = pd.concat([old, df], ignore_index=True).fillna("")
        df.to_csv(target, index=False, lineterminator="\n", encoding="utf-8")
    notes = sorted(folder.glob("*.md"))
    for path in notes:
        (reviews / "summaries").mkdir(exist_ok=True)
        shutil.copyfile(path, reviews / "summaries" / (f"{rnd}.md" if len(notes) == 1 else f"{rnd}_{path.name}"))
    if remove:
        shutil.rmtree(folder)
    return added


def main():
    ap = argparse.ArgumentParser(description="Append a review round folder to data/reviews/ and remove the folder.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--keep", action="store_true", help="keep the folder")
    args = ap.parse_args()
    print(archive_round(args.folder, args.folder.parent, remove=not args.keep))


if __name__ == "__main__":
    main()
