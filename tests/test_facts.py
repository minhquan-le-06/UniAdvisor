"""Step 6 facts (src/uniadvisor/facts/build.py) on a tiny invented O*NET / CIP fixture."""

import csv
import math
import sqlite3

import pytest

from uniadvisor import db
from uniadvisor.data.build import Review
from uniadvisor.facts.build import build_facts, load_config, spread, standardise

OCC = [("15-1252.00", "Software Developers"), ("15-1211.00", "Computer Systems Analysts"),
       ("13-2011.00", "Accountants and Auditors"), ("11-9199.00", "Managers, All Other"),
       ("25-1011.00", "Business Teachers, Postsecondary")]
# CIP -> occupations. "Managers, All Other" is listed under every CIP: a catch-all.
CROSS = {"11.0701": ["15-1252.00", "15-1211.00", "11-9199.00"], "11.0103": ["15-1252.00", "15-1211.00", "11-9199.00"],
         "52.0301": ["13-2011.00", "11-9199.00", "25-1011.00"], "52.0201": ["11-9199.00", "25-1011.00"]}
KNOW = {"15-1252.00": {"Computers": 4.8, "Mathematics": 3.9, "Economics": 1.5},
        "15-1211.00": {"Computers": 4.5, "Mathematics": 3.5, "Economics": 2.0},
        "13-2011.00": {"Computers": 3.0, "Mathematics": 4.0, "Economics": 4.5},
        "11-9199.00": {"Computers": 3.0, "Mathematics": 3.0, "Economics": 3.5},
        "25-1011.00": {"Computers": 2.5, "Mathematics": 3.0, "Economics": 4.0}}
RIASEC = ["Realistic", "Investigative", "Artistic", "Social", "Enterprising", "Conventional"]
INTEREST = {"15-1252.00": [2, 6, 3, 1, 2, 4], "15-1211.00": [2, 5, 2, 2, 3, 5], "13-2011.00": [1, 3, 1, 2, 4, 7],
            "11-9199.00": [2, 3, 2, 3, 6, 4], "25-1011.00": [1, 4, 2, 6, 4, 3]}
MAPPING = [("7480101", 1, "11.0701", "exact", "high"), ("7480201", 1, "11.0103", "exact", "high"),
           ("7480201", 2, "11.0701", "close", "high"), ("7340301", 1, "52.0301", "exact", "high"),
           ("7340101", 1, "52.0201", "exact", "high"), ("7340101", 2, "00.0000", "close", "low"),
           ("9999999", 1, "11.0701", "exact", "high")]


