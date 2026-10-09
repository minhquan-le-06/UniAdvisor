"""Open and create the SQLite database."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from uniadvisor.paths import DB_PATH

SCHEMA_VERSION = "7"


def schema_sql() -> str:
    return resources.files("uniadvisor.data").joinpath("schema.sql").read_text(encoding="utf-8")


def create(path: Path | str) -> sqlite3.Connection:
    """Create an empty database with the current schema (replacing any file at `path`)."""
    path = Path(path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(schema_sql())
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    return conn


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open an existing database read-only."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; build it with: python -m uniadvisor.data.build")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
