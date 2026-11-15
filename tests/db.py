"""Postgres test fixtures (testcontainers, pgvector). Imported by tests/conftest.py."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from testcontainers.community.postgres import PostgresContainer

from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.engine import make_engine

PGVECTOR_IMAGE = "pgvector/pgvector:pg16"
TABLES = (
    "build_assets", "model_set_members", "model_set_lineages", "model_sets", "model_set_sessions",
    "model_jobs", "model_lineages", "model_snapshots", "model_sessions",
    "job_events", "jobs", "evals",
    "facts", "chunks", "documents", "tags", "build_items", "builds", "apis", "embed_cache",
)  # fmt: skip


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer(PGVECTOR_IMAGE, driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_engine(pg_url: str) -> Iterator[Engine]:
    engine = make_engine(pg_url)
    AlembicMigrator(engine).upgrade_to_head()
    yield engine
    engine.dispose()


@pytest.fixture
def clean_engine(migrated_engine: Engine) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    return migrated_engine
