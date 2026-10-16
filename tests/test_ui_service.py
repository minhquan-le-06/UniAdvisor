"""Database start-up behaviour for the local Streamlit app."""

import pytest

from uniadvisor.ui import service


def test_ensure_db_builds_missing_default_once(tmp_path, monkeypatch):
    expected = tmp_path / "data" / "uniadvisor.db"
    calls = []

    def build(path):
        calls.append(path)
        path.parent.mkdir(parents=True)
        path.touch()

    monkeypatch.setattr(service, "DB_PATH", expected)
    monkeypatch.delenv(service.ENV_DB, raising=False)
    monkeypatch.setattr(service, "_build_default_db", build)

    assert service.ensure_db() == expected
    assert service.ensure_db() == expected
    assert calls == [expected]


def test_ensure_db_never_creates_an_explicit_missing_path(tmp_path, monkeypatch):
    explicit = tmp_path / "mounted" / "uniadvisor.db"
    monkeypatch.setenv(service.ENV_DB, str(explicit))
    monkeypatch.setattr(service, "_build_default_db", lambda path: pytest.fail("must not build an explicit path"))

    with pytest.raises(FileNotFoundError, match="set by UNIADVISOR_DB is missing"):
        service.ensure_db()
