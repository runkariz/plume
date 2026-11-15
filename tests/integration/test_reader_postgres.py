"""Reader over the real stack: Postgres + hash embedder, through HTTP and MCP (in-process)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from sqlalchemy import Engine

from plume.bootstrap.container import Container
from plume.bootstrap.servers import http_app, reader_server
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration
ASSIGNED = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"


@pytest.fixture
def container(clean_engine: Engine, pg_url: str, packages: Path) -> Iterator[Container]:
    c = Container(settings=Settings(database_url=pg_url, embedder="hash"))
    for name in ("shopify-mini", "test-catalog", "second-catalog"):
        c.build_pipeline().execute("job", str(packages / name))
    yield c
    c.engine.dispose()


def test_http_reader_on_postgres(container: Container) -> None:
    client = TestClient(http_app(container))
    apis = client.get("/v1/apis").json()["items"]
    assert [a["id"] for a in apis] == ["second-catalog-api", "shopify", "test-catalog-api"]

    hits = client.post(
        "/v1/apis/shopify/search", json={"query": "assigned fulfillment orders", "topK": 5}
    ).json()["results"]
    assert hits[0]["id"] == ASSIGNED
    assert hits[0]["textRank"] == 1

    for mode in ("dense", "text"):
        r = client.post(
            "/v1/apis/shopify/search", json={"query": "list products", "mode": mode, "topK": 3}
        )
        assert r.status_code == 200
        assert r.json()["results"]

    fact = client.post("/v1/apis/shopify/find-fact", json={"name": "since_id"}).json()
    assert fact["found"] is True
    absent = client.post(
        "/v1/apis/second-catalog-api/find-fact", json={"name": "loyalty_points"}
    ).json()
    assert (absent["found"], absent["complete"]) == (False, True)
    partial = client.post(
        "/v1/apis/shopify/find-fact", json={"name": "loyalty_points", "owner": "model:customer"}
    ).json()
    assert partial["complete"] is False

    call = client.post(
        "/v1/apis/shopify/check-call",
        json={"method": "PUT", "path": "/admin/api/2026-10/products/5.json"},
    ).json()
    assert call["verdict"] == "documented"

    items = client.get("/v1/apis/shopify/items", params={"kind": "model"}).json()
    assert items["total"] == 4
    doc = client.get(f"/v1/apis/shopify/documents/{ASSIGNED}").json()
    assert doc["sourceUrl"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_reader_on_postgres(container: Container) -> None:
    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(reader_server(container)) as client:
        found = await call(
            client, "search_docs", api="shopify", query="assigned fulfillment orders"
        )
        assert found["results"][0]["doc_id"] == ASSIGNED
        doc = await call(client, "get_document", api="shopify", doc_id=ASSIGNED)
        assert doc["citation"]["source_url"]
        fact = await call(client, "find_fact", api="test-catalog-api", name="nope_field")
        assert (fact["found"], fact["complete"]) == (False, True)
