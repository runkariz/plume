"""Model sets: several canonical models with relations (docs/design/model-relations.md).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTENT = (
    "set_id, session_id, name, apis, inputs, body, prompt_version, created_at, origin, "
    "generator, lineage_id, version, based_on, content_key"
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_set_sessions (
            session_id      text PRIMARY KEY,
            inputs          jsonb NOT NULL,
            concepts        text[] NOT NULL,
            member_sessions jsonb NOT NULL,
            origin          text NOT NULL,
            based_on        text,
            created_at      timestamptz NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_sets (
            set_id         text PRIMARY KEY,
            session_id     text NOT NULL REFERENCES model_set_sessions(session_id),
            name           text NOT NULL,
            apis           text[] NOT NULL,
            inputs         jsonb NOT NULL,
            body           jsonb NOT NULL,
            prompt_version text NOT NULL,
            created_at     timestamptz NOT NULL,
            visibility     text NOT NULL CHECK
                (visibility IN ('official', 'unreleased', 'unlisted', 'discarded')),
            origin         text NOT NULL,
            generator      text NOT NULL,
            lineage_id     text NOT NULL,
            version        integer NOT NULL,
            based_on       text,
            content_key    text NOT NULL,
            released_at    timestamptz
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX model_sets_lineage_version ON model_sets (lineage_id, version)")
    op.execute("CREATE INDEX model_sets_visibility ON model_sets (visibility, created_at)")
    op.execute("CREATE INDEX model_sets_apis ON model_sets USING gin (apis)")
    op.execute("CREATE INDEX model_sets_session ON model_sets (session_id)")
    op.execute(
        """
        CREATE TABLE model_set_lineages (
            lineage_id     text PRIMARY KEY,
            owner_key_hash text,
            created_at     timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX model_set_lineages_owner ON model_set_lineages (owner_key_hash) "
        "WHERE owner_key_hash IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE model_set_members (
            set_id      text NOT NULL REFERENCES model_sets(set_id),
            concept     text NOT NULL,
            snapshot_id text NOT NULL REFERENCES model_snapshots(snapshot_id),
            PRIMARY KEY (set_id, concept)
        )
        """
    )
    op.execute("CREATE INDEX model_set_members_snapshot ON model_set_members (snapshot_id)")
    op.execute(
        f"""
        CREATE FUNCTION plume_refuse_set_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW({", ".join("NEW." + c.strip() for c in _CONTENT.split(","))})
               IS DISTINCT FROM
               ROW({", ".join("OLD." + c.strip() for c in _CONTENT.split(","))}) THEN
                RAISE EXCEPTION 'model sets are immutable';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER model_sets_immutable BEFORE UPDATE ON model_sets "
        "FOR EACH ROW EXECUTE FUNCTION plume_refuse_set_update()"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_set_members")
    op.execute("DROP TABLE IF EXISTS model_set_lineages")
    op.execute("DROP TABLE IF EXISTS model_sets")
    op.execute("DROP FUNCTION IF EXISTS plume_refuse_set_update()")
    op.execute("DROP TABLE IF EXISTS model_set_sessions")
