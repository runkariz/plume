"""A model released over a failing model gold gate keeps the maintainer's reason and the
failures it overrode.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE model_snapshots ADD COLUMN release_override jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE model_snapshots DROP COLUMN IF EXISTS release_override")
