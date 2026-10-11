"""The questionnaire (config/questionnaire.yaml): loading and checking it."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from uniadvisor.paths import CONFIG_DIR

PATH = CONFIG_DIR / "questionnaire.yaml"


@dataclass(frozen=True)
class Option:
    code: str
    label: str
    holland: str = ""                    # RIASEC letters
    knowledge: str | None = None         # O*NET Knowledge area
    work_context: str | None = None      # O*NET Work Context element id
    against: bool = False                # choosing it counts against ngành with a high Work Context value
    subject: str | None = None           # exam subject code

    @property
    def learned_only(self) -> bool:
        return not (self.holland or self.knowledge or self.work_context or self.subject)


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str                            # 'multi' | 'single'
    options: tuple[Option, ...]
    max: int | None = None               # most options a multi question takes
    not_in: str | None = None            # options picked there cannot be picked here
    negative: bool = False               # the options count against (disliked subjects or topics)

    def by_label(self) -> dict[str, Option]:
        return {o.label: o for o in self.options}


@dataclass(frozen=True)
class Questionnaire:
    questions: tuple[Question, ...]
    subjects_knowledge: dict[str, str]
    free_text_label: str
    free_text_placeholder: str
    exclude_groups: tuple[str, ...] = field(default_factory=tuple)

    def get(self, qid: str) -> Question:
        return next(q for q in self.questions if q.id == qid)


def load_questionnaire(path=PATH) -> Questionnaire:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = []
    for q in raw["questions"]:
        a = q["answer"]
        opts = tuple(Option(o["code"], o["label"], o.get("holland", ""), o.get("knowledge"),
                            str(o["work_context"]) if o.get("work_context") else None, bool(o.get("against")),
                            o.get("subject")) for o in q["options"])
        questions.append(Question(q["id"], q["text"], a["kind"], opts, a.get("max"), a.get("not_in"),
                                  bool(q.get("negative"))))
    ft = raw["free_text"]
    return Questionnaire(tuple(questions), dict(raw["subjects_knowledge"]), ft["label"], ft["placeholder"],
                         tuple(raw.get("exclude_groups", [])))


def check(qn: Questionnaire, knowledge_areas: set[str], work_context_ids: set[str], subjects: set[str]) -> list[str]:
    """Problems with the questionnaire against the data it points to (empty when fine)."""
    problems = []
    ids = [q.id for q in qn.questions]
    if len(set(ids)) != len(ids):
        problems.append("duplicate question ids")
    for q in qn.questions:
        if q.kind not in ("multi", "single"):
            problems.append(f"{q.id}: unknown answer kind {q.kind}")
        if q.not_in and q.not_in not in ids:
            problems.append(f"{q.id}: not_in {q.not_in} is not a question")
        for what, values in (("code", [o.code for o in q.options]), ("label", [o.label for o in q.options])):
            if len(set(values)) != len(values):
                problems.append(f"{q.id}: duplicate option {what}s")
        for o in q.options:
            if set(o.holland) - set("RIASEC"):
                problems.append(f"{q.id}.{o.code}: holland {o.holland!r}")
            if o.knowledge and o.knowledge not in knowledge_areas:
                problems.append(f"{q.id}.{o.code}: knowledge area {o.knowledge!r} not in O*NET")
            if o.work_context and o.work_context not in work_context_ids:
                problems.append(f"{q.id}.{o.code}: work context {o.work_context!r} not imported")
            if o.subject and o.subject not in subjects:
                problems.append(f"{q.id}.{o.code}: subject {o.subject!r} unknown")
            # subjects keep their official names ("Giáo dục kinh tế và pháp luật" is one subject)
            if "(" in o.label or "," in o.label or (" và " in o.label and not o.subject):
                problems.append(f"{q.id}.{o.code}: label {o.label!r} is not one thing")
    for s, k in qn.subjects_knowledge.items():
        if s not in subjects or k not in knowledge_areas:
            problems.append(f"subjects_knowledge {s} -> {k}")
    return problems
