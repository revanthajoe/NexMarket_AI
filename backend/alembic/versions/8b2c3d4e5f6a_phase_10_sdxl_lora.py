"""phase 10 SDXL LoRA provenance and dataset manifests"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8b2c3d4e5f6a"
down_revision: Union[str, None] = "7a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    dataset_columns = {column["name"] for column in inspector.get_columns("training_datasets")}
    if "manifest" not in dataset_columns:
        if bind.dialect.name == "postgresql":
            op.add_column("training_datasets", sa.Column("manifest", sa.JSON(), nullable=True))
        else:
            with op.batch_alter_table("training_datasets", recreate="always") as batch_op:
                batch_op.add_column(sa.Column("manifest", sa.JSON(), nullable=True))

    poster_columns = {column["name"] for column in inspector.get_columns("posters")}
    poster_foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("posters")}
    if "model_version_id" not in poster_columns or "fk_posters_model_version_id" not in poster_foreign_keys:
        if bind.dialect.name == "postgresql":
            if "model_version_id" not in poster_columns:
                op.add_column("posters", sa.Column("model_version_id", sa.String(36), nullable=True))
            if "fk_posters_model_version_id" not in poster_foreign_keys:
                op.create_foreign_key(
                    "fk_posters_model_version_id", "posters", "model_versions",
                    ["model_version_id"], ["id"], ondelete="SET NULL",
                )
        else:
            with op.batch_alter_table("posters", recreate="always") as batch_op:
                if "model_version_id" not in poster_columns:
                    batch_op.add_column(sa.Column("model_version_id", sa.String(36), nullable=True))
                if "fk_posters_model_version_id" not in poster_foreign_keys:
                    batch_op.create_foreign_key(
                        "fk_posters_model_version_id",
                        "model_versions",
                        ["model_version_id"],
                        ["id"],
                        ondelete="SET NULL",
                    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_posters_model_version_id", "posters", type_="foreignkey")
        op.drop_column("posters", "model_version_id")
        op.drop_column("training_datasets", "manifest")
    else:
        with op.batch_alter_table("posters", recreate="always") as batch_op:
            batch_op.drop_constraint("fk_posters_model_version_id", type_="foreignkey")
            batch_op.drop_column("model_version_id")
        with op.batch_alter_table("training_datasets", recreate="always") as batch_op:
            batch_op.drop_column("manifest")