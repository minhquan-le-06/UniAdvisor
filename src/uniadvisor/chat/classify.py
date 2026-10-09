"""Which type a request is (spec 5, step 2).

The spec's classifier is a small trained model (trained on LLM-written messages). Until that model
exists, and as the baseline it must beat, RuleClassifier decides from keywords and the names found in the message.
load_classifier() returns the trained model when `models/message_classifier/model.joblib` exists, otherwise the rules.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from uniadvisor.chat.mentions import NganhIndex, SchoolIndex, find_area, find_category, find_levels, find_nv, \
    find_subjects
from uniadvisor.chat.numbers import find_numbers, normalise
from uniadvisor.chat.types import ALL_TYPES, LATE_TYPES, OTHER
from uniadvisor.data.scope import strip_accents
from uniadvisor.paths import ROOT

MODEL_DIR = ROOT / "models" / "message_classifier"


class Classifier(Protocol):
    name: str

    def classify(self, text: str) -> tuple[str, float]:
        """(type, confidence 0-1)."""


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern)


QUESTION = _rx(r"\?|\b(vi sao|tai sao|sao|why|la gi|nghia la|nghia gi|the nao|nhu nao|ra sao|hoi|cho (em|minh) "
               r"(hoi|biet)|giai thich|khac gi|khac nhau|lam sao|bao nhieu)\b")
UNDO = _rx(r"\b(hoan tac|undo|quay lai (nhu )?(cu|truoc)|tro lai nhu (cu|truoc)|lui lai|huy (thay doi|thao tac)( vua"
           r" (roi|xong))?|cho lai nhu cu)\b")
RERANK = _rx(r"\b(doi thu tu|dao (thu tu|nguoc|lai)|dao 2|hoan doi|doi cho (2|hai) lua chon|lua chon 2 (len )?(truoc|"
             r"dau|tren)|dua lua chon 2 len|uu tien lua chon 2|xep lai thu tu|doi (vi tri|lai) (2|hai) lua chon)\b")
RESTORE = _rx(r"\b(dua (lai|tro lai|vao lai)|them lai|lay lai|cho (vao )?lai|tra lai|khoi phuc|quay lai)\b")
REMOVE = _rx(r"\b(bo|xoa|loai|gach|cat|khong (muon|thich|can|hoc) (hoc )?(o |truong |nv |nguyen vong )?)\b")
EXTRA = _rx(r"\b(diem cong|cong (them )?\d|duoc cong|cong cho|ielts|chung chi|hoc sinh gioi|uu tien xet tuyen|"
            r"diem thuong)\b")
BUDGET = _rx(r"\b(ngan sach|hoc phi|chi phi|tien hoc|budget|tien (nong|dong)|kha nang tai chinh)\b")
NEAR = _rx(r"\b(gan nha|xa nha|di xa|o gan|hoc xa|que|xa que)\b")
REPLACE = _rx(r"\b(thay|doi|chuyen|doi sang|chuyen sang|chon lai|them nganh|nganh gan|bo nganh)\b")
WHY_NOT = _rx(r"\b(khong co|khong thay|ko co|k co|thieu|mat|bien mat|dau roi|o dau|khong nam)\b")
COMPARE = _rx(r"\b(khac (gi|nhau|nhu the nao|cho nao)|so sanh|giong|nen chon .* hay|hay hon|khac biet)\b")
WHAT_IS = _rx(r"\b(hoc gi|hoc nhung gi|la gi|la nganh gi|lam gi|ra truong|viec lam|thu nhap|luong|co kho|kho khong|"
              r"can (gioi|manh|hoc gioi) mon|hoc nhu the nao|tuong lai|co tot khong)\b")
FAVORITE = _rx(r"\b(yeu thich|thich nhat|muon (vao|hoc)( \w+){0,6} nhat|truong (trong )?mo|dream school)\b")
OWN_SCORE = _rx(r"\b(diem xet tuyen|tu tinh|em tinh (duoc|ra)|diem (cua )?(em|minh) tai|diem (cua )?(em|minh) o "
                r"truong|diem theo (cach tinh|cong thuc)|diem ket hop (cua )?(em|minh))\b")
CUTOFF = _rx(r"\b(diem chuan|diem dau vao)\b")
CUTOFF_DIRECTION = _rx(r"\b(cao hon|thap hon|tang|giam|thuc ra|that ra|ao|lam phat|nhieu (muc )?diem cong|dieu chinh|"
                       r"khong cao (bang|nhu)|de hon|kho hon|bi day len)\b")
# "30 điểm của trường A không cao bằng 29 của trường B": a cutoff compared across schools.
CUTOFF_COMPARED = _rx(r"\d+ (diem )?(cua )?(truong )?.+ khong (cao )?(bang|nhu) \d+")
ADDED = _rx(r"\bcong (diem|cho|them|e|em|\d)")            # "trường cộng điểm cho em": extra points, not own score
UNDO_LIKE = _rx(r"\b(lam lai|chon lai|tro lai)\b")
LEVEL_Q = _rx(r"\b(la gi|nghia la|nghia gi|la sao|hieu the nao|nghia la sao|y nghia|la the nao)\b")


class RuleClassifier:
    """Keyword and name rules. The order of the checks decides between types a message could fit."""
    name = "rules"

    def __init__(self, schools: SchoolIndex, nganh: NganhIndex, subjects: set[str]):
        self.schools, self.nganh, self.subjects = schools, nganh, subjects

    def classify(self, text: str) -> tuple[str, float]:
        key = strip_accents(normalise(text))
        if not key:
            return OTHER, 1.0
        question = bool(QUESTION.search(key))
        has_nv = bool(find_nv(text))
        has_school = bool(self.schools.find(text))
        nganh = self.nganh.find(text)
        numbers = find_numbers(normalise(text))
        if UNDO.search(key):
            return "undo", 0.9
        if RERANK.search(key):
            return "rerank", 0.9
        if find_levels(text) and (question or LEVEL_Q.search(key)):
            return "ask_level", 0.9
        if question and has_nv:
            return "ask_why_nv", 0.8
        if question and (has_school or "truong" in key) and WHY_NOT.search(key):
            return "ask_why_not", 0.8
        if len(nganh) >= 2 and COMPARE.search(key):
            return "ask_compare", 0.8
        if nganh and WHAT_IS.search(key) and not REPLACE.search(key.split("hoc gi")[0]):
            return "ask_what_is", 0.7
        if RESTORE.search(key) and (has_school or "nguyen vong" in key or re.search(r"\bnv\b", key)):
            return "restore", 0.8
        other_change = BUDGET.search(key) or NEAR.search(key) or UNDO_LIKE.search(key)
        if FAVORITE.search(key) and (has_school or "truong" in key) and not other_change and not question:
            return "favorite_school", 0.8
        if OWN_SCORE.search(key) and not EXTRA.search(key) and not ADDED.search(key):
            return "own_score", 0.8
        if (CUTOFF.search(key) and CUTOFF_DIRECTION.search(key) or CUTOFF_COMPARED.search(key)) and \
                (has_school or "truong" in key) and not question:
            return "cutoff_shift", 0.7
        if EXTRA.search(key):
            return "extra_points", 0.8
        if REMOVE.search(key) and (has_school or has_nv) and not nganh:
            return "remove", 0.8
        if find_subjects(text, self.subjects) and any(0 <= n.value <= 10 for n in numbers):
            return "change_score", 0.8
        if find_area(text) or find_category(text):
            return "change_priority", 0.8
        if BUDGET.search(key) or any(n.unit == "trieu" for n in numbers):
            return "change_budget", 0.7
        if NEAR.search(key):
            return "change_near_home", 0.7
        if nganh and (REPLACE.search(key) or REMOVE.search(key)):
            return "replace_nganh", 0.6
        if nganh and question:
            return "ask_what_is", 0.5
        if REMOVE.search(key) and has_school:
            return "remove", 0.5
        return OTHER, 0.5


class RulesFirst:
    """The trained model, with the rules deciding the types it was not trained on (types added after its training
    run, e.g. the three of 2026-10-08) until it is retrained."""

    def __init__(self, model: "ModelClassifier", rules: RuleClassifier, types: set[str]):
        self.model, self.rules, self.types = model, rules, types
        self.name = f"{model.name}+rules({', '.join(sorted(types))})"

    def classify(self, text: str) -> tuple[str, float]:
        rtype, conf = self.rules.classify(text)
        return (rtype, conf) if rtype in self.types else self.model.classify(text)


class ModelClassifier:
    """The trained classifier (uniadvisor.chat.train): a scikit-learn pipeline over accent-free text."""
    name = "model"

    def __init__(self, path: Path):
        import joblib
        bundle = joblib.load(path)
        self.pipeline = bundle["pipeline"]
        self.threshold = bundle.get("threshold", 0.0)
        self.meta = bundle.get("meta", {})

    def classify(self, text: str) -> tuple[str, float]:
        probs = self.pipeline.predict_proba([prepare(text)])[0]
        best = int(probs.argmax())
        label = self.pipeline.classes_[best]
        if probs[best] < self.threshold or label not in ALL_TYPES:
            return OTHER, float(probs[best])
        return label, float(probs[best])


def prepare(text: str) -> str:
    """What the model sees: lowercase, accent-free (students often type without accents), numbers kept."""
    return strip_accents(normalise(text))


def load_classifier(schools: SchoolIndex, nganh: NganhIndex, subjects: set[str],
                    model_dir: Path = MODEL_DIR) -> Classifier:
    path = model_dir / "model.joblib"
    rules = RuleClassifier(schools, nganh, subjects)
    if path.exists():
        model = ModelClassifier(path)
        unseen = set(LATE_TYPES) - set(model.pipeline.classes_)
        return RulesFirst(model, rules, unseen) if unseen else model
    return rules
