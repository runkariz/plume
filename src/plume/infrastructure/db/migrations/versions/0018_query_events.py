"""The query log: one row per reader call (redacted; opt-in with PLUME_QUERY_LOG).

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE query_events (
            id bigserial PRIMARY KEY,
            occurred_at timestamptz NOT NULL,
            schema_version smallint NOT NULL DEFAULT 1,
            surface text NOT NULL,
            tool text NOT NULL,
            api text,
            apis text[] NOT NULL DEFAULT '{}',
            build_id text,
            version_requested text,
            query_text text,
            call_method text,
            call_path_template text,
            param_names text[] NOT NULL DEFAULT '{}',
            fact_kind text,
            fact_name text,
            doc_id text,
            top_docs jsonb NOT NULL DEFAULT '[]',
            result_count integer,
            verdict text,
            complete boolean,
            answered_by text,
            error_class text,
            latency_ms integer,
            client_name text,
            session_hash text,
            redactions smallint NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX query_events_occurred_at ON query_events (occurred_at)")
    op.execute("CREATE INDEX query_events_api_occurred_at ON query_events (api, occurred_at)")
    op.execute("CREATE INDEX query_events_session ON query_events (session_hash, occurred_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_events")
