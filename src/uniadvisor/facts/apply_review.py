"""Apply a review round of the step 6 drafts to data/curated.

    python -m uniadvisor.facts.apply_review data/reviews/<round folder> --by "reviewer" --on 2026-10-07

The folder holds the reviewer's files, named like the review files plus `_done`:
- nganh_cip_review_done.csv: verdict ok / wrong / unsure per ngành -> CIP link -> nganh_cip.csv status reviewed /
  rejected / unsure (unsure and rejected links are not used; config/facts.yaml).
- nganh_close_review_done.csv: verdict ok / weak / wrong per close pair -> appended to nganh_close_verdicts.csv.
- *_names_vi_done.csv: verdict ok / fix (+ suggested_vi) -> data/curated/names_vi.csv, status reviewed.
Missing files are skipped. Rows already judged keep their first verdict unless the new file judges them again.
Afterwards the folder goes into the review archive: `python -m uniadvisor.reviews <folder>`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from uniadvisor.facts.build import NAMES_FILE
from uniadvisor.paths import CURATED_DIR

CIP_STATUS = {"ok": "reviewed", "wrong": "rejected", "unsure": "unsure"}
# reviewer file -> (kind in names_vi.csv, the file's id column, the names_vi.csv column it matches)
NAME_FILES = {"knowledge_names_vi": ("knowledge", "element_id", "onet_id"),
              "occupation_names_vi": ("occupation", "occupation_code", "key"),
              "riasec_names_vi": ("riasec", "riasec", "key")}


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _write(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def apply_cip(done: pd.DataFrame, curated: Path, by: str, on: str) -> dict:
    path = curated / "nganh_cip.csv"
    m = _read(path)
    for col in ("reviewed_by", "reviewed_on", "review_comment"):
        if col not in m:
            m[col] = ""
    key = ["nganh_code", "rank", "cip_code"]
    verdicts = {tuple(r[k] for k in key): (r["verdict"].strip(), r.get("comment", ""))
                for _, r in done.iterrows() if r["verdict"].strip() in CIP_STATUS}
    n = 0
    for i, r in m.iterrows():
        v = verdicts.get(tuple(r[k] for k in key))
        if v:
            m.loc[i, ["status", "reviewed_by", "reviewed_on", "review_comment"]] = [CIP_STATUS[v[0]], by, on, v[1]]
            n += 1
    _write(m, path)
    return {"links_judged": n, "not_found": len(verdicts) - n}


def apply_close(done: pd.DataFrame, curated: Path, by: str, on: str) -> dict:
    path = curated / "nganh_close_verdicts.csv"
    cols = ["nganh_code", "nganh_name", "other_code", "other_name", "verdict", "comment"]
    new = done[done["verdict"].str.strip().isin(["ok", "weak", "wrong"])][cols].assign(reviewed_by=by, reviewed_on=on)
    old = _read(path) if path.exists() else pd.DataFrame(columns=new.columns)
    out = pd.concat([old, new]).drop_duplicates(["nganh_code", "other_code"], keep="last")
    _write(out, path)
    return {"pairs_judged": len(new), "pairs_total": len(out)}


def apply_names(done: pd.DataFrame, curated: Path, review: str, by: str) -> dict:
    kind, key, match = NAME_FILES[review]
    path = curated / NAMES_FILE
    cur = _read(path)
    v = {r[key]: (r["verdict"].strip(), r.get("suggested_vi", "").strip()) for _, r in done.iterrows()}
    fixed = 0
    for i, r in cur[cur["kind"] == kind].iterrows():
        verdict, suggested = v.get(r[match], ("", ""))
        if verdict == "fix" and suggested:
            cur.loc[i, "note"] = (r["note"] + "; " if r["note"] else "") + f"was '{r['name_vi']}'"
            cur.loc[i, "name_vi"] = suggested
            fixed += 1
        if verdict in ("ok", "fix"):
            cur.loc[i, ["status", "reviewed_by"]] = ["reviewed", by]
    _write(cur, path)
    return {"names_judged": sum(1 for x in v.values() if x[0] in ("ok", "fix")), "fixed": fixed}


def apply_round(folder: Path, by: str, on: str, curated: Path = CURATED_DIR) -> dict:
    out = {}
    if (folder / "nganh_cip_review_done.csv").exists():
        out["cip"] = apply_cip(_read(folder / "nganh_cip_review_done.csv"), curated, by, on)
    if (folder / "nganh_close_review_done.csv").exists():
        out["close"] = apply_close(_read(folder / "nganh_close_review_done.csv"), curated, by, on)
    for name in NAME_FILES:
        if (folder / f"{name}_done.csv").exists():
            out[name] = apply_names(_read(folder / f"{name}_done.csv"), curated, name, by)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--by", required=True)
    ap.add_argument("--on", required=True)
    args = ap.parse_args()
    print(apply_round(args.folder, args.by, args.on))


if __name__ == "__main__":
    main()
