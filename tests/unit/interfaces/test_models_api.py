"""Canonical models over HTTP and over the maintainer MCP server (real MCP client, in-process)."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.maintainer_server import (
    McpMaintainerDependencies,
    create_maintainer_server,
)
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
TOKEN = "pl_models_test"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _draft(name: str) -> dict[str, Any]:
    return json.loads((DRAFTS / f"catalog-order-{name}.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


@pytest.fixture
def client(stack: FakeStack) -> TestClient:
    return TestClient(
        create_app(
            HttpDependencies(
                overviews=stack.overviews,
                browse=stack.browse,
                search=stack.search,
                get_document=stack.get_document,
                find_fact=stack.find_fact,
                check_call=stack.check_call,
                list_builds=lambda: ListBuilds(stack.builds, stack.tags),
                diff_builds=lambda: DiffBuilds(stack.builds),
                resolver=stack.resolver,
                rate_limit_per_minute=0,
                suggest=stack.suggest,
                models=stack.models,
                maintainer_tokens=(TOKEN,),
            )
        )
    )


def test_candidates_and_suggest(client: TestClient) -> None:
    ids = [a["id"] for a in client.get("/v1/models/candidates").json()["items"]]
    assert ids == ["second-catalog-api", "test-catalog-api"]
    r = client.post("/v1/models/suggest", json={"apis": APIS}).json()
    assert [a["id"] for a in r["apis"]] == APIS
    assert r["apis"][0]["logo"]["text"]
    assert r["apis"][0]["shortName"] == "Test"
    order = next(c for c in r["concepts"] if c["id"] == "order")
    assert order["coverage"] == {"test-catalog-api": "direct", "second-catalog-api": "direct"}
    assert order["difficulty"] == {"tone": "ok", "label": "Straightforward"}
    assert {"count", "summary"} <= set(r["notModeled"])
    assert client.post("/v1/models/suggest", json={"apis": ["x"]}).status_code == 422


def test_generate_submit_get(client: TestClient) -> None:
    g = client.post("/v1/models/generate", json={"apis": APIS, "concept": "Order"}).json()
    assert g["status"] == "awaiting_draft"
    assert g["snapshotId"] is None
    sid = g["sessionId"]
    assert "get_model_context" in g["claudePrompt"]
    ctx = client.get(g["contextUrl"]).json()
    assert ctx["session_id"] == sid

    url = f"/v1/models/sessions/{sid}/draft"
    assert client.post(url, json=_draft("good")).status_code == 401
    bad = client.post(url, headers=AUTH, json=_draft("bad-quote-not-in-doc"))
    assert bad.status_code == 422
    assert bad.json()["issues"][0]["code"] == "QUOTE_NOT_FOUND"
    ok = client.post(url, headers=AUTH, json=_draft("good"))
    assert ok.status_code == 201
    model = ok.json()["model"]
    assert model["status"] == "generated_unverified"
    assert model["coverage"]["test-catalog-api"] == {"mapped": 5, "total": 5}
    assert model["citations"] == {"checked": 10, "found": 10, "missing": []}
    total = next(f for f in model["fields"] if f["name"] == "total")
    assert total["support"]["second-catalog-api"] == "derived"
    assert total["sources"]["second-catalog-api"]["transform"] == "parse decimal string"
    assert model["inputs"][0]["logo"]["color"].startswith("#")
    assert client.post(url, headers=AUTH, json=_draft("good")).status_code == 200  # idempotent

    got = client.get(f"/v1/models/{model['id']}").json()
    assert got == model
    assert (
        client.get("/v1/models", params={"api": "test-catalog-api"}).json()["items"][0]["id"]
        == model["id"]
    )
    again = client.post("/v1/models/generate", json={"apis": APIS, "concept": "orders"}).json()
    assert again["status"] == "ready"
    assert again["snapshotId"] == model["id"]
    assert client.get("/v1/models/m-nope").status_code == 404


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_maintainer_mcp_model_flow(stack: FakeStack) -> None:
    server = create_maintainer_server(
        McpMaintainerDependencies(
            suggest=stack.suggest,
            models=stack.models,
            resolver=stack.resolver,
            tag_build=stack.tag,
        )
    )

    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(server) as client:
        assert client.instructions is not None
        assert "submit_model_draft" in client.instructions
        concepts = await call(client, "suggest_concepts", apis=APIS)
        assert any(c["id"] == "order" for c in concepts["concepts"])
        session = await call(client, "start_model_session", apis=APIS, concept="Order")
        sid = session["session_id"]
        ctx = await call(client, "get_model_context", session_id=sid)
        assert {a["api"] for a in ctx["apis"]} == set(APIS)
        for name in ("missing-citation", "field-not-in-api", "api-not-in-session"):
            raw = _draft(f"bad-{name}")
            refused = await call(client, "submit_model_draft", session_id=sid, draft=raw)
            assert refused["accepted"] is False
            assert [i["code"] for i in refused["issues"]] == [raw["_expect_code"]]
        accepted = await call(client, "submit_model_draft", session_id=sid, draft=_draft("good"))
        assert accepted["accepted"] is True
        snap = await call(client, "get_model", snapshot_id=accepted["snapshot_id"])
        assert snap["name"] == "Order"
        listed = await call(client, "list_models", api="second-catalog-api")
        assert listed["models"][0]["snapshot_id"] == accepted["snapshot_id"]
        build = stack.resolver().resolve("test-catalog-api").build.build_id.value
        pub = await call(client, "publish_build", api="test-catalog-api", build=build, tag="stable")
        assert pub["previous"] is None
        err = await client.call_tool("get_model_context", {"session_id": "s-nope"})
        assert err.is_error
