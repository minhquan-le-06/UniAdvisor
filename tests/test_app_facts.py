"""Step 6 facts in the app (src/uniadvisor/app/facts.py) on the fake database's invented facts."""

import pytest

from uniadvisor.app.catalog import Catalog
from uniadvisor.app.facts import FactsIndex
from uniadvisor.app.service import AppData
from uniadvisor.app.state import PlanState, ShortlistEntry


@pytest.fixture
def facts(fake_db):
    return FactsIndex.load(fake_db, Catalog.load(fake_db))


def test_nganh_facts(facts):
    cs = facts.get("7480101")
    assert cs.jobs == ["Nhà nghiên cứu khoa học máy tính", "Kỹ sư phát triển phần mềm"]   # display order
    assert cs.knowledge == ["Toán học", "Máy tính và điện tử", "Ngôn ngữ và viết"]   # most distinctive first
    assert cs.interests[0] == ("Nghiên cứu", "thích tìm hiểu, phân tích")
    assert cs.close == ["7480201", "7480103", "7480107"] and cs.draft
    assert facts.get("7140209").empty                                        # no facts for this ngành


def test_group_facts_combine_their_nganh(facts):
    g = facts.get("74801")                                                    # 7480101 + 7480103 (+ 7480107 none)
    assert "Kỹ sư phát triển phần mềm" in g.jobs and g.knowledge[0] == "Máy tính và điện tử"
    assert g.close and all(c[:5] != "74801" for c in g.close)                 # closest ngành outside the group


def test_proposed_close(facts):
    assert facts.proposed_close("7480101") == ["7480201", "7480103"]
    assert facts.proposed_close("7480101", exclude={"7480201"}) == ["7480103", "7480107"]


def test_further_close_feed_the_an_toan_top_up(fake_db_path):
    d = AppData.load(fake_db_path)
    state = PlanState(scores={"TO": 8.0}, home_province="Hà Nội",
                      shortlist=[ShortlistEntry("7480101", ["7480201"])])
    item = d.shortlist_items(state)[0]
    assert item.close_codes == ("7480201",) and item.further_close_codes == ("7480103", "7480107")


def test_chat_answer_uses_facts(fake_db_path):
    from uniadvisor.chat.classify import RuleClassifier
    from uniadvisor.chat.pipeline import handle
    d = AppData.load(fake_db_path)
    state = PlanState()
    ctx = d.chat_context(state, None)
    rules = RuleClassifier(d.indexes.schools, d.indexes.nganh, set(d.subjects))
    answer = handle("ngành Khoa học máy tính học gì", ctx, rules).answers[0]
    assert "kiến thức chính Toán học, Máy tính và điện tử" in answer and "Kỹ sư phát triển phần mềm" in answer
    assert "O*NET 31.0" in answer
