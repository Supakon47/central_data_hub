"""Test setup: every test runs against its own empty SQLite database.

The environment is set before the app is imported because ``app.config``
reads it at import time. Tests therefore never touch the PostgreSQL data.
"""

import base64
import hashlib
import os
import tempfile
from pathlib import Path

import pytest

TEST_DIR = Path(tempfile.mkdtemp(prefix="central-data-hub-tests-"))
ADMIN_PASSWORD = "test-password-123"


def _admin_password_hash(password: str) -> str:
    # Same format as admin_security.hash_password, with few iterations to stay fast.
    salt = b"fixed-test-salt!"
    iterations = 1_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")  # noqa: E731
    return f"pbkdf2_sha256${iterations}${encode(salt)}${encode(digest)}"


os.environ.update({
    "DATABASE_URL": f"sqlite:///{TEST_DIR / 'test.db'}",
    "IMAGE_STORAGE_DIR": str(TEST_DIR / "images"),
    "APP_ENV": "test",
    "ADMIN_PASSWORD_HASH": _admin_password_hash(ADMIN_PASSWORD),
    "ADMIN_SESSION_SECRET": "x" * 40,
    "GOOGLE_SHEETS_ENABLED": "false",
    "GOOGLE_SHEETS_WEB_SYNC_ENABLED": "false",
    "GOOGLE_SHEETS_AUTO_SYNC_ENABLED": "false",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import cache  # noqa: E402

assert engine.url.get_backend_name() == "sqlite", "tests must never run against the real database"


@pytest.fixture(autouse=True)
def empty_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    cache._RESULT_CACHE.clear()
    yield


@pytest.fixture
def session():
    with SessionLocal() as db_session:
        yield db_session


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client):
    response = client.post("/api/admin/login", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client
