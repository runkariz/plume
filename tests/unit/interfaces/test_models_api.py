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
                generate_models=stack.generate,
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
    assert order["name"] == "Order"
    assert next(c for c in r["concepts"] if c["id"] == "product")["name"] == "Product"
    assert order["coverage"] == {"test-catalog-api": "direct", "second-catalog-api": "direct"}
    assert order["difficulty"] == {"tone": "ok", "label": "Straightforward"}
    assert {"count", "summary"} <= set(r["notModeled"])
    assert client.post("/v1/models/suggest", json={"apis": ["x"]}).status_code == 422
    assert "description" not in order
    assert order["reason"].startswith("Test Catalog API has an Order model")
    assert set(order["apiCounts"]["test-catalog-api"]) == {
        "models",
        "endpoints",
        "operations",
        "fields",
    }
    assert (r["total"], r["limit"], r["offset"]) == (len(r["concepts"]), 24, 0)
    assert r["nextOffset"] is None
    assert set(r["counts"]) == {"all", "inAll", "write", "single"}
    page = client.post("/v1/models/suggest", json={"apis": APIS, "limit": 1}).json()
    assert (len(page["concepts"]), page["nextOffset"]) == (1, 1)
    q = client.post("/v1/models/suggest", json={"apis": APIS, "q": "order"}).json()
    assert [c["id"] for c in q["concepts"]][:1] == ["order"]
    bad = client.post("/v1/models/suggest", json={"apis": APIS, "require": ["shopify"]})
    assert bad.status_code == 400
    assert r["apis"][0]["logo"]["url"] is None  # these fixtures have no icon


def test_suggest_and_model_inputs_carry_the_icon(packages: Path, tmp_path: Path) -> None:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("shopify-mini", "test-catalog"):
        s.load(str(packages / p))
    client = TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews,
                browse=s.browse,
                search=s.search,
                get_document=s.get_document,
                find_fact=s.find_fact,
                check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds),
                resolver=s.resolver,
                rate_limit_per_minute=0,
                suggest=s.suggest,
                models=s.models,
                sections=s.sections,
                maintainer_tokens=(TOKEN,),
            )
        )
    )
    r = client.post("/v1/models/suggest", json={"apis": ["shopify", "test-catalog-api"]}).json()
    logos = {a["id"]: a["logo"]["url"] for a in r["apis"]}
    assert logos == {"shopify": "/v1/apis/shopify/icon", "test-catalog-api": None}


def test_maintainer_claude_flow_release(client: TestClient) -> None:  # noqa: PLR0915
    g = client.post(
        "/v1/models/generate",
        headers=AUTH,
        json={"apis": APIS, "concept": "Order", "engine": "claude"},
    ).json()
    assert g["status"] == "awaiting_draft"
    assert g["snapshotId"] is None
    sid = g["sessionId"]
    assert "maintainer MCP" in g["claudePrompt"]
    assert g["maintainerMcpUrl"].endswith("/maintainer/mcp")
    assert client.get(g["contextUrl"]).json()["session_id"] == sid

    url = f"/v1/models/sessions/{sid}/draft"
    bad = client.post(url, headers=AUTH, json=_draft("bad-quote-not-in-doc"))
    assert bad.status_code == 422
    assert bad.json()["issues"][0]["code"] == "QUOTE_NOT_FOUND"
    assert bad.json()["issues"][0]["message"]
    assert client.post(url, headers={"Authorization": "Bearer nope"}, json={}).status_code == 401
    ok = client.post(url, headers=AUTH, json=_draft("good"))
    assert ok.status_code == 201
    body = ok.json()
    assert (body["visibility"], body["ownerKey"]) == ("unreleased", None)
    model = body["model"]
    mid = model["id"]
    assert model["status"] == "generated_unverified"
    assert (model["visibility"], model["official"], model["origin"]) == (
        "unreleased",
        False,
        "maintainer",
    )
    assert model["lineage"]["version"] == 1
    assert model["sharePath"] == f"/models/{mid}"
    assert model["shareUrl"] is None
    assert f'revise_model("{mid}")' in model["revisePrompt"]
    assert model["coverage"]["test-catalog-api"] == {"mapped": 5, "total": 5}
    assert model["citations"] == {"checked": 10, "found": 10, "missing": []}
    total = next(f for f in model["fields"] if f["name"] == "total")
    assert total["support"]["second-catalog-api"] == "derived"
    assert total["sources"]["second-catalog-api"]["transform"] == "parse decimal string"
    assert model["inputs"][0]["logo"]["color"].startswith("#")
    assert client.post(url, headers=AUTH, json=_draft("good")).status_code == 200  # idempotent

    # unreleased: hidden from the public, visible with the token
    assert client.get(f"/v1/models/{mid}").status_code == 404
    assert client.get(f"/v1/models/{mid}", headers=AUTH).json() == model
    assert client.get("/v1/models").json()["items"] == []
    assert client.get("/v1/models", params={"visibility": "unreleased"}).status_code == 401
    pending = client.get("/v1/models", headers=AUTH, params={"visibility": "unreleased"}).json()
    assert [m["id"] for m in pending["items"]] == [mid]
    assert client.post(f"/v1/models/{mid}/release").status_code == 401
    released = client.post(f"/v1/models/{mid}/release", headers=AUTH).json()
    assert (released["visibility"], released["official"]) == ("official", True)
    assert released["releasedAt"]
    conflict = client.post(f"/v1/models/{mid}/release", headers=AUTH)
    assert (conflict.status_code, conflict.json()["error"]) == (409, "invalid_state")
    assert client.post(f"/v1/models/{mid}/discard", headers=AUTH).status_code == 409

    got = client.get(f"/v1/models/{mid}").json()
    assert (got["stale"], got["staleInputs"], got["visibility"]) == (False, [], "official")
    item = client.get("/v1/models", params={"api": "test-catalog-api"}).json()["items"][0]
    assert (item["id"], item["official"], item["version"], item["versions"]) == (mid, True, 1, 1)
    again = client.post("/v1/models/generate", json={"apis": APIS, "concept": "orders"}).json()
    assert again["status"] == "ready"
    assert again["snapshotId"] == mid
    assert client.get("/v1/models/m-nope").status_code == 404


