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
API = os.environ.get("PLUME_E2E_API", "http://127.0.0.1:18480")
MAINTAINER_MCP = os.environ.get("PLUME_E2E_MCP", "http://127.0.0.1:18481") + "/maintainer/mcp"
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
        ev = await call(client, "get_model_evidence", session_id=sid, api=APIS[0])
        assert any(f["path"] == "total" for d in ev["documents"] for f in d["fields"])
        assert ev["next_cursor"] is None
        for name in BAD:
            raw = _draft(f"bad-{name}")
            refused = await call(client, "submit_model_draft", session_id=sid, draft=raw)
            assert refused["accepted"] is False, name
            assert [i["code"] for i in refused["issues"]] == [raw["_expect_code"]], name
        accepted = await call(client, "submit_model_draft", session_id=sid, draft=_draft("good"))
        assert accepted["accepted"] is True
        snapshot_id = accepted["snapshot_id"]

    auth = {"Authorization": f"Bearer {token}"}
    assert httpx.get(f"{API}/v1/models/{snapshot_id}", timeout=10).status_code == 404
    pending = httpx.get(f"{API}/v1/models/{snapshot_id}", headers=auth, timeout=10).json()
    assert pending["visibility"] == "unreleased"
    released = httpx.post(f"{API}/v1/models/{snapshot_id}/release", headers=auth, timeout=10)
    assert released.status_code == 200
    model = httpx.get(f"{API}/v1/models/{snapshot_id}", timeout=10).json()
    assert (model["visibility"], model["official"]) == ("official", True)
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


def test_anonymous_model_is_unlisted_and_versioned() -> None:
    g = httpx.post(
        f"{API}/v1/models/generate", json={"apis": APIS, "concept": "Order"}, timeout=10
    ).json()
    sid = g["sessionId"]
    r = httpx.post(f"{API}/v1/models/sessions/{sid}/draft", json=_draft("good"), timeout=30)
    assert r.status_code == 201
    body = r.json()
    mid = body["model"]["id"]
    assert mid.startswith("u-")
    assert body["visibility"] == "unlisted"
    assert httpx.get(f"{API}/v1/models/{mid}", timeout=10).json()["id"] == mid
    listed = httpx.get(f"{API}/v1/models", timeout=10).json()["items"]
    assert mid not in {m["id"] for m in listed}
    rev = httpx.post(f"{API}/v1/models/{mid}/revise", timeout=10).json()
    v2 = httpx.post(
        f"{API}/v1/models/sessions/{rev['sessionId']}/draft",
        params={"basedOn": mid},
        json=dict(_draft("good"), description="Second version."),
        timeout=30,
    ).json()
    assert v2["model"]["lineage"]["version"] == 2
    mine = httpx.post(
        f"{API}/v1/models/mine", json={"ownerKeys": [body["ownerKey"]]}, timeout=10
    ).json()
    assert [m["id"] for m in mine["items"]] == [v2["model"]["id"]]
