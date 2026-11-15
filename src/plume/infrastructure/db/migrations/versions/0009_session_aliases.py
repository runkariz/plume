"""Accepted aliases (design D2): a concept named differently in one API (WooCommerce "variation"
for "Variant") is searched under that name in that API.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE model_sessions ADD COLUMN aliases jsonb NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE model_set_sessions ADD COLUMN aliases jsonb NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE model_set_sessions DROP COLUMN aliases")
    op.execute("ALTER TABLE model_sessions DROP COLUMN aliases")
