"""Collections remember the newest version saved INTO them (not a stranger's later version).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL for items saved before this (old owner keys): those list the lineage's latest
    # version, as before.
    op.execute("ALTER TABLE collection_items ADD COLUMN version_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE collection_items DROP COLUMN version_id")
