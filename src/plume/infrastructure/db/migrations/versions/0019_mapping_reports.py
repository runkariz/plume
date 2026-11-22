"""Mapping reports (wrong / missing canonical-model mappings reported by a reader's LLM), their
notes, and the verified mappings maintainers accept from them.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mapping_reports (
            report_id text PRIMARY KEY,
            concept text NOT NULL,
            concept_name text NOT NULL,
            model_id text,
            api text NOT NULL,
            build_id text,
            canonical_field text NOT NULL,
            field_key text NOT NULL,
            kind text NOT NULL,
            problem text NOT NULL,
            current_mapping text,
            suggestion jsonb,
            suggestion_status text NOT NULL DEFAULT 'none',
            validator_reason text,
            status text NOT NULL DEFAULT 'open',
            reason text,
            route text,
            report_count integer NOT NULL DEFAULT 1,
            note_count integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            client_name text,
            session_hash text,
            redactions smallint NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX mapping_reports_key ON mapping_reports (concept, api, field_key, kind)"
    )
    op.execute("CREATE INDEX mapping_reports_status ON mapping_reports (api, status)")
    op.execute("CREATE INDEX mapping_reports_session ON mapping_reports (session_hash, created_at)")
    op.execute(
        """
        CREATE TABLE mapping_report_notes (
            note_id text PRIMARY KEY,
            report_id text NOT NULL REFERENCES mapping_reports(report_id) ON DELETE CASCADE,
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
    op.execute(
        "CREATE INDEX mapping_report_notes_report ON mapping_report_notes (report_id, created_at)"
    )
    op.execute(
        "CREATE INDEX mapping_report_notes_session "
        "ON mapping_report_notes (session_hash, created_at)"
    )
    op.execute(
        """
        CREATE TABLE verified_mappings (
            mapping_id text PRIMARY KEY,
            concept text NOT NULL,
            canonical_field text NOT NULL,
            field_key text NOT NULL,
            api text NOT NULL,
            suggestion jsonb NOT NULL,
            build_id text NOT NULL,
            report_id text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            suspended_reason text,
            accepted_at timestamptz NOT NULL,
            revalidated_at timestamptz NOT NULL,
            UNIQUE (concept, field_key, api)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS verified_mappings")
    op.execute("DROP TABLE IF EXISTS mapping_report_notes")
    op.execute("DROP TABLE IF EXISTS mapping_reports")
