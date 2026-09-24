"""Test database guard.

This root conftest is loaded by pytest before any test module under backend/
is collected, so it runs before anything imports app.database (which builds
its engine from DATABASE_URL at import time).

Normal mode: points DATABASE_URL at TEST_DATABASE_URL and refuses to run if
that is missing or is the production database.

No-DB mode (PP_NO_DB=1): points DATABASE_URL at an unreachable dummy URL and
skips every test marked `db`. The rest of the suite runs normally.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_BACKEND_DIR = Path(__file__).resolve().parent

NO_DB = os.environ.get("PP_NO_DB") == "1"
# ".invalid" never resolves, so any accidental connection fails immediately.
NO_DB_DUMMY_URL = "postgresql+psycopg://pp_no_db@pp-no-db.invalid:5432/pp_no_db?connect_timeout=1"
DB_FIXTURES = {"db_session", "test_portfolio", "fake_market"}

# A manual connection-check script, not a test: importing it opens a DB connection.
collect_ignore = ["test_db.py"]


def _db_identity(url: str) -> tuple:
    parsed = make_url(url.strip())
    return (parsed.username, parsed.host, parsed.port, parsed.database)


_production_urls = [
    url
    for url in (
        os.environ.get("DATABASE_URL"),
        dotenv_values(_BACKEND_DIR / ".env").get("DATABASE_URL"),
    )
    if url
]

if NO_DB:
    _expected_url = NO_DB_DUMMY_URL
else:
    _test_url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(_BACKEND_DIR / ".env.test").get(
        "TEST_DATABASE_URL"
    )
    if not _test_url:
        raise pytest.UsageError(
            "TEST_DATABASE_URL is not set (env var or backend/.env.test). "
            "Refusing to run tests against the production database. "
            "Set PP_NO_DB=1 to run only the tests that need no database."
        )
    if any(_db_identity(_test_url) == _db_identity(url) for url in _production_urls):
        raise pytest.UsageError(
            "TEST_DATABASE_URL points at the same database as the production DATABASE_URL. "
            "Refusing to run tests."
        )
    _expected_url = _test_url

os.environ["DATABASE_URL"] = _expected_url

from app.database import engine  # noqa: E402

# Defense in depth: fails if app.database was somehow imported earlier with
# another URL, and never allows an engine bound to production.
_engine_identity = _db_identity(engine.url.render_as_string(hide_password=False))
if _engine_identity != _db_identity(_expected_url) or any(
    _engine_identity == _db_identity(url) for url in _production_urls
):
    raise pytest.UsageError("app.database engine is not bound to the expected test URL. Refusing to run tests.")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "db: needs the test database (TEST_DATABASE_URL); skipped when PP_NO_DB=1"
    )


def pytest_collection_modifyitems(config, items):
    unmarked = [
        item.nodeid
        for item in items
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())) and item.get_closest_marker("db") is None
    ]
    if unmarked:
        raise pytest.UsageError(
            "These tests use a database fixture but are not marked @pytest.mark.db:\n  "
            + "\n  ".join(unmarked)
        )

    if NO_DB:
        skip = pytest.mark.skip(reason="PP_NO_DB=1: database tests skipped")
        for item in items:
            if item.get_closest_marker("db") is not None:
                item.add_marker(skip)
