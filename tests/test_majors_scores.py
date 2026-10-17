"""Major suggester: data scores, behaviour checks, cleaning of generated students (fake database for the scores)."""

import json
import random

import pandas as pd
import pytest

from uniadvisor.ui.catalog import Catalog, search_key
from pipelines.majors_model import checks
from pipelines.majors_model.clean import Cleaner, plan_issues, text_as_asked
from pipelines.majors_model.prepare import prepare, report
from uniadvisor.majors.questions import load_questionnaire
from uniadvisor.majors.score import DataScorer, load_config


@pytest.fixture(scope="module")
def qn():
    return load_questionnaire()


@pytest.fixture
def scorer(fake_db, qn):
    return DataScorer.load(fake_db, Catalog.load(fake_db), qn)


def test_labels_stay_distinct_without_accents(qn):
    for q in qn.questions:                       # cleaning matches labels without accents or case
        keys = [search_key(o.label) for o in q.options]
        assert len(set(keys)) == len(keys), q.id


def test_data_scores_follow_the_facts(scorer):
    assert scorer.codes == ["71402", "72202", "74801", "74802", "77201", "77203"]
    computing = {"q1": ["TO", "TI"], "q6": ["computers"], "q8": ["office"]}
    assert scorer.rank(computing)[0] in ("74801", "74802")
    medicine = {"q1": ["SI"], "q6": ["health"], "q11": "helping"}
    assert scorer.rank(medicine)[0] == "77201"
    # Q12 "Tiếp xúc với người bệnh" counts against medicine (Work Context, against); Q7 against a liked topic.
    s = scorer.scores({"q12": ["sick_people"]})
    assert s[scorer.codes.index("77201")] == min(s)
    assert scorer.scores({"q7": ["computers"]})[scorer.codes.index("74801")] < 0
    # Learned-only options and skipped questions add nothing; the same answers give the same order.
    assert not scorer.scores({"q12": ["night_shift"], "q5": None}).any()
    assert scorer.rank(computing) == scorer.rank(dict(computing))
    # The options that speak for a suggestion are the student's own picks.
    top, why = scorer.suggest(medicine, top=1)[0]
    assert top == "77201" and why and all(k in [("q1", "SI"), ("q6", "health"), ("q11", "helping")] for k in why)


def test_question_weight_and_mean(scorer):
    one = scorer.scores({"q6": ["computers"]})
    assert scorer.scores({"q6": ["computers", "computers"]}) == pytest.approx(one)      # a mean per question
    assert scorer.scores({"q9": "alone"}) == pytest.approx(0.5 * scorer.table["q9"]["alone"])   # weak question


def test_behaviour_checks(scorer, qn):
    rng = random.Random(3)
    for _ in range(100):
        a = checks.random_answers(qn, rng)
        assert a["q1"]                                                   # q1 is never skipped
        for q in qn.questions:
            v = a[q.id]
            if q.kind == "multi" and v is not None:
                assert len(v) <= (q.max or 99) and len(set(v)) == len(v)
                if q.not_in and a[q.not_in]:
                    assert not set(v) & set(a[q.not_in])
    rank, answers = checks.best_rank(scorer, "77201")
    assert rank <= 5 and answers
    case = checks.Case("bác sĩ", checks.from_labels(qn, {"q6": ["Sức khỏe"], "q11": "Giúp đỡ người khác"}),
                       ("77201",))
    cfg = load_config()
    cfg["checks"]["random_sets"] = 200
    result = checks.run(scorer, [case], cfg)
    assert result["deterministic"] and result["cases"][0][2]
    text = checks.report(result, lambda c: c)
    assert "Hand-written cases: 1/1" in text


def test_hand_written_cases_parse(qn):
    cases = checks.load_cases(qn)
    assert len(cases) >= 25 and all(c.expect and c.answers for c in cases)


