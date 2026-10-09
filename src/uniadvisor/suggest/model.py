"""Step 7 learned model (decisions of 2026-10-07): the fixed data scores plus small learned option
weights.

    score_g(answers) = beta * data_score_g(answers) + sum over picked options o of W[o, g] / (picks in o's question)

a conditional logit over the nhóm ngành, fitted on the generated students by maximum likelihood with an L2 penalty on W
(so an option moves a group only as far as the students show it should; with no evidence W stays 0 and the model is
the data scores). There is no per-group intercept: no popularity term (decision 2026-10-07). An option counts once per
question, divided like the data scores by how many options the student picked there, so ticking many options does not
weigh more. The question weights of the data scores (config/suggest.yaml) apply to W as well. The weights of Q2, Q7
and Q12 (the dislikes) are bounded at 0 (2026-10-09): the writers' medical students "do not want blood", and
unbounded the model learned that this dislike pulls towards Nha khoa (+3.4).

The model has the same interface as `score.DataScorer` (`codes`, `qn`, `scores`, `rank`, `suggest`), so the behaviour
checks and the app use either.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from uniadvisor.suggest.score import Answers, DataScorer


@dataclass
class Features:
    options: list[tuple[str, str]]                 # (question id, option code), the columns of X

    @classmethod
    def from_questionnaire(cls, scorer: DataScorer) -> "Features":
        return cls([(q.id, o.code) for q in scorer.qn.questions for o in q.options])

    def row(self, answers: Answers, scorer: DataScorer) -> np.ndarray:
        x = np.zeros(len(self.options))
        index = {k: i for i, k in enumerate(self.options)}
        for qid, value in answers.items():
            picks = list(dict.fromkeys(c for c in scorer.picked(value) if (qid, c) in index))
            for code in picks:
                x[index[(qid, code)]] = scorer.weight(qid) / len(picks)
        return x

    def capped(self, questions) -> np.ndarray:
        """Options of these questions: their weights may only push a group down (a dislike never attracts)."""
        return np.array([q in set(questions) for q, _ in self.options], dtype=bool)


def _softmax_rows(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit(D: np.ndarray, X: np.ndarray, y: np.ndarray, l2: float,
        cap: np.ndarray | None = None) -> tuple[float, np.ndarray]:
    """beta, W maximising the penalised likelihood. D: students x groups (data scores), X: students x options,
    y: index of the target group. cap: options (rows of W) whose weights are kept at or below 0."""
    n, g = D.shape
    k = X.shape[1]
    onehot = np.zeros((n, g))
    onehot[np.arange(n), y] = 1.0

    def loss(theta):
        beta, W = theta[0], theta[1:].reshape(k, g)
        z = beta * D + X @ W
        p = _softmax_rows(z)
        ll = np.sum(np.log(p[np.arange(n), y] + 1e-12))
        diff = p - onehot                                   # d(-ll)/dz
        grad_beta = np.sum(diff * D)
        grad_W = X.T @ diff + 2 * l2 * W
        return -ll + l2 * np.sum(W * W), np.concatenate([[grad_beta], grad_W.ravel()])

    theta0 = np.concatenate([[1.0], np.zeros(k * g)])
    bounds = None
    if cap is not None and cap.any():
        bounds = [(None, None)] + [(None, 0.0) if c else (None, None) for c in cap for _ in range(g)]
    res = minimize(loss, theta0, jac=True, method="L-BFGS-B", bounds=bounds, options={"maxiter": 500})
    return float(res.x[0]), res.x[1:].reshape(k, g)


def fit_baseline(D: np.ndarray, y: np.ndarray) -> float:
    """The data scores alone with a fitted scale (the baseline's best calibration; its ranking is the data scores')."""
    beta, _ = fit(D, np.zeros((len(y), 0)), y, 0.0)
    return beta


class LearnedScorer:
    """The data scores plus learned option weights; same interface as DataScorer."""

    def __init__(self, data: DataScorer, features: Features, beta: float, W: np.ndarray, info: dict | None = None):
        self.data = data
        self.qn = data.qn
        self.codes = data.codes
        self.features = features
        self.beta = beta
        self.W = W
        self.info = info or {}
        self.picked = data.picked
        self.weight = data.weight

    def scores(self, answers: Answers) -> np.ndarray:
        return self.beta * self.data.scores(answers) + self.features.row(answers, self.data) @ self.W

    def rank(self, answers: Answers) -> list[str]:
        s = self.scores(answers)
        return [self.codes[i] for i in sorted(range(len(self.codes)), key=lambda i: (-round(s[i], 9), self.codes[i]))]

    def contributions(self, answers: Answers) -> dict[tuple[str, str], np.ndarray]:
        parts = {k: self.beta * v for k, v in self.data.contributions(answers).items()}
        x = self.features.row(answers, self.data)
        for i, key in enumerate(self.features.options):
            if x[i]:
                parts[key] = parts.get(key, 0.0) + x[i] * self.W[i]
        return parts

    def suggest(self, answers: Answers, top: int = 5, reasons: int = 3):
        parts = self.contributions(answers)
        out = []
        for code in self.rank(answers)[:top]:
            i = self.codes.index(code)
            best = sorted(((v[i], k) for k, v in parts.items() if v[i] > 0), key=lambda x: (-x[0], x[1]))
            out.append((code, [k for _, k in best[:reasons]]))
        return out

    def save(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(folder / "weights.npz", W=self.W, beta=np.array([self.beta]))
        (folder / "model.json").write_text(json.dumps(
            {"groups": self.codes, "options": [list(o) for o in self.features.options], **self.info},
            ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, folder: Path, data: DataScorer) -> "LearnedScorer | None":
        """None when there is no model, or it was fitted on other groups or options than the current ones."""
        if not (folder / "weights.npz").exists():
            return None
        meta = json.loads((folder / "model.json").read_text(encoding="utf-8"))
        features = Features.from_questionnaire(data)
        if meta["groups"] != data.codes or [tuple(o) for o in meta["options"]] != features.options:
            return None
        w = np.load(folder / "weights.npz")
        return cls(data, features, float(w["beta"][0]), w["W"], meta)


def metrics(scorer, students: list[tuple[dict, str]], top: int = 5) -> dict:
    """Hit@1, Hit@5 and mean reciprocal rank of the target group."""
    ranks = []
    for answers, target in students:
        ranked = scorer.rank(answers)
        ranks.append(ranked.index(target) + 1 if target in ranked else len(ranked) + 1)
    r = np.array(ranks, dtype=float)
    return {"n": len(r), "hit1": float(np.mean(r <= 1)), f"hit{top}": float(np.mean(r <= top)),
            "mrr": float(np.mean(1 / r)), "median_rank": float(np.median(r))} if len(r) else {"n": 0}
