"""Disposable migration-chain regression tests."""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


def test_complete_migration_chain_on_disposable_sqlite(tmp_path):
    database_path = tmp_path / "migration_regression.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    async_database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "development",
            "DATABASE_URL": async_database_url,
            "SYNC_DATABASE_URL": database_url,
            "USE_SQLITE_FALLBACK": "false",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    engine = create_engine(database_url)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "e1f2a3b4c5d6"
        assert len(inspector.get_table_names()) >= 20
        assert "analytics_events" in inspector.get_table_names()
        assert "ad_copies" in inspector.get_table_names()

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stderr

    upgrade_again = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade_again.returncode == 0, upgrade_again.stderr

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "e1f2a3b4c5d6"
