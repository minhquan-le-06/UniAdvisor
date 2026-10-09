"""Collectors for the three cutoff sites. Each returns rows in the same columns as the corresponding CSV in
data/inputs/collected, so the database build reads old and new rows the same way."""

from __future__ import annotations

import html
import json
import re

from uniadvisor.collect.http import PoliteClient
from uniadvisor.data.text import nfc

YEARS = (2025, 2026)


def _fetched_at(client: PoliteClient, url: str) -> str:
    meta = client._index.get(url)
    return json.loads(meta.read_text(encoding="utf-8"))["fetched_at"] if meta else ""


def _text(fragment: str) -> str:
    return nfc(html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip())


# ---------------------------------------------------------------- VnExpress

VNE_SEARCH = "https://diemthi.vnexpress.net/tra-cuu-dai-hoc/loadcollegev2?input_college={code}"
VNE_BENCHMARK = "https://diemthi.vnexpress.net/tra-cuu-dai-hoc/loadbenchmark/id/{vid}/year/{year}/sortby/1/block_name/-1"
VNE_COLUMNS = ["source", "school_code", "vne_id", "year", "program_name", "program_code", "combos", "thpt_score_raw",
               "other_methods", "tuition_raw", "url", "fetched_at"]


def vnexpress_id(client: PoliteClient, code: str) -> str | None:
    """VnExpress's numeric id for a school code (the suggestion whose text starts with '<CODE> - ')."""
    body = client.get(VNE_SEARCH.format(code=code))
    if not body:
        return None
    try:
        page = json.loads(body).get("html", "")
    except (json.JSONDecodeError, AttributeError):
        return None
    for vid, text in re.findall(r'data-id="(\d+)"[^>]*data-text="([^"]*)"', page):
        if html.unescape(text).strip().upper().startswith(f"{code.upper()} - "):
            return vid
    return None


def parse_vnexpress_rows(page: str) -> list[dict]:
    rows = []
    for tr in re.findall(r'<tr class="university__benchmark\s+(?:odd)?\s*">(.*?)</tr>', page, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells) < 5:
            continue
        name = re.search(r"<strong>(.*?)</strong>", cells[0], flags=re.S)
        code = re.search(r'<span style="display:\s*block;">\s*(.*?)\s*</span>', cells[0], flags=re.S)
        score = re.search(r"<span>\s*([\d.,]+)\s*</span>", cells[2], flags=re.S)
        if not (name and code and score):
            continue
        # One link per combination ("<a title=...>A00</a>"), or all in one link ("A00; A01; C01").
        combos = [c for text in re.findall(r"<a[^>]*>(.*?)</a>", cells[1], flags=re.S)
                  for c in re.split(r"[;,\s]+", _text(text)) if re.fullmatch(r"[A-Z0-9]{2,5}", c)]
        tuition = _text(cells[4])
        rows.append({"program_name": _text(name.group(1)), "program_code": _text(code.group(1)),
                     "combos": ";".join(combos), "thpt_score_raw": score.group(1).strip(),
                     "other_methods": _text(cells[3]), "tuition_raw": "" if tuition in ("", "--") else tuition})
    return rows


def collect_vnexpress(client: PoliteClient, code: str) -> list[dict]:
    vid = vnexpress_id(client, code)
    if vid is None:
        return []
    out = []
    for year in YEARS:
        url = VNE_BENCHMARK.format(vid=vid, year=year)
        body = client.get(url)
        if not body:
            continue
        try:
            page = json.loads(body).get("html", "")
        except (json.JSONDecodeError, AttributeError):
            continue
        for r in parse_vnexpress_rows(page):
            out.append({"source": "vnexpress_cutoffs", "school_code": code, "vne_id": vid, "year": year, **r,
                        "url": url, "fetched_at": _fetched_at(client, url)})
    return out


# ---------------------------------------------------------------- Tuyensinh247

TS_LIST = "https://diemthi.tuyensinh247.com/diem-chuan.html"
TS_COLUMNS = ["source", "school_code", "year", "program_code", "program_name", "combos", "score_raw", "url",
              "fetched_at"]


def tuyensinh247_urls(client: PoliteClient) -> dict[str, str]:
    """School code -> its cutoff page, from the site's list of schools."""
    body = client.get(TS_LIST) or ""
    return {code: "https://diemthi.tuyensinh247.com" + path
            for path, code in re.findall(r'href="(/diem-chuan/[a-z0-9-]+-([A-Z0-9]+)\.html)"', body)}


def parse_tuyensinh247_objects(body: str) -> list[dict]:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', body)
    text = "".join(json.loads(c) for c in chunks)
    out = []
    for m in re.finditer(r'\{"id":\s*\d+,\s*"school_id":\s*\d+,[^{}]*\}', text):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if "mark" in obj and "code" in obj:
            out.append(obj)
    return out


def collect_tuyensinh247(client: PoliteClient, code: str, urls: dict[str, str]) -> list[dict]:
    url = urls.get(code)
    body = client.get(url) if url else None
    if not body:
        return []
    out = []
    for obj in parse_tuyensinh247_objects(body):
        if obj.get("year") not in YEARS or obj.get("mark") is None:
            continue
        out.append({"source": "tuyensinh247_cutoffs", "school_code": code, "year": obj["year"],
                    "program_code": nfc(obj["code"] or ""), "program_name": nfc(obj.get("name") or ""),
                    "combos": ";".join(c.strip() for c in (obj.get("block") or "").split(";") if c.strip()),
                    "score_raw": obj["mark"], "url": url, "fetched_at": _fetched_at(client, url)})
    return out


# ---------------------------------------------------------------- VietNamNet

VNN_API = ("https://vietnamnet.vn/newsapi-edu/UniversityDetail/GetDetail?pageId=49ff289efde0446f9ae2f5c385595744"
           "&componentId=COMPONENT002302&keyword={code}&year={year}&pageSize=25&pageIndex={page}"
           "&typeOfTraining=0&subjectGroup=")
VNN_COLUMNS = ["source", "school_code", "school_name_src", "province_src", "year", "program_code", "program_name",
               "score_raw", "combos_raw", "note", "training_type", "url", "fetched_at"]


def collect_vietnamnet(client: PoliteClient, code: str, max_pages: int = 20) -> list[dict]:
    out = []
    for year in YEARS:
        seen = set()
        for page in range(max_pages):
            url = VNN_API.format(code=code, year=year, page=page)
            body = client.get(url)
            if not body:
                break
            try:
                model = json.loads(body)["data"]["model"]
            except (json.JSONDecodeError, KeyError, TypeError):
                break
            scores = model.get("schoolScores") or []
            fresh = [s for s in scores if json.dumps(s, sort_keys=True) not in seen]
            if not fresh:
                break
            for s in fresh:
                seen.add(json.dumps(s, sort_keys=True))
                out.append({"source": "vietnamnet_cutoffs", "school_code": code,
                            "school_name_src": nfc(model.get("schoolName") or ""), "province_src": "",
                            "year": year, "program_code": nfc(s.get("code") or ""),
                            "program_name": nfc(s.get("name") or ""), "score_raw": s.get("score"),
                            "combos_raw": nfc(s.get("subjectGroup") or ""), "note": nfc(s.get("note") or ""),
                            "training_type": s.get("typeOfTraining", ""), "url": url,
                            "fetched_at": _fetched_at(client, url)})
            if len(scores) < 25:
                break
    return out
