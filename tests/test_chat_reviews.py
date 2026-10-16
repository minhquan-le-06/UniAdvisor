"""People's judgements of chat messages and how training uses them."""

import pandas as pd
import pytest

from pipelines.chat_model.train import apply_judgements, apply_reviews, judgement, load_checks, load_human_checks, review_rates


@pytest.mark.parametrize("value, expected", [
    ("dung", "right"), ("Đúng", "right"), (" ĐÚNG ", "right"), ("sai loại", "wrong_type"), ("sai_loai", "wrong_type"),
    ("không tự nhiên", "unnatural"), ("hai-yeu-cau", "two_requests"), ("không chắc", "unsure"), ("", None),
    ("ok", "invalid"),
])
def test_judgement_values(value, expected):
    assert judgement(value) == expected


def frame(rows):
    return pd.DataFrame(rows, columns=["text", "type", "danh_gia", "loai_dung"])


def test_apply_judgements():
    df = frame([("a", "undo", "đúng", ""), ("b", "undo", "sai loại", "rerank"), ("c", "undo", "sai loại", "nope"),
                ("d", "undo", "không tự nhiên", ""), ("e", "undo", "hai yêu cầu", ""), ("f", "undo", "", ""),
                ("g", "undo", "không chắc", "")])
    out, stats = apply_judgements(df)
    assert list(out["text"]) == ["a", "b", "f", "g"]                       # unnatural, two requests, bad relabel dropped
    assert list(out["type"]) == ["undo", "rerank", "undo", "undo"]         # relabelled to the reviewer's type
    assert list(out["reviewed"]) == [True, True, False, False]
    assert stats == {"right": 1, "wrong_type": 2, "unnatural": 1, "two_requests": 1, "unsure": 1, "invalid": 0,
                     "wrong_type_without_valid_loai_dung": 1}


def test_reviews_carry_over_to_training_data():
    generated = pd.DataFrame([("x", "undo", "qwen", "m"), ("y", "undo", "qwen", "m"), ("z", "undo", "aya", "m")],
                             columns=["text", "type", "family", "model"])
    reviews = pd.DataFrame([("x", "undo", "qwen", "sai loại", "rerank"), ("y", "undo", "qwen", "không tự nhiên", ""),
                            ("w", "undo", "aya", "đúng", "")], columns=["text", "type", "family", "danh_gia", "loai_dung"])
    out, stats = apply_reviews(generated, reviews)
    assert list(zip(out["text"], out["type"])) == [("x", "rerank"), ("z", "undo")]
    assert list(out.columns) == ["text", "type", "family", "model"]
    assert review_rates(reviews) == {"aya": {"right": 1.0, "n": 1}, "qwen": {"wrong_type": 0.5, "unnatural": 0.5, "n": 2}}


def test_people_come_before_the_agent_and_agent_unsure_is_dropped():
    generated = pd.DataFrame([(t, "undo", "qwen", "m") for t in "pqrs"], columns=["text", "type", "family", "model"])
    people = pd.DataFrame([("p", "undo", "qwen", "đúng", ""), ("r", "undo", "qwen", "không chắc", "")],
                          columns=["text", "type", "family", "danh_gia", "loai_dung"])
    agent = pd.DataFrame([("p", "undo", "qwen", "không tự nhiên", "", "agent"),
                          ("q", "undo", "qwen", "sai loại", "restore", "agent"),
                          ("r", "undo", "qwen", "không tự nhiên", "", "agent"),
                          ("s", "undo", "qwen", "không chắc", "", "agent")],
                         columns=["text", "type", "family", "danh_gia", "loai_dung", "nguoi_cham"])
    out, stats = apply_reviews(generated, people, agent)
    # p: the person's "right" wins over the LLM reviewer; q: relabelled by the LLM reviewer; r: a person's "unsure" is kept;
    # s: the LLM reviewer's own "unsure" is not trained on.
    assert list(zip(out["text"], out["type"])) == [("p", "undo"), ("q", "restore"), ("r", "undo")]
    assert stats["judged_by_people"] == 2 and stats["judged_by_agent"] == 2


def test_agent_review_files_cover_the_generated_messages():
    from pipelines.chat_model.train import clean, load_agent_reviews, load_generated
    agent = load_agent_reviews()
    if agent.empty:
        pytest.skip("no LLM review yet")
    generated, _ = clean(load_generated())
    train = generated[generated["family"].isin(set(agent["family"]))]
    assert set(train["text"]) <= set(agent["text"])                        # every training message was judged
    assert agent["danh_gia"].map(judgement).isin(["right", "wrong_type", "unnatural", "two_requests", "unsure"]).all()


def test_check_file_has_the_judgement_columns():
    checks = load_checks()
    assert {"danh_gia", "loai_dung", "ghi_chu", "reviewed"} <= set(checks.columns)
    assert len(checks) == 190 and "text" in checks.columns               # the UTF-8 marker is not part of a name


def test_part4_human_holdout_loader_keeps_reviewed_rows_and_marks_multi_requests(tmp_path):
    path = tmp_path / "part4_human.csv"
    pd.DataFrame([
        ("a1", "học phí NV3 bao nhiêu", "ask_tuition", '["ask_tuition"]', "{}", "no", "w1", "r1", "reviewed", ""),
        ("a2", "toán 8 rồi học phí NV3", "ask_tuition", '["change_score", "ask_tuition"]', "{}", "no", "w2", "r1", "reviewed", ""),
        ("a3", "dự báo điểm chuẩn", "out_forecast", '["out_forecast"]', "{}", "no", "w1", "r1", "draft", ""),
    ], columns=["id", "text", "type", "expected_requests", "expected_values", "needs_clarification", "writer",
                "reviewer", "status", "note"]).to_csv(path, index=False, encoding="utf-8-sig")
    loaded = load_human_checks(path)
    assert list(loaded["id"]) == ["a1", "a2"] and list(loaded["single_request"]) == [True, False]
    assert load_human_checks(tmp_path / "missing.csv").empty


def test_part4_human_holdout_loader_rejects_unknown_labels(tmp_path):
    path = tmp_path / "part4_human.csv"
    pd.DataFrame([
        ("a1", "x", "not_a_type", '["not_a_type"]', "{}", "no", "w1", "r1", "reviewed", ""),
    ], columns=["id", "text", "type", "expected_requests", "expected_values", "needs_clarification", "writer",
                "reviewer", "status", "note"]).to_csv(path, index=False, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="unknown types"):
        load_human_checks(path)