def test_cleaner_repairs_trial_answers(qn):
    c = Cleaner(qn, load_config()["cleaning"]["aliases"])
    out = c.clean({
        "q1": "Văn học",                                         # a string, and a subject name students use
        "q2": ["Ngữ văn", "Công nghệ công nghiệp"],              # Ngữ văn was liked in q1 (not_in)
        "q3": ["Con người", "Số liệu", "Ý tưởng"],               # max 2
        "q4": ["Viết code", "Tranh luận"],                       # Tranh luận belongs to q5
        "q5": "Giảng bài cho bạn|Nghe bạn bè tâm sự",            # joined with '|'
        "q6": ["Lịch史", "Địa lí", "Kinh tê"],                    # foreign characters; other spelling; typo
        "q7": "",                                                # none
        "q8": None,                                              # skipped
        "q9": ["Một mình", "Cùng một nhóm"],                     # a list for a single question
        "q11": "Hiểu vì sao mọithing xảy ra",                    # near miss
        "diem": {"Toán": 8.75, "Vật lý": "8,5", "Tiếng Anh": 11, "Lịch史": 7},
        "ke_them": "  Em thích máy tính. ",
    })
    a = out.answers
    assert a["q1"] == ["VA"] and a["q2"] == ["CNCN"] and len(a["q3"]) == 2
    assert a["q4"] == ["code"] and a["q5"] == ["tutoring", "listening"]
    assert a["q6"] == ["history", "geography", "economics"] and a["q7"] == [] and a["q8"] is None   # 史 read "sử"
    assert a["q9"] == "alone" and a["q11"] == "understanding" and a["q10"] is None
    assert out.scores == {"TO": 8.75, "LI": 8.5, "SU": 7.0} and out.text == "Em thích máy tính."
    kinds = {i.split(":")[0] for i in out.issues}
    assert {"alias", "not_in", "too_many", "foreign", "joined", "fuzzy", "scores", "han"} <= kinds
    assert out.answered == 9
    assert plan_issues(out, {"q3": 1, "q8": None, "q10": None, "q4": 1}) == ["plan_count:q3"]
    assert plan_issues(out, {"q4": None}) == ["plan_skip:q4"]



def test_cleaner_reads_option_codes(qn):
    out = Cleaner(qn).clean({"q1": ["to", "LI"], "q4": ["code", "experimnt"], "q9": "team",
                             "diem": {"TO": 8.5, "li": "7"}})
    assert out.answers["q1"] == ["TO", "LI"] and out.answers["q4"] == ["code", "experiment"]
    assert out.answers["q9"] == "team" and out.scores == {"TO": 8.5, "LI": 7.0}
    assert [i for i in out.issues if not i.startswith("code_fuzzy")] == []             # codes are clean answers
    assert "code_fuzzy:q4:experimnt" in out.issues


def test_cleaner_moves_options_between_halves_and_reads_null_words(qn):
    c = Cleaner(qn, siblings=load_config()["cleaning"]["siblings"])
    out = c.clean({"q4": ["code", "debating", "Tranh luận"], "q5": ["tutoring", "Vẽ"], "q3": "null", "q8": "[]",
                   "q12": ["null"], "diem": {"TO": 8.0, "LI": None}})
    a = out.answers
    assert a["q4"] == ["code", "drawing"] and a["q5"] == ["tutoring", "debating"]   # each option in its own half
    assert a["q3"] is None and a["q8"] == [] and a["q12"] == []
    assert out.scores == {"TO": 8.0} and not [i for i in out.issues if i.startswith(("scores", "foreign"))]
    assert {i for i in out.issues if i.startswith("moved")} == {
        "moved:q4:debating", "moved:q4:Tranh luận", "moved:q5:Vẽ"}
    skipped = c.clean({"q4": ["listening"], "q5": None})                            # a moved option answers q5
    assert skipped.answers["q4"] == [] and skipped.answers["q5"] == ["listening"]
    assert Cleaner(qn).clean({"q4": ["listening"]}).answers["q4"] == []             # without siblings: dropped
    q5 = [o.code for o in qn.get("q5").options]
    capped = c.clean({"q5": q5[:8]})                                                # every multi question has a cap
    assert capped.answers["q5"] == q5[:4] and "too_many:q5" in capped.issues         # (Q4, Q5 and Q12 hold four)
    assert c.too_many(c.clean({"q4": [o.code for o in qn.get("q4").options], "q5": q5}), 0.5) == []   # nothing is uncapped


def test_text_as_asked(qn):
    c = Cleaner(qn)
    out = c.clean({"ke_them": "Em thích Địa lí và đi phượt"})
    text_as_asked(out, {"free_text": "hai ba câu", "free_text_style": "không dấu"})
    assert out.text == "Em thich Dia li va di phuot" and "text:unaccented" in out.issues
    out = c.clean({"ke_them": "Em thích vẽ"})
    text_as_asked(out, {"free_text": "để trống", "free_text_style": "không dấu"})
    assert out.text == "" and out.issues == ["text:blanked"]
    out = c.clean({"ke_them": "Em thích vẽ"})
    text_as_asked(out, {})                                                          # first runs' rows without the plan
    assert out.text == "Em thích vẽ" and out.issues == []

