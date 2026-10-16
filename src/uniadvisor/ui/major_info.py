"""What the Chọn ngành page shows about a ngành, as plain data (no Streamlit): search results and the facts behind
"Xem chi tiết". Streamlit (pages.py) and the web API (api/views.py) draw the same data.
"""

from __future__ import annotations

from uniadvisor.data.school_docs import combo_label
from uniadvisor.ui.facts import ONET_CREDIT
from uniadvisor.ui.service import AppData
from uniadvisor.ui.texts import INCOME_CONTEXT

SEARCH_LIMIT = 12
CHILDREN_SHOWN = 4


def kind(d: AppData, code: str) -> str:
    return "Nhóm ngành" if d.catalog.majors[code].level == "nhom_nganh" else "Ngành"


def where(d: AppData, code: str) -> str:
    m = d.catalog.majors[code]
    return f"{m.n_programs_hn} chương trình ở Hà Nội, {m.n_programs_hcm} ở TP.HCM"


def search(d: AppData, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Matches for a typed name, abbreviation or familiar word."""
    cat = d.catalog
    out = []
    for h in cat.search(query, limit=limit):
        m = cat.majors[h.code]
        out.append({
            "code": h.code, "label": m.label, "kind": kind(d, h.code),
            "official": m.official if m.display and m.display != m.official else None,
            "matched": h.matched if h.tier == 3 else None,
            "children": [cat.label(c) for c in m.children[:CHILDREN_SHOWN]] if m.level == "nhom_nganh" else [],
            "more_children": m.level == "nhom_nganh" and len(m.children) > CHILDREN_SHOWN,
            "where": where(d, h.code),
        })
    return out


def detail(d: AppData, code: str) -> dict:
    """One ngành or nhóm ngành: a one-line summary and the four facts (what is learnt, strong subjects, jobs, who it
    suits); a nhóm ngành also lists its ngành and the reviewed fact sheet."""
    cat = d.catalog
    m = cat.majors[code]
    f = d.facts.get(code)
    shares = cat.combo_shares(code, top=4)
    sheet = (d.sheets or {}).get(code)
    return {
        "code": code, "label": m.label, "kind": kind(d, code),
        "official": m.official if m.display and m.display != m.official else None,
        "where": where(d, code),
        "top_combos": [combo_label(s.combo) for s in shares[:3]],
        "interest_names": [name.lower() for name, _ in f.interests[:2]],
        "knowledge": list(f.knowledge),
        "children": [cat.label(c) for c in m.children] if m.level == "nhom_nganh" else [],
        "combos": [{"label": combo_label(s.combo), "subjects": list(s.subjects), "share_pct": round(s.share * 100)}
                   for s in shares],
        "jobs": list(f.jobs), "income": INCOME_CONTEXT,
        "interests": [{"name": name, "description": desc} for name, desc in f.interests],
        "close": [cat.label(c) for c in f.close[:3]],
        "sheet": (sheet.split("\n", 1)[1] if sheet.startswith("# ") else sheet) if sheet else None,
        "has_facts": not f.empty, "draft": f.draft,
    }


def credit(details: list[dict]) -> str | None:
    """The O*NET credit line when any of the ngành has facts, with the draft warning when a name is a draft."""
    if not any(x["has_facts"] for x in details):
        return None
    return ONET_CREDIT + (" Tên tiếng Việt và cách ghép ngành với nghề đang là bản nháp, chưa duyệt."
                          if any(x["draft"] for x in details) else "")
