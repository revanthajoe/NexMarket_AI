"""phase 6 sentiment provenance

Revision ID: 59cf09e73ad8
Revises: e0f460a59703
Create Date: 2026-09-25 22:18:30.988474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59cf09e73ad8'
down_revision: Union[str, None] = 'e0f460a59703'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for column in (
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("input_source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(100), nullable=True),
            sa.Column("source_reference", sa.String(500), nullable=True),
            sa.Column("model_name", sa.String(200), nullable=True),
            sa.Column("model_version", sa.String(100), nullable=True),
            sa.Column("model_version_id", sa.String(36), nullable=True),
        ):
            op.add_column("sentiment_results", column)
        op.create_foreign_key(
            "fk_sentiment_results_model_version_id",
            "sentiment_results",
            "model_versions",
            ["model_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
    else:
        with op.batch_alter_table("sentiment_results", recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("source_type", sa.String(length=20), nullable=False, server_default="UNKNOWN")
            )
            batch_op.add_column(
                sa.Column("input_source_type", sa.String(length=20), nullable=False, server_default="UNKNOWN")
            )
            batch_op.add_column(sa.Column("source_system", sa.String(length=100), nullable=True))
            batch_op.add_column(sa.Column("source_reference", sa.String(length=500), nullable=True))
            batch_op.add_column(sa.Column("model_name", sa.String(length=200), nullable=True))
            batch_op.add_column(sa.Column("model_version", sa.String(length=100), nullable=True))
            batch_op.add_column(sa.Column("model_version_id", sa.String(length=36), nullable=True))
            batch_op.create_foreign_key(
                "fk_sentiment_results_model_version_id",
                "model_versions",
                ["model_version_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_sentiment_results_model_version_id",
            "sentiment_results",
            type_="foreignkey",
        )
        for column in (
            "model_version_id",
            "model_version",
            "model_name",
            "source_reference",
            "source_system",
            "input_source_type",
            "source_type",
        ):
            op.drop_column("sentiment_results", column)
    else:
        with op.batch_alter_table("sentiment_results", recreate="always") as batch_op:
            batch_op.drop_column("model_version_id")
            batch_op.drop_column("model_version")
            batch_op.drop_column("model_name")
            batch_op.drop_column("source_reference")
            batch_op.drop_column("source_system")
            batch_op.drop_column("input_source_type")
            batch_op.drop_column("source_type")
