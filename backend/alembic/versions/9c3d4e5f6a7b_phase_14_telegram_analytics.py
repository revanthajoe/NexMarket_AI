"""Phase 14 Telegram analytics and comment provenance.

Revision ID: 9c3d4e5f6a7b
Revises: 8b2c3d4e5f6a
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9c3d4e5f6a7b"
down_revision: Union[str, None] = "8b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("social_post_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=100), nullable=False),
        sa.Column("platform_comment_id", sa.String(length=500), nullable=False),
        sa.Column("parent_platform_message_id", sa.String(length=500)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("comment_date", sa.DateTime()),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_system", sa.String(length=100)),
        sa.Column("source_reference", sa.String(length=500)),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["social_post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("social_post_id", "platform_comment_id", name="uq_social_comment_platform_id"),
    )
    with op.batch_alter_table("analytics_events") as batch_op:
        batch_op.add_column(sa.Column("social_post_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("reactions", sa.BigInteger(), nullable=True))
        batch_op.create_foreign_key(
            "fk_analytics_events_social_post_id",
            "social_posts",
            ["social_post_id"],
            ["id"],
            ondelete="SET NULL",
        )
        for column in ("impressions", "clicks", "likes", "shares", "comments", "reach", "ctr", "spend"):
            batch_op.alter_column(column, nullable=True, existing_nullable=False)
    with op.batch_alter_table("sentiment_results") as batch_op:
        batch_op.add_column(sa.Column("social_comment_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_sentiment_results_social_comment_id",
            "social_comments",
            ["social_comment_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("sentiment_results") as batch_op:
        batch_op.drop_constraint("fk_sentiment_results_social_comment_id", type_="foreignkey")
        batch_op.drop_column("social_comment_id")
    with op.batch_alter_table("analytics_events") as batch_op:
        for column in ("impressions", "clicks", "likes", "shares", "comments", "reach", "ctr", "spend"):
            batch_op.alter_column(column, nullable=False, existing_nullable=True)
    with op.batch_alter_table("analytics_events") as batch_op:
        batch_op.drop_constraint("fk_analytics_events_social_post_id", type_="foreignkey")
        batch_op.drop_column("reactions")
        batch_op.drop_column("social_post_id")
    op.drop_table("social_comments")