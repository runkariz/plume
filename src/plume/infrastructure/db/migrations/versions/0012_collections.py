"""Collections: the "My models" link replaces per-model owner keys.

Every distinct owner-key hash (models and sets) becomes one collection holding that key's
lineages; the hash is kept as legacy_key_hash so an old key still finds its collection.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-16
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE collections (
            collection_id   text PRIMARY KEY,
            created_at      timestamptz NOT NULL,
            legacy_key_hash text UNIQUE,
            merged_into     text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE collection_items (
            collection_id text NOT NULL REFERENCES collections (collection_id),
            kind          text NOT NULL CHECK (kind IN ('model', 'set')),
            lineage_id    text NOT NULL,
            added_at      timestamptz NOT NULL,
            PRIMARY KEY (collection_id, kind, lineage_id)
        )
        """
    )
    op.execute("CREATE INDEX collection_items_lineage ON collection_items (kind, lineage_id)")
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT 'model' AS kind, lineage_id, owner_key_hash, created_at FROM model_lineages "
            "WHERE owner_key_hash IS NOT NULL UNION ALL "
            "SELECT 'set', lineage_id, owner_key_hash, created_at FROM model_set_lineages "
            "WHERE owner_key_hash IS NOT NULL ORDER BY created_at"
        )
    ).all()
    made: dict[str, str] = {}
    for r in rows:
        cid = made.get(r.owner_key_hash)
        if cid is None:
            cid = made[r.owner_key_hash] = "c-" + secrets.token_urlsafe(16)
            conn.execute(
                sa.text(
                    "INSERT INTO collections (collection_id, created_at, legacy_key_hash) "
                    "VALUES (:c, :t, :h)"
                ),
                {"c": cid, "t": r.created_at, "h": r.owner_key_hash},
            )
        conn.execute(
            sa.text(
                "INSERT INTO collection_items (collection_id, kind, lineage_id, added_at) "
                "VALUES (:c, :k, :l, :t) ON CONFLICT DO NOTHING"
            ),
            {"c": cid, "k": r.kind, "l": r.lineage_id, "t": r.created_at},
        )


def downgrade() -> None:
    op.execute("DROP TABLE collection_items")
    op.execute("DROP TABLE collections")
