"""Free-text reader: plain phrases into options, dislikes into Q2 / Q7 / Q12, no guesses beyond the text."""

import pytest

from uniadvisor.majors.reader import HAND_WRITTEN, evaluate, load_reader


@pytest.fixture(scope="module")
def reader():
    return load_reader()


def read(reader, text):
    return {(g.question, g.option) for g in reader.read(text)}


@pytest.mark.parametrize("text, expected", HAND_WRITTEN)
def test_hand_written_texts(reader, text, expected):
    assert expected <= read(reader, text)


def test_dislikes_and_their_cancelling(reader):
    assert read(reader, "em sợ máu") == {("q12", "blood")}
    assert read(reader, "em không ngại tiếp xúc với người bệnh") == set()          # "không ngại": not a dislike
    assert read(reader, "em ko thích làm ngoài trời") == {("q12", "outdoor_work")}
    assert read(reader, "em thích làm ngoài trời") == {("q8", "outdoors")}
    assert read(reader, "em giỏi toán nhưng ghét môn hóa") == {("q1", "TO"), ("q2", "HO")}
    assert ("q7", "law") in read(reader, "em không thích pháp luật")


def test_no_guess_from_look_alike_words(reader):
    assert read(reader, "em thích môi trường làm việc năng động") == set()        # workplace, not the topic
    assert read(reader, "em tò mò về quy luật tự nhiên") == set()
    assert read(reader, "em nói về màu sắc") == set()                            # "về", "màu": not vẽ, máu
    assert read(reader, "em khong so mau") == set()                             # unaccented and ambiguous
    assert read(reader, "") == set() and read(reader, "   ") == set()


def test_unaccented_text(reader):
    assert {("q4", "code"), ("q4", "hard_problem")} <= read(reader, "em thich lap trinh va giai toan kho")
    assert ("q12", "night_shift") in read(reader, "em khong thich lam ca dem")


def test_evaluate_counts_ticked_guesses(reader):
    rows = [("em thích vẽ", {"q4": ["drawing"]}), ("em thích vẽ và chụp ảnh", {"q4": ["drawing"]})]
    r = evaluate(reader, rows)
    assert r["n"] == 2 and r["precision"] == pytest.approx(2 / 3) and r["texts_with_a_guess"] == 1.0
