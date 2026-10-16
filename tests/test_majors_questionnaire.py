"""The questionnaire (config/questionnaire.yaml) and the student-generation notebook builder."""

import csv
import glob
import json
import os
import random

import pandas as pd
import pytest

from pipelines.facts.build import load_config
from uniadvisor.paths import ROOT
from uniadvisor.majors.questions import Questionnaire, Question, Option, check, load_questionnaire

ONET = ROOT / "pipelines" / "data" / "inputs" / "onet_31_0"


def onet_names():
    with (ONET / "Content_Model_Reference.txt").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    with (ONET / "Knowledge.txt").open(encoding="utf-8") as f:
        knowledge = {r["Element Name"] for r in csv.DictReader(f, delimiter="\t")}
    context ={r["Element ID"] for r in rows if r["Element ID"].startswith("4.C.")}
    context |= {f"{e}:{c}" for e, c in load_config()["work_context"]["category_shares"].items()}
    with (ROOT / "pipelines" / "data" / "inputs" / "unipilot" / "subject.csv").open(encoding="utf-8-sig") as f:
        subjects = {r["code"] for r in csv.DictReader(f)}
    return knowledge, context, subjects


def test_questionnaire_points_to_real_data():
    qn = load_questionnaire()
    assert [q.id for q in qn.questions] == [f"q{i}" for i in range(1, 13)]
    assert check(qn, *onet_names()) == []
    assert qn.get("q2").negative and qn.get("q2").not_in == "q1" and qn.get("q9").kind == "single"
    assert qn.get("q12").by_label()["Tiếp xúc với người bệnh"].work_context == "4.C.2.c.1.b"
    assert qn.get("q12").by_label()["Làm ca đêm"].learned_only
    assert set(qn.exclude_groups) == {"78601", "78602"}


def test_check_catches_combined_and_unknown_options():
    bad = Questionnaire((Question("q1", "x", "multi", (
        Option("a", "Đọc sách và nghe nhạc"), Option("b", "Đồ vật (máy móc)", knowledge="Nope"),
        Option("c", "Ngồi", work_context="9.Z"), Option("c", "Giáo dục kinh tế và pháp luật", subject="GDKTPL"))),),
        {}, "", "")
    problems = check(bad, {"Mathematics"}, {"4.C.2.d.1.a"}, {"GDKTPL"})
    assert any("not one thing" in p and "Đọc sách" in p for p in problems)
    assert any("Nope" in p for p in problems) and any("9.Z" in p for p in problems)
    assert any("duplicate option codes" in p for p in problems)
    assert not any("Giáo dục kinh tế" in p for p in problems)                  # an official subject name


