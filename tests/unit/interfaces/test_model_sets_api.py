"""Model sets over HTTP and MCP (the shapes plume-9a builds the diagram on)."""

from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.apps.model_view import MODEL_VIEW_URI
from plume.interfaces.mcp.maintainer_server import (
    McpMaintainerDependencies,
    create_maintainer_server,
)
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.application.test_model_sets import APIS, _order, _product, _relation

TOKEN = "pl_sets_test_token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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
                collections=stack.collections,
                model_sets=stack.model_sets,
                maintainer_tokens=(TOKEN,),
                web_public_url="https://plume.example",
            )
        )
    )


def _members(
    client: TestClient, stack: FakeStack, headers: dict[str, str]
) -> tuple[str, dict[str, str], dict[str, str]]:
    start = client.post(
        "/v1/model-sets/sessions", json={"apis": APIS, "concepts": ["Order", "Product"]},
        headers=headers,
    ).json()  # fmt: skip
    pins = {i["api"]: i["build"] for i in start["inputs"]}
    ids = {}
    for concept, draft in (("Order", _order(stack, pins)), ("Product", _product(stack, pins))):
        sid = start["memberSessions"][concept]
        r = client.post(f"/v1/models/sessions/{sid}/draft", json=draft, headers=headers)
        assert r.status_code == 201, r.json()
        ids[concept] = r.json()["model"]["id"]
    return start["setSessionId"], pins, ids


def test_user_set_over_http(client: TestClient, stack: FakeStack) -> None:
    ss, pins, ids = _members(client, stack, {})
    ctx = client.get(f"/v1/model-sets/sessions/{ss}/context").json()
    assert [m["concept"] for m in ctx["members"]] == ["Order", "Product"]
    body = {"name": "Shop", "members": ids, "relations": [_relation(stack, pins)]}
    r = client.post(f"/v1/model-sets/sessions/{ss}/draft", json=body)
    assert r.status_code == 201
    out = r.json()
    x = out["set"]
    assert (out["visibility"], x["kind"], x["visibility"]) == ("unlisted", "model_set", "unlisted")
    assert "ownerKey" not in out
    link = out["collection"]
    assert link["created"] is True
    assert link["url"] == f"https://plume.example/mine/{link['id']}"
    assert [m["concept"] for m in x["members"]] == ["Order", "Product"]
    assert x["members"][0]["fieldCount"] == 6
    rel = x["relations"][0]
    assert (rel["from"], rel["to"], rel["kind"], rel["confirmed"]) == (
        "Order", "Product", "embedded", True,
    )  # fmt: skip
    assert rel["support"] == {APIS[0]: "nested", APIS[1]: "nested"}
    assert rel["sources"][APIS[0]]["evidence"][0]["docId"].startswith("endpoint:")
    assert x["shareUrl"] == f"https://plume.example/model-sets/{x['id']}"
    assert x["inputs"][0]["logo"]["text"]
    assert client.get(f"/v1/model-sets/{x['id']}").json()["id"] == x["id"]
    assert client.get("/v1/model-sets").json()["items"] == []
    mine = client.get(f"/v1/collections/{link['id']}").json()
    assert [i["id"] for i in mine["sets"]] == [x["id"]]
    status = client.get(f"/v1/model-sets/sessions/{ss}").json()
    assert (status["status"], status["set_id"]) == ("submitted", x["id"])
    bad = {**body, "relations": [_relation(stack, pins, cardinality="1:1")]}
    refused = client.post(f"/v1/model-sets/sessions/{ss}/draft", json=bad)
    assert refused.status_code == 422
    assert refused.json()["issues"][0]["code"] == "RELATION_SHAPE_MISMATCH"
    assert client.post(f"/v1/model-sets/{x['id']}/release").status_code == 401


def test_maintainer_release_lists_members(client: TestClient, stack: FakeStack) -> None:
    ss, pins, ids = _members(client, stack, AUTH)
    body = {"name": "Shop", "members": ids, "relations": [_relation(stack, pins)]}
    x = client.post(f"/v1/model-sets/sessions/{ss}/draft", json=body, headers=AUTH).json()["set"]
    assert client.get(f"/v1/model-sets/{x['id']}").status_code == 404
    pending = client.get("/v1/model-sets", params={"visibility": "unreleased"}, headers=AUTH)
    assert [i["id"] for i in pending.json()["items"]] == [x["id"]]
    released = client.post(f"/v1/model-sets/{x['id']}/release", headers=AUTH).json()
    assert sorted(released["releasedMembers"]) == sorted(ids.values())
    assert released["set"]["official"] is True
    assert [i["id"] for i in client.get("/v1/model-sets").json()["items"]] == [x["id"]]
    assert client.post(f"/v1/model-sets/{x['id']}/release", headers=AUTH).status_code == 409


