"""Reported questions: what a reader's LLM reports Plume could not answer, and notes on them.

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
        CREATE TABLE reported_questions (
            report_id text PRIMARY KEY,
            api text NOT NULL,
            build_id text,
            question text NOT NULL,
            duplicate_key text NOT NULL,
            what_was_tried text,
            what_was_missing text,
            status text NOT NULL DEFAULT 'open',
            reason text,
            report_count integer NOT NULL DEFAULT 1,
            note_count integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            client_name text,
            session_hash text,
            redactions smallint NOT NULL DEFAULT 0,
            embed_model text,
            embedding halfvec
        )
        """
    )
    op.execute("CREATE INDEX reported_questions_api ON reported_questions (api, status)")
    op.execute("CREATE INDEX reported_questions_key ON reported_questions (api, duplicate_key)")
    op.execute(
        "CREATE INDEX reported_questions_session ON reported_questions (session_hash, created_at)"
    )
    op.execute(
        """
        CREATE TABLE report_notes (
            note_id text PRIMARY KEY,
            report_id text NOT NULL REFERENCES reported_questions(report_id) ON DELETE CASCADE,
            kind text NOT NULL DEFAULT 'note',
            text text NOT NULL,
            created_at timestamptz NOT NULL,
            client_name text,
            session_hash text,
            build_id text,
            redactions smallint NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX report_notes_report ON report_notes (report_id, created_at)")
    op.execute("CREATE INDEX report_notes_session ON report_notes (session_hash, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_notes")
    op.execute("DROP TABLE IF EXISTS reported_questions")
