"""The semantic layer of the free-text reader (majors/semantic.py) with a stand-in for the model: word overlap instead of
meaning, so what is checked is the selection around it: negation, the options already known, short clauses and the fallback."""

import dataclasses
import zlib

import numpy as np

from uniadvisor.majors import semantic
from uniadvisor.majors.reader import load_reader
from uniadvisor.majors.semantic import Settings, SemanticReader


class WordEncoder:
    """A hashed bag of words, normalised: two texts are close when they share words."""

    def encode(self, texts):
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in text.lower().replace("query:", "").replace("passage:", "").split():
                out[i, zlib.crc32(word.encode()) % 256] += 1
        return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def make(**changes):
    s = dataclasses.replace(Settings.load(), min_score=0.5, min_z=2.0, min_words=3, **changes)
    return SemanticReader(load_reader(), s, make_encoder=WordEncoder)


def test_a_clause_is_read_into_the_option_it_resembles():
    got = {(g.question, g.option) for g in make().read("Em thích làm việc với máy móc")}
    assert ("q3", "machines") in got


def test_a_clause_that_says_a_dislike_only_reaches_the_not_wanted_questions():
    reader = make()
    got = reader.read("Em không muốn công việc phải thấy máu")
    assert ("q12", "blood") in {(g.question, g.option) for g in got}
    assert {g.question for g in got} <= {"q2", "q7", "q12"}
    assert {g.question for g in reader.read("Em thích làm việc với máy móc")} <= set(reader.s.positive)


def test_options_already_known_are_left_out_and_the_words_are_kept():
    reader = make()
    text = "Em thích làm việc với máy móc"
    assert ("q3", "machines") not in {(g.question, g.option) for g in reader.read(text, have={("q3", "machines")})}
    guess = next(g for g in reader.read(text) if g.option == "machines")
    assert guess.words == "em thích làm việc với máy móc"


def test_a_clause_of_fewer_than_three_words_is_not_read():
    assert make().read("máy móc") == []


def test_nothing_is_loaded_before_a_text_needs_it():
    calls = []
    reader = SemanticReader(load_reader(), make_encoder=lambda: calls.append(1) or WordEncoder())
    assert not reader.ready and not calls
    assert reader.read("") == [] and not calls
    reader.read("Em thích làm việc với máy móc")
    assert reader.ready and calls == [1]


def test_when_the_model_cannot_be_loaded_the_rules_alone_answer(monkeypatch):
    calls = []

    def broken():
        calls.append(1)
        raise OSError("no network")

    reader = SemanticReader(load_reader(), make_encoder=broken)
    assert reader.read("Em thích làm việc với máy móc") == []
    assert reader.read("Em thích làm việc với máy móc") == [] and calls == [1]      # not tried again at once
    now = semantic.time.monotonic()
    monkeypatch.setattr(semantic.time, "monotonic", lambda: now + reader.s.retry_seconds + 1)
    reader.read("Em thích làm việc với máy móc")
    assert calls == [1, 1]


def test_the_options_are_said_as_sentences_from_the_configured_templates():
    reader = make()
    assert len(reader.options) > 100
    passage = {(q, c): p for q, c, p in reader.options}
    assert passage[("q3", "machines")] == "Em thích làm việc với Máy móc"
    assert passage[("q12", "blood")].startswith("Em không muốn công việc:")
