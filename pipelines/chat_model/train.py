"""Train and evaluate the message classifier, and score the rule baseline.

Training data: LLM-written messages from pipelines/notebooks/chat_message_generation.ipynb (run on Kaggle), saved as
pipelines/data/chat/generated/*.csv with columns text, type, family, model. Method:
- generation: prompts conditioned on the request type with seed examples (Sahu et al. 2022, "Data Augmentation for
  Intent Classification with Off-the-shelf Large Language Models", NLP4ConvAI @ ACL 2022) and on sampled attributes
  (style, accents, typos, length, persona) for diversity (Yu et al. 2023, "Large Language Model as Attributed Training
  Data Generator: A Tale of Diversity and Bias", NeurIPS 2023 Datasets and Benchmarks); see also the survey of Long et
  al. 2024 (Findings of ACL 2024).
- filtering: exact duplicates and empty/overlong messages are dropped; then, as Sahu et al. suggest for intents an LLM
  confuses, messages that a classifier trained on the rest (5-fold) assigns to another type with high probability are
  dropped.
- model: TF-IDF of character n-grams (2-5, within words) and word n-grams (1-2) on accent-free text, multinomial
  logistic regression. A few MB, milliseconds per message on CPU.
- tests: the held-out LLM family, the older reviewed check set, and the separate human-written Part 4 holdout when it
  has been supplied outside Git (see pipelines/data/chat/part4_human/README.md).

Run:
    python -m pipelines.chat_model.train            # train if generated data exists; always score the rule baseline
Writes models/message_classifier/{model.joblib, report.md} (report also without a model).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from uniadvisor.chat.classify import MODEL_DIR, Classifier, RuleClassifier, prepare
from uniadvisor.chat.types import ALL_TYPES, PART4_TYPES
from uniadvisor.data.scope import strip_accents
from uniadvisor.paths import CONFIG_DIR, ROOT

CHAT_DATA = ROOT / "pipelines" / "data" / "chat"
MAX_CHARS = 300
HUMAN_COLUMNS = ["id", "text", "type", "expected_requests", "expected_values", "needs_clarification", "writer",
                 "reviewer", "status", "note"]


def load_config() -> dict:
    return yaml.safe_load((CONFIG_DIR / "chat.yaml").read_text(encoding="utf-8"))["classifier"]


def load_generated(folder: Path = CHAT_DATA / "generated") -> pd.DataFrame:
    frames = [pd.read_csv(p, dtype=str, keep_default_na=False) for p in sorted(folder.glob("*.csv"))]
    if not frames:
        return pd.DataFrame(columns=["text", "type", "family", "model"])
    df = pd.concat(frames, ignore_index=True)
    return df[["text", "type", "family", "model"]]


# People's judgements: columns danh_gia (judgement), loai_dung (the right type), ghi_chu.
JUDGEMENTS = {"dung": "right", "sai_loai": "wrong_type", "khong_tu_nhien": "unnatural", "hai_yeu_cau": "two_requests",
              "khong_chac": "unsure"}


def judgement(value: str) -> str | None:
    """'Đúng' / 'dung' / 'sai loại' -> 'right' / 'wrong_type' ...; '' -> None; anything else -> 'invalid'."""
    key = "_".join(strip_accents(value or "").replace("-", " ").split())
    if not key:
        return None
    return JUDGEMENTS.get(key, "invalid")


def apply_judgements(df: pd.DataFrame, drop_unsure: bool = False) -> tuple[pd.DataFrame, dict]:
    """Rows judged right are kept as reviewed; wrong-type rows get the right type (Sahu et al. 2022: relabel what the
    LLM wrote for a neighbouring intent); unnatural or two-request rows are dropped. Unjudged rows pass unchanged;
    unsure rows too, unless drop_unsure (the LLM reviewer's own unsure verdicts are not trained on)."""
    df = df.copy()
    for col in ("danh_gia", "loai_dung"):
        if col not in df:
            df[col] = ""
    j = df["danh_gia"].map(judgement)
    right_type = df["loai_dung"].str.strip()
    relabel = (j == "wrong_type") & right_type.isin(ALL_TYPES)
    stats = {k: int((j == k).sum()) for k in ["right", "wrong_type", "unnatural", "two_requests", "unsure", "invalid"]}
    stats["wrong_type_without_valid_loai_dung"] = int(((j == "wrong_type") & ~relabel).sum())
    df.loc[relabel, "type"] = right_type[relabel]
    df["reviewed"] = j.isin(["right"]) | relabel
    drop = j.isin(["unnatural", "two_requests"]) | ((j == "wrong_type") & ~relabel)
    if drop_unsure:
        drop |= (j == "unsure") & (df.get("nguoi_cham", "") == "agent")
    return df[~drop].reset_index(drop=True), stats


def load_checks(path: Path = CHAT_DATA / "checks.csv", reviewed_only: bool = False) -> pd.DataFrame:
    """The check set with people's judgements applied. A row counts as reviewed when it was judged right (or
    relabelled), or when its status is 'reviewed'."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df, _ = apply_judgements(df)
    df["reviewed"] = df["reviewed"] | (df["status"] == "reviewed")
    return df[df["reviewed"]] if reviewed_only else df


def load_human_checks(path: Path = CHAT_DATA / "part4_human" / "part4_human.csv") -> pd.DataFrame:
    """Load the separately managed T5 holdout without ever treating it as training data.

    The file is ignored by Git.  Only reviewed, single-request rows can score a classifier; multi-request rows are
    retained with their expected request sequence for the end-to-end test runner, but do not distort a single-label
    accuracy metric.
    """
    if not path.exists():
        return pd.DataFrame(columns=HUMAN_COLUMNS + ["single_request"])
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = set(HUMAN_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError("Part 4 human check file is missing columns: " + ", ".join(sorted(missing)))
    df = df[HUMAN_COLUMNS].copy()
    invalid_types = sorted(set(df["type"]) - set(ALL_TYPES))
    if invalid_types:
        raise ValueError("Part 4 human check file has unknown types: " + ", ".join(invalid_types))
    invalid_status = sorted(set(df["status"]) - {"draft", "reviewed", "rejected"})
    if invalid_status:
        raise ValueError("Part 4 human check file has invalid status: " + ", ".join(invalid_status))
    if df["id"].str.strip().eq("").any() or df["id"].duplicated().any():
        raise ValueError("Part 4 human check file needs unique, non-empty ids.")
    if df["text"].str.strip().str.len().between(2, MAX_CHARS).eq(False).any():
        raise ValueError(f"Part 4 human check text must contain 2-{MAX_CHARS} characters.")
    if set(df["needs_clarification"]) - {"yes", "no"}:
        raise ValueError("Part 4 human check needs_clarification must be yes or no.")
    sequences = []
    for requests, values in zip(df["expected_requests"], df["expected_values"]):
        try:
            sequence = json.loads(requests)
        except json.JSONDecodeError as e:
            raise ValueError("Part 4 human check expected_requests must be JSON lists.") from e
        if not isinstance(sequence, list) or not sequence or any(t not in ALL_TYPES for t in sequence):
            raise ValueError("Part 4 human check expected_requests must be a non-empty list of known types.")
        try:
            expected_values = json.loads(values)
        except json.JSONDecodeError as e:
            raise ValueError("Part 4 human check expected_values must be JSON objects.") from e
        if not isinstance(expected_values, dict):
            raise ValueError("Part 4 human check expected_values must be JSON objects.")
        sequences.append(sequence)
    df["single_request"] = [len(s) == 1 and s[0] == t for s, t in zip(sequences, df["type"])]
    return df[df["status"] == "reviewed"].reset_index(drop=True)


def load_reviews(folder: Path = CHAT_DATA / "review") -> pd.DataFrame:
    """Judged samples of generated messages (chat_review_sample_<family>.csv with the judgement columns filled)."""
    frames = [pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig") for p in sorted(folder.glob("*.csv"))]
    if not frames:
        return pd.DataFrame(columns=["text", "type", "family", "danh_gia", "loai_dung"])
    df = pd.concat(frames, ignore_index=True)
    for col in ("danh_gia", "loai_dung", "family"):
        if col not in df:
            df[col] = ""
    return df


def review_rates(reviews: pd.DataFrame) -> dict:
    """Share of judged sample messages per judgement, per family: how good each generator was."""
    j = reviews["danh_gia"].map(judgement)
    judged = reviews[j.notna()].assign(j=j[j.notna()])
    if judged.empty:
        return {}
    return {fam: {k: round(float(v), 3) for k, v in g["j"].value_counts(normalize=True).items()} | {"n": len(g)}
            for fam, g in judged.groupby("family")}


def load_agent_reviews(folder: Path = CHAT_DATA / "agent_review") -> pd.DataFrame:
    """The LLM reviewer's judgement of every generated message (agent_review_<family>.csv; it reviews only what other
    models wrote). Same columns as people's judgements, plus nguoi_cham = 'agent'."""
    reviews = load_reviews(folder)
    reviews["nguoi_cham"] = "agent"
    return reviews