def test_notebook_builder(fake_db_path, monkeypatch, tmp_path):
    from uniadvisor.ui.service import ENV_DB
    from pipelines.majors_model import make_notebook
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    nb = make_notebook.build()
    sources = ["".join(c["source"]) for c in nb["cells"]]
    text = "\n".join(sources)
    for cited in ("Sahu et al. 2022", "Yu et al. 2023", "Chan et al. 2024", "Long et al. 2024", "Holland 1997",
                  "Prediger 1982", "Lewis and Rivkin 1999"):
        assert cited in text
    for cell, source in zip(nb["cells"], sources):
        if cell["cell_type"] == "code":
            compile("\n".join(l for l in source.splitlines() if not l.startswith("!")), "cell", "exec")
    ns = {}
    exec(sources[5], ns)
    assert ns["GROUPS"] and all(g["code"] not in ("78601", "78602") for g in ns["GROUPS"])
    assert {"code", "name", "nganh"} == set(ns["GROUPS"][0])
    assert len(ns["QUESTIONS"]) == 12 and ns["SUBJECTS"][0] == "Toán"
    exec("SEED = 1\n" + sources[7].split("def load(")[0], ns)
    prompt, attrs = ns["build_prompt"](ns["GROUPS"][0], random.Random(1))
    assert ns["GROUPS"][0]["name"] in prompt and "Đối mặt với người nóng giận" in prompt and "persona" in attrs
    assert '"Toán": 8.0' not in prompt                          # the trial's writer copied this example score
    assert "TO=Toán" in prompt and "dùng các mã của q1" in prompt and attrs["format"] == "codes"   # codes, q2 = q1
    other = ns["build_prompt"](ns["GROUPS"][1], random.Random(2))[0]
    assert prompt.split("HỌC SINH CẦN TƯỞNG TƯỢNG")[0] == other.split("HỌC SINH CẦN TƯỞNG TƯỢNG")[0]   # shared prefix
    counts = attrs["counts"]
    assert counts["q1"] is not None and counts["q9"] in (1, None)
    for q in ns["QUESTIONS"]:                                   # concrete counts within the question's limits
        k = counts[q["id"]]
        assert k is None or 0 <= k <= (q["max"] or len(q["options"]))
        assert (f"{q['id']}: chọn đúng {k} mã" in prompt) or k in (None, 0, 1)
    plans = [ns["build_prompt"](ns["GROUPS"][0], random.Random(s))[1] for s in range(200)]
    assert any(None in p["counts"].values() for p in plans) and any(
        None not in p["counts"].values() for p in plans)                      # some skip, some answer everything
    empty = next(s for s in range(200) if ns["build_prompt"](ns["GROUPS"][0], random.Random(s))[1]["free_text"]
                 == "để trống")
    assert 'ke_them: "" (chuỗi rỗng' in ns["build_prompt"](ns["GROUPS"][0], random.Random(empty))[0]
    # the check of one student against its plan (the trial's first student, simplified)
    plan = {"counts": {**{q["id"]: 1 for q in ns["QUESTIONS"]}, "q6": 4, "q2": None}, "n_scores": 5}
    answers = {"q1": ["Toán"], "q2": [], "q4": ["Tranh luận"], "q6": ["Kinh tế"] * 7, "q9": "Cùng một nhóm",
               "diem": {"Toán": 8.0}}
    f = ns["follows"](answers, plan)
    assert "q6" in f["count"] and "q4:Tranh luận" in f["foreign"] and f["skip"] == [] and f["scores"] == 1
    f = ns["follows"]({"q1": ["to"], "q4": ["code"], "q9": "team"}, plan)       # codes, any case
    assert f["foreign"] == []
    assert ns["summary"]([{"answers": json.dumps(answers), "attributes": json.dumps(plan)}]).startswith("1 parsed")
    assert ns["parse"]('ok {"q1": ["Toán"], "q9": null} ok') == {"q1": ["Toán"], "q9": None}
    assert ns["parse"]("{bad") is None and ns["parse"]("[1, 2]") is None
    assert "def load(" in sources[7] and "def chat_text(" in sources[7]          # the chat notebook's model code
    assert "MAX_HOURS" in sources[1] and "time.time() > deadline" in sources[7]   # stops before Kaggle's limit
    compile(ns["WORKER"], "worker", "exec")
    assert 'if __name__ == "__main__":\n    main()' in ns["WORKER"]          # safe when vLLM spawns processes
    assert '"gemma": {"dtype": "float32", "quantization": "bitsandbytes"}' in sources[1]
    assert "vllm-bnb-plugin" in "".join(sources) and '"max_num_batched_tokens": 8192' in sources[1]
    exec("import glob, os\nimport pandas as pd\n" + "def previous(" + sources[7].split("def previous(")[1]
         .split("def run_family(")[0], ns)
    ns["REQUIRE_PREVIOUS"] = False
    assert ns["previous"]("nobody") == []                                       # resume: nothing attached
    attached = tmp_path / "input"
    attached.mkdir()
    one = pd.DataFrame([{"student_id": "gemma-1-0", "family": "gemma", "answers": "{}", "raw": "x"}])
    one.to_csv(attached / "student_generated_gemma.csv", index=False)
    pd.concat([one, one.assign(student_id="gemma-9-9")]).to_csv(attached / "student_review_sample_gemma.csv",
                                                                index=False)
    ns["glob"] = type("G", (), {"glob": staticmethod(lambda *a, **k: sorted(str(p) for p in attached.iterdir()))})
    assert [r["student_id"] for r in ns["previous"]("gemma")] == ["gemma-1-0"]  # review samples are not more students
    ns["glob"] = glob
    ns["REQUIRE_PREVIOUS"] = True                                               # a top-up run stops before the model
    with pytest.raises(SystemExit, match="No earlier nobody file"):
        ns["previous"]("nobody")
    topup = make_notebook.build(topup="gemma")
    config = "".join(topup["cells"][2]["source"])
    assert 'RUN_FAMILIES = ["gemma"]' in config and "REQUIRE_PREVIOUS = True" in config and '"gemma": 20' in config
    aya = make_notebook.build(topup="aya")
    config = "".join(aya["cells"][2]["source"])
    assert 'RUN_FAMILIES = ["aya"]' in config and "MAX_HOURS = 4.6 " in config and '"aya": 40' in config
    assert "2,008" in "".join(aya["cells"][0]["source"])
    compile(config, "config", "exec")


def test_notebook_engines_fall_through(fake_db_path, monkeypatch):
    """vLLM writes part of the students and fails: the transformers engine writes the rest; each row names its engine."""
    from uniadvisor.ui.service import ENV_DB
    from pipelines.majors_model import make_notebook
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    sources = ["".join(c["source"]) for c in make_notebook.build()["cells"]]
    ns = {"pd": pd, "os": os}
    exec(sources[1], ns)
    exec(sources[5], ns)
    exec(sources[7].replace("results = {f: run_family(f) for f in RUN_FAMILIES}", ""), ns)
    earlier = [{"student_id": "gemma-x-0"}]                                   # a trial leaves the attached file alone
    ns.update(TRIAL=True, VLLM_OK=True, previous=lambda family: earlier,
              save=lambda rows, family, final=False: pd.DataFrame(rows))
    answer = '{"q1": ["TO"], "q9": "team"}'

    def fake_vllm(family, todo, deadline):
        return {j[0]: answer for j in todo[:2]}, 1

    def fake_transformers(family, todo, rows, deadline):
        rows += [ns["row"](sid, group, family, attrs, answer, "transformers") for sid, group, _, attrs in todo]

    ns.update(run_vllm=fake_vllm, run_transformers=fake_transformers)
    df = ns["run_family"]("gemma")
    engines = [json.loads(a)["engine"] for a in df["attributes"]]
    assert len(df) == 6 and engines.count("vllm") == 2 and engines.count("transformers") == 4
    assert (df["answers"] != "").all()
