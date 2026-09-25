"""Compatibility predecessor for the Phase 3 generated revision.

The development database may already be stamped at this revision from an
 earlier local migration attempt. The generated Phase 3 revision performs the
actual schema work and is the current migration head.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