def test_set_tools_on_the_maintainer_mcp(stack: FakeStack) -> None:
    server = create_maintainer_server(
        McpMaintainerDependencies(
            suggest=stack.suggest,
            models=stack.models,
            resolver=stack.resolver,
            tag_build=stack.tag,
            model_sets=stack.model_sets,
        )
    )

    async def flow() -> dict[str, Any]:
        async with Client(server) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert (tools["get_model_set"].meta or {})["ui"]["resourceUri"] == MODEL_VIEW_URI
            assert (tools["submit_model_set"].meta or {})["ui"]["visibility"] == ["model"]
            assert {"release_model_set", "discard_model_set", "list_model_sets"} <= set(tools)
            start = (
                await c.call_tool(
                    "start_set_session", {"apis": APIS, "concepts": ["Order", "Product"]}
                )
            ).structured_content or {}
            pins = {i["api"]: i["build"] for i in start["inputs"]}
            ids = {}
            for concept, draft in (
                ("Order", _order(stack, pins)),
                ("Product", _product(stack, pins)),
            ):
                r = await c.call_tool(
                    "submit_model_draft",
                    {"session_id": start["member_sessions"][concept], "draft": draft},
                )
                ids[concept] = (r.structured_content or {})["snapshot_id"]
            undecided = await c.call_tool(
                "submit_model_set",
                {
                    "set_session_id": start["set_session_id"],
                    "draft": {"name": "Shop", "members": ids,
                              "relations": [_relation(stack, pins, confirmed=False)]},
                },
            )  # fmt: skip
            text = "".join(getattr(x, "text", "") for x in undecided.content)
            assert "UNDECIDED: ask the user" in text
            set_id = (undecided.structured_content or {})["set_id"]
            refused = await c.call_tool("release_model_set", {"set_id": set_id})
            assert refused.is_error
            got = await c.call_tool("get_model_set", {"set_id": set_id})
            return dict(got.structured_content or {})

    x = anyio.run(flow)
    assert (x["kind"], x["undecided"]) == ("model_set", ["order-items"])


def test_web_relation_edit(client: TestClient, stack: FakeStack) -> None:
    ss, pins, ids = _members(client, stack, {})
    body = {"name": "Shop", "members": ids, "relations": [_relation(stack, pins)]}
    x = client.post(f"/v1/model-sets/sessions/{ss}/draft", json=body).json()["set"]
    options = x["relations"][0]["editableOptions"]
    by = {(o["kind"], o["cardinality"]): o for o in options}
    assert by[("embedded", "1:n")]["editable"] is True
    assert by[("embedded", "1:n")]["current"] is True
    assert by[("embedded", "1:1")]["editable"] is False  # Order.items is an array
    ref = by[("reference", "n:1")]
    assert (ref["from"], ref["to"], ref["editable"]) == ("Product", "Order", False)
    assert ref["missing"] == ["Product: a field holding the Order id"]
    url = f"/v1/model-sets/{x['id']}/relations"
    v2 = client.post(url, json={"relations": [{"id": "order-items", "confirmed": False}]})
    assert v2.status_code == 201
    v2set = v2.json()["set"]
    assert (v2set["lineage"]["version"], v2set["undecided"]) == (2, ["order-items"])
    assert v2.json()["collection"]["created"] is False  # the set's existing link
    stale = client.post(url, json={"relations": [{"id": "order-items", "confirmed": True}]})
    assert stale.status_code == 409  # v1 is no longer the latest
    url2 = f"/v1/model-sets/{v2set['id']}/relations"
    shape = client.post(url2, json={"relations": [{"id": "order-items", "cardinality": "1:1"}]})
    assert shape.status_code == 422
    assert shape.json()["issues"][0]["code"] == "RELATION_SHAPE_MISMATCH"
    evidence = client.post(url2, json={"relations": [{"id": "order-items", "sources": {}}]})
    assert evidence.status_code == 400
    unknown = client.post(url2, json={"relations": [{"id": "nope", "confirmed": True}]})
    assert unknown.status_code == 400