def test_user_flow_unlisted_share_mine_and_versions(client: TestClient) -> None:
    g = client.post("/v1/models/generate", json={"apis": APIS, "concept": "Order"}).json()
    assert g["status"] == "awaiting_draft"
    sid = g["sessionId"]
    assert "Plume MCP" in g["claudePrompt"]
    assert "maintainer" not in g["claudePrompt"]
    status = client.get(f"/v1/models/sessions/{sid}").json()
    assert (status["status"], status["snapshotId"]) == ("open", None)
    assert (
        client.post(
            "/v1/models/generate", json={"apis": APIS, "concept": "Order", "engine": "server"}
        ).status_code
        == 401
    )

    ok = client.post(f"/v1/models/sessions/{sid}/draft", json=_draft("good"))
    assert ok.status_code == 201
    body = ok.json()
    key = body["ownerKey"]
    model = body["model"]
    mid = model["id"]
    assert key.startswith("pk_")
    assert mid.startswith("u-")
    assert (body["visibility"], model["visibility"], model["official"]) == (
        "unlisted",
        "unlisted",
        False,
    )
    assert client.get(f"/v1/models/sessions/{sid}").json() == {
        "sessionId": sid,
        "status": "submitted",
        "snapshotId": mid,
        "visibility": "unlisted",
        "apis": APIS,
        "concept": "Order",
        "basedOn": None,
    }
    assert client.get(f"/v1/models/{mid}").json()["id"] == mid  # the link works for anyone
    assert client.get("/v1/models").json()["items"] == []  # never listed
    again = client.post("/v1/models/generate", json={"apis": APIS, "concept": "Order"}).json()
    assert again["status"] == "awaiting_draft"  # someone's unlisted model is never offered
    mine = client.post("/v1/models/mine", json={"ownerKeys": [key, "pk_other"]}).json()
    assert [m["id"] for m in mine["items"]] == [mid]
    assert client.post("/v1/models/mine", json={"ownerKeys": []}).status_code == 422

    rev = client.post(f"/v1/models/{mid}/revise").json()
    assert rev["basedOn"] == mid
    assert rev["startingDraft"]["name"] == "Order"
    draft = dict(_draft("good"), description="Version two.")
    v2 = client.post(
        f"/v1/models/sessions/{rev['sessionId']}/draft", params={"basedOn": mid}, json=draft
    ).json()
    assert v2["ownerKey"] is None
    lineage = v2["model"]["lineage"]
    assert (lineage["id"], lineage["version"], lineage["versions"], lineage["basedOn"]) == (
        mid,
        2,
        2,
        mid,
    )
    assert [h["version"] for h in lineage["history"]] == [1, 2]
    mine = client.post("/v1/models/mine", json={"ownerKeys": [key]}).json()["items"]
    assert [(m["id"], m["version"], m["versions"]) for m in mine] == [(v2["model"]["id"], 2, 2)]
    assert client.post(f"/v1/models/{mid}/release", headers=AUTH).status_code == 409


