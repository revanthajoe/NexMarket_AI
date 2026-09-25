"""phase 3 model metadata foundation"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6d592efdd9fe"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "model_metadata" not in existing_tables:
        op.create_table(
            "model_metadata",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False, unique=True),
            sa.Column("model_type", sa.String(50), nullable=False),
            sa.Column("framework", sa.String(100)),
            sa.Column("description", sa.Text()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if "model_versions" not in existing_tables:
        op.create_table(
            "model_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("model_id", sa.String(36), sa.ForeignKey("model_metadata.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.String(100), nullable=False),
            sa.Column("artifact_path", sa.String(1000)),
            sa.Column("artifact_hash", sa.String(64)),
            sa.Column("source", sa.String(50), nullable=False, server_default="UNKNOWN"),
            sa.Column("framework", sa.String(100)),
            sa.Column("configuration", sa.JSON()),
            sa.Column("status", sa.String(20), nullable=False, server_default="REGISTERED"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("model_id", "version", name="uq_model_version"),
        )
    if "training_datasets" not in existing_tables:
        op.create_table(
            "training_datasets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("version", sa.String(100), nullable=False),
            sa.Column("source", sa.String(50), nullable=False, server_default="UNKNOWN"),
            sa.Column("description", sa.Text()),
            sa.Column("record_count", sa.Integer()),
            sa.Column("data_hash", sa.String(64)),
            sa.Column("provenance_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("status", sa.String(20), nullable=False, server_default="REGISTERED"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("name", "version", name="uq_training_dataset_version"),
        )
    if "training_runs" not in existing_tables:
        op.create_table(
            "training_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("model_id", sa.String(36), sa.ForeignKey("model_metadata.id", ondelete="CASCADE"), nullable=False),
            sa.Column("dataset_id", sa.String(36), sa.ForeignKey("training_datasets.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("output_model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="SET NULL")),
            sa.Column("started_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("status", sa.String(20), nullable=False, server_default="REGISTERED"),
            sa.Column("configuration", sa.JSON()),
            sa.Column("metrics_summary", sa.JSON()),
        )
    if "model_validations" not in existing_tables:
        op.create_table(
            "model_validations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("validation_dataset_id", sa.String(36), sa.ForeignKey("training_datasets.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(20), nullable=False, server_default="REGISTERED"),
            sa.Column("validated_at", sa.DateTime()),
            sa.Column("metrics", sa.JSON()),
            sa.Column("baseline_comparison", sa.JSON()),
            sa.Column("approval_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
        )

    for table in ("poster_evaluations", "ad_copies", "lead_scores", "engagement_forecasts"):
        inspector = sa.inspect(bind)
        columns = {column["name"] for column in inspector.get_columns(table)}
        foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table)}
        constraint_name = f"fk_{table}_model_version_id"
        if "model_version_id" not in columns or constraint_name not in foreign_keys:
            with op.batch_alter_table(table, recreate="always") as batch:
                if "model_version_id" not in columns:
                    batch.add_column(sa.Column("model_version_id", sa.String(36), nullable=True))
                if constraint_name not in foreign_keys:
                    batch.create_foreign_key(
                        constraint_name,
                        "model_versions",
                        ["model_version_id"],
                        ["id"],
                        ondelete="SET NULL",
                    )


def downgrade() -> None:
    for table in ("poster_evaluations", "ad_copies", "lead_scores", "engagement_forecasts"):
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(f"fk_{table}_model_version_id", type_="foreignkey")
            batch.drop_column("model_version_id")
    op.drop_table("model_validations")
    op.drop_table("training_runs")
    op.drop_table("training_datasets")
    op.drop_table("model_versions")
    op.drop_table("model_metadata")
