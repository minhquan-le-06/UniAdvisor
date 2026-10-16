"""Settings of the web API, all from environment variables (a Hugging Face Space sets them as variables and secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from uniadvisor.paths import ROOT


@dataclass(frozen=True)
class Settings:
    access_code: str | None          # ACCESS_CODE: when set, every /api call except health needs it (X-Access-Code)
    rate_limit: str                  # RATE_LIMIT per client address, in slowapi's words ("60/minute"); "" turns it off
    cors_origins: tuple[str, ...]    # CORS_ORIGINS, comma separated; empty: same origin only (the usual case)
    web_dist: Path | None            # WEB_DIST: the built frontend served at / when the folder exists
    max_body: int                    # MAX_BODY bytes of a request (a plan file is at most 200 KB)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            access_code=env("ACCESS_CODE") or None,
            rate_limit=env("RATE_LIMIT", "60/minute"),
            cors_origins=tuple(o.strip() for o in env("CORS_ORIGINS", "").split(",") if o.strip()),
            web_dist=Path(env("WEB_DIST") or ROOT / "web" / "dist"),
            max_body=int(env("MAX_BODY", "262144")),
        )
