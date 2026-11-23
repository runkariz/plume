"""find_fact matches a name or a dotted suffix of it ("id" finds "results[].id"). The suffix
(LIKE '%.id') could not use the name index, so every lookup scanned the whole build's facts
(Shopware: 569k on plume-l2, about 2 s per query on prod). An index on the reversed
lower-case name turns the suffix into a prefix: reverse(lower(name)) LIKE 'di.%'.

Built CONCURRENTLY outside a transaction, so a live database keeps serving reads and writes
while it builds; IF NOT EXISTS adopts a valid index built by hand before, and an invalid one
(an interrupted build) is dropped and built again.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # an interrupted CONCURRENTLY build leaves an INVALID index that IF NOT EXISTS would keep
        invalid = (
            op.get_bind()
            .exec_driver_sql(
                "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'facts_name_reversed' AND NOT i.indisvalid"
            )
            .first()
        )
        if invalid is not None:
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS facts_name_reversed")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS facts_name_reversed "
            "ON facts (build_id, reverse(lower(name)) text_pattern_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS facts_name_reversed")
