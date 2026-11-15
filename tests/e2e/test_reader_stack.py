"""Level 1, step 2 against the compose stack: HTTP API on 18480 and MCP (streamable HTTP) on
18481, with a real MCP client. Runs after test_compose_stack.py has loaded the fixtures."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

pytestmark = pytest.mark.e2e
API = os.environ.get("PLUME_E2E_API", "http://127.0.0.1:18480")
MCP = os.environ.get("PLUME_E2E_MCP", "http://127.0.0.1:18481") + "/mcp"
PLUME = str(Path(sys.executable).parent / "plume")
PACKAGES = Path(__file__).resolve().parents[1] / "fixtures" / "packages"
ASSIGNED = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"


@pytest.fixture(scope="module", autouse=True)
def _shopify_loaded() -> None:
    env = {**os.environ, "PLUME_EMBEDDER": "hash"}
    r = subprocess.run(
        [PLUME, "load", str(PACKAGES / "shopify-mini"), "--json"],
        capture_output=True, text=True, check=False, env=env,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1])["api"] == "shopify"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_http_reader() -> None:
    with httpx.Client(base_url=API, timeout=10) as http:
        assert http.get("/health").json()["status"] == "ok"
        ids = {a["id"] for a in http.get("/v1/apis").json()["items"]}
        assert {"shopify", "test-catalog-api", "second-catalog-api"} <= ids
        r = http.post("/v1/apis/shopify/search", json={"query": "assigned fulfillment orders"})
        assert r.status_code == 200
        assert r.json()["results"][0]["id"] == ASSIGNED
        r = http.post(
            "/v1/apis/shopify/check-call",
            json={"method": "GET", "path": "/admin/api/2026-10/products.json", "params": ["limit"]},
        )
        assert r.json()["verdict"] == "documented"
        assert http.get("/v1/apis/nope").status_code == 404


@pytest.mark.anyio
async def test_mcp_reader_over_http() -> None:
    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(MCP) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {"search_docs", "find_fact", "get_document", "check_call"} <= tools

        found = await call(
            client, "search_docs", api="shopify", query="assigned fulfillment orders"
        )
        assert found["results"][0]["doc_id"] == ASSIGNED

        present = await call(client, "find_fact", api="shopify", name="since_id")
        assert present["found"] is True
        assert present["matches"][0]["evidence"]["anchor"]

        absent = await call(client, "find_fact", api="test-catalog-api", name="made_up_field")
        assert (absent["found"], absent["complete"]) == (False, True)

        partial = await call(
            client, "find_fact", api="shopify", name="made_up_field", owner="model:customer"
        )
        assert partial["complete"] is False

        doc = await call(client, "get_document", api="shopify", doc_id=ASSIGNED)
        assert doc["anchor"]
        assert doc["source_url"].startswith("https://shopify.dev/")


def test_mcp_rejects_a_foreign_host_header() -> None:
    r = httpx.post(
        MCP,
        headers={"Host": "evil.example", "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=10,
    )
    assert r.status_code in (400, 403, 421)
