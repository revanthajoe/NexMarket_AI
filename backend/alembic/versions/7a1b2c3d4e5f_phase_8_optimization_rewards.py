"""phase 8 optimization reward provenance

Revision ID: 7a1b2c3d4e5f
Revises: 59cf09e73ad8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a1b2c3d4e5f"
down_revision: Union[str, None] = "59cf09e73ad8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("optimization_results", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("reward", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("bandit_updated", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("optimization_results", recreate="always") as batch_op:
        batch_op.drop_column("bandit_updated")
        batch_op.drop_column("reward")