"""ad copy fallback flag

Adds ad_copies.fallback: True when Qwen's raw output failed to parse as JSON
(twice, after a retry) and the row is the hardcoded English placeholder
template rather than a real generation result — same provenance-flag
convention as analytics_events.is_mock (a1b2c3d4e5f6). Without this, a failed
non-English ad copy request was indistinguishable from a real translated one:
the placeholder slots real campaign data into fake copy, in the wrong
language, and reads as plausible.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ad_copies",
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ad_copies", "fallback")
