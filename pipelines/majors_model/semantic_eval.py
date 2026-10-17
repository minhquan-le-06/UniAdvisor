"""Speed and quality of the semantic layer on the generated students' free texts (python -m pipelines.majors_model.semantic_eval).

Writes models/text_reader/semantic_report.md. As in the rules' report, a guess counts as right when the student also ticked the
option, a lower bound (writers mention things they did not tick). The table is read per `min_score`: the guesses added
on top of the rules, how many texts the rules left without any guess now get one, and how often an added guess is ticked.
"""

from __future__ import annotations

import statistics
import sys
import time

import numpy as np

from pipelines.majors_model.train import load_students
from uniadvisor.majors.reader import ticked, load_reader
from uniadvisor.majors.semantic import SemanticReader
from uniadvisor.paths import ROOT

OUT = ROOT / "models" / "text_reader" / "semantic_report.md"
GRID = [(0.80, 0.0), (0.84, 2.5), (0.86, 3.0), (0.86, 3.5), (0.88, 3.0), (0.88, 3.5)]      # (min_score, min_z)
EXAMPLES = ["Em thích máy móc", "Em thich nghe nhac va ve tranh", "Em thích khám phá cơ thể con người và cách nó hoạt động",
            "Em luôn mơ ước trở thành kỹ sư nuôi trồng thủy sản", "Em không thích làm việc ban đêm",
            "Em muốn làm việc với con số"]


def main():
    qn_reader = load_reader()
    sem = SemanticReader(qn_reader)
    students = load_students()
    kept = students[(students["dropped"] == "") & (students["text"].str.strip() != "")
                    & ~students["issues"].str.contains("text:chinese", regex=False)]
    rows = list(zip(kept["text"], kept["parsed"]))

    t = time.monotonic()
    sem.scored("Em thích máy móc")                          # downloads (first run) and loads the model
    first = time.monotonic() - t
    per_text, scored = [], []
    for text, answers in rows:
        a = time.monotonic()
        scored.append(sem.scored(text) or [])
        per_text.append((time.monotonic() - a) * 1000)
    rules = [{(g.question, g.option) for g in qn_reader.read(text)} for text, _ in rows]
    ticks = [ticked(a) for _, a in rows]
    sem_options = sem.options

    def guesses(clauses, min_score, min_z):
        return {k for _, negative, row in clauses for k in sem.pick(row, negative, min_score, min_z)}

    lines = ["# Semantic layer report", "",
             f"Model {sem.s.repo} ({sem.s.model_file}), {len(rows)} generated texts. The model is {'loaded' if sem.ready else 'NOT loaded'}.",
             f"Load with the files already downloaded (tokenizer, session, {len(sem_options)} options): {first:.1f} s.",
             f"Per text: median {statistics.median(per_text):.0f} ms, 95th percentile {np.percentile(per_text, 95):.0f} ms.", "",
             "A guess is right when the student also ticked it (a lower bound). 'New' = guesses the rules did not make.", "",
             "| min_score, min_z | new guesses per text | precision of new | texts the rules left empty now with a guess | rules' own precision |",
             "|---|---|---|---|---|"]
    rule_hits = sum(len(r & t) for r, t in zip(rules, ticks))
    rule_all = sum(len(r) for r in rules)
    empty = [i for i, r in enumerate(rules) if not r]
    for min_score, min_z in GRID:
        new_n = new_hit = filled = 0
        for i, clauses in enumerate(scored):
            new = guesses(clauses, min_score, min_z) - rules[i]
            new_n += len(new)
            new_hit += len(new & ticks[i])
            filled += bool(new) and i in set(empty)
        lines.append(f"| {min_score:.2f}, {min_z:.1f} | {new_n / len(rows):.2f} | {new_hit / new_n if new_n else 0:.1%} | "
                     f"{filled / len(empty):.0%} of {len(empty)} | {rule_hits / rule_all:.1%} |")
    lines += ["", "Examples (the config's settings):", ""]
    labels = {(q.id, o.code): o.label for q in qn_reader.qn.questions for o in q.options}
    for text in EXAMPLES:
        got = sem.read(text)
        lines.append(f"- \"{text}\" -> " + (", ".join(f"{labels[(g.question, g.option)]} ({g.question})" for g in got) or "(nothing)"))
    try:
        import psutil
        lines += ["", f"Memory of this process after the run: {psutil.Process().memory_info().rss / 1e6:.0f} MB (with the texts)."]
    except ImportError:
        pass
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
