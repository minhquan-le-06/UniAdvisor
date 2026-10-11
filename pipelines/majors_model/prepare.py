"""Prepare the generated students for training:

1. clean every student's answers into option codes (suggest.clean);
2. drop students the writer did not give usable answers (not parsed, too few answered questions, nearly every option
   of Q12 ticked, exact duplicates);
3. consistency filter: keep students whose data scores put their own target group in the top N, so a
   "Quản lý giáo dục" student who only talks about software does not teach the model nonsense;
4. writer-habit audit: how often each family ticks each option, and which options are near-certain for one group.

    python -m pipelines.majors_model.prepare        # pipelines/data/students/generated/*.csv -> pipelines/data/students/clean/

Outputs: pipelines/data/students/clean/students.csv (kept and dropped, with the reason), pipelines/data/students/clean/report.md.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

from uniadvisor.paths import ROOT
from pipelines.majors_model.clean import Cleaner, plan_issues, text_as_asked, to_row
from uniadvisor.majors.score import DataScorer, load_config

GENERATED = ROOT / "pipelines" / "data" / "students" / "generated"
OUT = ROOT / "pipelines" / "data" / "students" / "clean"
# Options whose label nearly names a group: watched for students copying the group's name.
WATCHED = {"q8": ["school", "hospital", "site"], "q6": ["law", "journalism", "languages", "construction", "marketing"],
           "q4": ["code", "cooking"]}


def read_generated(folder: Path = GENERATED) -> pd.DataFrame:
    files = sorted(p for p in folder.glob("student_generated_*.csv") if not p.stem.endswith("_trial"))
    frames = [pd.read_csv(p, dtype=str, keep_default_na=False) for p in files]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def prepare(raw: pd.DataFrame, cleaner: Cleaner, scorer: DataScorer, cfg: dict) -> pd.DataFrame:
    keep_top = cfg["checks"]["own_group_top"]
    quantile = cfg["checks"].get("group_quantile", 1.0)
    min_answered = cfg["cleaning"]["min_answered"]
    ticked_share = cfg["cleaning"].get("max_unlimited_share", 1.0)
    rows, seen = [], set()
    for s in raw.to_dict("records"):
        try:
            data = json.loads(s["answers"]) if s.get("answers") else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            rows.append({**{k: s[k] for k in ("student_id", "family", "target_group")}, "dropped": "not_parsed"})
            continue
        c = cleaner.clean(data)
        attrs = json.loads(s["attributes"]) if s.get("attributes") else {}
        c.issues += plan_issues(c, attrs.get("counts", {}))
        text_as_asked(c, attrs)
        row = to_row(s, c)
        key = (s["family"], row["answers"])
        rank = scorer.rank(c.answers).index(s["target_group"]) + 1 if s["target_group"] in scorer.codes else None
        row["own_rank"] = rank
        if c.answered < min_answered:
            row["dropped"] = "too_few_answers"
        elif cleaner.too_many(c, ticked_share):
            row["dropped"] = "ticked_almost_all"
        elif key in seen:
            row["dropped"] = "duplicate"
        elif rank is None:
            row["dropped"] = "unknown_group"
        else:
            row["dropped"] = ""
        seen.add(key)
        rows.append(row)
    df = pd.DataFrame(rows)
    # Consistency filter, relative to each group (config/majors.yaml checks): below the global top and among the
    # worst of its own group's students.
    ok = df["dropped"] == "" if "dropped" in df else pd.Series(dtype=bool)
    if len(df) and ok.any():
        ranks = pd.to_numeric(df["own_rank"], errors="coerce")
        cut = ranks[ok].groupby(df.loc[ok, "target_group"]).quantile(quantile)
        limit = df["target_group"].map(cut)
        df.loc[ok & (ranks > keep_top) & (ranks >= limit), "dropped"] = "inconsistent"
    return df


def option_rates(df: pd.DataFrame, qn) -> pd.DataFrame:
    """Share of students ticking each option, per family and per target group."""
    out = []
    for r in df.to_dict("records"):
        answers = json.loads(r["answers"])
        for qid, v in answers.items():
            for code in Cleaner.picked(v):
                out.append((r["family"], r["target_group"], qid, code))
    return pd.DataFrame(out, columns=["family", "target_group", "question", "option"])


def audit(df: pd.DataFrame, scorer: DataScorer, label) -> list[str]:
    kept = df[df["dropped"] == ""]
    lines = []
    picks = option_rates(kept, scorer.qn)
    n_family = kept.groupby("family").size()
    n_group = kept.groupby("target_group").size()
    labels = {(q.id, o.code): o.label for q in scorer.qn.questions for o in q.options}

    # 1. Family habits: options one family ticks far more often than the others.
    rate = picks.groupby(["family", "question", "option"]).size().unstack("family", fill_value=0) / n_family
    rate = rate.fillna(0.0)
    if len(rate.columns) > 1:
        spread = (rate.max(axis=1) - rate.min(axis=1)).sort_values(ascending=False)
        lines += ["## Writer habits by family", "",
                  "Options whose pick rate differs most between families (a habit of one writer, not a trait of "
                  "students):", "", "| Option | " + " | ".join(rate.columns) + " |",
                  "|---|" + "---|" * len(rate.columns)]
        for (q, o), _ in spread.head(15).items():
            lines.append(f"| {q} {labels.get((q, o), o)} | " + " | ".join(f"{rate.loc[(q, o), f]:.0%}"
                                                                         for f in rate.columns) + " |")
        lines.append("")

    # 2. Near-certain options: ticked by almost every student of one group and rarely by others (the writer copying
    # the group's name into the answers).
    overall = picks.groupby(["question", "option"]).size() / len(kept)
    flagged = []
    for (g, q, o), n in picks.groupby(["target_group", "question", "option"]).size().items():
        r, base = n / n_group[g], overall.get((q, o), 0.0)
        if r >= 0.8 and base <= 0.2 and n_group[g] >= 10:
            flagged.append((r, g, q, o, base))
    lines += ["## Near-certain options per group", "",
              f"{len(flagged)} option-group pairs ticked by at least 80% of a group's students and at most 20% "
              "overall (groups with at least 10 kept students)" + (":" if flagged else "."), ""]
    for r, g, q, o, base in sorted(flagged, key=lambda x: (-x[0], x[1]))[:30]:
        watched = " (watched label)" if o in WATCHED.get(q, []) else ""
        lines.append(f"- {label(g)}: {q} {labels.get((q, o), o)} {r:.0%} (all students {base:.0%}){watched}")
    lines.append("")
    return lines


def report(df: pd.DataFrame, scorer: DataScorer, label) -> str:
    lines = ["# Generated students after cleaning", ""]
    total = df.groupby("family").size()
    kept = df[df["dropped"] == ""].groupby("family").size()
    reasons = df[df["dropped"] != ""].groupby(["family", "dropped"]).size()
    lines += ["| Family | Generated | Kept | Dropped (why) |", "|---|---|---|---|"]
    for f in total.index:
        why = ", ".join(f"{r} {n}" for (ff, r), n in reasons.items() if ff == f)
        lines.append(f"| {f} | {total[f]} | {kept.get(f, 0)} | {why or '-'} |")
    issues = Counter()
    for r in df[df["dropped"] == ""]["issues"]:
        issues.update(i.split(":")[0] for i in r.split(";") if i)
    lines += ["", "Repairs in kept students: " + (", ".join(f"{k} {v}" for k, v in issues.most_common()) or "none"),
              ""]
    per_group = df[df["dropped"] == ""].groupby("target_group").size()
    thin = [g for g in scorer.codes if per_group.get(g, 0) < 10]
    lines += [f"Groups with fewer than 10 kept students: {len(thin)}"
              + (" (" + ", ".join(label(g) for g in thin) + ")" if 0 < len(thin) <= 15 else ""), ""]
    lines += audit(df, scorer, label)
    return "\n".join(lines) + "\n"


def main():
    from uniadvisor.ui.service import AppData, db_path

    cfg = load_config()
    d = AppData.load()
    with sqlite3.connect(db_path()) as conn:
        scorer = DataScorer.load(conn, d.catalog, cfg=cfg)
    raw = read_generated()
    if raw.empty:
        print(f"no generated students in {GENERATED}")
        return
    cleaner = Cleaner(scorer.qn, cfg["cleaning"]["aliases"], cfg["cleaning"].get("siblings"))
    df = prepare(raw, cleaner, scorer, cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "students.csv", index=False, lineterminator="\n")
    text = report(df, scorer, d.catalog.label)
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
