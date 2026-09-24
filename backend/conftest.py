"""Test database guard.

This root conftest is loaded by pytest before any test module under backend/
is collected, so it runs before anything imports app.database (which builds
its engine from DATABASE_URL at import time). It points DATABASE_URL at
TEST_DATABASE_URL and refuses to run if that is missing or is the production
database.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_BACKEND_DIR = Path(__file__).resolve().parent


def _db_identity(url: str) -> tuple:
    parsed = make_url(url.strip())
    return (parsed.username, parsed.host, parsed.port, parsed.database)


_test_url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(_BACKEND_DIR / ".env.test").get(
    "TEST_DATABASE_URL"
)
if not _test_url:
    raise pytest.UsageError(
        "TEST_DATABASE_URL is not set (env var or backend/.env.test). "
        "Refusing to run tests against the production database."
    )

_production_urls = [
    url
    for url in (
        os.environ.get("DATABASE_URL"),
        dotenv_values(_BACKEND_DIR / ".env").get("DATABASE_URL"),
    )
    if url
]
if any(_db_identity(_test_url) == _db_identity(url) for url in _production_urls):
    raise pytest.UsageError(
        "TEST_DATABASE_URL points at the same database as the production DATABASE_URL. "
        "Refusing to run tests."
    )

os.environ["DATABASE_URL"] = _test_url

from app.database import engine  # noqa: E402

# Defense in depth: fails if app.database was somehow imported earlier with
# another URL.
if _db_identity(engine.url.render_as_string(hide_password=False)) != _db_identity(_test_url):
    raise pytest.UsageError("app.database engine is not bound to TEST_DATABASE_URL. Refusing to run tests.")
