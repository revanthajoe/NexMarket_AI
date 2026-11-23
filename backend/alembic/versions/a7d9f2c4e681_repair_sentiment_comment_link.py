"""Repair the sentiment-to-comment link when the database was stamped at head."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7d9f2c4e681"
down_revision: Union[str, None] = "c8cc6a537001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("sentiment_results")}
    foreign_keys = inspector.get_foreign_keys("sentiment_results")
    has_comment_fk = any(
        "social_comment_id" in foreign_key.get("constrained_columns", [])
        for foreign_key in foreign_keys
    )

    if "social_comment_id" in columns and has_comment_fk:
        return

    with op.batch_alter_table("sentiment_results") as batch_op:
        if "social_comment_id" not in columns:
            batch_op.add_column(sa.Column("social_comment_id", sa.String(length=36), nullable=True))
        if not has_comment_fk:
            batch_op.create_foreign_key(
                "fk_sentiment_results_social_comment_id",
                "social_comments",
                ["social_comment_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    # The parent revision already defines this link; this revision repairs only
    # databases whose schema drifted while the Alembic stamp remained current.
    pass