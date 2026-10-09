import pytest

from uniadvisor import db
from tests.fakedb import build_fake_db


@pytest.fixture(scope="session")
def fake_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("fakedb") / "fake.db"
    build_fake_db(path).close()
    return path


@pytest.fixture
def fake_db(fake_db_path):
    """Read-only connection to the fake database."""
    conn = db.connect(fake_db_path)
    yield conn
    conn.close()
