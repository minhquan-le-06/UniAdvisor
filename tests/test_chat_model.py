"""The classifier's training pipeline (on a tiny synthetic set), the runtime model loader, the check set, and the
Kaggle notebook builder."""

import json

import joblib
import pandas as pd
import pytest

from uniadvisor.chat.classify import ModelClassifier, RuleClassifier, RulesFirst, load_classifier
from pipelines.chat_model.train import _Wrapped, clean, evaluate, load_checks, load_config, make_pipeline, relabel_filter
from uniadvisor.chat.types import ALL_TYPES, LATE_TYPES

TOY = {
    "undo": ["hoàn tác", "hoan tac giup em", "quay lại như cũ", "undo đi", "huỷ thay đổi vừa rồi", "lui lại một bước"],
    "rerank": ["đổi thứ tự hai lựa chọn", "doi thu tu 2 lua chon", "đảo hai lựa chọn", "lựa chọn 2 lên trước",
               "hoán đổi lựa chọn", "ưu tiên lựa chọn 2"],
    "other": ["chào bạn", "hôm nay trời đẹp", "cảm ơn nhiều", "bạn tên gì", "em buồn quá", "ok nhé"],
}


def toy_frame():
    rows = [(t, k, "qwen", "m") for k, texts in TOY.items() for t in texts]
    return pd.DataFrame(rows, columns=["text", "type", "family", "model"])


def test_clean_drops_bad_rows():
    df = toy_frame()
    extra = pd.DataFrame([("Hoàn tác", "undo", "qwen", "m"), ("x", "undo", "qwen", "m"),
                          ("toán 8", "not_a_type", "qwen", "m"), ("a" * 400, "undo", "qwen", "m")],
                         columns=df.columns)
    cleaned, stats = clean(pd.concat([df, extra], ignore_index=True))
    assert len(cleaned) == len(df)
    assert stats == {"rows": len(df) + 4, "unknown_type": 1, "empty_or_long": 2, "duplicates": 1}


def test_pipeline_learns_and_filter_keeps_consistent_rows():
    df = toy_frame()
    kept, dropped = relabel_filter(df, 0.8, seed=1)
    assert len(kept) + len(dropped) == len(df)
    model = _Wrapped(make_pipeline(1).fit(df["text"].tolist(), df["type"].tolist()), threshold=0.0)
    result = evaluate(model, df)
    assert result["n"] == len(df) and result["accuracy"] >= 0.9
    assert evaluate(model, df.iloc[0:0]) == {"n": 0}


def test_model_classifier_loads_a_saved_bundle(tmp_path, fake_db_path):
    from uniadvisor.ui.service import AppData
    idx = AppData.load(fake_db_path).indexes
    names = (idx.schools, idx.nganh, {"TO", "VA"})
    df = toy_frame()
    pipeline = make_pipeline(1).fit(df["text"].tolist(), df["type"].tolist())
    joblib.dump({"pipeline": pipeline, "threshold": 0.0, "meta": {}}, tmp_path / "model.joblib")
    loaded = load_classifier(*names, model_dir=tmp_path)
    # The toy model was not trained on the types added later: the rules decide those, the model the rest.
    assert isinstance(loaded, RulesFirst) and isinstance(loaded.model, ModelClassifier)
    assert loaded.types == set(LATE_TYPES)
    assert loaded.classify("hoàn tác")[0] == "undo"
    assert loaded.classify("trường em thích nhất là FHN")[0] == "favorite_school"
    joblib.dump({"pipeline": pipeline, "threshold": 0.99, "meta": {}}, tmp_path / "model.joblib")
    assert load_classifier(*names, model_dir=tmp_path).classify("xyz")[0] == "other"   # unsure -> other
    assert isinstance(load_classifier(*names, model_dir=tmp_path / "none"), RuleClassifier)
    full = pd.concat([df, pd.DataFrame([(f"{t} {i}", t, "qwen", "m") for t in LATE_TYPES for i in range(3)],
                                       columns=df.columns)], ignore_index=True)
    trained = make_pipeline(1).fit(full["text"].tolist(), full["type"].tolist())
    joblib.dump({"pipeline": trained, "threshold": 0.0, "meta": {}}, tmp_path / "model.joblib")
    assert isinstance(load_classifier(*names, model_dir=tmp_path), ModelClassifier)   # retrained: model only


def test_check_set_and_config():
    checks = load_checks()
    assert set(checks["type"]) == set(ALL_TYPES)
    assert checks["type"].value_counts().min() >= 10
    assert set(checks["status"]) <= {"draft", "reviewed"}
    assert checks["text"].str.len().max() <= 300 and not checks["text"].duplicated().any()
    cfg = load_config()
    assert cfg["test_family"] not in cfg["train_families"]


def test_rules_on_the_check_set(fake_db_path):
    """The rule baseline on the LLM-drafted checks, with the fake database's names (school names differ from the
    real ones, so this only guards against large regressions; the real score is in models/message_classifier)."""
    from uniadvisor.ui.service import AppData
    d = AppData.load(fake_db_path)
    rules = RuleClassifier(d.indexes.schools, d.indexes.nganh, set(d.subjects))
    checks = load_checks()
    no_names = checks[checks["type"].isin(["change_score", "change_priority", "change_budget", "change_near_home",
                                           "rerank", "undo", "ask_level", "other"])]
    assert evaluate(rules, no_names)["accuracy"] >= 0.85


def test_notebook_builder(fake_db_path, monkeypatch):
    from uniadvisor.ui.service import ENV_DB
    from pipelines.chat_model import make_notebook
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    nb = make_notebook.build()
    assert nb["nbformat"] == 4
    sources = ["".join(c["source"]) for c in nb["cells"]]
    text = "\n".join(sources)
    for cited in ("Sahu et al. 2022", "Yu et al. 2023", "Long et al. 2024"):
        assert cited in text
    data = next(s for s in sources if s.startswith("SLOTS = "))
    slots = json.loads(data.split("\n\nTYPES = ")[0].removeprefix("SLOTS = "))
    assert "Giả Hà Nội" in slots["schools"] and "FHN" in slots["schools"]
    assert "Toán" in slots["subjects"]
    types = json.loads(data.split("\n\nTYPES = ")[1].split("\n\nSEEDS = ")[0])
    assert set(types) == set(ALL_TYPES)
    for cell in nb["cells"]:                         # every code cell is valid Python (shell lines aside)
        if cell["cell_type"] == "code":
            code = "".join(cell["source"])
            compile("\n".join(l for l in code.splitlines() if not l.startswith("!")), "cell", "exec")


@pytest.mark.parametrize("bad", ["{", "[1, 2"])
def test_notebook_parser_ignores_bad_output(bad, fake_db_path, monkeypatch):
    from uniadvisor.ui.service import ENV_DB
    from pipelines.chat_model import make_notebook
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    source = "".join(make_notebook.build()["cells"][7]["source"])
    ns = {}
    exec("import json, random, re\n" + source.split("def load(")[0].replace("random.seed(SEED)", ""), ns)
    assert ns["parse"](bad) == []
    assert ns["parse"]('ok ["toán 8", 5, " "] ok') == ["toán 8"]
