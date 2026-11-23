"""phase 4 poster feedback regeneration

Revision ID: 304fafc34888
Revises: 6d592efdd9fe
Create Date: 2026-09-25 21:40:48.097060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '304fafc34888'
down_revision: Union[str, None] = '6d592efdd9fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    poster_columns = {column["name"] for column in inspector.get_columns("posters")}
    if bind.dialect.name == "postgresql":
        if "parent_poster_id" not in poster_columns:
            op.add_column("posters", sa.Column("parent_poster_id", sa.String(36), nullable=True))
        if "version" not in poster_columns:
            op.add_column("posters", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        if "generation_reason" not in poster_columns:
            op.add_column("posters", sa.Column("generation_reason", sa.String(100), nullable=True))
        if "improvement_instruction" not in poster_columns:
            op.add_column("posters", sa.Column("improvement_instruction", sa.Text(), nullable=True))
        if "fk_posters_parent_poster_id" not in {
            fk["name"] for fk in inspector.get_foreign_keys("posters")
        }:
            op.create_foreign_key(
                "fk_posters_parent_poster_id", "posters", "posters",
                ["parent_poster_id"], ["id"], ondelete="SET NULL",
            )
    else:
        with op.batch_alter_table("posters", recreate="always") as batch_op:
            if "parent_poster_id" not in poster_columns:
                batch_op.add_column(sa.Column("parent_poster_id", sa.String(length=36), nullable=True))
            if "version" not in poster_columns:
                batch_op.add_column(
                    sa.Column("version", sa.Integer(), nullable=False, server_default="1")
                )
            if "generation_reason" not in poster_columns:
                batch_op.add_column(sa.Column("generation_reason", sa.String(length=100), nullable=True))
            if "improvement_instruction" not in poster_columns:
                batch_op.add_column(sa.Column("improvement_instruction", sa.Text(), nullable=True))
            if "parent_poster_id" not in poster_columns:
                batch_op.create_foreign_key(
                    "fk_posters_parent_poster_id",
                    "posters",
                    ["parent_poster_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    if "poster_feedback" not in inspector.get_table_names():
        op.create_table(
            "poster_feedback",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("poster_id", sa.String(length=36), nullable=False),
            sa.Column("feedback_type", sa.String(length=50), nullable=False, server_default="QUALITY"),
            sa.Column("feedback_text", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False, server_default="SYSTEM"),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("source_type", sa.String(length=20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(length=100), nullable=True),
            sa.Column("model_name", sa.String(length=200), nullable=True),
            sa.Column("model_version", sa.String(length=100), nullable=True),
            sa.Column("is_fallback", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["poster_id"], ["posters.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "poster_feedback" in inspector.get_table_names():
        op.drop_table("poster_feedback")

    if bind.dialect.name == "postgresql":
        if "fk_posters_parent_poster_id" in {
            fk["name"] for fk in inspector.get_foreign_keys("posters")
        }:
            op.drop_constraint("fk_posters_parent_poster_id", "posters", type_="foreignkey")
        for column in ("improvement_instruction", "generation_reason", "version", "parent_poster_id"):
            if column in {item["name"] for item in inspector.get_columns("posters")}:
                op.drop_column("posters", column)
    else:
        with op.batch_alter_table("posters", recreate="always") as batch_op:
            batch_op.drop_column("improvement_instruction")
            batch_op.drop_column("generation_reason")
            batch_op.drop_column("version")
            batch_op.drop_column("parent_poster_id")