def _shop_draft(stack: FakeStack, name: str, fields: dict[str, str]) -> dict[str, Any]:
    from plume.domain.shared.ids import BuildId  # noqa: PLC0415

    build = BuildId(stack.resolver().resolve("shopify").build.build_id.value)
    doc_id = "endpoint:GET~/admin/api/{version}/products.json"
    doc = stack.documents.get_document(build, doc_id)
    assert doc is not None
    specs = {f.name: f for f in doc.fields}
    return {
        "name": name,
        "fields": [
            {
                "name": canonical,
                "type": "string",
                "sources": {
                    "shopify": {
                        "paths": [{"path": path}],
                        "evidence": [{"doc_id": doc_id, "quote": specs[path].description}],
                    }
                },
            }
            for canonical, path in fields.items()
        ],
    }


def test_server_generated_set_proposes_undecided_relations(packages: Path, tmp_path: Path) -> None:
    s = FakeStack(embedder=WordEmbedder(), data_dir=tmp_path)
    for p in ("shopify-mini", "woo-mini"):
        s.load(str(packages / p))
    s.writer.replies = [
        _shop_draft(s, "Product", {"id": "products[].id"}),
        _shop_draft(
            s, "Variant",
            {"id": "products[].variants[].id", "product_id": "products[].variants[].product_id"},
        ),
    ]  # fmt: skip
    client = TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews, browse=s.browse, search=s.search,
                get_document=s.get_document, find_fact=s.find_fact, check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds), resolver=s.resolver,
                rate_limit_per_minute=0, suggest=s.suggest, models=s.models,
                collections=s.collections,
                model_sets=s.model_sets, generate_models=s.generate, maintainer_tokens=(TOKEN,),
            )
        )
    )  # fmt: skip
    body = {"apis": ["shopify", "woocommerce"], "concepts": ["Product", "Variant"]}
    assert client.post("/v1/model-sets/generate", json=body).status_code == 401
    job = client.post("/v1/model-sets/generate", json=body, headers=AUTH).json()
    done = client.get(f"/v1/models/jobs/{job['jobId']}", headers=AUTH).json()
    assert (done["status"], done["kind"]) == ("succeeded", "model_set")
    x = client.get(f"/v1/model-sets/{done['setId']}", headers=AUTH).json()
    assert x["visibility"] == "unreleased"
    (rel,) = x["relations"]
    assert (rel["from"], rel["to"], rel["kind"], rel["confirmed"]) == (
        "Variant", "Product", "reference", False,
    )  # fmt: skip
    assert rel["ref"] == {"field": "product_id", "key": "id"}
    assert rel["support"] == {"shopify": "id_field", "woocommerce": None}
    assert x["undecided"] == [rel["id"]]
    assert client.post(f"/v1/model-sets/{x['id']}/release", headers=AUTH).status_code == 409
    with client.stream("GET", f"/v1/models/jobs/{job['jobId']}/events", headers=AUTH) as r:
        events = [ln[7:] for ln in "".join(r.iter_text()).splitlines() if ln.startswith("event: ")]
    assert events.count("member") == 2
    assert events[-3:] == ["proposals", "accepted", "done"]
    decided = client.post(
        f"/v1/model-sets/{x['id']}/relations",
        json={"relations": [{"id": rel["id"], "confirmed": True}]},
        headers=AUTH,
    ).json()["set"]
    released = client.post(f"/v1/model-sets/{decided['id']}/release", headers=AUTH).json()
    assert len(released["releasedMembers"]) == 2


def test_aliases_on_set_sessions(client: TestClient) -> None:
    body = {
        "apis": APIS,
        "concepts": ["Order", "Product"],
        "aliases": [{"concept": "Product", "names": {APIS[1]: "items"}}],
    }
    r = client.post("/v1/model-sets/sessions", json=body).json()
    assert r["aliases"] == [{"concept": "Product", "names": {APIS[1]: "items"}}]
    assert f"Treat {APIS[1]} 'items' as Product" in r["claudePrompt"]
    ctx = client.get(r["contextUrl"]).json()
    assert ctx["accepted_aliases"] == r["aliases"]
    bad = {**body, "aliases": [{"concept": "Nope", "names": {APIS[0]: "x"}}]}
    assert client.post("/v1/model-sets/sessions", json=bad).status_code == 400
