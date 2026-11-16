"""Maintainer display names per API (not per build; kept across loads) and where the package's
own name came from (app.json title/displayName: "package"; else "derived").

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE apis ADD COLUMN name_source text NOT NULL DEFAULT 'derived'")
    op.execute(
        """
        CREATE TABLE api_display_names (
            api_id     text PRIMARY KEY,
            name       text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE api_display_names")
    op.execute("ALTER TABLE apis DROP COLUMN name_source")
