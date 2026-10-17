"""The semantic layer of the free-text reader: what the rules cannot see ("thích máy móc", "nghe nhac va ve tranh").

The rules (reader.py) stay the first reader. This layer only adds guesses the rules did not make, each clause of the text
compared by meaning with the options of the questionnaire (a small multilingual sentence model, multilingual-e5-small,
int8, on the CPU). A clause that says a dislike is compared only with the options of the "not wanted" questions, as the
rules do. The guesses are shown apart ("Có thể em muốn nói"), never ticked, each with the words it came from.

The model (about 135 MB) is not in the code or the bundle: the first time a student's text needs it, it is downloaded
into a temporary folder from a public Hugging Face repository (as the database is, api/dbfetch.py). Nothing the student
wrote leaves the server. When the model cannot be downloaded or loaded the layer stays silent and the rules alone answer.

Variables: UNIADVISOR_MODEL_DIR (where to put the model, default the system temp folder).

    python -m pipelines.majors_model.semantic_eval      # speed and quality report on the generated students' texts
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import yaml

from uniadvisor.majors.questions import Questionnaire
from uniadvisor.majors.reader import CONFIG, Guess, Reader, _plain


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:
        """L2-normalised vectors, one row per text."""


@dataclass
class Settings:
    repo: str
    model_file: str
    tokenizer_file: str
    max_tokens: int
    threads: int
    min_score: float
    min_z: float
    within_best: float
    top_per_clause: int
    min_words: int
    retry_seconds: float
    templates: dict[str, str]
    positive: list[str]
    negative: list[str]

    @classmethod
    def load(cls, path: Path = CONFIG) -> "Settings":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["semantic"]
        return cls(raw["repo"], raw["model_file"], raw["tokenizer_file"], int(raw["max_tokens"]), int(raw["threads"]),
                   float(raw["min_score"]), float(raw["min_z"]), float(raw["within_best"]), int(raw["top_per_clause"]), int(raw["min_words"]),
                   float(raw["retry_seconds"]), dict(raw["templates"]), list(raw["positive_questions"]),
                   list(raw["negative_questions"]))


def download_model(s: Settings) -> tuple[Path, Path]:
    """The model and tokenizer files, downloaded once into the model folder (a serverless host keeps the temporary
    folder between calls of one instance)."""
    directory = Path(os.environ.get("UNIADVISOR_MODEL_DIR") or tempfile.gettempdir()) / "uniadvisor-model"
    directory.mkdir(parents=True, exist_ok=True)
    model, tokenizer = directory / s.model_file, directory / s.tokenizer_file
    if not (model.is_file() and tokenizer.is_file()):
        os.environ.setdefault("HF_HOME", str(directory / "hf-home"))        # the library's caches: the folder is writable
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from huggingface_hub import hf_hub_download
        for name in (s.model_file, s.tokenizer_file):
            hf_hub_download(repo_id=s.repo, filename=name, local_dir=str(directory))
    return model, tokenizer


class OnnxEncoder:
    """multilingual-e5 on ONNX Runtime: tokenise, run, mean-pool over the real tokens, normalise."""

    def __init__(self, model: Path, tokenizer: Path, max_tokens: int, threads: int):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=max_tokens)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>") or 0, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: list[str]) -> np.ndarray:
        batch = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in batch], dtype=np.int64)
        mask = np.array([e.attention_mask for e in batch], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0]
        weights = mask[..., None].astype(hidden.dtype)
        pooled = (hidden * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
        return (pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)).astype(np.float32)


class SemanticReader:
    """Guesses by meaning for what the rules missed. The model is loaded on the first text that needs it."""

    def __init__(self, reader: Reader, settings: Settings | None = None, make_encoder=None):
        self.reader = reader
        self.s = settings or Settings.load()
        self._make_encoder = make_encoder or self._onnx
        self._lock = threading.Lock()
        self._ready: tuple[Encoder, np.ndarray] | None = None
        self._failed_at: float | None = None
        self.load_seconds: float | None = None
        self.options = self._options(reader.qn)                                 # (question, code, passage) in a fixed order

    def _onnx(self) -> Encoder:
        model, tokenizer = download_model(self.s)
        return OnnxEncoder(model, tokenizer, self.s.max_tokens, self.s.threads)

    def _options(self, qn: Questionnaire) -> list[tuple[str, str, str]]:
        out = []
        for q in qn.questions:
            if q.id not in self.s.templates:
                continue
            for o in q.options:
                out.append((q.id, o.code, self.s.templates[q.id].format(label=o.label)))
        return out

    def _load(self) -> tuple[Encoder, np.ndarray] | None:
        with self._lock:
            if self._ready is not None:
                return self._ready
            if self._failed_at is not None and time.monotonic() - self._failed_at < self.s.retry_seconds:
                return None
            started = time.monotonic()
            try:
                encoder = self._make_encoder()
                matrix = encoder.encode(["passage: " + p for _, _, p in self.options])
            except Exception:                    # the rules alone answer; the student is not told, the host's log is
                self._failed_at = time.monotonic()
                return None
            self.load_seconds = time.monotonic() - started
            self._ready = (encoder, matrix)
            return self._ready

    @property
    def ready(self) -> bool:
        return self._ready is not None

    def scored(self, text: str) -> list[tuple[str, bool, np.ndarray]] | None:
        """Per clause: its words, whether it says a dislike, and its cosine to every option (None: no model, or no clause)."""
        r = self.reader
        clauses = []
        for clause in r.clauses(text or ""):
            for m in r.masks:
                clause = m.sub(lambda x: " " * len(x.group(0)), clause)
            clause = " ".join(clause.split())
            if len(clause.split()) >= self.s.min_words:
                clauses.append(clause)
        if not clauses:
            return []
        loaded = self._load()
        if loaded is None:
            return None
        encoder, matrix = loaded
        sims = encoder.encode(["query: " + c for c in clauses]) @ matrix.T
        return [(c, r._negative(c, _plain(c)), row) for c, row in zip(clauses, sims)]

    def pick(self, row: np.ndarray, negative: bool, min_score: float | None = None,
             min_z: float | None = None) -> list[tuple[str, str]]:
        """The options one clause means: cosine at least `min_score`, standing out from the clause's other options by
        `min_z` standard deviations (the model's scores sit close together, so a bare cosine says little), and within
        `within_best` of the best one; at most `top_per_clause`."""
        s = self.s
        min_score = s.min_score if min_score is None else min_score
        min_z = s.min_z if min_z is None else min_z
        allowed = set(s.negative if negative else s.positive)
        idx = [i for i, (q, _, _) in enumerate(self.options) if q in allowed]
        scores = row[idx]
        z = (scores - scores.mean()) / (scores.std() + 1e-9)
        best = scores.max()
        out = []
        for j in np.argsort(-scores)[:s.top_per_clause]:
            if scores[j] >= min_score and z[j] >= min_z and best - scores[j] <= s.within_best:
                out.append(self.options[idx[j]][:2])
        return out

    def read(self, text: str, have: set[tuple[str, str]] = frozenset()) -> list[Guess]:
        """Guesses for the clauses of `text`, leaving out the options in `have` (ticked, or guessed by the rules)."""
        out: dict[tuple[str, str], Guess] = {}
        for clause, negative, row in self.scored(text) or []:
            for key in self.pick(row, negative):
                if key not in have and key not in out:
                    out[key] = Guess(key[0], key[1], clause if len(clause) <= 90 else clause[:87] + "...")
        order = {q.id: n for n, q in enumerate(self.reader.qn.questions)}
        return sorted(out.values(), key=lambda g: (order[g.question], g.option))
