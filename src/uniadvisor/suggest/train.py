"""Train and test the step 7 model on the cleaned generated students.

    python -m uniadvisor.suggest.prepare         # first: data/step7/generated/ -> data/step7/clean/students.csv
    python -m uniadvisor.suggest.train           # -> models/suggester/ (weights, model.json, report.md)

Training: the kept students of the training families. The L2 penalty is chosen on a validation part of them (by mean
reciprocal rank). Testing: the held-out family (config/suggest.yaml `model.test_family`, an LLM family the model never
saw) against the baseline, the data scores alone; reported on its kept students and on all its parsed students (the
consistency filter uses the data scores, which would flatter them). Until the held-out family's students exist, a
random part of the training families is held out instead, and the model is not marked ready.

The app uses the model only when model.json says `ready` (decided here: the held-out family exists, the model beats
the baseline's mean reciprocal rank on all its parsed students, and the behaviour checks pass); otherwise the data
scores.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from uniadvisor.paths import ROOT
from uniadvisor.suggest.checks import load_cases, run as run_checks
from uniadvisor.suggest.model import Features, LearnedScorer, fit, metrics
from uniadvisor.suggest.score import DataScorer, load_config

CLEAN = ROOT / "data" / "step7" / "clean" / "students.csv"
OUT = ROOT / "models" / "suggester"


def load_students(path: Path = CLEAN) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df[df["answers"] != ""].copy()
    df["parsed"] = df["answers"].map(json.loads)
    return df


def matrices(rows: pd.DataFrame, scorer: DataScorer, features: Features):
    index = {g: i for i, g in enumerate(scorer.codes)}
    rows = rows[rows["target_group"].isin(index)]
    D = np.array([scorer.scores(a) for a in rows["parsed"]])
    X = np.array([features.row(a, scorer) for a in rows["parsed"]])
    y = np.array([index[g] for g in rows["target_group"]])
    return D, X, y


def split(rows: pd.DataFrame, share: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A share of each group's students held out (stratified, seeded)."""
    rng = random.Random(seed)
    held = []
    for _, g in rows.groupby("target_group"):
        ids = sorted(g.index)
        rng.shuffle(ids)
        held += ids[:max(1, round(len(ids) * share))]
    return rows.drop(index=held), rows.loc[held]


def choose_l2(rows: pd.DataFrame, scorer: DataScorer, features: Features, grid: list[float], seed: int,
              cap: np.ndarray | None = None):
    fit_part, val = split(rows, 0.2, seed)
    D, X, y = matrices(fit_part, scorer, features)
    pairs = list(zip(val["parsed"], val["target_group"]))
    results = {}
    for l2 in grid:
        beta, W = fit(D, X, y, l2, cap)
        results[l2] = metrics(LearnedScorer(scorer, features, beta, W), pairs)["mrr"]
    return max(results, key=lambda k: (results[k], k)), results


def top_weights(model: LearnedScorer, label, n: int = 15) -> list[str]:
    labels = {(q.id, o.code): o.label for q in model.qn.questions for o in q.options}
    flat = sorted(((abs(model.W[i, j]), model.W[i, j], o, model.codes[j]) for i, o in enumerate(model.features.options)
                   for j in range(len(model.codes))), reverse=True)[:n]
    return [f"- {o[0]} {labels[o]} -> {label(g)}: {w:+.2f}" for _, w, o, g in flat]


def train(students: pd.DataFrame, scorer: DataScorer, cfg: dict) -> tuple[LearnedScorer, dict]:
    m = cfg["model"]
    features = Features.from_questionnaire(scorer)
    kept = students[students["dropped"] == ""]
    families = sorted(set(students["family"]))
    test_family = m["test_family"] if m["test_family"] in families else None
    train_rows = kept[kept["family"].isin([f for f in m["train_families"] if f in families])]
    if test_family:
        test_kept = kept[kept["family"] == test_family]
        test_all = students[(students["family"] == test_family) & (students["dropped"] != "not_parsed")]
    else:                                   # no held-out family yet: a random part of the training families
        train_rows, test_kept = split(train_rows, m["holdout_share"], m["seed"])
        # plus every student the consistency filter dropped (never trained on): the filter uses the data scores
        test_all = students[students["student_id"].isin(test_kept["student_id"])
                            | (students["dropped"] == "inconsistent")]
    cap = features.capped(m.get("no_positive", []))
    l2, grid = choose_l2(train_rows, scorer, features, m["l2_grid"], m["seed"], cap)
    D, X, y = matrices(train_rows, scorer, features)
    beta, W = fit(D, X, y, l2, cap)
    model = LearnedScorer(scorer, features, beta, W)
    report = {"families": families, "test_family": test_family, "train_students": int(len(y)), "l2": l2,
              "l2_grid_mrr": {str(k): round(v, 4) for k, v in grid.items()}, "beta": round(beta, 3)}
    for name, rows in (("test_kept", test_kept), ("test_all_parsed", test_all)):
        pairs = list(zip(rows["parsed"], rows["target_group"]))
        report[name] = {"baseline": metrics(scorer, pairs), "model": metrics(model, pairs)}
    return model, report


