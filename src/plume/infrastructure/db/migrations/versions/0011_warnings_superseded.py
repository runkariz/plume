"""Validation warnings on model snapshots; superseded official models.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not in the immutability trigger's column list: warnings are written once with the insert;
    # superseded_by / superseded_at change with the visibility, like released_at.
    op.execute(
        "ALTER TABLE model_snapshots ADD COLUMN warnings jsonb, "
        "ADD COLUMN superseded_by text, ADD COLUMN superseded_at timestamptz"
    )
    op.execute("ALTER TABLE model_snapshots DROP CONSTRAINT model_snapshots_visibility")
    op.execute(
        "ALTER TABLE model_snapshots ADD CONSTRAINT model_snapshots_visibility CHECK "
        "(visibility IN ('official', 'unreleased', 'unlisted', 'discarded', 'superseded'))"
    )


def downgrade() -> None:
    op.execute("UPDATE model_snapshots SET visibility = 'official' WHERE visibility = 'superseded'")
    op.execute("ALTER TABLE model_snapshots DROP CONSTRAINT model_snapshots_visibility")
    op.execute(
        "ALTER TABLE model_snapshots ADD CONSTRAINT model_snapshots_visibility CHECK "
        "(visibility IN ('official', 'unreleased', 'unlisted', 'discarded'))"
    )
    op.execute(
        "ALTER TABLE model_snapshots DROP COLUMN superseded_at, DROP COLUMN superseded_by, "
        "DROP COLUMN warnings"
    )
