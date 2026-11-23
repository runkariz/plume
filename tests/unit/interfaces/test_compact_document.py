"""MCP get_document is compact by default (plain text without the field lists, fields paged);
full=true gives the stored text."""

from typing import Any

import pytest
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces import payloads
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.stack import FakeStack

DOC = "endpoint:GET~/admin/api/{version}/products.json"


@pytest.mark.anyio
async def test_compact_by_default_and_full_on_request(packages: Any, monkeypatch: Any) -> None:
    s = FakeStack()
    s.load(str(packages / "shopify-mini"))
    monkeypatch.setattr(payloads, "COMPACT_FIELDS", 5)
    server = create_reader_server(
        McpReaderDependencies(
            overviews=s.overviews, search=s.search, get_document=s.get_document,
            find_fact=s.find_fact, check_call=s.check_call,
            list_builds=lambda: ListBuilds(s.builds, s.tags),
            diff_builds=lambda: DiffBuilds(s.builds), resolver=s.resolver,
        )
    )  # fmt: skip

    async def get(**args: Any) -> dict[str, Any]:
        r = await client.call_tool("get_document", {"api": "shopify", "doc_id": DOC, **args})
        assert not r.is_error, r.content
        return dict(r.structured_content or {})

    async with Client(server) as client:
        compact = await get()
        assert compact["compact"] is True
        assert "## Response fields" not in compact["text"]
        assert len(compact["fields"]) == 5
        assert compact["next_cursor"] == 5
        assert compact["fields_total"] > 5
        more = await get(cursor=5)
        assert more["fields"][0]["name"] != compact["fields"][0]["name"]
        full = await get(full=True)
        assert "## Response fields" in full["text"]
        assert len(full["fields"]) == compact["fields_total"]  # every field, not a page
        assert "next_cursor" not in full
        assert full["fields"][0]["name"] == compact["fields"][0]["name"]
