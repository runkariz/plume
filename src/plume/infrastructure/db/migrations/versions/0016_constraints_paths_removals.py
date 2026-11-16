"""Field value constraints on facts (enum, minimum, maximum, default, format, pattern, ...),
verbatim from the package schemas as JSON text; an endpoint's real path when the package fixes
its API version; its rate limit (bucket, cost, group); an audit row per removed API.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE facts ADD COLUMN constraints text")
    op.execute("ALTER TABLE documents ADD COLUMN real_path text")
    op.execute("ALTER TABLE documents ADD COLUMN rate_limit text")
    op.execute(
        """
        CREATE TABLE api_removals (
            id         bigserial PRIMARY KEY,
            api_id     text NOT NULL,
            removed_at timestamptz NOT NULL DEFAULT now(),
            forced     boolean NOT NULL,
            reason     text,
            counts     jsonb NOT NULL,
            affected   jsonb NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE api_removals")
    op.execute("ALTER TABLE documents DROP COLUMN rate_limit")
    op.execute("ALTER TABLE documents DROP COLUMN real_path")
    op.execute("ALTER TABLE facts DROP COLUMN constraints")
