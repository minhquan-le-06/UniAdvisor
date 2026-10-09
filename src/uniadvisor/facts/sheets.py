"""Fact sheets per nhóm ngành (spec 3.4).

Each sheet is drafted in plain Vietnamese from the nhóm ngành's facts pack only (table-to-text; Zhao et al.,
EMNLP 2023 Industry Track); automatic checks run before any review; an LLM reviewer then lists claims the pack does not
support, and people review every sheet. The app shows a sheet only once its status is 'reviewed'.

    python -m uniadvisor.facts.sheets packs    # data/build/fact_packs/<code>.json + all_packs.md (what to write from)
    python -m uniadvisor.facts.sheets draft    # a draft sheet for every nhóm ngành without one (never overwrites)
    python -m uniadvisor.facts.sheets check    # checks every sheet; review bundle data/build/review/fact_sheets_review.md

Drafts use fixed Vietnamese wording over the pack (draft_sheet): a sheet may only restate its pack, so free prose would
add nothing but the risk of unsupported claims (design choice, 2026-10-07). Reviewers may rewrite a sheet freely; the
checks still apply.

Sheets: data/curated/fact_sheets/<code>.md, a front matter block (code, status, written_by, reviewed_by) then the
fixed headings in HEADINGS.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from uniadvisor.paths import CURATED_DIR, DB_PATH

SHEET_DIR = CURATED_DIR / "fact_sheets"
PACK_DIR = DB_PATH.parent / "fact_packs"
HEADINGS = ["Học gì", "Cần mạnh môn nào", "Ra trường làm gì", "Hợp với ai", "Ngành gần", "Nguồn"]
SOURCES = ("O*NET 31.0 (Bộ Lao động Hoa Kỳ, CC BY 4.0) cho việc làm, kiến thức và sở thích nghề nghiệp; danh sách "
           "chương trình và tổ hợp xét tuyển của UniAdvisor (Hà Nội, TP.HCM); thu nhập: Tổng cục Thống kê, 2024.")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


# ---------------------------------------------------------------- packs

def facts_pack(code: str, data) -> dict:
    """Everything a nhóm ngành's sheet may say (data: uniadvisor.app.service.AppData)."""
    from uniadvisor.app.texts import INCOME_CONTEXT
    from uniadvisor.data.school_docs import combo_label

    cat, m = data.catalog, data.catalog.majors[code]
    f = data.facts.get(code)
    kids = [cat.majors[c] for c in m.children]
    schools = {p.school_code for p in data.programs if p.moet_code in set(m.children)}
    return {
        "code": code,
        "name": m.label,
        "official_name": m.official,
        "programs": {"total": m.n_programs, "ha_noi": m.n_programs_hn, "tp_hcm": m.n_programs_hcm,
                     "schools": len(schools)},
        "nganh": [{"code": k.code, "name": k.label, "programs": k.n_programs} for k in kids],
        "knowledge": f.knowledge,
        "jobs": f.jobs,
        "interests": [{"type": t, "meaning": d} for t, d in f.interests],
        "combos": [{"code": combo_label(s.combo), "subjects": list(s.subjects), "share_pct": round(s.share * 100)}
                   for s in cat.combo_shares(code, top=4)],
        "close_nganh": [cat.label(c) for c in f.close[:5]],
        "income": INCOME_CONTEXT,
        "sources": SOURCES,
        "facts_reviewed": not f.draft,
    }


def all_packs(data) -> dict[str, dict]:
    return {c: facts_pack(c, data) for c, m in sorted(data.catalog.majors.items())
            if m.level == "nhom_nganh" and m.children}


