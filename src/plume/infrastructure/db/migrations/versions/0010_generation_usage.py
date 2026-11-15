"""Token usage of server-side generation, on the job and on the generated model snapshot.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not in the immutability trigger's column list: it is written once, with the insert.
    op.execute("ALTER TABLE model_snapshots ADD COLUMN generator_usage jsonb")
    op.execute("ALTER TABLE model_jobs ADD COLUMN usage jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE model_jobs DROP COLUMN usage")
    op.execute("ALTER TABLE model_snapshots DROP COLUMN generator_usage")
