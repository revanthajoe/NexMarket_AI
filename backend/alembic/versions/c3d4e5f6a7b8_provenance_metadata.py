"""phase 1 provenance metadata

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    additions = {
        "poster_evaluations": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(100), nullable=True),
            sa.Column("model_name", sa.String(200), nullable=True),
            sa.Column("model_version", sa.String(100), nullable=True),
            sa.Column("is_fallback", sa.Boolean(), nullable=True),
        ],
        "ad_copies": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(100), nullable=True),
            sa.Column("model_name", sa.String(200), nullable=True),
            sa.Column("model_version", sa.String(100), nullable=True),
        ],
        "analytics_events": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(100), nullable=True),
            sa.Column("source_reference", sa.String(500), nullable=True),
        ],
        "lead_scores": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_system", sa.String(100), nullable=True),
            sa.Column("model_name", sa.String(200), nullable=True),
            sa.Column("model_version", sa.String(100), nullable=True),
            sa.Column("is_fallback", sa.Boolean(), nullable=True),
        ],
        "engagement_forecasts": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("history_source", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("source_reference", sa.String(500), nullable=True),
            sa.Column("is_fallback", sa.Boolean(), nullable=True),
        ],
        "optimization_results": [
            sa.Column("source_type", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("algorithm", sa.String(200), nullable=True),
            sa.Column("policy_version", sa.String(100), nullable=True),
            sa.Column("reward_source", sa.String(20), nullable=True),
            sa.Column("analytics_reference", sa.String(500), nullable=True),
        ],
    }
    for table, columns in additions.items():
        for column in columns:
            op.add_column(table, column)

    op.execute("UPDATE analytics_events SET source_type='SIMULATED' WHERE is_mock = 1")
    op.execute("UPDATE ad_copies SET source_type='FALLBACK' WHERE fallback = 1")


def downgrade() -> None:
    for table, columns in {
        "optimization_results": ["analytics_reference", "reward_source", "policy_version", "algorithm", "source_type"],
        "engagement_forecasts": ["is_fallback", "source_reference", "history_source", "source_type"],
        "lead_scores": ["is_fallback", "model_version", "model_name", "source_system", "source_type"],
        "analytics_events": ["source_reference", "source_system", "source_type"],
        "ad_copies": ["model_version", "model_name", "source_system", "source_type"],
        "poster_evaluations": ["is_fallback", "model_version", "model_name", "source_system", "source_type"],
    }.items():
        for column in columns:
            op.drop_column(table, column)