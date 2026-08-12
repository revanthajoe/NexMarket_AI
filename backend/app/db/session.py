"""
SQLAlchemy async engine + session factory.
Use get_db() as a FastAPI dependency in every endpoint.

SQLite note:
  aiosqlite does NOT support concurrent writers with the default journal mode.
  We use NullPool so every session gets a fresh connection (no connection pooling
  between concurrent coroutines), and enable WAL mode on startup so readers never
  block writers and vice-versa.
"""
from __future__ import annotations

from typing import AsyncGenerator

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
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.effective_database_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def _enable_wal(conn):
    """Enable Write-Ahead Logging on SQLite — allows concurrent readers + one writer."""
    await conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))
    await conn.execute(__import__("sqlalchemy").text("PRAGMA synchronous=NORMAL"))
    await conn.execute(__import__("sqlalchemy").text("PRAGMA busy_timeout=5000"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        if settings.is_sqlite:
            await session.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))
            await session.execute(__import__("sqlalchemy").text("PRAGMA busy_timeout=5000"))
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
