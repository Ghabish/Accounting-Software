"""Test fixtures.

Tests run against PostgreSQL when UCF_TEST_DATABASE_URL is set (recommended - this
is how CI and the final validation run), otherwise against SQLite in a temp file.
Each test module gets a freshly created and seeded schema.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("UCF_PASSWORD_ITERATIONS", "1000")
os.environ.setdefault("UCF_ENVIRONMENT", "test")
os.environ.setdefault("UCF_SECRET_KEY", "test-secret-key-for-automated-tests-only-0123456789")
os.environ.setdefault("UCF_ATTACHMENT_DIR", tempfile.mkdtemp(prefix="ucf_att_"))
os.environ.setdefault("UCF_FRONTEND_DIST", "/nonexistent")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.database import models  # noqa: F401
from backend.database.base import Base
from backend.database.session import SessionLocal, make_engine, set_engine
from backend.database.seed.seed import DEMO_PASSWORD, seed_all

TEST_URL = os.environ.get("UCF_TEST_DATABASE_URL")


def _engine():
    if TEST_URL:
        return make_engine(TEST_URL)
    path = os.path.join(tempfile.mkdtemp(prefix="ucf_db_"), "test.db")
    return make_engine(f"sqlite:///{path}")


@pytest.fixture(scope="module")
def engine():
    eng = _engine()
    if eng.dialect.name == "postgresql":
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        from migrations.triggers import install_triggers
        Base.metadata.create_all(eng)
        with eng.begin() as c:
            install_triggers(c)
    else:
        Base.metadata.create_all(eng)
    set_engine(eng)
    with SessionLocal() as db:
        seed_all(db, demo=True, admin_password="Admin@2026pass")
        db.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def client(engine):
    from backend.main import create_app
    return TestClient(create_app())


@pytest.fixture()
def db(engine):
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


_tokens: dict[str, str] = {}


def login(client: TestClient, username: str, password: str = DEMO_PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def H(client):
    """Auth headers per demo user: H['cfo'], H['fm'], ..."""
    cache: dict[str, dict] = {}

    class _H(dict):
        def __missing__(self, user):
            pwd = "Admin@2026pass" if user == "admin" else DEMO_PASSWORD
            cache[user] = login(client, user, pwd)
            return cache[user]
    return _H()
