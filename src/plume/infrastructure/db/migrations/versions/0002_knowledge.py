"""Knowledge schema: apis, builds, build items, tags, documents, chunks, embed cache, facts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIMS = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE apis (
            api_id              text PRIMARY KEY,
            name                text NOT NULL,
            summary             text NOT NULL DEFAULT '',
            doc_link            text,
            icon_url            text,
            category_key        text,
            category_reason     text,
            category_confidence real,
            category_bundle     integer,
            versions            text[] NOT NULL DEFAULT '{}',
            updated_at          timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE builds (
            build_id        text PRIMARY KEY,
            api_id          text NOT NULL REFERENCES apis(api_id),
            status          text NOT NULL CHECK (status IN ('draft', 'sealed')),
            created_at      timestamptz NOT NULL,
            sealed_at       timestamptz,
            content_hash    text,
            package_hash    text,
            chunker_version text,
            embed_model     text,
            dims            integer,
            source_ref      text,
            run_id          text,
            CHECK ((status = 'sealed') = (content_hash IS NOT NULL AND sealed_at IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX builds_api_created ON builds (api_id, created_at DESC)")
    op.execute(
        """
        CREATE TABLE build_items (
            build_id     text NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
            item_id      text NOT NULL,
            content_hash text NOT NULL,
            PRIMARY KEY (build_id, item_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE tags (
            api_id     text NOT NULL REFERENCES apis(api_id),
            name       text NOT NULL,
            build_id   text NOT NULL REFERENCES builds(build_id),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (api_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
            build_id     text NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
            doc_id       text NOT NULL,
            kind         text NOT NULL,
            title        text NOT NULL,
            text         text NOT NULL,
            source_url   text,
            anchor       text,
            resource     text,
            method       text,
            path         text,
            deprecated   boolean NOT NULL DEFAULT false,
            complete     boolean NOT NULL DEFAULT true,
            fields       jsonb NOT NULL DEFAULT '[]',
            scopes       text[] NOT NULL DEFAULT '{}',
            source_id    text,
            content_hash text NOT NULL,
            PRIMARY KEY (build_id, doc_id)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE chunks (
            build_id     text NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
            chunk_id     text NOT NULL,
            doc_id       text NOT NULL,
            ordinal      integer NOT NULL,
            heading      text NOT NULL,
            text         text NOT NULL,
            embed_hash   text NOT NULL,
            content_hash text NOT NULL,
            embedding    halfvec({DIMS}),
            tsv          tsvector GENERATED ALWAYS AS (
                             setweight(to_tsvector('english', heading), 'A')
                             || setweight(to_tsvector('english', text), 'B')
                         ) STORED,
            PRIMARY KEY (build_id, chunk_id),
            FOREIGN KEY (build_id, doc_id) REFERENCES documents(build_id, doc_id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX chunks_tsv ON chunks USING gin (tsv)")
    op.execute("CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding halfvec_cosine_ops)")
    op.execute(
        f"""
        CREATE TABLE embed_cache (
            embed_hash text NOT NULL,
            model      text NOT NULL,
            dims       integer NOT NULL,
            embedding  halfvec({DIMS}) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (embed_hash, model, dims)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE facts (
            build_id   text NOT NULL REFERENCES builds(build_id) ON DELETE CASCADE,
            fact_id    text NOT NULL,
            kind       text NOT NULL,
            owner_id   text NOT NULL,
            owner_kind text NOT NULL,
            resource   text,
            name       text NOT NULL,
            location   text,
            type       text,
            required   boolean NOT NULL DEFAULT false,
            complete   boolean NOT NULL DEFAULT true,
            doc_id     text NOT NULL,
            source_url text,
            anchor     text,
            quote      text,
            PRIMARY KEY (build_id, fact_id)
        )
        """
    )
    op.execute("CREATE INDEX facts_name ON facts (build_id, lower(name))")
    op.execute("CREATE INDEX facts_owner ON facts (build_id, owner_id)")


def downgrade() -> None:
    for table in (
        "facts",
        "embed_cache",
        "chunks",
        "documents",
        "tags",
        "build_items",
        "builds",
        "apis",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
