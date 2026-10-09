"""A polite HTTP client for the collectors: robots.txt is respected, requests to a host are spaced out, and every
response is cached (same layout as data/inputs/http_cache: <host>/<hash>.body + <hash>.meta.json)."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

USER_AGENT = "UniAdvisorResearchBot/0.1 (student project; cutoff collection; contact via project owner)"


class PoliteClient:
    def __init__(self, cache_dir: Path, delay: float = 2.0, timeout: float = 30.0, offline: bool = False):
        self.cache_dir = cache_dir
        self.delay = delay
        self.timeout = timeout
        self.offline = offline                     # True: only read the cache, never fetch
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._index: dict[str, Path] = {}
        if cache_dir.exists():
            for meta in cache_dir.rglob("*.meta.json"):
                self._index[json.loads(meta.read_text(encoding="utf-8"))["url"]] = meta
        self.fetched = 0

    def _paths(self, url: str) -> tuple[Path, Path]:
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
        d = self.cache_dir / urlsplit(url).netloc
        return d / f"{name}.body", d / f"{name}.meta.json"

    def cached(self, url: str) -> str | None:
        meta = self._index.get(url)
        if meta is None:
            return None
        info = json.loads(meta.read_text(encoding="utf-8"))
        if info.get("status") != 200:
            return None
        return meta.with_name(meta.name.replace(".meta.json", ".body")).read_text(encoding="utf-8", errors="replace")

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser(host + "/robots.txt")
            try:
                rp.read()
            except (urllib.error.URLError, TimeoutError):
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> str | None:
        """The page body (from the cache when present), or None when not allowed, offline or failed."""
        hit = self.cached(url)
        if hit is not None or self.offline:
            return hit
        if not self.allowed(url):
            return None
        host = urlsplit(url).netloc
        wait = self._last.get(host, 0) + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        status, body = 0, b""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "vi"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, body = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            status = 0
        self._last[host] = time.monotonic()
        self.fetched += 1
        body_path, meta_path = self._paths(url)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        meta_path.write_text(json.dumps({"url": url, "status": status,
                                         "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                             encoding="utf-8")
        self._index[url] = meta_path
        return body.decode("utf-8", errors="replace") if status == 200 else None