def test_server_generation_job(stack: FakeStack, client: TestClient) -> None:
    good = _draft("good")
    stack.writer.replies = [
        "not json",
        "```json\n" + json.dumps(_draft("bad-quote-not-in-doc")) + "\n```",
        good,
    ]
    r = client.post("/v1/models/generate", headers=AUTH, json={"apis": APIS, "concept": "Order"})
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "queued"
    assert job["eventsUrl"] == f"/v1/models/jobs/{job['jobId']}/events"
    done = client.get(f"/v1/models/jobs/{job['jobId']}", headers=AUTH).json()
    assert (done["status"], done["round"], done["maxRounds"]) == ("succeeded", 3, 3)
    assert done["generator"] == "fake:scripted"
    assert client.get(f"/v1/models/jobs/{job['jobId']}").status_code == 401
    with client.stream("GET", job["eventsUrl"], headers=AUTH) as events:
        text = "".join(events.iter_text())
    kinds = [
        line.removeprefix("event: ") for line in text.splitlines() if line.startswith("event: ")
    ]
    assert kinds == [
        "queued", "started", "context", "round", "usage", "refused", "round", "usage",
        "refused", "round", "usage", "accepted", "done",
    ]  # fmt: skip
    usage_events = [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ") and '"type": "usage"' in line
    ]
    assert all(e["totalTokens"] > 0 for e in usage_events)
    assert done["usage"]["total"] == sum(e["totalTokens"] for e in usage_events)
    refused = [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ") and '"refused"' in line
    ]
    assert refused[0]["issues"][0]["code"] == "INVALID_FORMAT"
    assert refused[1]["issues"][0]["code"] == "QUOTE_NOT_FOUND"
    assert set(refused[1]["issues"][0]) == {"code", "field", "api", "message"}
    model = client.get(f"/v1/models/{done['snapshotId']}", headers=AUTH).json()
    assert (model["visibility"], model["generator"]) == ("unreleased", "fake:scripted")
    assert model["generatorUsage"]["total"] > 0  # tokens of all its rounds
    # the LLM saw the evidence pack and, after a refusal, the issues
    system, turns = stack.writer.calls[-1]
    assert "verbatim" in system
    assert "evidence pack" in turns[0].text
    assert "QUOTE_NOT_FOUND" in turns[-1].text
    # an existing model is returned instead of regenerating, unless force
    ready = client.post(
        "/v1/models/generate", headers=AUTH, json={"apis": APIS, "concept": "Order"}
    )
    assert (ready.status_code, ready.json()["snapshotId"]) == (200, model["id"])


def test_server_generation_fails_after_max_rounds_and_without_key(
    stack: FakeStack, client: TestClient
) -> None:
    stack.writer.replies = ["{}", "{}", "{}"]
    job = client.post(
        "/v1/models/generate",
        headers=AUTH,
        json={"apis": APIS, "concept": "Order", "force": True},
    ).json()
    done = client.get(f"/v1/models/jobs/{job['jobId']}", headers=AUTH).json()
    assert done["status"] == "failed"
    assert done["error"].startswith("draft_refused")
    stack.writer = type(stack.writer)(available=False)
    r = client.post("/v1/models/generate", headers=AUTH, json={"apis": APIS, "concept": "Order"})
    assert (r.status_code, r.json()["error"]) == (503, "llm_unavailable")


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
            generate=stack.generate,
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
        assert accepted["visibility"] == "unreleased"
        assert "owner_key" not in accepted
        snap = await call(client, "get_model", snapshot_id=accepted["snapshot_id"])
        assert snap["name"] == "Order"
        listed = await call(
            client, "list_models", api="second-catalog-api", visibility="unreleased"
        )
        assert listed["models"][0]["snapshot_id"] == accepted["snapshot_id"]
        assert listed["models"][0]["stale"] is False
        assert "stale" in listed["note"]
        released = await call(client, "release_model", snapshot_id=accepted["snapshot_id"])
        assert released["official"] is True
        stack.writer.replies = [_draft("good")]
        job = await call(client, "generate_model", apis=APIS, concept="Order")
        gen = await call(client, "get_generation", job_id=job["job_id"])
        assert gen["status"] == "succeeded"
        build = stack.resolver().resolve("test-catalog-api").build.build_id.value
        pub = await call(client, "publish_build", api="test-catalog-api", build=build, tag="stable")
        assert pub["previous"] is None
        err = await client.call_tool("get_model_context", {"session_id": "s-nope"})
        assert err.is_error


