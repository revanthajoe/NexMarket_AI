"""
Test-only database isolation.

Without this, pytest hits the exact same nexmarket.db the dev server reads and
writes. Confirmed damage: 389 "Test Summer Sale" campaigns (the literal fixture
payload below) accumulated in the real dev database from running this suite
repeatedly, which pushed every real campaign out of the dashboard's
`GET /campaigns/` (ORDER BY created_at DESC LIMIT 100) — nothing was deleted or
corrupted, the real rows were simply outside the window a LIMIT 100 query
returns once 389 newer test rows existed.

This is plain module-level code, not a fixture, and that's deliberate: pytest
imports every conftest.py in a directory *before* collecting test modules in
it, so the env var below is set before test_main.py's `from app.main import
app` ever runs. `app.core.config.get_settings()` is `@lru_cache`d and
`app.db.session` builds its engine from that settings object at import time —
so this only works if it happens here, first, not inside a fixture that could
run after something has already imported `app.core.config`.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TEST_DB_PATH = Path(tempfile.gettempdir()) / "nexmarket_test.db"


def _remove_db_files() -> None:
    """
    Best-effort delete of the test db + its WAL/SHM sidecars.

    Must never raise: confirmed live that SQLite (WAL mode) can still hold the
    main file open at `pytest_sessionfinish` time even after the engine
    disposes its connections, which raised `PermissionError` there — an
    unhandled exception from a pytest hook is a bad way to fail a green run.
    Broadened past the original `FileNotFoundError`-only catch to any OSError.
    """
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(f"{_TEST_DB_PATH}{suffix}").unlink()
        except OSError:
            pass


_remove_db_files()  # best-effort; see _sessions_finish note on why this can't be relied on
os.environ["SQLITE_DB_PATH"] = str(_TEST_DB_PATH)
# Tests must not publish to real integrations just because a developer's local
# .env enables live mode. Individual live-adapter tests monkeypatch the adapter.
os.environ["SOCIAL_MODE"] = "mock"

# Import AFTER the env override above, and this is deliberately the first
# import of anything under `app.*` in the whole test process — it's what
# locks in the test database path for every engine/session built afterward.
from app.core.config import settings  # noqa: E402
from app.db.session import Base       # noqa: E402
import app.models.models              # noqa: E402,F401

# app.main's lifespan normally creates the schema (see app/main.py), but that
# only fires on a real ASGI startup event. AsyncClient(transport=ASGITransport
# (app=app)) never sends one, so the schema has to be created here instead —
# a fresh test database file otherwise has zero tables and every test fails
# with "no such table". Base.metadata.create_all is plain SQLAlchemy Core, so
# a throwaway *sync* engine does this without touching asyncio at all.
#
# `import app.models.models` above is load-bearing, not decoration: Base
# starts with empty metadata until the modules defining its subclasses
# (Campaign, Poster, ...) are actually imported somewhere. Without this line,
# create_all() below silently creates zero tables — no error, just an empty
# schema — because nothing had registered any table with Base.metadata yet.
#
# The path is resolved via Settings._sqlite_path() (.resolve().as_posix())
# rather than str(_TEST_DB_PATH) directly, so this engine's URL matches the
# app's own engine exactly — a raw Windows backslash path embedded in a
# "sqlite:///..." URL can parse differently than the resolved posix path.
#
# drop_all() before create_all(), not create_all() alone: the file-delete
# above is best-effort and can fail (confirmed: SQLite/WAL can hold the file
# open past process exit). If a previous run's file survives, drop_all wipes
# its tables and data so this run always starts from a genuinely empty
# schema regardless of whether the unlink above succeeded.
from sqlalchemy import create_engine

_sync_engine = create_engine(f"sqlite:///{settings._sqlite_path()}")
Base.metadata.drop_all(_sync_engine)
Base.metadata.create_all(_sync_engine)


@pytest.fixture(autouse=True)
def isolate_test_database():
    """Give every test a clean schema so ordering cannot leak persisted rows."""
    Base.metadata.drop_all(_sync_engine)
    Base.metadata.create_all(_sync_engine)
    yield


_sync_engine.dispose()


def pytest_sessionfinish(session, exitstatus) -> None:
    """Remove the throwaway test database once the whole run finishes."""
    _remove_db_files()
