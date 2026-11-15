"""Level 1 step 3 against compose: canonical models over the maintainer MCP (streamable HTTP,
bearer token) with recorded drafts, then GET the model over HTTP."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

pytestmark = pytest.mark.e2e
API = "http://127.0.0.1:18480"
MAINTAINER_MCP = "http://127.0.0.1:18481/maintainer/mcp"
DRAFTS = Path(__file__).resolve().parents[1] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
BAD = [
    "missing-citation",
    "quote-not-in-doc",
    "field-not-in-api",
    "api-not-in-session",
    "endpoint-not-in-api",
    "doc-not-in-build",
]


@pytest.fixture
def token() -> str:
    value = os.environ.get("PLUME_E2E_TOKEN")
    if not value:
        pytest.skip("PLUME_E2E_TOKEN not set (run through `make e2e`)")
    return value


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _draft(name: str) -> dict[str, Any]:
    return json.loads((DRAFTS / f"catalog-order-{name}.json").read_text())  # type: ignore[no-any-return]


def test_maintainer_mcp_needs_the_token() -> None:
    r = httpx.post(
        MAINTAINER_MCP,
        headers={"Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=10,
    )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_canonical_model_over_maintainer_mcp(token: str) -> None:
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})

    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(streamable_http_client(MAINTAINER_MCP, http_client=http)) as client:
        session = await call(client, "start_model_session", apis=APIS, concept="Order")
        sid = session["session_id"]
        ctx = await call(client, "get_model_context", session_id=sid)
        assert {a["api"] for a in ctx["apis"]} == set(APIS)
        for name in BAD:
            raw = _draft(f"bad-{name}")
            refused = await call(client, "submit_model_draft", session_id=sid, draft=raw)
            assert refused["accepted"] is False, name
            assert [i["code"] for i in refused["issues"]] == [raw["_expect_code"]], name
        accepted = await call(client, "submit_model_draft", session_id=sid, draft=_draft("good"))
        assert accepted["accepted"] is True
        snapshot_id = accepted["snapshot_id"]

    model = httpx.get(f"{API}/v1/models/{snapshot_id}", timeout=10).json()
    assert model["status"] == "generated_unverified"
    assert [i["id"] for i in model["inputs"]] == APIS
    assert model["coverage"] == {a: {"mapped": 5, "total": 5} for a in APIS}
    assert model["citations"]["checked"] == 10
    by_name = {f["name"]: f for f in model["fields"]}
    assert by_name["total"]["support"] == {
        "test-catalog-api": "derived",
        "second-catalog-api": "derived",
    }
    evidence = by_name["id"]["sources"]["test-catalog-api"]["evidence"][0]
    assert evidence["quote"] == "Unique identifier of the order."
    assert len(model["openQuestions"]) == 2
