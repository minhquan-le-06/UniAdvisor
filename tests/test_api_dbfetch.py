"""Getting the database onto a server: from the path set, or downloaded from a private dataset; never built, and a
database of another version is refused."""

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from uniadvisor.api import dbfetch
from uniadvisor.ui import service
from uniadvisor.ui.service import ENV_DB


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "absent" / "uniadvisor.db")    # a fresh server has no database
    for name in (ENV_DB, "UNIADVISOR_DB_REPO", "UNIADVISOR_DB_FILE", "UNIADVISOR_DB_DIR", "HF_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_uses_the_database_that_is_set(fake_db_path, monkeypatch):
    monkeypatch.setenv(ENV_DB, str(fake_db_path))
    assert dbfetch.ensure_database(fetch=lambda *a: pytest.fail("must not download")) == fake_db_path


def test_downloads_from_the_private_dataset_when_nothing_is_set(fake_db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("UNIADVISOR_DB_REPO", "owner/private-db")
    monkeypatch.setenv("UNIADVISOR_DB_DIR", str(tmp_path))
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")
    calls = []

    def fetch(repo, filename, token, directory):
        calls.append((repo, filename, token))
        target = Path(directory) / filename
        shutil.copy(fake_db_path, target)
        return target

    path = dbfetch.ensure_database(fetch=fetch)
    assert calls == [("owner/private-db", "uniadvisor.db", "hf_secret_value")]
    assert path.is_file() and path.parent == tmp_path / "uniadvisor-db"
    assert os.environ[ENV_DB] == str(path)                  # the rest of the app finds it through the usual setting


def test_a_failed_download_names_neither_token_nor_cause(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIADVISOR_DB_REPO", "owner/private-db")
    monkeypatch.setenv("UNIADVISOR_DB_DIR", str(tmp_path))
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")

    def fetch(*args):
        raise OSError("401 for hf_secret_value")

    with pytest.raises(dbfetch.DatabaseUnavailable) as e:
        dbfetch.ensure_database(fetch=fetch)
    assert "hf_secret_value" not in str(e.value) and "OSError" in str(e.value)


def test_no_database_and_nowhere_to_get_it():
    with pytest.raises(dbfetch.DatabaseUnavailable, match="UNIADVISOR_DB"):
        dbfetch.ensure_database()


def test_a_database_of_another_version_is_refused(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    conn.commit()
    conn.close()
    monkeypatch.setenv(ENV_DB, str(old))
    with pytest.raises(dbfetch.DatabaseUnavailable, match="schema version 1"):
        dbfetch.ensure_database()


def test_the_dataset_may_be_given_as_its_address():
    assert dbfetch.repo_id("owner/name") == "owner/name"
    assert dbfetch.repo_id("https://huggingface.co/datasets/owner/name") == "owner/name"
    assert dbfetch.repo_id("  https://huggingface.co/datasets/owner/name/ ") == "owner/name"
    assert dbfetch.repo_id("") == ""


def test_the_failure_message_does_not_name_the_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIADVISOR_DB_REPO", "https://huggingface.co/datasets/owner/secret-name")
    monkeypatch.setenv("UNIADVISOR_DB_DIR", str(tmp_path))
    seen = []

    def fetch(repo, filename, token, directory):
        seen.append(repo)
        raise ValueError("bad")

    with pytest.raises(dbfetch.DatabaseUnavailable) as e:
        dbfetch.ensure_database(fetch=fetch)
    assert seen == ["owner/secret-name"] and "secret-name" not in str(e.value) and "owner/name" in str(e.value)
