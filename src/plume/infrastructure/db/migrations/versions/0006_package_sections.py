"""Package sections: documents keep the package's source JSON (raw) and tags; build assets
(the package's own icon) are stored with the build.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN raw jsonb")
    op.execute("ALTER TABLE documents ADD COLUMN tags text[] NOT NULL DEFAULT '{}'")
    op.execute("CREATE INDEX documents_tags ON documents USING gin (tags)")
    op.execute(
        """
        CREATE TABLE build_assets (
            build_id     text NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
            name         text NOT NULL,
            content_type text NOT NULL,
            data         bytea NOT NULL,
            sha256       text NOT NULL,
            source       text NOT NULL,
            PRIMARY KEY (build_id, name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS build_assets")
    op.execute("DROP INDEX IF EXISTS documents_tags")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS raw")
