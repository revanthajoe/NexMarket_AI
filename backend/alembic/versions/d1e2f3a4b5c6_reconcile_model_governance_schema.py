"""Reconcile model-governance tables with the current ORM models.

This migration is retained as the prior schema-reconciliation migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "a7d9f2c4e681"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _unique_constraint_names(bind, table_name: str) -> set[str]:
    return {constraint["name"] for constraint in sa.inspect(bind).get_unique_constraints(table_name)}


def _upgrade_postgresql() -> None:
    bind = op.get_bind()
    now = sa.func.now()
    inspector = sa.inspect(bind)

    op.execute(sa.text("UPDATE model_metadata SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE model_metadata SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
    op.execute(sa.text("UPDATE model_versions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE social_comments SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    if "uq_model_metadata_name" not in _unique_constraint_names(bind, "model_metadata"):
        op.create_unique_constraint("uq_model_metadata_name", "model_metadata", ["name"])
    op.alter_column("model_metadata", "created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
    op.alter_column("model_metadata", "updated_at", existing_type=sa.DateTime(), nullable=False, server_default=now)

    op.alter_column("model_versions", "artifact_hash", existing_type=sa.String(64), type_=sa.String(128))
    op.alter_column("model_versions", "created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
    unique_names = _unique_constraint_names(bind, "model_versions")
    if "uq_model_version" in unique_names:
        op.drop_constraint("uq_model_version", "model_versions", type_="unique")
    if "uq_model_versions_model_version" not in unique_names:
        op.create_unique_constraint("uq_model_versions_model_version", "model_versions", ["model_id", "version"])

    op.add_column("model_validations", sa.Column("created_at", sa.DateTime(), server_default=now, nullable=False))
    op.alter_column("model_validations", "approval_status", existing_type=sa.String(20), nullable=True)
    op.alter_column("social_comments", "created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)

    dataset_columns = {column["name"] for column in inspector.get_columns("training_datasets")}
    if "provenance_policy" not in dataset_columns:
        op.add_column("training_datasets", sa.Column("provenance_policy", sa.String(50), nullable=True))
    op.alter_column("training_datasets", "data_hash", existing_type=sa.String(64), type_=sa.String(128))
    op.alter_column("training_datasets", "created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
    unique_names = _unique_constraint_names(bind, "training_datasets")
    if "uq_training_dataset_version" in unique_names:
        op.drop_constraint("uq_training_dataset_version", "training_datasets", type_="unique")
    if "uq_training_datasets_name_version" not in unique_names:
        op.create_unique_constraint("uq_training_datasets_name_version", "training_datasets", ["name", "version"])
    if "provenance_status" in dataset_columns:
        op.drop_column("training_datasets", "provenance_status")

    op.add_column("training_runs", sa.Column("created_at", sa.DateTime(), server_default=now, nullable=False))
    op.alter_column("training_runs", "dataset_id", existing_type=sa.String(36), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()
    now = sa.func.now()

    if bind.dialect.name == "postgresql":
        _upgrade_postgresql()
        return

    op.execute(sa.text("UPDATE model_metadata SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE model_metadata SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
    op.execute(sa.text("UPDATE model_versions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.execute(sa.text("UPDATE social_comments SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    with op.batch_alter_table("model_metadata", recreate="always") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
        if "uq_model_metadata_name" not in _unique_constraint_names(bind, "model_metadata"):
            batch.create_unique_constraint("uq_model_metadata_name", ["name"])

    with op.batch_alter_table("model_versions", recreate="always") as batch:
        batch.alter_column("artifact_hash", existing_type=sa.String(length=64), type_=sa.String(length=128))
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
        unique_names = _unique_constraint_names(bind, "model_versions")
        if "uq_model_version" in unique_names:
            batch.drop_constraint("uq_model_version", type_="unique")
        if "uq_model_versions_model_version" not in unique_names:
            batch.create_unique_constraint("uq_model_versions_model_version", ["model_id", "version"])

    with op.batch_alter_table("model_validations", recreate="always") as batch:
        batch.add_column(sa.Column("created_at", sa.DateTime(), server_default=now, nullable=False))
        batch.alter_column("approval_status", existing_type=sa.String(length=20), nullable=True)

    with op.batch_alter_table("social_comments", recreate="always") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)

    with op.batch_alter_table("training_datasets", recreate="always") as batch:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("training_datasets")}
        if "provenance_policy" not in columns:
            batch.add_column(sa.Column("provenance_policy", sa.String(length=50), nullable=True))
        batch.alter_column("data_hash", existing_type=sa.String(length=64), type_=sa.String(length=128))
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False, server_default=now)
        unique_names = _unique_constraint_names(bind, "training_datasets")
        if "uq_training_dataset_version" in unique_names:
            batch.drop_constraint("uq_training_dataset_version", type_="unique")
        if "uq_training_datasets_name_version" not in unique_names:
            batch.create_unique_constraint("uq_training_datasets_name_version", ["name", "version"])
        if "provenance_status" in columns:
            batch.drop_column("provenance_status")

    with op.batch_alter_table("training_runs", recreate="always") as batch:
        batch.add_column(sa.Column("created_at", sa.DateTime(), server_default=now, nullable=False))
        batch.alter_column("dataset_id", existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        unique_names = _unique_constraint_names(bind, "training_datasets")
        op.alter_column("training_runs", "dataset_id", existing_type=sa.String(36), nullable=False)
        op.drop_column("training_runs", "created_at")
        if "uq_training_datasets_name_version" in unique_names:
            op.drop_constraint("uq_training_datasets_name_version", "training_datasets", type_="unique")
        op.create_unique_constraint("uq_training_dataset_version", "training_datasets", ["name", "version"])
        op.alter_column("training_datasets", "created_at", existing_type=sa.DateTime(), nullable=True)
        op.alter_column("training_datasets", "data_hash", existing_type=sa.String(128), type_=sa.String(64))
        op.drop_column("training_datasets", "provenance_policy")
        op.alter_column("social_comments", "created_at", existing_type=sa.DateTime(), nullable=True)
        op.alter_column("model_validations", "approval_status", existing_type=sa.String(20), nullable=False)
        op.drop_column("model_validations", "created_at")
        unique_names = _unique_constraint_names(bind, "model_versions")
        if "uq_model_versions_model_version" in unique_names:
            op.drop_constraint("uq_model_versions_model_version", "model_versions", type_="unique")
        op.create_unique_constraint("uq_model_version", "model_versions", ["model_id", "version"])
        op.alter_column("model_versions", "created_at", existing_type=sa.DateTime(), nullable=True)
        op.alter_column("model_versions", "artifact_hash", existing_type=sa.String(128), type_=sa.String(64))
        if "uq_model_metadata_name" in _unique_constraint_names(bind, "model_metadata"):
            op.drop_constraint("uq_model_metadata_name", "model_metadata", type_="unique")
        op.alter_column("model_metadata", "updated_at", existing_type=sa.DateTime(), nullable=True)
        op.alter_column("model_metadata", "created_at", existing_type=sa.DateTime(), nullable=True)
        return

    with op.batch_alter_table("training_runs", recreate="always") as batch:
        batch.alter_column("dataset_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("created_at")

    with op.batch_alter_table("training_datasets", recreate="always") as batch:
        columns = {column["name"] for column in sa.inspect(bind).get_columns("training_datasets")}
        if "provenance_status" not in columns:
            batch.add_column(sa.Column("provenance_status", sa.String(length=20), nullable=False, server_default="UNKNOWN"))
        unique_names = _unique_constraint_names(bind, "training_datasets")
        if "uq_training_datasets_name_version" in unique_names:
            batch.drop_constraint("uq_training_datasets_name_version", type_="unique")
        if "uq_training_dataset_version" not in unique_names:
            batch.create_unique_constraint("uq_training_dataset_version", ["name", "version"])
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=True)
        batch.alter_column("data_hash", existing_type=sa.String(length=128), type_=sa.String(length=64))
        if "provenance_policy" in columns:
            batch.drop_column("provenance_policy")

    with op.batch_alter_table("social_comments", recreate="always") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=True)

    with op.batch_alter_table("model_validations", recreate="always") as batch:
        batch.alter_column("approval_status", existing_type=sa.String(length=20), nullable=False)
        batch.drop_column("created_at")

    with op.batch_alter_table("model_versions", recreate="always") as batch:
        unique_names = _unique_constraint_names(bind, "model_versions")
        if "uq_model_versions_model_version" in unique_names:
            batch.drop_constraint("uq_model_versions_model_version", type_="unique")
        if "uq_model_version" not in unique_names:
            batch.create_unique_constraint("uq_model_version", ["model_id", "version"])
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=True)
        batch.alter_column("artifact_hash", existing_type=sa.String(length=128), type_=sa.String(length=64))

    with op.batch_alter_table("model_metadata", recreate="always") as batch:
        unique_names = _unique_constraint_names(bind, "model_metadata")
        if "uq_model_metadata_name" in unique_names:
            batch.drop_constraint("uq_model_metadata_name", type_="unique")
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=True)
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=True)
