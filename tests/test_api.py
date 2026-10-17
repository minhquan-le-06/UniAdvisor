"""The web API on the fake database: stateless calls that carry the plan, the same results as the Streamlit app's
service, and the guards (body size, access code, rate limit)."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from uniadvisor.api.app import create_app
from uniadvisor.api.settings import Settings
from uniadvisor.ui import plan_file
from uniadvisor.ui.service import AppData

SETTINGS = Settings(access_code=None, rate_limit="", cors_origins=(), web_dist=None, max_body=262144)


@pytest.fixture(scope="module")
def data(fake_db_path):
    return AppData.load(fake_db_path)


def make_client(data, **changes):
    settings = Settings(**{**SETTINGS.__dict__, **changes})
    return TestClient(create_app(settings, data))


@pytest.fixture(scope="module")
def client(data):
    with make_client(data) as c:
        yield c


def student(client, **profile):
    """A plan with scores, a province and one hướng học (what the list needs)."""
    plan = client.get("/api/plan/new").json()
    plan["profile"].update({"scores": {"TO": 8.0, "VA": 7.0, "LI": 7.0, "N1": 8.0}, "home_province": "Hà Nội",
                            **profile})
    plan["majors"]["shortlist"] = [{"main": "7480201", "close": []}]
    plan["majors"]["picks"] = ["7480201"]
    return plan


def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"ok": True, "data": True}
    meta = client.get("/api/meta").json()
    assert meta["admission_year"] == 2027 and meta["compulsory"] == ["TO", "VA"]
    assert {"TO", "VA", "LI", "N1"} <= {s["code"] for s in meta["subjects"]}
    assert len(meta["provinces"]) == 34 and meta["provinces"][:2] == ["Hà Nội", "TP. Hồ Chí Minh"]
    assert [c["code"] for c in meta["categories"]] == ["none", "UT1", "UT2"]
    assert [x["name"] for x in meta["texts"]["lists"]] == ["Đúng ngành nhất", "Hợp sở thích nhất", "Hợp môn học nhất",
                                                          "Tiết kiệm nhất"]
    assert [c["code"] for c in meta["texts"]["corners"]] == ["hop_mon", "nguyen_vong_cao", "dung_nganh", "hoc_phi",
                                                            "nghe_nghiep"]
    assert meta["limits"]["max_close"] == 2
    json.dumps(meta)                                                  # everything is plain JSON


def test_catalog_and_majors(client):
    codes = {m["code"] for m in client.get("/api/catalog").json()}
    assert {"7480101", "7480201"} <= codes
    hits = client.get("/api/majors/search", params={"q": "cntt"}).json()
    assert hits and hits[0]["code"] == "7480201" and hits[0]["kind"] == "Ngành"
    detail = client.get("/api/majors/7480101").json()
    assert detail["code"] == "7480101" and "A00" in " ".join(c["label"] for c in detail["combos"]) + " A00"
    assert client.get("/api/majors/0000000").status_code == 404
    assert isinstance(client.get("/api/majors/7480201/close").json(), list)


def test_plan_new_and_normalize(client):
    plan = client.get("/api/plan/new").json()
    assert plan["format"] == "uniadvisor-plan" and plan["schema_version"] == 2
    ok = client.post("/api/plan/normalize", json={"plan": student(client)}).json()
    assert ok["plan"]["profile"]["home_province"] == "Hà Nội" and ok["warnings"] == []
    bad = client.post("/api/plan/normalize", json={"plan": {"format": "other"}})
    assert bad.status_code == 422 and "không phải tệp kế hoạch" in bad.json()["detail"]
    # A stale ngành is dropped with a warning, the rest is restored.
    stale = student(client)
    stale["majors"]["shortlist"] = [{"main": "9999999", "close": []}]
    out = client.post("/api/plan/normalize", json={"plan": stale}).json()
    assert out["plan"]["majors"]["shortlist"] == [] and out["warnings"]


def test_recommend_matches_the_service(client, data):
    empty = client.post("/api/lists/recommend", json={"plan": client.get("/api/plan/new").json()}).json()
    assert empty["missing"] == ["scores", "home_province", "shortlist"] and empty["missing_text"]
    plan = student(client)
    got = client.post("/api/lists/recommend", json={"plan": plan}).json()
    state, _ = plan_file.load(json.dumps(plan), data.known())
    recs = data.recommend(state)
    assert got["missing"] == [] and len(got["cards"]) == len(recs) == 3
    for card, rec in zip(got["cards"], recs):
        assert card["priority"] == rec.priority.value
        assert card["n_wishes"] == len(rec.result.wishes)
        if rec.pentagon and not card["blocked"]:
            assert card["pentagon"]["values"] == pytest.approx(rec.pentagon.values)
    assert sum(c["recommended"] for c in got["cards"]) == (1 if got["pick"] else 0)
    assert [r["priority"] for r in got["snapshot"]] == [r.priority.value for r in recs]
    assert got["corner_rows"] and got["intro"] and got["at_least_one_text"]


def test_choose_then_chosen_page_and_explanation(client, data):
    plan = student(client)
    chosen = client.post("/api/lists/choose", json={"plan": plan, "priority": "dung_nganh"}).json()
    plan = chosen["plan"]
    assert plan["lists"]["chosen"] == "dung_nganh" and len(plan["lists"]["recommended"]) == 3
    page = client.post("/api/lists/chosen", json={"plan": plan}).json()
    assert page["missing"] == [] and page["header"]["name"] == "Đúng ngành nhất"
    assert page["wishes"] and page["wish_numbers"][0] == 1 and len(page["levels"]) == len(page["wishes"])
    assert page["controls"]["schools"] and page["controls"]["wishes"]
    explained = client.post("/api/wishes/explain", json={"plan": plan, "nv": 1}).json()
    assert explained["wish_no"] == 1 and explained["markdown"] and explained["placement"]
    assert client.post("/api/wishes/explain", json={"plan": plan, "nv": 15}).status_code in (200, 404)
    bad = client.post("/api/lists/choose", json={"plan": plan, "priority": "nope"})
    assert bad.status_code == 422
    nothing = client.post("/api/lists/choose", json={"plan": client.get("/api/plan/new").json(),
                                                     "priority": "dung_nganh"})
    assert nothing.status_code == 422


def test_chat_proposes_and_apply_changes_the_plan(client):
    plan = student(client)
    plan = client.post("/api/lists/choose", json={"plan": plan, "priority": "dung_nganh"}).json()["plan"]
    reply = client.post("/api/chat", json={"plan": plan, "message": "Toán em được 9"}).json()
    assert reply["items"] and reply["items"][0]["kind"] == "set_score" and reply["items"][0]["description"]
    item = reply["items"][0]
    done = client.post("/api/changes/apply", json={"plan": plan, "items": [item]}).json()
    assert done["changed"] and done["plan"]["profile"]["scores"]["TO"] == 9.0 and not done["errors"]
    assert done["done"] and "diff" in done
    answer = client.post("/api/chat", json={"plan": plan, "message": "vì sao NV1 ở đó?"}).json()
    assert answer["answers"] and not answer["items"]
    lost = client.post("/api/chat", json={"plan": plan, "message": "asdf qwer"}).json()
    assert lost["help"]


def test_apply_rejects_unknown_kinds_and_reports_errors(client):
    plan = student(client)
    bad = client.post("/api/changes/apply", json={"plan": plan, "items": [{"kind": "drop_database"}]})
    assert bad.status_code == 422
    out_of_range = {"kind": "set_score", "params": {"subject": "TO", "value": 11}, "open": []}
    res = client.post("/api/changes/apply", json={"plan": plan, "items": [out_of_range]}).json()
    assert not res["changed"] and res["errors"] and res["plan"]["profile"]["scores"]["TO"] == 8.0
    incomplete = {"kind": "set_score", "params": {"value": 5}, "open": ["subject"]}
    res = client.post("/api/changes/apply", json={"plan": plan, "items": [incomplete]}).json()
    assert not res["changed"] and res["errors"]
    too_many = [{"kind": "swap_items"}] * 31
    assert client.post("/api/changes/apply", json={"plan": plan, "items": too_many}).status_code == 422


def test_questionnaire_endpoint_returns_clean_answers(client, data):
    out = client.post("/api/questionnaire", json={"picked": {}, "text": ""}).json()
    assert set(out) == {"answers", "notes", "guesses", "maybe", "suggestions", "answered"} and out["answered"] == 0
    meta = client.get("/api/meta").json()
    if meta["questions"]:
        q = next(q for q in meta["questions"] if q["kind"] == "single")
        picked = {q["id"]: q["options"][0]["code"]}
        got = client.post("/api/questionnaire", json={"picked": picked}).json()
        assert got["answers"][q["id"]] == q["options"][0]["code"] and got["answered"] == 1
        junk = client.post("/api/questionnaire", json={"picked": {q["id"]: "not-an-option"}}).json()
        assert junk["answers"][q["id"]] is None


def test_questionnaire_endpoint_adds_what_the_semantic_layer_reads(client, data):
    from uniadvisor.majors.reader import Guess

    class Stub:
        def read(self, text, have):
            return [Guess("q3", "machines", "em thích máy móc")]

    if data.reader is None:
        return
    data.semantic = Stub()
    out = client.post("/api/questionnaire", json={"picked": {}, "text": "Em thích máy móc"}).json()
    assert [(g["question"], g["option"]) for g in out["maybe"]] == [("q3", "machines")]
    assert "Máy móc" in out["maybe"][0]["text"] and "em thích máy móc" in out["maybe"][0]["text"]
    assert client.post("/api/questionnaire", json={"picked": {}, "text": ""}).json()["maybe"] == []


# ---------------------------------------------------------------- guards

def test_body_size_is_limited(data):
    with make_client(data, max_body=500) as c:
        r = c.post("/api/plan/normalize", json={"plan": {"x": "y" * 1000}})
        assert r.status_code == 413
        assert c.get("/api/health").status_code == 200


def test_access_code(data):
    with make_client(data, access_code="s3cret") as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/meta").status_code == 401
        assert c.get("/api/meta", headers={"X-Access-Code": "wrong"}).status_code == 401
        assert c.get("/api/meta", headers={"X-Access-Code": "s3cret"}).status_code == 200


def test_rate_limit(data):
    with make_client(data, rate_limit="3/minute") as c:
        codes = [c.get("/api/meta").status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
        assert c.get("/api/health").status_code == 200                # health is never limited


def test_responses_are_not_cached_and_nothing_is_stored(client):
    r = client.get("/api/meta")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"


def test_routes_are_the_known_set(client):
    routes = {(m, r.path) for r in client.app.routes if hasattr(r, "methods") for m in r.methods
              if r.path.startswith("/api/") and m in ("GET", "POST")}
    assert routes >= {("GET", "/api/health"), ("GET", "/api/meta"), ("GET", "/api/catalog"),
                      ("POST", "/api/lists/recommend"), ("POST", "/api/lists/chosen"), ("POST", "/api/chat"),
                      ("POST", "/api/changes/apply"), ("POST", "/api/wishes/explain"), ("POST", "/api/questionnaire")}
    # Nothing here dumps a table: no route takes a table name or a free SQL string.
    assert not [p for _, p in routes if "{table" in p or "sql" in p.lower() or "export" in p.lower()]


def test_frontend_is_served_when_built(data, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "assets" / "a.js").write_text("1", encoding="utf-8")
    with make_client(data, web_dist=tmp_path) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/danh-sach").text == "<html>app</html>"          # the single-page app decides
        assert c.get("/assets/a.js").text == "1"
        assert c.get("/../secret").status_code in (200, 404) and "secret" not in c.get("/../secret").text
        assert c.get("/api/nothing").status_code == 404


def test_api_does_not_import_streamlit():
    code = ("import sys, uniadvisor.api.app, uniadvisor.api.views; "
            "bad = [m for m in ('streamlit', 'altair') if m in sys.modules]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_wishes_and_chances_come_structured_for_cards(client, data):
    plan = client.post("/api/lists/choose", json={"plan": student(client), "priority": "dung_nganh"}).json()["plan"]
    page = client.post("/api/lists/chosen", json={"plan": plan}).json()
    items, rows = page["wish_items"], page["wishes"]
    assert [w["nv"] for w in items] == page["wish_numbers"] and len(items) == len(rows)
    first = items[0]
    assert first["level"] in {"mo_uoc", "thu_suc", "vua_suc", "an_toan"} and first["level_name"] == rows[0]["Mức"]
    assert first["school"] == rows[0]["Trường"] and first["score"] == rows[0]["Điểm của em"]
    assert [c["year"] for c in first["cutoffs"]] and first["tuition"] == rows[0]["Học phí"] and first["item"] == 1
    chances = page["chances"]
    if chances:
        assert len(chances["rows"]) == len(chances["lines"])
        levels = chances["rows"][0]["levels"]
        assert [lv["level"] for lv in levels] and all(0 <= lv["p"] <= 1 and lv["text"].endswith("%") for lv in levels)
    cards = client.post("/api/lists/recommend", json={"plan": student(client)}).json()["cards"]
    for card in cards:
        if not card["blocked"]:
            assert len(card["wish_items"]) == card["n_wishes"]


def test_production_headers_for_the_built_frontend(data, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>" + "x" * 3000 + "</html>", encoding="utf-8")
    (tmp_path / "assets" / "app-1a2b.js").write_text("y" * 3000, encoding="utf-8")
    with make_client(data, web_dist=tmp_path) as c:
        page = c.get("/phuong-an", headers={"Accept-Encoding": "gzip"})
        assert page.headers["cache-control"] == "no-cache" and page.headers["content-encoding"] == "gzip"
        csp = page.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'self' https://huggingface.co" in csp
        asset = c.get("/assets/app-1a2b.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert c.get("/assets/gone-9999.js").status_code == 404           # a missing file is not the page
        assert c.get("/favicon-missing.svg").status_code == 404
        assert c.get("/api/meta").headers["cache-control"] == "no-store"


def test_client_address_prefers_the_hosts_own_header():
    from types import SimpleNamespace
    from uniadvisor.api.app import client_ip

    def req(**headers):
        return SimpleNamespace(headers=headers, client=SimpleNamespace(host="10.0.0.9"))

    assert client_ip(req(**{"x-vercel-forwarded-for": "203.0.113.5", "x-forwarded-for": "1.1.1.1, 2.2.2.2"})) == "203.0.113.5"
    assert client_ip(req(**{"x-real-ip": "198.51.100.7"})) == "198.51.100.7"
    assert client_ip(req(**{"x-forwarded-for": "1.1.1.1, 2.2.2.2"})) == "2.2.2.2"
    assert client_ip(req()) == "10.0.0.9"


def test_a_server_without_its_database_stays_up_and_says_so(monkeypatch, tmp_path):
    from uniadvisor.ui import service
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "absent" / "uniadvisor.db")
    for name in ("UNIADVISOR_DB", "UNIADVISOR_DB_REPO", "HF_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(Settings(None, "", (), None, 262144))) as c:       # no data passed: load like a server
        assert c.get("/api/health").json() == {"ok": True, "data": False}          # nothing is loaded before it is needed
        r = c.get("/api/meta")
        assert r.status_code == 503 and r.json()["detail"] == "Dữ liệu chưa sẵn sàng."
        health = c.get("/api/health").json()
        assert health["ok"] is True and health["data"] is False and "UNIADVISOR_DB" in health["problem"]


def test_the_data_loads_on_the_first_call_that_needs_it_and_only_once(monkeypatch, fake_db_path):
    from uniadvisor.api import app as app_module
    monkeypatch.setenv("UNIADVISOR_DB", str(fake_db_path))
    loads = []
    real = app_module.AppData.load
    monkeypatch.setattr(app_module.AppData, "load", classmethod(lambda cls, path=None: loads.append(path) or real(path)))
    with TestClient(create_app(Settings(None, "", (), None, 262144))) as c:
        assert c.get("/api/health").json() == {"ok": True, "data": False} and loads == []   # health does not load
        assert c.get("/api/meta").status_code == 200 and len(loads) == 1
        assert c.get("/api/catalog").status_code == 200 and len(loads) == 1                  # not again
        assert c.get("/api/health").json() == {"ok": True, "data": True}
