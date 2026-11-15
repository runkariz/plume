from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from testcontainers.community.postgres import PostgresContainer

from plume.infrastructure.db.engine import make_engine

PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer(PGVECTOR_IMAGE, driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture
def engine(pg_url: str) -> Iterator[Engine]:
    engine = make_engine(pg_url)
    yield engine
    engine.dispose()