def write_packs(packs: dict[str, dict], out: Path = PACK_DIR) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Facts packs per nhóm ngành", ""]
    for code, p in packs.items():
        (out / f"{code}.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        lines += [f"## {code} {p['name']}", "", "```json", json.dumps(p, ensure_ascii=False, indent=2), "```", ""]
    (out / "all_packs.md").write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------- drafts

def _join(items: list[str]) -> str:
    """'a, b và c'; with semicolons when an item has its own 'và' ('máy tính và điện tử; toán học')."""
    if len(items) == 1:
        return items[0]
    if any(" và " in i or "," in i for i in items):
        return "; ".join(items)
    return ", ".join(items[:-1]) + " và " + items[-1]


def _lower_first(text: str) -> str:
    return text[0].lower() + text[1:] if text else text


def draft_sheet(pack: dict) -> str:
    """A sheet that says exactly what the pack says, under HEADINGS."""
    p, pr = pack, pack["programs"]
    lines = ["---", f"code: {p['code']}", "status: draft", "written_by: agent (fixed wording over the facts pack)",
             "reviewed_by:", "---", f"# {p['name']}", ""]
    intro = (f"Tên nhóm ngành theo Bộ GD&ĐT: {p['official_name']}. " if p["official_name"] != p["name"] else "")
    kids = p["nganh"]
    if len(kids) == 1:
        intro += f"Nhóm có một ngành: {kids[0]['name']}. "
    elif len(kids) <= 8:
        intro += "Gồm các ngành: " + _join([f"{k['name']} ({k['programs']} chương trình)" for k in kids]) + ". "
    else:
        intro += ("Gồm nhiều ngành, đông nhất là " + _join([f"{k['name']} ({k['programs']} chương trình)"
                                                           for k in kids[:6]]) + ". ")
    where = (f"{pr['ha_noi']} ở Hà Nội, {pr['tp_hcm']} ở TP.HCM" if pr["ha_noi"] and pr["tp_hcm"]
             else "tất cả ở Hà Nội" if pr["ha_noi"] else "tất cả ở TP.HCM")
    intro += f"Ở Hà Nội và TP.HCM có {pr['total']} chương trình tại {pr['schools']} trường ({where})."
    lines += [intro, ""]

    lines += ["## Học gì", ""]
    if p["knowledge"]:
        lines += ["Những mảng kiến thức chính mà công việc của nhóm ngành này cần: "
                  + _join([_lower_first(k) for k in p["knowledge"]]) + ".",
                  "Đây là kiến thức công việc cần, không phải danh sách môn học; chương trình học của từng trường xem "
                  "trên trang của trường.", ""]
    else:
        lines += ["Chưa có dữ liệu.", ""]

    lines += ["## Cần mạnh môn nào", ""]
    if p["combos"]:
        lines.append("Các tổ hợp xét tuyển hay gặp nhất: " + "; ".join(
            f"{c['code']} ({', '.join(c['subjects'])}) ở {c['share_pct']}% chương trình" for c in p["combos"]) + ".")
        common = set(p["combos"][0]["subjects"]).intersection(*[set(c["subjects"]) for c in p["combos"][1:]])
        if common and len(p["combos"]) > 1:
            lines.append(f"Môn có trong tất cả các tổ hợp trên: {_join(sorted(common))}.")
        lines.append("")
    else:
        lines += ["Chưa có dữ liệu về tổ hợp xét tuyển của các chương trình trong nhóm này.", ""]

    lines += ["## Ra trường làm gì", ""]
    if p["jobs"]:
        lines.append("Theo dữ liệu nghề nghiệp của Mỹ (O*NET), người học các ngành này thường làm: "
                     + _join([_lower_first(j) for j in p["jobs"]]) + ". Công việc ở Việt Nam có thể khác.")
    else:
        lines.append("Chưa có dữ liệu việc làm cho nhóm ngành này.")
    lines += [f"Thu nhập: {p['income']}.", ""]

    lines += ["## Hợp với ai", ""]
    if p["interests"]:
        meanings = [i["meaning"] for i in p["interests"]]
        lines += ["Theo cách chia sở thích nghề nghiệp của Holland, các công việc này hợp nhất với người "
                  + meanings[0] + (("; tiếp theo là người " + "; và người ".join(meanings[1:])) if meanings[1:] else "")
                  + ".", ""]
    else:
        lines += ["Chưa có dữ liệu.", ""]

    lines += ["## Ngành gần", ""]
    lines += [("Ngành ở nhóm khác có công việc và kiến thức gần nhất: " + _join(p["close_nganh"]) + ".")
              if p["close_nganh"] else "Không có ngành ở nhóm khác đủ gần với nhóm này.", ""]
    lines += ["## Nguồn", "", p["sources"], ""]
    return "\n".join(lines)


def write_drafts(packs: dict[str, dict], folder: Path = SHEET_DIR) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    n = 0
    for code, pack in packs.items():
        path = folder / f"{code}.md"
        if not (pack["jobs"] or pack["knowledge"] or pack["interests"]):
            continue                    # no facts: no sheet (Quân sự; LLM review, round 4)
        if not path.exists():
            path.write_text(draft_sheet(pack), encoding="utf-8", newline="\n")
            n += 1
    return n


# ---------------------------------------------------------------- sheets

def read_sheet(path: Path) -> tuple[dict, str]:
    """(front matter, body)."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta: dict[str, str] = {}
    if text.startswith("---\n"):
        head, _, text = text[4:].partition("\n---\n")
        for line in head.splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, text.strip()


def pack_numbers(pack: dict) -> set[str]:
    """Every number the pack states, normalised ('8,7' -> '8.7')."""
    return {n.replace(",", ".") for n in _NUMBER.findall(json.dumps(pack, ensure_ascii=False))}


def check_sheet(meta: dict, body: str, pack: dict | None) -> list[str]:
    """Automatic checks: the pack exists, the headings are the fixed ones in order, every
    number in the sheet appears in the pack, the sheet names its sources."""
    issues = []
    if pack is None:
        return ["no_facts_pack"]
    if meta.get("code") != pack["code"]:
        issues.append("code_mismatch")
    found = re.findall(r"^## (.+)$", body, flags=re.M)
    if found != HEADINGS:
        issues.append("headings:" + "|".join(found))
    allowed = pack_numbers(pack)
    extra = sorted({n.replace(",", ".") for n in _NUMBER.findall(body)} - allowed)
    if extra:
        issues.append("numbers_not_in_pack:" + ";".join(extra))
    if "O*NET" not in body:
        issues.append("no_onet_credit")
    return issues


def load_sheets(folder: Path = SHEET_DIR) -> dict[str, tuple[dict, str]]:
    if not folder.exists():
        return {}
    return {p.stem: read_sheet(p) for p in sorted(folder.glob("*.md"))}


def insert_sheets(conn: sqlite3.Connection, folder: Path = SHEET_DIR) -> int:
    """Table fact_sheet from data/curated/fact_sheets (the build; checks run in `check`)."""
    rows = [(code, body, meta.get("status", "draft"), meta.get("written_by", ""), meta.get("reviewed_by", ""))
            for code, (meta, body) in load_sheets(folder).items()]
    conn.executemany("INSERT INTO fact_sheet VALUES (?,?,?,?,?)", rows)
    return len(rows)


def review_bundle(packs: dict[str, dict], sheets: dict[str, tuple[dict, str]], out: Path) -> dict:
    """data/build/review/fact_sheets_review.md (pack + sheet per nhóm ngành, for the LLM review) and
    fact_sheets_check.csv (automatic check results)."""
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Fact sheets to review", "", "For each nhóm ngành: the facts pack (the only allowed source) and the sheet.",
             "Instructions: the reviewers' prompt, section 'Fact sheets'.", ""]
    rows = ["code,name,status,issues"]
    counts = {"sheets": 0, "with_issues": 0, "missing": 0, "no_facts": 0}
    for code, pack in packs.items():
        if not (pack["jobs"] or pack["knowledge"] or pack["interests"]):
            counts["no_facts"] += 1
            continue
        if code not in sheets:
            counts["missing"] += 1
            continue
        meta, body = sheets[code]
        issues = check_sheet(meta, body, pack)
        counts["sheets"] += 1
        counts["with_issues"] += bool(issues)
        if meta.get("status") == "reviewed" and not issues:
            counts["reviewed"] = counts.get("reviewed", 0) + 1
            rows.append(f"{code},\"{pack['name']}\",reviewed,")
            continue                    # the bundle holds only sheets still to review
        rows.append(f"{code},\"{pack['name']}\",{meta.get('status', 'draft')},\"{' '.join(issues)}\"")
        lines += [f"## {code} {pack['name']}", "", "### Facts pack", "", "```json",
                  json.dumps(pack, ensure_ascii=False, indent=2), "```", "", "### Sheet", "", body, "",
                  "### Automatic checks: " + ("; ".join(issues) if issues else "passed"), "", "---", ""]
    (out / "fact_sheets_review.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "fact_sheets_check.csv").write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["packs", "draft", "check"])
    args = ap.parse_args()
    from uniadvisor.app.service import AppData
    packs = all_packs(AppData.load())
    if args.command == "packs":
        print(f"{len(packs)} packs -> {write_packs(packs)}")
    elif args.command == "draft":
        print(f"{write_drafts(packs)} new drafts in {SHEET_DIR}")
    else:
        print(review_bundle(packs, load_sheets(), DB_PATH.parent / "review"))


if __name__ == "__main__":
    main()
