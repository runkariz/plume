"""The reader MCP server through a real MCP client (in-process transport)."""

from typing import Any

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

pytestmark = pytest.mark.anyio

ASSIGNED = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _call(server: MCPServer, tool: str, **args: Any) -> dict[str, Any]:
    async with Client(server) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return dict(result.structured_content)


async def test_tools_and_instructions(mcp_server: MCPServer) -> None:
    async with Client(mcp_server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert client.instructions is not None
        assert "find_fact" in client.instructions
    assert set(tools) == {
        "list_apis",
        "search_docs",
        "get_document",
        "find_fact",
        "check_call",
        "list_builds",
        "diff_builds",
    }
    assert all(t.annotations and t.annotations.read_only_hint for t in tools.values())


async def test_search_then_get_document(mcp_server: MCPServer) -> None:
    found = await _call(
        mcp_server, "search_docs", api="shopify", query="assigned fulfillment orders"
    )
    assert found["results"][0]["doc_id"] == ASSIGNED
    assert found["build"].startswith("b-")
    doc = await _call(mcp_server, "get_document", api="shopify", doc_id=ASSIGNED)
    assert doc["source_url"]
    assert doc["anchor"] is not None
    assert doc["citation"]["doc_id"] == ASSIGNED


async def test_find_fact_exists_absent_incomplete(mcp_server: MCPServer) -> None:
    present = await _call(mcp_server, "find_fact", api="shopify", name="since_id")
    assert present["found"] is True
    assert present["matches"][0]["evidence"]["doc_id"].startswith("endpoint:")
    absent = await _call(mcp_server, "find_fact", api="test-catalog-api", name="made_up_field")
    assert absent["found"] is False
    assert absent["complete"] is True
    partial = await _call(
        mcp_server, "find_fact", api="shopify", name="made_up_field", owner="model:customer"
    )
    assert partial["complete"] is False


async def test_check_call_and_lists(mcp_server: MCPServer) -> None:
    r = await _call(
        mcp_server, "check_call", api="shopify", method="DELETE",
        path="/admin/api/latest/products/9.json",
    )  # fmt: skip
    assert r["verdict"] == "documented"
    apis = await _call(mcp_server, "list_apis")
    assert {a["api"] for a in apis["apis"]} == {"shopify", "test-catalog-api"}
    builds = await _call(mcp_server, "list_builds", api="shopify")
    assert builds["builds"][0]["tags"] == ["latest"]
    diff = await _call(mcp_server, "diff_builds", api="shopify", from_version="latest")
    assert diff["added"] == []
    assert diff["truncated"] is False


async def test_errors_are_tool_errors(mcp_server: MCPServer) -> None:
    async with Client(mcp_server) as client:
        r = await client.call_tool("get_document", {"api": "nope", "doc_id": "x"})
        assert r.is_error
        assert "unknown api" in str(r.content)
        r = await client.call_tool("list_builds", {"api": "nope"})
        assert r.is_error


@pytest.mark.anyio
async def test_compact_fields_name_their_model(mcp_server: MCPServer) -> None:
    doc = await _call(mcp_server, "get_document", api="shopify", doc_id="model:customer")
    by_name = {f["name"]: f for f in doc["fields"]}
    assert by_name["default_address"]["model_id"] == "model:address"
    assert "model_id" not in by_name["email"]  # only when there is one
