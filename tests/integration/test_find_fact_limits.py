"""find_fact over Postgres: matches are paged in SQL (keyset), counted, and a lookup that runs
past the reader's statement timeout answers "too broad" instead of loading everything."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event

from plume.application.ports.search_index import QueryTooBroadError, fact_key
from plume.bootstrap.container import Container
from plume.bootstrap.servers import http_app
from plume.domain.knowledge.fact import Fact
from plume.domain.shared.ids import BuildId
from plume.infrastructure.search.postgres_search import PostgresFactQuery
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def container(clean_engine: Engine, pg_url: str, packages: Path) -> Iterator[Container]:
    c = Container(settings=Settings(database_url=pg_url, embedder="hash"))
    c.build_pipeline().execute("job", str(packages / "shopify-mini"))
    yield c
    c.engine.dispose()


def _build(c: Container) -> BuildId:
    return c.resolver().resolve("shopify").build.build_id


def test_keyset_pages_walk_every_match_once(container: Container) -> None:
    facts = PostgresFactQuery(container.engine)
    build = _build(container)
    every = facts.find(build, "id")
    assert len(every) > 6
    seen: list[Fact] = []
    after = None
    while True:
        page, total = facts.find_page(build, "id", limit=4, after=after)
        assert total == len(every) - len(seen)  # what matches from this page on
        assert len(page) <= 4
        if not page:
            break
        seen += page
        after = fact_key(page[-1])
    assert [fact_key(f) for f in seen] == [fact_key(f) for f in every]  # find's order, no gaps


def test_the_reader_api_caps_and_pages(container: Container) -> None:
    client = TestClient(http_app(container))
    first = client.post("/v1/apis/shopify/find-fact", json={"name": "id", "limit": 3}).json()
    assert len(first["matches"]) == 3
    assert first["total"] > 3
    assert first["nextCursor"]
    assert "owner=" in first["hint"]
    names: list[str] = [f"{m['ownerId']}|{m['name']}|{m['location']}" for m in first["matches"]]
    cursor = first["nextCursor"]
    while cursor:
        page = client.post("/v1/apis/shopify/find-fact",
                           json={"name": "id", "limit": 3, "cursor": cursor}).json()  # fmt: skip
        names += [f"{m['ownerId']}|{m['name']}|{m['location']}" for m in page["matches"]]
        cursor = page["nextCursor"]
    assert len(names) == first["total"]
    assert len(set(names)) == len(names)  # every match once
    bad = client.post("/v1/apis/shopify/find-fact", json={"name": "id", "cursor": "nope"})
    assert bad.status_code == 400


def test_a_lookup_past_the_statement_timeout_is_too_broad(container: Container) -> None:
    """The query is slowed on purpose (pg_sleep around it) past a 50 ms limit."""
    engine = container.engine

    def slow(_conn: Any, _cur: Any, statement: str, params: Any, _ctx: Any, _many: bool) -> Any:
        if statement.lstrip().startswith("SELECT kind, owner_id"):
            statement = f"SELECT q.* FROM ({statement}) q CROSS JOIN (SELECT pg_sleep(0.3)) s"  # noqa: S608
        return statement, params

    event.listen(engine, "before_cursor_execute", slow, retval=True)
    try:
        with pytest.raises(QueryTooBroadError):
            PostgresFactQuery(engine, statement_timeout_ms=50).find_page(
                _build(container), "id", limit=5
            )
        page, _ = PostgresFactQuery(engine, statement_timeout_ms=0).find_page(
            _build(container), "id", limit=5
        )  # no limit set: the slow query still answers
        assert page
    finally:
        event.remove(engine, "before_cursor_execute", slow)


def test_one_query_per_call_and_busy_over_http(container: Container) -> None:
    from plume.application.reader.use_cases import LookupLimit  # noqa: PLC0415

    statements: list[str] = []

    def seen(_conn: Any, _cur: Any, statement: str, *_a: Any) -> None:
        if " FROM facts " in statement:
            statements.append(statement)

    event.listen(container.engine, "before_cursor_execute", seen)
    try:
        page, total = PostgresFactQuery(container.engine, 5000).find_page(
            _build(container), "id", limit=3
        )
    finally:
        event.remove(container.engine, "before_cursor_execute", seen)
    assert len(page) == 3
    assert total == len(PostgresFactQuery(container.engine).find(_build(container), "id"))
    assert len(statements) == 1  # the page and its count in one statement
    assert "count(*) OVER ()" in statements[0]

    container.__dict__["lookup_limit"] = LookupLimit(1, wait=0.05)
    client = TestClient(http_app(container))
    with container.lookup_limit:  # every slot taken
        busy = client.post("/v1/apis/shopify/find-fact", json={"name": "id"})
    assert busy.status_code == 503
    assert busy.headers["retry-after"] == "2"
    assert "busy" in busy.text
