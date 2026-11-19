"""check_call: query / body names, parameters documented by pagination (contract or guide),
fixed version segments, and unknown MCP arguments refused."""

import json
import shutil
from pathlib import Path

import pytest
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.stack import FakeStack

PRODUCTS = "/admin/api/2026-10/products.json"


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> FakeStack:
    dst = tmp_path / "shopify-paged"
    shutil.copytree(packages / "shopify-mini", dst)
    req = dst / "connector" / "endpoints" / "get-admin-api-latest-products-json" / "request.json"
    data = json.loads(req.read_text())
    req.write_text(json.dumps({**data, "pagination": {"style": "link-header",
                                                      "cursorParam": "page_info"}}))  # fmt: skip
    knowledge = dst / "connector" / "knowledge"
    (knowledge / "pagination.json").write_text(json.dumps(
        {"id": "pagination", "kind": "pagination", "title": "Pagination"}))  # fmt: skip
    (knowledge / "pagination.md").write_text(
        "# Pagination\n\nPage through results with the `since_cursor` query parameter; "
        "a page has at most 250 items.\n"
    )
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    s.load(str(dst))
    return s


def _check(stack: FakeStack, path: str, **names: list[str]):  # type: ignore[no-untyped-def]
    return stack.check_call().execute(
        "shopify", "GET", path, names.get("params", []), None,
        names.get("query", []), names.get("body", []),
    )  # fmt: skip


def test_pagination_contract_and_guide(stack: FakeStack) -> None:
    r = _check(stack, PRODUCTS, params=["limit", "page_info", "since_cursor"])
    assert [(p.name, p.found, p.where) for p in r.params] == [
        ("limit", True, "query"),
        ("page_info", True, "pagination"),  # the endpoint's contract names it
        ("since_cursor", True, "pagination"),  # the pagination guide uses it as a parameter
    ]
    assert r.verdict == "documented"
    assert _check(stack, PRODUCTS, params=["nope"]).verdict == "not_documented"


def test_query_and_body_names_are_checked_where_given(stack: FakeStack) -> None:
    r = _check(stack, PRODUCTS, query=["limit"], body=["limit"])
    assert [(p.name, p.found) for p in r.params] == [("limit", True), ("limit", False)]


def test_a_fixed_version_must_match(stack: FakeStack) -> None:
    calls = stack.check_call()
    ok = calls.execute("test-catalog-api", "GET", "/api/v1/orders")
    assert ok.verdict == "documented"
    other = calls.execute("test-catalog-api", "GET", "/api/v2/orders")
    assert other.verdict == "not_documented"
    assert other.note == "the documented operation is GET /api/v1/orders"


@pytest.mark.anyio
async def test_unknown_mcp_arguments_are_refused(stack: FakeStack) -> None:
    server = create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews, search=stack.search, get_document=stack.get_document,
            find_fact=stack.find_fact, check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
        )
    )  # fmt: skip
    async with Client(server) as client:
        bad = await client.call_tool(
            "check_call", {"api": "shopify", "method": "GET", "path": PRODUCTS, "foo": ["x"]}
        )
        assert bad.is_error
        assert "Extra inputs are not permitted" in str(bad.content)
        ok = await client.call_tool(
            "check_call",
            {"api": "shopify", "method": "GET", "path": PRODUCTS, "query": ["limit"]},
        )
        assert not ok.is_error
