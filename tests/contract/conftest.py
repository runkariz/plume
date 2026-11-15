"""Port contract suites run against the in-memory fake AND the Postgres adapter."""

from dataclasses import dataclass
from typing import Any

import pytest

from plume.application.ports.api_repo import ApiRepo
from plume.application.ports.build_repo import BuildRepo
from plume.application.ports.document_repo import DocumentRepo
from plume.application.ports.fact_index import FactIndex
from plume.application.ports.search_index import FactQuery, SearchIndex
from plume.application.ports.tag_repo import TagRepo
from plume.application.ports.vector_index import VectorIndex
from plume.infrastructure.db.repos.api_repo import PostgresApiRepo
from plume.infrastructure.db.repos.build_repo import PostgresBuildRepo
from plume.infrastructure.db.repos.document_repo import PostgresDocumentRepo
from plume.infrastructure.db.repos.tag_repo import PostgresTagRepo
from plume.infrastructure.search.pgvector_index import PgVectorIndex
from plume.infrastructure.search.postgres_fact_index import PostgresFactIndex
from plume.infrastructure.search.postgres_search import PostgresFactQuery, PostgresSearchIndex
from tests.fakes.knowledge import (
    InMemoryApiRepo,
    InMemoryBuildRepo,
    InMemoryDocumentRepo,
    InMemoryFactIndex,
    InMemoryTagRepo,
    InMemoryVectorIndex,
)
from tests.fakes.search import InMemoryFactQuery, InMemorySearchIndex


@dataclass
class Store:
    kind: str
    apis: ApiRepo
    builds: BuildRepo
    tags: TagRepo
    documents: DocumentRepo
    vectors: VectorIndex
    facts: FactIndex
    search: SearchIndex
    fact_query: FactQuery


def _fake() -> Store:
    docs = InMemoryDocumentRepo()
    facts = InMemoryFactIndex()
    return Store(
        "fake",
        InMemoryApiRepo(),
        InMemoryBuildRepo(),
        InMemoryTagRepo(),
        docs,
        InMemoryVectorIndex(docs),
        facts,
        InMemorySearchIndex(docs),
        InMemoryFactQuery(facts, docs),
    )


def _postgres(request: pytest.FixtureRequest) -> Store:
    engine: Any = request.getfixturevalue("clean_engine")
    return Store(
        "postgres",
        PostgresApiRepo(engine),
        PostgresBuildRepo(engine),
        PostgresTagRepo(engine),
        PostgresDocumentRepo(engine),
        PgVectorIndex(engine),
        PostgresFactIndex(engine),
        PostgresSearchIndex(engine),
        PostgresFactQuery(engine),
    )


@pytest.fixture(params=["fake", pytest.param("postgres", marks=pytest.mark.integration)])
def store(request: pytest.FixtureRequest) -> Store:
    return _fake() if request.param == "fake" else _postgres(request)
