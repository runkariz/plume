"""GET /v1/apis read every latest release note's whole body to project the card fields of its
visible items: Shopware's latest note is 66,826 items (7 MB) with none visible, and the
projection took 425 ms of a 650 ms list on plume-l2, growing with the notes' size. The card
projection (api, to, toDocsAsOf and the visible items' visibleToUsers / class / breaking /
wordingOnly / kind) is now stored beside the body when notes are saved, and backfilled here
with the same expression the list used.

ADD COLUMN without a default is instant; the backfill reads each body once.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# frozen copy of release_notes_repo.CARD_SQL at this revision (migrations never import app code)
CARD = (
    "jsonb_build_object('api', body->'api', 'to', body->'to', 'toDocsAsOf', body->'toDocsAsOf', "
    "'items', coalesce((SELECT jsonb_agg(jsonb_build_object('visibleToUsers', i->'visibleToUsers', "
    "'class', i->'class', 'breaking', i->'breaking', 'wordingOnly', i->'wordingOnly', "
    "'kind', i->'kind')) FROM jsonb_array_elements(body->'items') i "
    "WHERE i->'visibleToUsers' = 'true'::jsonb), '[]'::jsonb))"
)


def upgrade() -> None:
    op.execute("ALTER TABLE release_notes ADD COLUMN IF NOT EXISTS card jsonb")
    op.execute(f"UPDATE release_notes SET card = {CARD} WHERE card IS NULL")  # noqa: S608


def downgrade() -> None:
    op.execute("ALTER TABLE release_notes DROP COLUMN IF EXISTS card")
