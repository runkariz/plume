"""Model access: visibility (official | unreleased | unlisted | discarded), lineages with versions
and owner keys, model generation jobs. Snapshots stay immutable except their visibility.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONTENT = (
    "snapshot_id, session_id, concept, apis, inputs, model, citations_checked, prompt_version, "
    "created_at, origin, generator, lineage_id, version, based_on, content_key"
)


def upgrade() -> None:
    op.execute("DROP TRIGGER model_snapshots_immutable ON model_snapshots")
    op.execute(
        """
        ALTER TABLE model_snapshots
            ADD COLUMN visibility  text NOT NULL DEFAULT 'official',
            ADD COLUMN origin      text NOT NULL DEFAULT 'maintainer',
            ADD COLUMN generator   text NOT NULL DEFAULT 'claude',
            ADD COLUMN lineage_id  text,
            ADD COLUMN version     integer NOT NULL DEFAULT 1,
            ADD COLUMN based_on    text,
            ADD COLUMN content_key text,
            ADD COLUMN released_at timestamptz
        """
    )
    op.execute(
        "UPDATE model_snapshots SET lineage_id = snapshot_id, content_key = snapshot_id, "
        "released_at = created_at"
    )
    op.execute(
        "ALTER TABLE model_snapshots ALTER COLUMN lineage_id SET NOT NULL, "
        "ALTER COLUMN content_key SET NOT NULL, "
        "ADD CONSTRAINT model_snapshots_visibility CHECK "
        "(visibility IN ('official', 'unreleased', 'unlisted', 'discarded'))"
    )
    op.execute(
        "CREATE UNIQUE INDEX model_snapshots_lineage_version ON model_snapshots "
        "(lineage_id, version)"
    )
    op.execute(
        "CREATE INDEX model_snapshots_visibility ON model_snapshots (visibility, created_at)"
    )
    op.execute("CREATE INDEX model_snapshots_session ON model_snapshots (session_id)")
    op.execute(
        """
        CREATE TABLE model_lineages (
            lineage_id     text PRIMARY KEY,
            owner_key_hash text,
            created_at     timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX model_lineages_owner ON model_lineages (owner_key_hash) "
        "WHERE owner_key_hash IS NOT NULL"
    )
    op.execute(
        "INSERT INTO model_lineages (lineage_id, created_at) "
        "SELECT snapshot_id, created_at FROM model_snapshots"
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION plume_refuse_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW({", ".join("NEW." + c.strip() for c in _CONTENT.split(","))})
               IS DISTINCT FROM
               ROW({", ".join("OLD." + c.strip() for c in _CONTENT.split(","))}) THEN
                RAISE EXCEPTION 'model snapshots are immutable';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER model_snapshots_immutable BEFORE UPDATE ON model_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION plume_refuse_update()"
    )
    op.execute(
        "ALTER TABLE model_sessions ADD COLUMN origin text NOT NULL DEFAULT 'maintainer', "
        "ADD COLUMN based_on text"
    )
    op.execute(
        """
        CREATE TABLE model_jobs (
            job_id      text PRIMARY KEY,
            status      text NOT NULL,
            apis        text[] NOT NULL,
            concept     text NOT NULL,
            session_id  text,
            round       integer NOT NULL DEFAULT 0,
            max_rounds  integer NOT NULL DEFAULT 0,
            snapshot_id text,
            error       text,
            generator   text NOT NULL DEFAULT '',
            created_at  timestamptz NOT NULL,
            updated_at  timestamptz NOT NULL
        )
        """
    )
    # Model jobs share the job event log (and its NOTIFY channel) with build jobs.
    op.execute("ALTER TABLE job_events DROP CONSTRAINT IF EXISTS job_events_job_id_fkey")


def downgrade() -> None:
    op.execute("DELETE FROM job_events WHERE job_id NOT IN (SELECT job_id FROM jobs)")
    op.execute(
        "ALTER TABLE job_events ADD CONSTRAINT job_events_job_id_fkey FOREIGN KEY (job_id) "
        "REFERENCES jobs(job_id) ON DELETE CASCADE"
    )
    op.execute("DROP TABLE IF EXISTS model_jobs")
    op.execute("ALTER TABLE model_sessions DROP COLUMN based_on, DROP COLUMN origin")
    op.execute("DROP TRIGGER model_snapshots_immutable ON model_snapshots")
    op.execute("DROP TABLE IF EXISTS model_lineages")
    op.execute("DELETE FROM model_snapshots WHERE visibility <> 'official'")
    op.execute(
        "ALTER TABLE model_snapshots DROP CONSTRAINT model_snapshots_visibility, "
        "DROP COLUMN visibility, DROP COLUMN origin, DROP COLUMN generator, "
        "DROP COLUMN lineage_id, DROP COLUMN version, DROP COLUMN based_on, "
        "DROP COLUMN content_key, DROP COLUMN released_at"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION plume_refuse_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'model snapshots are immutable'; END $$
        """
    )
    op.execute(
        "CREATE TRIGGER model_snapshots_immutable BEFORE UPDATE ON model_snapshots "
        "FOR EACH ROW EXECUTE FUNCTION plume_refuse_update()"
    )
