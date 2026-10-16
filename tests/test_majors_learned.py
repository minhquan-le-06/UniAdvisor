"""The learned major suggester: fitting, the interface shared with the data scores, saving and the app's ready gate."""

import json

import numpy as np
import pandas as pd
import pytest

from uniadvisor.ui.catalog import Catalog
from pipelines.majors_model import checks
from uniadvisor.majors.model import Features, LearnedScorer, fit, metrics
from uniadvisor.majors.score import DataScorer, load_config
from pipelines.majors_model.train import split, train


@pytest.fixture
def scorer(fake_db):
    return DataScorer.load(fake_db, Catalog.load(fake_db))


def test_fit_learns_an_option_the_data_scores_miss():
    rng = np.random.default_rng(0)
    n, g = 300, 3
    D = rng.normal(size=(n, g))
    y = rng.integers(0, g, size=n)
    X = np.zeros((n, 2))
    X[y == 2, 0] = 1.0                              # option 0 is ticked by group 2's students only
    X[:, 1] = rng.integers(0, 2, size=n)            # option 1 is noise
    beta, W = fit(D, X, y, l2=0.1)
    assert W[0, 2] > 1.0 and W[0, 2] == W.max()          # the real signal is the largest weight
    _, W_strong = fit(D, X, y, l2=100.0)            # a strong penalty keeps the weights small
    assert abs(W_strong).max() < abs(W).max()
    _, W_cap = fit(D, X, y, l2=0.1, cap=np.array([True, False]))     # option 0 as a dislike: may only push away
    assert W_cap[0].max() <= 0.0 and W_cap[0, :2].min() < 0.0      # group 2 rises by pushing the others down


def test_dislike_questions_are_capped_by_default(scorer):
    features = Features.from_questionnaire(scorer)
    cap = features.capped(load_config()["model"]["no_positive"])
    assert {q for (q, _), c in zip(features.options, cap) if c} == {"q2", "q7", "q12"}


def test_learned_scorer_shares_the_interface(scorer, tmp_path):
    features = Features.from_questionnaire(scorer)
    W = np.zeros((len(features.options), len(scorer.codes)))
    zero = LearnedScorer(scorer, features, 1.0, W)
    computing = {"q1": ["TO", "TI"], "q6": ["computers"]}
    assert zero.rank(computing) == scorer.rank(computing)              # no learned weight: the data scores
    W[features.options.index(("q4", "cooking")), scorer.codes.index("77203")] = 5.0
    model = LearnedScorer(scorer, features, 1.0, W, {"ready": False})
    assert model.rank({"q4": ["cooking"]})[0] == "77203"
    top, why = model.suggest({"q4": ["cooking"]}, top=1)[0]
    assert top == "77203" and why == [("q4", "cooking")]
    model.save(tmp_path)
    again = LearnedScorer.load(tmp_path, scorer)
    assert again is not None and again.rank({"q4": ["cooking"]})[0] == "77203" and again.info["ready"] is False
    meta = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    meta["groups"] = meta["groups"][:-1]                                  # fitted on other groups: not loaded
    (tmp_path / "model.json").write_text(json.dumps(meta), encoding="utf-8")
    assert LearnedScorer.load(tmp_path, scorer) is None
    assert checks.run(model, [], {**load_config(), "checks": {**load_config()["checks"], "random_sets": 50}})[
        "deterministic"]


def test_metrics_and_split(scorer):
    pairs = [({"q1": ["SI"], "q6": ["health"]}, "77201"), ({"q1": ["TO", "TI"]}, "74801")]
    m = metrics(scorer, pairs)
    assert m["n"] == 2 and 0 < m["mrr"] <= 1 and m["hit5"] == 1.0
    rows = pd.DataFrame({"target_group": ["a"] * 10 + ["b"] * 5, "x": range(15)})
    rest, held = split(rows, 0.2, seed=1)
    assert len(held) == 3 and set(held["target_group"]) == {"a", "b"} and len(rest) == 12


def test_train_without_a_held_out_family_is_not_ready(scorer):
    medicine = {"q1": ["SI"], "q6": ["health"], "q11": "helping", "q3": ["people"]}
    computing = {"q1": ["TO", "TI"], "q6": ["computers"], "q4": ["code"]}
    rows = []
    for i in range(20):
        for group, answers in (("77201", medicine), ("74801", computing)):
            rows.append({"student_id": f"{group}-{i}", "family": "qwen", "target_group": group, "dropped": "",
                         "parsed": answers})
    cfg = load_config()
    cfg["model"] = {**cfg["model"], "l2_grid": [1.0]}
    model, report = train(pd.DataFrame(rows), scorer, cfg)
    assert report["test_family"] is None and report["train_students"] > 0
    assert report["test_kept"]["model"]["hit1"] >= report["test_kept"]["baseline"]["hit1"]
