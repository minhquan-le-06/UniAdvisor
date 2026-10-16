"""Get the database onto the server without it ever being in the code repository.

On a Hugging Face Space the database is a file in a private dataset. At startup, when UNIADVISOR_DB does not already
name a file, it is downloaded with the token held in the Space's secrets and UNIADVISOR_DB is set to it. A database of
another schema version is refused. The database is never built here (the offline pipeline is not in the image).

Variables: HF_TOKEN (secret), UNIADVISOR_DB_REPO (the private dataset, "owner/name"), UNIADVISOR_DB_FILE (the file in
it, default uniadvisor.db), UNIADVISOR_DB_DIR (where to put it, default the system temp folder).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from uniadvisor import db
from uniadvisor.ui.service import ENV_DB, db_path

DEFAULT_FILE = "uniadvisor.db"


class DatabaseUnavailable(RuntimeError):
    """The database could not be found or is of another version (the message says what to set)."""


def repo_id(value: str) -> str:
    """`owner/name`, also when the setting holds the dataset's address (https://huggingface.co/datasets/owner/name)."""
    v = value.strip().rstrip("/")
    for prefix in ("https://huggingface.co/datasets/", "http://huggingface.co/datasets/", "huggingface.co/datasets/",
                   "datasets/"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v


def schema_version(path: Path) -> str | None:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def download(repo: str, filename: str, token: str | None, directory: Path) -> Path:
    # A serverless host has a read-only home folder: the library's caches (and its token file) go to the temporary
    # folder, set before the library is imported.
    os.environ.setdefault("HF_HOME", str(directory / "hf-home"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import hf_hub_download     # imported here: only a hosted server needs the package
    return Path(hf_hub_download(repo_id=repo, filename=filename, repo_type="dataset", token=token,
                                local_dir=str(directory)))


def ensure_database(fetch=download) -> Path:
    """The path of a usable database, downloading it first when the settings say where it is."""
    path = db_path()
    if not path.is_file() and os.environ.get(ENV_DB) is None:
        repo = repo_id(os.environ.get("UNIADVISOR_DB_REPO", ""))
        if repo:
            directory = Path(os.environ.get("UNIADVISOR_DB_DIR") or tempfile.gettempdir()) / "uniadvisor-db"
            directory.mkdir(parents=True, exist_ok=True)
            try:
                path = fetch(repo, os.environ.get("UNIADVISOR_DB_FILE", DEFAULT_FILE), os.environ.get("HF_TOKEN"),
                             directory)
            except Exception as e:      # the token and the repository name stay out of the message
                raise DatabaseUnavailable(f"Could not download the database from the dataset named in UNIADVISOR_DB_REPO "
                                          f"({type(e).__name__}). It must read owner/name, the token must be allowed to "
                                          f"read it, and the file must be called {os.environ.get('UNIADVISOR_DB_FILE', DEFAULT_FILE)}."
                                          ) from None
            os.environ[ENV_DB] = str(path)
    if not path.is_file():
        raise DatabaseUnavailable("No database: set UNIADVISOR_DB to a built database, or UNIADVISOR_DB_REPO and "
                                  "HF_TOKEN to download it from a private dataset.")
    version = schema_version(path)
    if version != db.SCHEMA_VERSION:
        raise DatabaseUnavailable(f"The database has schema version {version}, the code needs {db.SCHEMA_VERSION}; "
                                  "upload a database built by this version of the code.")
    return path