def apply_reviews(generated: pd.DataFrame, reviews: pd.DataFrame,
                  agent: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """Carry the judgements of the reviewed samples over to the same messages in the training data. People's
    judgements come first; the LLM reviewer's judgement applies where no person judged the message."""
    cols = ["text", "danh_gia", "loai_dung", "nguoi_cham"]
    people = reviews.assign(nguoi_cham="people")
    frames = [people[people["danh_gia"].map(judgement).notna()]]
    if agent is not None and not agent.empty:
        frames.append(agent[agent["danh_gia"].map(judgement).notna()])
    judged = pd.concat(frames, ignore_index=True)[cols].drop_duplicates("text")
    merged = generated.merge(judged, on="text", how="left").fillna({"danh_gia": "", "loai_dung": "",
                                                                    "nguoi_cham": ""})
    out, stats = apply_judgements(merged, drop_unsure=True)
    stats["judged_by_people"] = int((merged["nguoi_cham"] == "people").sum())
    stats["judged_by_agent"] = int((merged["nguoi_cham"] == "agent").sum())
    return out.drop(columns=["danh_gia", "loai_dung", "reviewed", "nguoi_cham"]), stats


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Drop unknown types, empty or overlong texts, and duplicates (accent-free, per type)."""
    stats = {"rows": len(df)}
    df = df[df["type"].isin(ALL_TYPES)]
    stats["unknown_type"] = stats["rows"] - len(df)
    df = df[df["text"].str.strip().str.len().between(2, MAX_CHARS)]
    stats["empty_or_long"] = stats["rows"] - stats["unknown_type"] - len(df)
    df = df.assign(key=df["text"].map(prepare))
    before = len(df)
    df = df.drop_duplicates(["key"]).drop(columns="key")
    stats["duplicates"] = before - len(df)
    return df.reset_index(drop=True), stats


def make_pipeline(seed: int):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    features = FeatureUnion([
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("words", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True,
                                  token_pattern=r"(?u)\b\w+\b")),
    ])
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(C=5.0, max_iter=3000, class_weight="balanced", random_state=seed))])


def relabel_filter(df: pd.DataFrame, probability: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(kept, dropped): 5-fold out-of-fold predictions; drop rows confidently predicted as another type."""
    from sklearn.model_selection import StratifiedKFold
    X = df["text"].map(prepare).tolist()
    y = df["type"].tolist()
    drop = [False] * len(df)
    folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    for train_idx, test_idx in folds.split(X, y):
        model = make_pipeline(seed).fit([X[i] for i in train_idx], [y[i] for i in train_idx])
        probs = model.predict_proba([X[i] for i in test_idx])
        classes = list(model.classes_)
        for row, i in zip(probs, test_idx):
            best = int(row.argmax())
            drop[i] = classes[best] != y[i] and row[best] >= probability
    mask = pd.Series(drop, index=df.index)
    return df[~mask].reset_index(drop=True), df[mask].reset_index(drop=True)


def evaluate(classifier: Classifier, df: pd.DataFrame) -> dict:
    from sklearn.metrics import accuracy_score, f1_score
    if df.empty:
        return {"n": 0}
    pred = [classifier.classify(t)[0] for t in df["text"]]
    confusions = Counter((a, b) for a, b in zip(df["type"], pred) if a != b)
    labels = sorted(set(df["type"]))
    per_type = f1_score(df["type"], pred, labels=labels, average=None, zero_division=0)
    return {"n": len(df), "accuracy": round(accuracy_score(df["type"], pred), 4),
            "macro_f1": round(f1_score(df["type"], pred, labels=labels, average="macro", zero_division=0), 4),
            "per_type_f1": {lab: round(float(f), 3) for lab, f in zip(labels, per_type)},
            "top_confusions": [f"{a} -> {b}: {n}" for (a, b), n in confusions.most_common(8)]}


class _Wrapped:
    """A fitted pipeline with the same classify() as the runtime ModelClassifier."""
    name = "model"

    def __init__(self, pipeline, threshold: float):
        self.pipeline, self.threshold = pipeline, threshold

    def classify(self, text: str) -> tuple[str, float]:
        probs = self.pipeline.predict_proba([prepare(text)])[0]
        best = int(probs.argmax())
        label = self.pipeline.classes_[best]
        return ("other" if probs[best] < self.threshold else label), float(probs[best])


def cross_family(train: pd.DataFrame, cfg: dict, rules: Classifier | None = None) -> dict:
    """Leave-one-family-out among the training families: train on the others, test on the one left out. An interim
    check of how well the model carries over to an unseen generator, before the held-out family's data exists."""
    out = {}
    for fam in sorted(train["family"].unique()):
        rest, held = train[train["family"] != fam], train[train["family"] == fam]
        if rest.empty or held.empty:
            continue
        pipeline = make_pipeline(cfg["seed"]).fit(rest["text"].map(prepare).tolist(), rest["type"].tolist())
        out[fam] = {"model": evaluate(_Wrapped(pipeline, cfg["other_threshold"]), held)}
        if rules is not None:
            out[fam]["rules"] = evaluate(rules, held)
    return out


def rule_classifier() -> RuleClassifier:
    from uniadvisor.ui.service import AppData
    d = AppData.load()
    return RuleClassifier(d.indexes.schools, d.indexes.nganh, set(d.subjects))


def _section(title: str, result: dict) -> list[str]:
    if not result.get("n"):
        return [f"### {title}", "", "No data.", ""]
    lines = [f"### {title}", "", f"{result['n']} messages: accuracy {result['accuracy']}, macro-F1 "
                                  f"{result['macro_f1']}.", "", "| type | F1 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in result["per_type_f1"].items()]
    if result["top_confusions"]:
        lines += ["", "Most frequent mistakes (true -> predicted): " + "; ".join(result["top_confusions"]) + "."]
    return lines + [""]


def run(out_dir: Path = MODEL_DIR) -> dict:
    cfg = load_config()
    checks_all = load_checks()
    checks_reviewed = checks_all[checks_all["reviewed"]]
    human_checks = load_human_checks()
    human_single = human_checks[human_checks["single_request"]]
    rules = rule_classifier()
    report = {"rules": {"checks_all": evaluate(rules, checks_all), "checks_reviewed": evaluate(rules, checks_reviewed),
                        "human": evaluate(rules, human_single)}}
    generated, stats = clean(load_generated())
    reviews, agent = load_reviews(), load_agent_reviews()
    # The held-out family is scored twice: "raw", as its model wrote it (only people's
    # judgements apply), and "reviewed", after the LLM review too (wrong labels fixed, unusable messages dropped).
    # The targets use the reviewed set: the raw set keeps messages whose label is known to be wrong.
    raw, _ = apply_reviews(generated, reviews, agent[agent["family"] != cfg["test_family"]])
    generated, stats["review_judgements"] = apply_reviews(generated, reviews, agent)
    stats["review_rates_by_family"] = review_rates(reviews)
    stats["agent_review_rates_by_family"] = review_rates(agent)
    report["data"] = stats
    if not generated.empty:
        test = generated[generated["family"] == cfg["test_family"]]
        test_raw = raw[raw["family"] == cfg["test_family"]]
        train = generated[generated["family"].isin(cfg["train_families"])]
        report["data"]["by_family"] = generated["family"].value_counts().to_dict()
        report["cross_family"] = cross_family(train, cfg, rules)
        train, dropped = relabel_filter(train, cfg["relabel_filter_probability"], cfg["seed"])
        report["data"]["relabel_dropped"] = len(dropped)
        report["data"]["train"] = len(train)
        pipeline = make_pipeline(cfg["seed"]).fit(train["text"].map(prepare).tolist(), train["type"].tolist())
        model = _Wrapped(pipeline, cfg["other_threshold"])
        report["model"] = {"test_family": evaluate(model, test), "test_family_raw": evaluate(model, test_raw),
                           "checks_all": evaluate(model, checks_all), "checks_reviewed": evaluate(model, checks_reviewed),
                           "human": evaluate(model, human_single)}
        report["rules"]["test_family"] = evaluate(rules, test)
        report["rules"]["test_family_raw"] = evaluate(rules, test_raw)
        targets = cfg["targets"]
        m = report["model"]
        reached = (m["test_family"].get("macro_f1", 0) >= targets["test_family_macro_f1"]
                   and m["checks_reviewed"].get("n", 0) > 0
                   and m["checks_reviewed"]["accuracy"] >= targets["checks_accuracy"]
                   and m["human"].get("n", 0) >= targets["human_checks_min_rows"]
                   and m["human"].get("accuracy", 0) >= targets["human_checks_accuracy"]
                   and set(PART4_TYPES) <= set(human_checks["type"])
                   and m["test_family"].get("macro_f1", 0) > report["rules"]["test_family"].get("macro_f1", 0))
        report["model"]["targets_reached"] = reached
        out_dir.mkdir(parents=True, exist_ok=True)
        import joblib
        meta = {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "train_rows": len(train),
                "families": cfg["train_families"], "test_family": cfg["test_family"], "targets_reached": reached}
        target = out_dir / ("model.joblib" if reached else "candidate.joblib")
        joblib.dump({"pipeline": pipeline, "threshold": cfg["other_threshold"], "meta": meta}, target)
        report["model"]["saved_as"] = target.relative_to(ROOT).as_posix()
        dropped.to_csv(out_dir / "relabel_dropped.csv", index=False, encoding="utf-8")
    write_report(report, out_dir)
    return report


def write_report(report: dict, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Message classifier report", "", f"Written {datetime.now(timezone.utc).date()} by "
             "`python -m pipelines.chat_model.train`.", "", "## Rule baseline (runtime fallback)", ""]
    lines += _section("Check set, all rows (LLM-drafted, not yet judged by people)", report["rules"]["checks_all"])
    lines += _section("Check set, rows people judged", report["rules"]["checks_reviewed"])
    lines += _section("Independent human-written Part 4 holdout (single requests)", report["rules"]["human"])
    if "test_family" in report["rules"]:
        lines += _section("Held-out LLM family, after the LLM review", report["rules"]["test_family"])
        lines += _section("Held-out LLM family, raw (as generated)", report["rules"]["test_family_raw"])
    lines += ["## Training data", "", "```", json.dumps(report["data"], ensure_ascii=False, indent=2), "```", ""]
    if report.get("cross_family"):
        lines += ["## Interim: leave-one-family-out among the training families", "",
                  "Trained on the other training families, tested on the one left out (no relabel filter). Not the "
                  "main test: that is the held-out family.", ""]
        for fam, result in report["cross_family"].items():
            lines += _section(f"Left out: {fam} (model)", result["model"])
            if "rules" in result:
                lines += _section(f"Left out: {fam} (rule baseline, same messages)", result["rules"])
    if "model" in report:
        m = report["model"]
        lines += ["## Trained model", ""]
        lines += _section("Held-out LLM family, after the LLM review (used for the targets)", m["test_family"])
        lines += _section("Held-out LLM family, raw (as generated)", m["test_family_raw"])
        lines += _section("Check set, all rows", m["checks_all"])
        lines += _section("Check set, rows people judged", m["checks_reviewed"])
        lines += _section("Independent human-written Part 4 holdout (single requests)", m["human"])
        lines += [f"Targets reached (and beats the rules): **{m['targets_reached']}**. Saved as `{m['saved_as']}` "
                  "(the app loads only `model.joblib`).", ""]
    else:
        lines += ["## Trained model", "", "No generated training data yet (`pipelines/data/chat/generated/`). The app uses the "
                  "rule baseline.", ""]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    report = run()
    print((MODEL_DIR / "report.md").read_text(encoding="utf-8"))
    return report


if __name__ == "__main__":
    main()
