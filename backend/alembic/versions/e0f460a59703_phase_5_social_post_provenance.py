"""phase 5 social post provenance

Revision ID: e0f460a59703
Revises: 304fafc34888
Create Date: 2026-09-25 22:03:44.826238

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0f460a59703'
down_revision: Union[str, None] = '304fafc34888'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.add_column("social_posts", sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"))
        op.add_column("social_posts", sa.Column("source_system", sa.String(100), nullable=True))
    else:
        with op.batch_alter_table("social_posts", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "source_type",
                    sa.String(length=20),
                    nullable=False,
                    server_default="UNKNOWN",
                )
            )
            batch_op.add_column(sa.Column("source_system", sa.String(length=100), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_column("social_posts", "source_system")
        op.drop_column("social_posts", "source_type")
    else:
        with op.batch_alter_table("social_posts", recreate="always") as batch_op:
            batch_op.drop_column("source_system")
            batch_op.drop_column("source_type")