def render(report: dict, checks_model: dict, checks_base: dict, weights: list[str]) -> str:
    def row(name, r):
        return (f"| {name} | {r['n']} | {r['hit1']:.1%} | {r['hit5']:.1%} | {r['mrr']:.3f} | {r['median_rank']:g} |"
                if r.get("n") else f"| {name} | 0 | - | - | - | - |")
    test = f"held-out family `{report['test_family']}`" if report["test_family"] else \
        "a random 20% of the training families' kept students (no held-out family yet)"
    lines = ["# Step 7 model report", "",
             f"Families: {', '.join(report['families'])}. Trained on {report['train_students']} kept students; tested "
             f"on {test}. L2 = {report['l2']} (validation MRR by L2: {report['l2_grid_mrr']}); data-score scale "
             f"beta = {report['beta']}.", "", "| Test set | students | Hit@1 | Hit@5 | MRR | median rank |",
             "|---|---|---|---|---|---|"]
    for key, title in (("test_kept", "kept"), ("test_all_parsed", "all parsed")):
        lines.append(row(f"{title}: data scores (baseline)", report[key]["baseline"]))
        lines.append(row(f"{title}: model", report[key]["model"]))
    lines += ["", "Behaviour checks (31 hand-written cases, random answer sets, reachability):", "",
              "| Check | data scores | model |", "|---|---|---|",
              f"| hand-written cases passed | {checks_base['passed']} | {checks_model['passed']} |",
              f"| most frequent group in random top 5 | {checks_base['max_share']:.1%} | {checks_model['max_share']:.1%} |",
              f"| groups that cannot reach the top 5 | {checks_base['unreachable']} | {checks_model['unreachable']} |",
              f"| same answers, same order | {checks_base['deterministic']} | {checks_model['deterministic']} |", "",
              f"Ready for the app: **{report['ready']}** ({report['ready_reason']}).", "",
              "Largest learned option weights (a label that nearly names a group should not dominate):", ""]
    return "\n".join(lines + weights) + "\n"


def summary(result: dict, n_cases: int) -> dict:
    return {"passed": f"{sum(ok for _, _, ok in result['cases'])}/{n_cases}", "max_share": result["max_share"],
            "unreachable": len(result["unreachable"]), "deterministic": result["deterministic"]}


def main():
    from uniadvisor.app.service import AppData, db_path

    cfg = load_config()
    d = AppData.load()
    with sqlite3.connect(db_path()) as conn:
        scorer = DataScorer.load(conn, d.catalog, cfg=cfg)
    students = load_students()
    model, report = train(students, scorer, cfg)
    cases = load_cases(scorer.qn)
    cb = summary(run_checks(scorer, cases, cfg), len(cases))
    cm_raw = run_checks(model, cases, cfg)
    cm = summary(cm_raw, len(cases))
    gate = cfg["model"]["gate"]
    beats = report["test_all_parsed"]["model"].get("mrr", 0) > report["test_all_parsed"]["baseline"].get("mrr", 0)
    checks_ok = (cm_raw["max_share"] <= cfg["checks"]["max_share_random"] and cm_raw["deterministic"]
                 and sum(ok for _, _, ok in cm_raw["cases"]) >= sum(ok for _, _, ok in run_checks(scorer, cases, cfg)["cases"])
                 - gate["cases_may_lose"])
    report["ready"] = bool(report["test_family"] and beats and checks_ok)
    report["ready_reason"] = ("held-out family missing" if not report["test_family"] else
                              "beats the baseline and passes the checks" if report["ready"] else
                              "does not beat the baseline on the held-out family" if not beats else
                              "behaviour checks fail")
    model.info = {k: report[k] for k in ("ready", "ready_reason", "families", "test_family", "l2", "beta")}
    model.save(OUT)
    text = render(report, cm, cb, top_weights(model, d.catalog.label))
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
