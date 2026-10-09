"""Behaviour checks of a step 7 scorer (decisions of 2026-10-07):

- every group can reach the top 5 (some answer set puts it there);
- no group is in the top 5 of more than 25% of random answer sets;
- the same answers always give the same order;
- hand-written cases (config/step7_checks.yaml): plain students whose suitable groups are obvious.

    python -m uniadvisor.suggest.checks          # report on the data scores (the baseline)

Works with any scorer that has `codes`, `qn`, `scores(answers)` and `rank(answers)`.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter
from dataclasses import dataclass

import yaml

from uniadvisor.paths import CONFIG_DIR
from uniadvisor.suggest.questions import Questionnaire

CASES = CONFIG_DIR / "step7_checks.yaml"


@dataclass(frozen=True)
class Case:
    name: str
    answers: dict
    expect: tuple[str, ...]          # at least one of these groups in the top 5


def from_labels(qn: Questionnaire, labels: dict) -> dict:
    """Answers written with option labels (readable) -> option codes."""
    out = {}
    for qid, value in labels.items():
        q = qn.get(qid)
        by = q.by_label()
        if q.kind == "single":
            out[qid] = by[value].code
        else:
            out[qid] = [by[v].code for v in value]
    return out


def load_cases(qn: Questionnaire, path=CASES) -> list[Case]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Case(c["name"], from_labels(qn, c["answers"]), tuple(str(x) for x in c["expect"])) for c in raw["cases"]]


def random_answers(qn: Questionnaire, rng: random.Random, skip: float = 0.2) -> dict:
    """A random answer set that respects the questionnaire's rules (max picks, not_in)."""
    out: dict = {}
    for q in qn.questions:
        if q.id != "q1" and rng.random() < skip:
            out[q.id] = None
            continue
        codes = [o.code for o in q.options]
        if q.not_in and out.get(q.not_in):
            codes = [c for c in codes if c not in out[q.not_in]]
        if q.kind == "single":
            out[q.id] = rng.choice(codes)
        else:
            k = rng.randint(1, min(q.max or 4, 4, len(codes)))
            out[q.id] = rng.sample(codes, k)
    return out


def random_shares(scorer, n: int, seed: int, top: int = 5) -> Counter:
    rng = random.Random(seed)
    seen: Counter = Counter()
    for _ in range(n):
        seen.update(scorer.rank(random_answers(scorer.qn, rng))[:top])
    return seen


def best_rank(scorer, group: str, top: int = 5, rounds: int = 25) -> tuple[int, dict]:
    """Greedy search for answers that put `group` high: add one option at a time (within the questionnaire's rules),
    the one that most raises the group's lead over the 5th-best other group, until nothing helps."""
    i = scorer.codes.index(group)
    answers: dict = {}

    def margin(a) -> float:
        s = scorer.scores(a)
        others = sorted((v for j, v in enumerate(s) if j != i), reverse=True)
        return s[i] - others[top - 1]

    current = margin(answers)
    for _ in range(rounds):
        best = None
        for q in scorer.qn.questions:
            have = scorer.picked(answers.get(q.id))
            full = q.kind == "single" and have or q.kind == "multi" and q.max and len(have) >= q.max
            banned = set(scorer.picked(answers.get(q.not_in))) if q.not_in else set()
            if full:
                continue
            for o in q.options:
                if o.code in have or o.code in banned:
                    continue
                trial = dict(answers)
                trial[q.id] = o.code if q.kind == "single" else have + [o.code]
                m = margin(trial)
                if m > current + 1e-9 and (best is None or m > best[0]):
                    best = (m, trial)
        if best is None:
            break
        current, answers = best
    return scorer.rank(answers).index(group) + 1, answers


def run(scorer, cases: list[Case], cfg: dict, top: int = 5) -> dict:
    c = cfg["checks"]
    ranks = {g: best_rank(scorer, g, top)[0] for g in scorer.codes}
    shares = random_shares(scorer, c["random_sets"], c["random_seed"], top)
    n = c["random_sets"]
    results = []
    for case in cases:
        ranked = scorer.rank(case.answers)
        hit = [g for g in ranked[:top] if g in case.expect]
        results.append((case, ranked[:top], bool(hit)))
    rng = random.Random(1)
    same = all(scorer.rank(a) == scorer.rank(dict(a)) for a in (random_answers(scorer.qn, rng) for _ in range(50)))
    return {"unreachable": {g: r for g, r in ranks.items() if r > top}, "ranks": ranks,
            "max_share": max(shares.values()) / n if shares else 0.0,
            "too_often": {g: k / n for g, k in shares.items() if k / n > c["max_share_random"]},
            "never": [g for g in scorer.codes if not shares.get(g)], "shares": {g: k / n for g, k in shares.items()},
            "cases": results, "deterministic": same}


def report(result: dict, label, top: int = 5) -> str:
    lines = ["# Step 7 behaviour checks", ""]
    n_cases = len(result["cases"])
    passed = sum(ok for _, _, ok in result["cases"])
    lines += [f"- Every group can reach the top {top}: "
              + ("yes" if not result["unreachable"] else
                 "no: " + ", ".join(f"{label(g)} (best rank {r})" for g, r in sorted(result["unreachable"].items()))),
              f"- Most frequent group in the top {top} of random answer sets: {result['max_share']:.1%}"
              + ("" if not result["too_often"] else " (over the limit: " + ", ".join(
                  f"{label(g)} {s:.0%}" for g, s in sorted(result["too_often"].items())) + ")"),
              f"- Groups never in a random top {top}: {len(result['never'])}"
              + (" (" + ", ".join(label(g) for g in result["never"]) + ")" if result["never"] else ""),
              f"- Same answers, same order: {'yes' if result['deterministic'] else 'NO'}",
              f"- Hand-written cases: {passed}/{n_cases} with an expected group in the top {top}", ""]
    lines += ["| Case | Top 5 | Expected (one of) | OK |", "|---|---|---|---|"]
    for case, ranked, ok in result["cases"]:
        lines.append(f"| {case.name} | {'; '.join(label(g) for g in ranked)} | "
                     f"{'; '.join(label(g) for g in case.expect)} | {'yes' if ok else '**no**'} |")
    lines += ["", f"Top-{top} share in random answer sets, most frequent first:", ""]
    lines += [f"- {label(g)}: {s:.1%}" for g, s in sorted(result["shares"].items(), key=lambda x: (-x[1], x[0]))[:10]]
    return "\n".join(lines) + "\n"


def main():
    from uniadvisor.app.service import AppData, db_path
    from uniadvisor.suggest.score import DataScorer, load_config

    d = AppData.load()
    cfg = load_config()
    with sqlite3.connect(db_path()) as conn:
        scorer = DataScorer.load(conn, d.catalog, cfg=cfg)
    result = run(scorer, load_cases(scorer.qn), cfg, cfg["suggest"]["top"])
    print(report(result, d.catalog.label, cfg["suggest"]["top"]))


if __name__ == "__main__":
    main()
