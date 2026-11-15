"""Baseline: empty schema.

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No tables yet; the knowledge schema arrives with slice 2."""


def downgrade() -> None:
    """Nothing to undo."""
