"""Eval results, maintainer jobs and their events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE evals (
            build_id       text PRIMARY KEY REFERENCES builds(build_id) ON DELETE CASCADE,
            api_id         text NOT NULL REFERENCES apis(api_id),
            gold_hash      text NOT NULL,
            metrics        jsonb NOT NULL,
            passed         boolean NOT NULL,
            message        text NOT NULL,
            baseline_build text,
            details        jsonb NOT NULL DEFAULT '[]',
            evaluated_at   timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jobs (
            job_id       text PRIMARY KEY,
            status       text NOT NULL,
            api_id       text,
            display_name text,
            tag          text NOT NULL DEFAULT 'latest',
            package_path text NOT NULL,
            package      jsonb NOT NULL,
            diff         jsonb,
            plan         jsonb,
            eval         jsonb,
            live_build   text,
            staged_build text,
            error        text,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE job_events (
            seq        bigserial PRIMARY KEY,
            job_id     text NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            payload    jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX job_events_job ON job_events (job_id, seq)")


def downgrade() -> None:
    for table in ("job_events", "jobs", "evals"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