def write_inputs(root):
    d = root / "inputs" / "onet_31_0"
    d.mkdir(parents=True)
    tsv = lambda name, header, rows: (d / name).write_text(
        "\t".join(header) + "\n" + "".join("\t".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")
    tsv("Occupation_Data.txt", ["O*NET-SOC Code", "Title", "Description"], [(c, t, "x") for c, t in OCC])
    tsv("Knowledge.txt", ["O*NET-SOC Code", "Element ID", "Element Name", "Scale ID", "Data Value"],
        [(c, f"2.C.{i}", k, s, v if s == "IM" else 9) for c, ks in KNOW.items()
         for i, (k, v) in enumerate(ks.items()) for s in ("IM", "LV")])
    tsv("Career_Interest_Types.txt", ["O*NET-SOC Code", "Element ID", "Element Name", "Scale ID", "Data Value"],
        [(c, f"1.B.1.{i}", r, "OI", v) for c, vs in INTEREST.items() for i, (r, v) in enumerate(zip(RIASEC, vs))]
        + [(c, "1.B.2.a", "First Interest High-Point", "IH", 2) for c in INTEREST])
    wc_header = ["O*NET-SOC Code", "Element ID", "Element Name", "Scale ID", "Category", "Data Value",
                 "Recommend Suppress"]
    tsv("Work_Context.txt", wc_header,
        [(c, "4.C.2.d.1.a", "Spend Time Sitting", "CX", "n/a", v, "N") for c, v in
         [("15-1252.00", 4.6), ("15-1211.00", 4.4), ("13-2011.00", 4.2), ("11-9199.00", 3.0), ("25-1011.00", 3.5)]]
        + [("13-2011.00", "4.C.1.a.2.c", "Public Speaking", "CX", "n/a", 1.0, "Y")]          # suppressed
        + [(c, "4.C.3.d.8", "Duration of Typical Work Week", "CTP", k, p, "N") for c in ("15-1252.00", "13-2011.00")
           for k, p in (("1", 10.0), ("2", 50.0), ("3", 40.0 if c == "15-1252.00" else 60.0))]
        + [("15-1252.00", "4.C.3.d.8", "Duration of Typical Work Week", "CT", "n/a", 2.3, "N")])
    tsv("Work_Context_Categories.txt", ["Element ID", "Element Name", "Scale ID", "Category", "Category Description"],
        [("4.C.3.d.8", "Duration of Typical Work Week", "CTP", "3", "More than 40 hours")])
    tsv("Job_Zones.txt", ["O*NET-SOC Code", "Job Zone"], [(c, 4) for c, _ in OCC])
    tsv("Related_Occupations.txt", ["O*NET-SOC Code", "Related O*NET-SOC Code", "Relatedness Tier", "Index"],
        [("15-1252.00", "15-1211.00", "Primary-Short", 1), ("15-1211.00", "15-1252.00", "Primary-Short", 1),
         ("13-2011.00", "11-9199.00", "Supplemental", 1)])
    c = root / "inputs" / "cip"
    c.mkdir()
    (c / "cip2020_to_onetsoc2019.csv").write_text(
        "cip_code,cip_title,onet_soc_code,onet_soc_title\n"
        + "".join(f"{cip},T{cip},{o},x\n" for cip, occs in CROSS.items() for o in occs), encoding="utf-8")
    cur = root / "curated"
    cur.mkdir()
    (cur / "nganh_cip.csv").write_text(
        "nganh_code,rank,cip_code,match,confidence,retrieved,note,status,origin\n"
        + "".join(f"{n},{r},{c},{m},{conf},yes,,draft,test\n" for n, r, c, m, conf in MAPPING), encoding="utf-8")
    return root / "inputs", cur


@pytest.fixture
def built(tmp_path):
    inputs, curated = write_inputs(tmp_path)
    conn = db.create(tmp_path / "facts.db")
    conn.executemany("INSERT INTO source VALUES (?, ?, 'export', NULL, NULL, NULL)",
                     [(s, s) for s in ("onet_31_0", "cip_crosswalk", "curated", "moet")])
    conn.executemany("INSERT INTO moet_major (code, level, name, parent_code, source_id) VALUES (?,?,?,?, 'moet')",
                     [("748", "linh_vuc", "Máy tính", None), ("74801", "nhom_nganh", "Máy tính", "748"),
                      ("7480101", "nganh", "Khoa học máy tính", "74801"), ("74802", "nhom_nganh", "CNTT", "748"),
                      ("7480201", "nganh", "Công nghệ thông tin", "74802"), ("734", "linh_vuc", "Kinh doanh", None),
                      ("73403", "nhom_nganh", "Kế toán", "734"), ("7340301", "nganh", "Kế toán", "73403"),
                      ("73401", "nhom_nganh", "Kinh doanh", "734"), ("7340101", "nganh", "QTKD", "73401")])
    review = Review()
    cfg = load_config()
    stats = build_facts(conn, inputs, curated, review, cfg)
    conn.commit()
    yield conn, review, stats
    conn.close()


def q(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def test_loads_and_reports_invalid_mapping_rows(built):
    conn, review, stats = built
    # occupations used for profiles: the residual "Managers, All Other" is left out (drop_residual)
    assert stats == {"nganh_mapped": 4, "links": 5, "occupations_used": 4, "close_rows": 2}   # pairs >= min_score
    issues = sorted((r["nganh_code"], r["issue"]) for r in review.rows["nganh_cip_invalid"])
    assert issues == [("7340101", "cip_not_in_crosswalk"), ("9999999", "nganh_not_in_catalog")]
    assert q(conn, "SELECT count(*) FROM occupation_knowledge")[0][0] == 15        # IM scale only
    assert q(conn, "SELECT count(*) FROM occupation_interest")[0][0] == 30         # 6 RIASEC types, no high-points
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_weights_and_idf(built):
    conn, _, _ = built
    for n, w, s in q(conn, "SELECT nganh_code, sum(weight), sum(share) FROM nganh_occupation GROUP BY 1"):
        assert w == pytest.approx(1.0, abs=1e-5) and s == pytest.approx(1.0, abs=1e-5)
    # 7480101: three occupations with equal shares; the catch-all (in all 4 CIPs) gets idf ln(4/4) = 0.
    cs = dict(q(conn, "SELECT occupation_code, weight FROM nganh_occupation WHERE nganh_code = '7480101'"))
    assert cs["11-9199.00"] == 0 and cs["15-1252.00"] == pytest.approx(0.5, abs=1e-5)
    shares = dict(q(conn, "SELECT occupation_code, share FROM nganh_occupation WHERE nganh_code = '7480101'"))
    assert set(round(v, 4) for v in shares.values()) == {0.3333}


def test_display_ranks_hide_catch_alls_and_postsecondary_teachers(built):
    conn, _, _ = built
    rows = q(conn, "SELECT nganh_code, occupation_code, display_rank FROM nganh_occupation WHERE nganh_code IN "
                   "('7340301', '7340101') ORDER BY 1, 2")
    assert rows == [("7340101", "11-9199.00", None), ("7340101", "25-1011.00", None),
                    ("7340301", "11-9199.00", None), ("7340301", "13-2011.00", 1), ("7340301", "25-1011.00", None)]


def test_profiles(built):
    conn, _, _ = built
    k = dict(q(conn, "SELECT element, importance FROM nganh_knowledge WHERE nganh_code = '7480101'"))
    # weights 0.5 / 0.5 / 0 (idf): mean of the two computer occupations
    assert k["Computers"] == pytest.approx(4.65) and k["Economics"] == pytest.approx(1.75)
    r = dict(q(conn, "SELECT riasec, score FROM nganh_interest WHERE nganh_code = '7340301'"))
    # accountants ln4 = 2 ln2, postsecondary teacher ln2 x postsecondary_factor 0.5, residual left out
    assert r["Conventional"] == pytest.approx((7 * 2 + 3 * 0.5) / 2.5, abs=1e-4)
    w = dict(q(conn, "SELECT occupation_code, weight FROM nganh_occupation WHERE nganh_code = '7340301'"))
    assert w["11-9199.00"] == 0 and w["25-1011.00"] == pytest.approx(0.2, abs=1e-5)


def test_work_context(built):
    conn, _, _ = built
    wc = {(n, e): (scale, v) for n, e, scale, v in
          q(conn, "SELECT nganh_code, element_id, scale, value FROM nganh_work_context")}
    assert wc[("7480101", "4.C.2.d.1.a")] == ("CX", pytest.approx(4.5))                 # sitting: 0.5 / 0.5
    assert wc[("7340301", "4.C.2.d.1.a")] == ("CX", pytest.approx((4.2 * 2 + 3.5 * 0.5) / 2.5, abs=1e-4))
    assert wc[("7480101", "4.C.3.d.8:3")] == ("CTP", 40.0)                               # % above 40 hours
    assert ("7340301", "4.C.1.a.2.c") not in wc                                         # suppressed by O*NET
    names = dict(q(conn, "SELECT element_id, element FROM nganh_work_context WHERE nganh_code = '7340301'"))
    assert names["4.C.3.d.8:3"] == "Duration of Typical Work Week: More than 40 hours"
    assert q(conn, "SELECT count(*) FROM occupation_work_context WHERE element_id = '4.C.3.d.8'")[0][0] == 0


def test_closeness(built):
    conn, _, _ = built
    top = q(conn, "SELECT nganh_code, other_code, rank, round(occupation_part, 4) FROM nganh_close "
                  "WHERE rank = 1 ORDER BY 1")
    assert dict((a, b) for a, b, _, _ in top)["7480101"] == "7480201"   # computer science <-> IT
    assert dict((a, b) for a, b, _, _ in top)["7480201"] == "7480101"
    cs_it = q(conn, "SELECT occupation_part, knowledge_part, score FROM nganh_close "
                    "WHERE nganh_code = '7480101' AND other_code = '7480201'")[0]
    assert cs_it[0] == pytest.approx(1.0) and cs_it[2] == pytest.approx(0.5 * cs_it[0] + 0.5 * cs_it[1])
    assert all(rank >= 1 for (rank,) in q(conn, "SELECT rank FROM nganh_close"))


def test_teacher_training_rule():
    from uniadvisor.facts.build import TeacherTraining
    t = TeacherTraining({"subject_groups": {"stem": ["7140209", "7140211"], "arts": ["7140222"],
                                            "languages": ["7140231"]},
                         "subject_nganh": {"7140209": ["7460101"], "7140231": ["7220201"]}})
    assert not t.unrelated("7140209", "7140211")                   # Sư phạm Toán, Sư phạm Vật lý: one group
    assert t.unrelated("7140209", "7140222") and t.unrelated("7140222", "7140209")
    assert t.unrelated("7140222", "7220202") and t.unrelated("7220202", "7140222")   # Mỹ thuật vs Ngôn ngữ Nga
    assert not t.unrelated("7140211", "7460101")                   # Toán học is a subject ngành of the group
    assert not t.unrelated("7140222", "7140101")                   # Giáo dục học: an education ngành
    assert not t.unrelated("7480201", "7220202")                   # neither is Sư phạm
    assert t.is_subject("7140209", "7460101") and not t.is_subject("7460101", "7140209")


def test_close_verdicts_and_occupation_floor(tmp_path):
    """A reviewer's 'wrong' removes a pair and 'weak' ranks it last; pairs sharing no jobs are dropped unless judged
    'ok'."""
    inputs, curated = write_inputs(tmp_path)
    conn = db.create(tmp_path / "facts.db")
    conn.executemany("INSERT INTO source VALUES (?, ?, 'export', NULL, NULL, NULL)",
                     [(s, s) for s in ("onet_31_0", "cip_crosswalk", "curated", "moet")])
    conn.executemany("INSERT INTO moet_major (code, level, name, parent_code, source_id) VALUES (?,?,?,?, 'moet')",
                     [("748", "linh_vuc", "Máy tính", None), ("74801", "nhom_nganh", "Máy tính", "748"),
                      ("7480101", "nganh", "Khoa học máy tính", "74801"), ("7480201", "nganh", "CNTT", "74801"),
                      ("7480202", "nganh", "An toàn thông tin", "74801"), ("734", "linh_vuc", "Kinh doanh", None),
                      ("73403", "nhom_nganh", "Kế toán", "734"), ("7340301", "nganh", "Kế toán", "73403"),
                      ("73401", "nhom_nganh", "Kinh doanh", "734"), ("7340101", "nganh", "QTKD", "73401")])
    with open(curated / "nganh_cip.csv", "a", encoding="utf-8") as fh:
        fh.write("7480202,1,11.0103,exact,high,yes,,draft,test\n")
    (curated / "nganh_close_verdicts.csv").write_text(
        "nganh_code,other_code,verdict,comment\n7480101,7480201,weak,x\n7480101,7480202,wrong,x\n"
        "7340301,7340101,ok,a reviewer accepts it\n", encoding="utf-8")
    cfg = load_config()
    cfg["closeness"]["min_occupation_part"] = 0.99
    review = Review()
    build_facts(conn, inputs, curated, review, cfg)
    close = {(a, b): r for a, b, r in q(conn, "SELECT nganh_code, other_code, rank FROM nganh_close")}
    assert (("7480101", "7480202") not in close) and close[("7480101", "7480201")] == 1    # weak, but the only one
    assert close[("7480201", "7480202")] in (1, 2)                                         # shares every job
    assert close.get(("7340301", "7340101")) == 1                                          # below the floor, but ok
    assert ("7340101", "7340301") not in close                                             # below the floor
    reviewed = {(r["nganh_code"], r["other_code"]) for r in review.rows["nganh_close_review"]}
    assert ("7480101", "7480201") not in reviewed and ("7480201", "7480202") in reviewed  # judged pairs not re-sent
    conn.close()


def test_helpers():
    assert spread({"a": 1.0}, {"a": ["b", "c"]}, 0.5) == {"a": 1.0, "b": 0.25, "c": 0.25}
    z = standardise({"x": {"k": 1.0}, "y": {"k": 3.0}})
    assert z == {"x": {"k": -1.0}, "y": {"k": 1.0}}
    assert standardise({"x": {"k": 2.0}, "y": {"k": 2.0}}) == {"x": {"k": 0.0}, "y": {"k": 0.0}}
    assert math.isclose(sum(v for v in spread({"a": 0.4, "b": 0.6}, {}, 0.5).values()), 1.0)


def test_apply_review_round(tmp_path):
    from uniadvisor.facts.apply_review import apply_round
    cur, rnd = tmp_path / "curated", tmp_path / "round"
    cur.mkdir()
    rnd.mkdir()
    (cur / "nganh_cip.csv").write_text("nganh_code,rank,cip_code,match,confidence,retrieved,note,status,origin\n"
                                       "7480101,1,11.0701,exact,high,yes,,draft,t\n7480201,1,11.0103,exact,high,yes,,draft,t\n"
                                       "7480201,2,11.0701,close,high,yes,,draft,t\n", encoding="utf-8")
    (rnd / "nganh_cip_review_done.csv").write_text("nganh_code,rank,cip_code,verdict,correct_cip,comment\n"
                                                   "7480101,1,11.0701,ok,,\n7480201,2,11.0701,unsure,,why\n",
                                                   encoding="utf-8")
    (rnd / "nganh_close_review_done.csv").write_text(
        "nganh_code,nganh_name,rank,other_code,other_name,score,shared_occupations,shared_knowledge,verdict,comment\n"
        "7480101,KHMT,1,7480201,CNTT,1,1,1,ok,\n", encoding="utf-8")
    (cur / "names_vi.csv").write_text("kind,key,onet_id,english,name_vi,description_vi,status,origin,reviewed_by,note\n"
                                      "riasec,Social,,Social,Xã hội,x,draft,t,,\n"
                                      "knowledge,Biology,2.C.4.b,Biology,Sinh học,,draft,t,,\n", encoding="utf-8")
    (rnd / "knowledge_names_vi_done.csv").write_text("element_id,element,name_vi,verdict,suggested_vi\n"
                                                     "2.C.4.b,Biology,Sinh học,ok,\n", encoding="utf-8")
    (rnd / "riasec_names_vi_done.csv").write_text("riasec,name_vi,verdict,suggested_vi\nSocial,Xã hội,fix,Giúp đỡ\n",
                                                  encoding="utf-8")
    out = apply_round(rnd, "reviewer", "2026-10-07", cur)
    assert out["cip"] == {"links_judged": 2, "not_found": 0}
    m = {(r["nganh_code"], r["cip_code"]): r["status"] for r in csv.DictReader(open(cur / "nganh_cip.csv", encoding="utf-8"))}
    assert m == {("7480101", "11.0701"): "reviewed", ("7480201", "11.0103"): "draft", ("7480201", "11.0701"): "unsure"}
    assert out["close"] == {"pairs_judged": 1, "pairs_total": 1}
    names = list(csv.DictReader(open(cur / "names_vi.csv", encoding="utf-8")))
    assert names[0]["name_vi"] == "Giúp đỡ" and names[0]["status"] == "reviewed" and "was 'Xã hội'" in names[0]["note"]
    assert names[1]["status"] == "reviewed" and names[1]["reviewed_by"] == "reviewer"        # matched by element id


def test_family_members_need_a_title_match_and_named_jobs_come_first():
    import pandas as pd
    from uniadvisor.facts.build import display_ranks, match_residual_families, named_after_field
    titles = {"11-9041.00": "Architectural and Engineering Managers",
              "11-9041.01": "Biofuels/Biodiesel Technology and Product Development Managers",
              "17-2141.00": "Mechanical Engineers", "17-2199.05": "Mechatronics Engineers",
              "17-2199.00": "Engineers, All Other", "51-4041.00": "Machinists"}
    cross = pd.DataFrame([("14.1901", "Mechanical Engineering", o) for o in
                          ("11-9041.00", "11-9041.01", "17-2141.00", "51-4041.00")]
                         + [("14.4201", "Mechatronics, Robotics, and Automation Engineering", o) for o in
                            ("17-2199.00", "17-2199.05")],
                         columns=["cip_code", "cip_title", "onet_soc_code"])
    kept = set(zip(*[match_residual_families(cross, titles)[c] for c in ("cip_code", "onet_soc_code")]))
    assert ("14.1901", "11-9041.01") not in kept and ("14.4201", "17-2199.05") in kept
    assert ("14.1901", "11-9041.00") in kept and ("14.1901", "51-4041.00") in kept
    mapping = pd.DataFrame([{"nganh_code": "7520103", "cip_code": "14.1901", "status": "reviewed"}])
    named = named_after_field(mapping, cross, titles, {"mapping": {"use_status": ["reviewed"]}})
    assert named["7520103"] == {"17-2141.00"}
    share = {"7520103": {"11-9041.00": 1 / 3, "17-2141.00": 1 / 3, "51-4041.00": 1 / 3}}
    weight = {"7520103": {"11-9041.00": 0.2, "17-2141.00": 0.3, "51-4041.00": 0.5}}
    ranks = display_ranks(share, {}, titles, weight, named)["7520103"]
    assert sorted(ranks, key=ranks.get) == ["17-2141.00", "51-4041.00", "11-9041.00"]


def test_hidden_jobs_and_separate_tracks(tmp_path):
    from uniadvisor.facts.build import hide_occupations, separate_tracks
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE moet_major (code TEXT, level TEXT, parent_code TEXT)")
    conn.execute("INSERT INTO moet_major VALUES ('7220201', 'nganh', '72202')")
    (tmp_path / "occupation_hidden.csv").write_text("scope,occupation_code\n72202,43-9081.00\n", encoding="utf-8")
    rank = {"7220201": {"43-9081.00": 1, "27-3091.00": 2}, "7229030": {"43-9081.00": 1}}
    hide_occupations(rank, conn, tmp_path)
    assert rank == {"7220201": {"27-3091.00": 1}, "7229030": {"43-9081.00": 1}}
    assert separate_tracks("7860214", "7580201") and not separate_tracks("7860214", "7860218")
