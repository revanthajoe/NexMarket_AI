"""
SQLAlchemy async engine + session factory.
Use get_db() as a FastAPI dependency in every endpoint.

SQLite note:
  aiosqlite does NOT support concurrent writers with the default journal mode.
  We use NullPool so every session gets a fresh connection (no connection pooling
  between concurrent coroutines), and enable WAL mode so readers never block
  writers and vice-versa.

  The pragmas are configured **per connection, at the engine**, never per session.
  `busy_timeout` is a connection-scoped setting that does not persist, and with
  NullPool a Session *closes* its DBAPI connection when it releases it at the end
  of a transaction — so a session that commits and then writes again is running on
  a brand-new, unconfigured connection. Setting the pragmas inside get_db() looked
  correct and silently left every post-commit write at busy_timeout=0, which is
  exactly how "database is locked" surfaced on the poster INSERT.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── Engine kwargs ─────────────────────────────────────────────────────────────

engine_kwargs: dict = {
    "echo": settings.APP_ENV == "development",
}

if settings.is_sqlite:
    # NullPool: every connection is created fresh and closed immediately.
    # This is the only safe option for aiosqlite with concurrent coroutines.
    from sqlalchemy.pool import NullPool
    engine_kwargs["poolclass"] = NullPool
    # sqlite3.connect(timeout=...) sets the busy timeout in C, before any SQL can
    # run on the connection. Belt and braces alongside the PRAGMA below: this one
    # cannot be lost, skipped, or overwritten by a later statement.
    engine_kwargs["connect_args"] = {"timeout": 30.0}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.effective_database_url, **engine_kwargs)


if settings.is_sqlite:
    # Fires for EVERY new DBAPI connection — request sessions, the posting
    # worker's loops, background tasks, tests. Attached to `sync_engine` because
    # AsyncEngine itself does not emit the core "connect" event.
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            # 30s, not 5s: AI endpoints interleave with the posting worker and
            # analytics sync, and multi-second waits for the single SQLite
            # writer are normal here.
            cursor.execute("PRAGMA busy_timeout=30000")
            # OFF is SQLite's default, which makes every ON DELETE CASCADE /
            # SET NULL declared on the models' ForeignKeys purely decorative —
            # confirmed for real: deleting a campaign left its posters/ad
            # copies/etc behind as orphans (found 16+ of them accumulated from
            # past deletes). Must be set per-connection, same as the pragmas
            # above, for the same NullPool-churn reason.
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # No PRAGMAs here — see the module docstring. They are applied on connect, so
    # they survive the connection churn that NullPool causes at every commit.
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
