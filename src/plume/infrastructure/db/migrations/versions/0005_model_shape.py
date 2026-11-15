"""documents.shape: structural hash of model schemas (same structure under several names).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN shape text")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN shape")