def test_prepare_drops_and_reports(scorer, qn):
    cfg = load_config()
    cfg["checks"]["own_group_top"] = 2
    cfg["checks"]["group_quantile"] = 0.0          # only the global rule here
    cleaner = Cleaner(qn, cfg["cleaning"]["aliases"])
    medicine = {"q1": ["Sinh học"], "q3": ["Con người"], "q5": ["Chăm sóc người ốm"], "q6": ["Sức khỏe"],
                "q9": "Cùng một nhóm", "q11": "Giúp đỡ người khác"}
    rows = [("s1", "77201", medicine), ("s2", "77201", medicine),                    # the second is a duplicate
            ("s3", "74801", {**medicine, "q10": "Tự nghĩ ra cách làm"}),            # suits medicine, not computing
            ("s4", "77201", {"q1": ["Sinh học"]}), ("s5", "77201", None)]           # too few answers; not parsed
    raw = pd.DataFrame([{"student_id": i, "family": "qwen", "target_group": g, "attributes": "{}",
                         "answers": json.dumps(a, ensure_ascii=False) if a else ""} for i, g, a in rows])
    df = prepare(raw, cleaner, scorer, cfg)
    assert dict(zip(df["student_id"], df["dropped"])) == {
        "s1": "", "s2": "duplicate", "s3": "inconsistent", "s4": "too_few_answers", "s5": "not_parsed"}
    text = report(df, scorer, lambda c: c)
    assert "| qwen | 5 | 1 |" in text


def test_prepare_drops_q12_glitch_and_flags_chinese(scorer, qn):
    cfg = load_config()
    cleaner = Cleaner(qn, cfg["cleaning"]["aliases"])
    medicine = {"q1": ["Sinh học"], "q3": ["Con người"], "q5": ["Chăm sóc người ốm"], "q6": ["Sức khỏe"],
                "q9": "Cùng một nhóm", "q11": "Giúp đỡ người khác"}
    q12 = [o.label for o in qn.get("q12").options]
    rows = [("s1", {**medicine, "q12": q12[:3]}), ("s2", {**medicine, "q12": q12[:7], "q8": ["Bệnh viện"]}),
            ("s3", {**medicine, "q12": q12[:8], "q8": ["Trường học"]}),
            ("s4", {**medicine, "q8": ["Văn phòng"], "ke_them": "Em thích chăm sóc动植物，希望"})]
    raw = pd.DataFrame([{"student_id": i, "family": "qwen", "target_group": "77201", "attributes": "{}",
                         "answers": json.dumps(a, ensure_ascii=False)} for i, a in rows])
    df = prepare(raw, cleaner, scorer, cfg).set_index("student_id")
    assert df.loc["s3", "dropped"] == "" and "too_many:q12" in df.loc["s3", "issues"]   # 8 of 15: the first four stay
    assert df.loc["s2", "dropped"] == "" and "too_many:q12" in df.loc["s2", "issues"]
    assert "too_many:q12" not in df.loc["s1", "issues"]                    # 3 of 15 is within the cap
    assert "text:chinese:5" in df.loc["s4", "issues"] and "text:chinese" not in df.loc["s1", "issues"]


def test_consistency_filter_is_relative_to_the_group(scorer, qn):
    cfg = load_config()
    cfg["checks"]["own_group_top"] = 1
    cleaner = Cleaner(qn, cfg["cleaning"]["aliases"])
    base = {"q3": ["Con người"], "q5": ["Chăm sóc người ốm"], "q9": "Cùng một nhóm", "q11": "Giúp đỡ người khác",
            "q10": "Làm theo quy trình rõ ràng"}
    subjects = [["Sinh học"], ["Hóa học"], ["Toán"], ["Ngữ văn"], ["Tiếng Anh"], ["Vật lí"]]
    rows = [{"student_id": f"s{i}", "family": "qwen", "target_group": "74801", "attributes": "{}",
             "answers": json.dumps({**base, "q1": s}, ensure_ascii=False)} for i, s in enumerate(subjects)]
    df = prepare(pd.DataFrame(rows), cleaner, scorer, cfg)
    ranks = pd.to_numeric(df["own_rank"])
    dropped = df["dropped"] == "inconsistent"
    assert dropped.any() and not dropped.all()
    assert ranks[dropped].min() >= ranks[~dropped].max()                    # only the group's worst ranks
