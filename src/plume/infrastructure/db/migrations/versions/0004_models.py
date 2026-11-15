"""Canonical-model sessions and immutable snapshots.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_sessions (
            session_id text PRIMARY KEY,
            concept    text NOT NULL,
            inputs     jsonb NOT NULL,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_snapshots (
            snapshot_id       text PRIMARY KEY,
            session_id        text NOT NULL REFERENCES model_sessions(session_id),
            concept           text NOT NULL,
            apis              text[] NOT NULL,
            inputs            jsonb NOT NULL,
            model             jsonb NOT NULL,
            citations_checked integer NOT NULL,
            prompt_version    text NOT NULL,
            created_at        timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX model_snapshots_apis ON model_snapshots USING gin (apis)")
    # Snapshots are immutable: refuse UPDATE at the database level too.
    op.execute(
        """
        CREATE FUNCTION plume_refuse_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'model snapshots are immutable'; END $$
        """
    )
    op.execute(
        "CREATE TRIGGER model_snapshots_immutable BEFORE UPDATE ON model_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION plume_refuse_update()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_snapshots")
    op.execute("DROP FUNCTION IF EXISTS plume_refuse_update()")
    op.execute("DROP TABLE IF EXISTS model_sessions")
