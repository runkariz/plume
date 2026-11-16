"""Release notes per build (field-level diff against the previous build, its classification and
the maintainer's review) and each build's package extraction metadata.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE release_notes (
            to_build    text PRIMARY KEY,
            api_id      text NOT NULL,
            from_build  text NOT NULL,
            computed_at timestamptz NOT NULL,
            review      text NOT NULL CHECK (review IN ('pending', 'kept', 'rolled_back')),
            body        jsonb NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX release_notes_api ON release_notes (api_id, computed_at DESC)")
    op.execute("CREATE TABLE build_package_meta (build_id text PRIMARY KEY, meta jsonb NOT NULL)")


def downgrade() -> None:
    op.execute("DROP TABLE build_package_meta")
    op.execute("DROP TABLE release_notes")