@pytest.mark.anyio
async def test_reader_mcp_user_model_flow(stack: FakeStack) -> None:
    from plume.interfaces.mcp.reader_server import (  # noqa: PLC0415
        McpReaderDependencies,
        create_reader_server,
    )

    server = create_reader_server(
        McpReaderDependencies(
            overviews=stack.overviews,
            search=stack.search,
            get_document=stack.get_document,
            find_fact=stack.find_fact,
            check_call=stack.check_call,
            list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds),
            resolver=stack.resolver,
            models=stack.models,
            web_public_url="http://127.0.0.1:18493",
        )
    )

    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(server) as client:
        assert client.instructions is not None
        assert "list_my_models" in client.instructions
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {"submit_model_draft", "revise_model", "list_my_models", "list_models"} <= tools
        assert not {"release_model", "discard_model", "generate_model"} & tools
        session = await call(client, "start_model_session", apis=APIS, concept="Order")
        saved = await call(
            client, "submit_model_draft", session_id=session["session_id"], draft=_draft("good")
        )
        assert saved["visibility"] == "unlisted"
        assert saved["share_url"] == f"http://127.0.0.1:18493/models/{saved['snapshot_id']}"
        assert saved["owner_key"].startswith("pk_")
        rev = await call(client, "revise_model", snapshot_id=saved["snapshot_id"])
        v2 = await call(
            client,
            "submit_model_draft",
            session_id=rev["session_id"],
            draft=dict(rev["starting_draft"], description="Changed."),
            based_on=saved["snapshot_id"],
        )
        assert v2["version"] == 2
        mine = await call(client, "list_my_models", owner_keys=[saved["owner_key"]])
        assert [m["snapshot_id"] for m in mine["models"]] == [v2["snapshot_id"]]
        assert (await call(client, "list_models"))["models"] == []


def test_suggest_related_route_and_mcp_tool(packages: Path, tmp_path: Path) -> None:
    import anyio  # noqa: PLC0415

    from plume.interfaces.mcp.reader_server import (  # noqa: PLC0415
        McpReaderDependencies,
        create_reader_server,
    )

    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("shopify-mini", "woo-mini"):
        s.load(str(packages / p))
    client = TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews,
                browse=s.browse,
                search=s.search,
                get_document=s.get_document,
                find_fact=s.find_fact,
                check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds),
                resolver=s.resolver,
                rate_limit_per_minute=0,
                suggest=s.suggest,
                models=s.models,
                suggest_related=s.suggest_related,
                maintainer_tokens=(TOKEN,),
            )
        )
    )
    body = {"apis": ["shopify", "woocommerce"], "concept": "Product"}
    r = client.post("/v1/models/suggest-related", json=body).json()
    assert r["concept"] == {"id": "product", "name": "Product"}
    variant = next(x for x in r["related"] if x["id"] == "variant")
    assert variant["kinds"]["shopify"] == ["id_field"]
    cand = variant["candidates"][0]
    assert cand["parent"]["id"] == "product"
    assert cand["options"] == [
        {"kind": "reference", "cardinality": "n:1", "needs": cand["options"][0]["needs"]}
    ]
    ev = cand["sources"]["shopify"][0]
    assert set(ev) == {"kind", "docId", "quote", "paths", "fetch", "many", "read"}
    assert r["apis"][0]["logo"]["text"]
    assert (r["total"], r["offset"], r["nextOffset"]) == (len(r["related"]), 0, None)
    bad = client.post("/v1/models/suggest-related", json={**body, "apis": ["shopify"]})
    assert bad.status_code == 422

    server = create_reader_server(
        McpReaderDependencies(
            overviews=s.overviews,
            search=s.search,
            get_document=s.get_document,
            find_fact=s.find_fact,
            check_call=s.check_call,
            list_builds=lambda: ListBuilds(s.builds, s.tags),
            diff_builds=lambda: DiffBuilds(s.builds),
            resolver=s.resolver,
            models=s.models,
            suggest_related=s.suggest_related,
        )
    )

    async def mcp() -> dict[str, Any]:
        async with Client(server) as c:
            tool = next(t for t in (await c.list_tools()).tools if t.name == "suggest_related")
            assert "never decide silently" in (tool.description or "")
            res = await c.call_tool("suggest_related", body)
            return dict(res.structured_content or {})

    assert anyio.run(mcp)["related"] == r["related"]
