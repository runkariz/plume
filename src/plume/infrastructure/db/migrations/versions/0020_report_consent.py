"""How the user consented to each stored report and note: elicitation (Plume asked the user
through the MCP client) or llm_attested (the client's LLM showed the text and asked).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("reported_questions", "report_notes", "mapping_reports", "mapping_report_notes")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN consent_method text")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS consent_method")
