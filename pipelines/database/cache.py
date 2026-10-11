"""Read the cached HTTP responses (pipelines/data/inputs/http_cache) and parse the cutoff rows they contain.

Used to check every row of the collected CSVs against the page it says it came from, and to read
fields the CSVs dropped (Tuyensinh247's admission method).
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from uniadvisor.data.text import nfc, norm_code, parse_score


@dataclass(frozen=True)
class PageRow:
    code: str            # normalised program code
    score: float | None
    method: str | None   # admission method label when the page gives one
    converted: bool | None = None


class HttpCache:
    def __init__(self, *roots: Path):
        """Index one or more cache directories; a later root wins for the same URL."""
        self.roots = roots
        self._by_url: dict[str, Path] = {}
        for root in roots:
            if root is None or not root.exists():
                continue
            for meta in sorted(root.rglob("*.meta.json")):
                info = json.loads(meta.read_text(encoding="utf-8"))
                if info.get("status") == 200:
                    self._by_url[info["url"]] = meta.with_name(meta.name.replace(".meta.json", ".body"))
        self._parsed: dict[str, list[PageRow] | None] = {}

    def __len__(self) -> int:
        return len(self._by_url)

    def has(self, url: str) -> bool:
        return url in self._by_url

    def body(self, url: str) -> str | None:
        path = self._by_url.get(url)
        return path.read_text(encoding="utf-8", errors="replace") if path else None

    def rows(self, url: str) -> list[PageRow] | None:
        """Cutoff rows parsed from the cached page at `url`, or None when the page is not cached."""
        if url not in self._parsed:
            body = self.body(url)
            if body is None:
                self._parsed[url] = None
            elif "vnexpress.net" in url:
                self._parsed[url] = parse_vnexpress(body)
            elif "tuyensinh247.com" in url:
                self._parsed[url] = parse_tuyensinh247(body)
            elif "vietnamnet.vn" in url:
                self._parsed[url] = parse_vietnamnet(body)
            else:
                self._parsed[url] = []
        return self._parsed[url]


def parse_vnexpress(body: str) -> list[PageRow]:
    """VnExpress benchmark page: JSON {"html": "<table>..."}; one <tr> per program row."""
    try:
        page = json.loads(body).get("html", "")
    except (json.JSONDecodeError, AttributeError):
        return []
    rows = []
    for tr in re.findall(r'<tr class="university__benchmark\s+(?:odd)?\s*">(.*?)</tr>', page, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if len(cells) < 3:
            continue
        code = re.search(r'<span style="display:\s*block;">\s*(.*?)\s*</span>', cells[0], flags=re.S)
        score = re.search(r"<span>\s*([\d.,]+)\s*</span>", cells[2], flags=re.S)
        if code:
            rows.append(PageRow(norm_code(html.unescape(code.group(1))),
                                parse_score(score.group(1)) if score else None, "THPT"))
    return rows


_TS_OBJECT = re.compile(r'\{"id":\s*\d+,\s*"school_id":\s*\d+,[^{}]*\}')


def parse_tuyensinh247(body: str) -> list[PageRow]:
    """Tuyensinh247 pages embed their data in Next.js `self.__next_f.push([1, "..."])` string chunks."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', body)
    text = "".join(json.loads(c) for c in chunks)
    rows = []
    for m in _TS_OBJECT.finditer(text):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if "mark" not in obj or "code" not in obj:
            continue
        rows.append(PageRow(norm_code(obj["code"] or ""), parse_score(obj["mark"]),
                            nfc(obj.get("admission_name") or ""), obj.get("is_converted_score") == 1))
    return rows


def parse_vietnamnet(body: str) -> list[PageRow]:
    try:
        model = json.loads(body)["data"]["model"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return [PageRow(norm_code(s.get("code", "")), parse_score(s.get("score")), nfc(s.get("note") or ""))
            for s in model.get("schoolScores") or []]


def check_row(cache: HttpCache, url: str, code: str, score: float | None) -> tuple[str, PageRow | None]:
    """('verified' | 'mismatch' | 'not_cached', matching page row)."""
    rows = cache.rows(url) if isinstance(url, str) else None
    if rows is None:
        return "not_cached", None
    for row in rows:
        if row.code == code and row.score is not None and score is not None and abs(row.score - score) < 1e-6:
            return "verified", row
    return "mismatch", None
