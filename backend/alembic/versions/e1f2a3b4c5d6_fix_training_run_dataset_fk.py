"""Align training_runs.dataset_id deletion behavior with the ORM model.

The ORM intentionally keeps training-run traceability when a dataset is
deleted, so the nullable reference is set to NULL rather than blocking the
delete. This migration is PostgreSQL-only because SQLite's disposable test
schema does not retain a named FK for this column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dataset_fk(bind):
    for constraint in sa.inspect(bind).get_foreign_keys("training_runs"):
        if (
            constraint.get("constrained_columns") == ["dataset_id"]
            and constraint.get("referred_table") == "training_datasets"
        ):
            return constraint.get("name")
    return None


def _replace_dataset_fk(ondelete: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    constraint_name = _dataset_fk(bind)
    if not constraint_name:
        return

    op.drop_constraint(constraint_name, "training_runs", type_="foreignkey")
    op.create_foreign_key(
        constraint_name,
        "training_runs",
        "training_datasets",
        ["dataset_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _replace_dataset_fk("SET NULL")


def downgrade() -> None:
    _replace_dataset_fk("RESTRICT")
