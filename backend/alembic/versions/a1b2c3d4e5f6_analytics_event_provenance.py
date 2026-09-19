"""analytics event provenance: is_mock + synced_at

Adds the two columns the analytics tab needs to be honest about its numbers:
whether an event came from the mock adapter, and when it was last refreshed
from the platform.

Revision ID: a1b2c3d4e5f6
Revises: 506f2a01bec2
Create Date: 2026-09-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "506f2a01bec2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analytics_events",
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "analytics_events",
        sa.Column("synced_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analytics_events", "synced_at")
    op.drop_column("analytics_events", "is_mock")
