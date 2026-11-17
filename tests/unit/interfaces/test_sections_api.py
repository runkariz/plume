"""Package sections over HTTP and MCP: auth, triggers, icon, tags, raw (fixtures, in memory)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from plume.interfaces.mcp.reader_server import McpReaderDependencies, create_reader_server
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.infrastructure.test_trigger_payload import payload_package


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("shopify-mini", "woo-mini", "test-catalog"):
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
                sections=stack.sections,
                rate_limit_per_minute=0,
            )
        )
    )


def test_auth_list_and_detail_are_verbatim(client: TestClient) -> None:
    woo = client.get("/v1/apis/woocommerce/auth").json()
    assert woo["present"] is True
    assert woo["note"] is None
    assert {s["type"] for s in woo["schemes"]} == {"API_KEY", "BASIC"}
    key = next(s for s in woo["schemes"] if s["queryParam"] == "consumer_key")
    detail = client.get(f"/v1/apis/woocommerce/auth/{key['id']}").json()
    assert detail["scheme"]["codeQueryParamName"] == "consumer_key"
    assert detail["variablesSchema"]["required"] == ["api_key", "host"]
    assert {v["name"]: v["required"] for v in detail["variables"]} == {
        "api_key": True,
        "host": True,
    }
    assert client.get(f"/v1/apis/woocommerce/auth/{key['docId']}").status_code == 200
    shop = client.get("/v1/apis/shopify/auth/oauth2-authorization-code").json()
    assert shop["type"] == "OAUTH2"
    assert shop["grantType"] == "authorization_code"
    assert len(shop["scopes"]) > 10
    assert client.get("/v1/apis/shopify/auth/nope").status_code == 404


def test_triggers_present_and_absent(client: TestClient) -> None:
    shop = client.get("/v1/apis/shopify/triggers").json()
    assert shop["present"] is True
    assert shop["total"] == 3
    keys = {t["key"]: t for t in shop["items"]}
    assert set(keys) == {"app/scopes_update", "carts/create", "draft_orders/create"}
    assert keys["carts/create"]["delivery"] == "webhook"
    one = client.get("/v1/apis/shopify/triggers/app/scopes_update").json()
    assert one["event"]["key"] == "app/scopes_update"
    assert one["description"].startswith("Occurs whenever the access scopes")
    by_doc = client.get(f"/v1/apis/shopify/triggers/{one['docId']}").json()
    assert by_doc["key"] == "app/scopes_update"
    woo = client.get("/v1/apis/woocommerce/triggers").json()
    assert (woo["present"], woo["note"], woo["items"]) == (False, "not in this package", [])
    assert client.get("/v1/apis/shopify/triggers/nope/nope").status_code == 404


def test_icon_and_logo(client: TestClient) -> None:
    items = {a["id"]: a for a in client.get("/v1/apis").json()["items"]}
    assert items["shopify"]["logo"]["url"] == "/v1/apis/shopify/icon"
    assert items["test-catalog-api"]["logo"]["url"] is None  # no icon in that package
    r = client.get("/v1/apis/woocommerce/icon")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cross-origin-resource-policy"] == "cross-origin"
    other = client.get("/v1/apis")
    assert other.headers["cross-origin-resource-policy"] == "same-site"  # only the icon differs
    again = client.get("/v1/apis/woocommerce/icon", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
    assert client.get("/v1/apis/test-catalog-api/icon").status_code == 404


def test_items_tags_kinds_and_resolvable_ids(client: TestClient) -> None:
    hooks = client.get("/v1/apis/shopify/items", params={"kind": "trigger"}).json()
    assert hooks["total"] == 3
    for kind in ("endpoint", "model", "guide", "auth", "trigger", "app"):
        for item in client.get("/v1/apis/shopify/items", params={"kind": kind}).json()["items"]:
            doc = client.get(f"/v1/apis/shopify/documents/{item['id']}")
            assert doc.status_code == 200, item["id"]
    first = client.get("/v1/apis/woocommerce/items", params={"kind": "endpoint"}).json()
    assert all("v3" in i["tags"] for i in first["items"])
    tagged = client.get("/v1/apis/woocommerce/items", params={"tag": "nope"}).json()
    assert tagged["total"] == 0


def test_document_raw_responses_errors_and_sections(client: TestClient) -> None:
    item = client.get("/v1/apis/woocommerce/items", params={"kind": "endpoint"}).json()["items"][0]
    doc = client.get(f"/v1/apis/woocommerce/documents/{item['id']}").json()
    assert doc["raw"]["endpointId"]
    assert doc["rawTruncated"] is False
    assert "v3" in doc["tags"]
    assert doc["responses"] == [r for r in doc["raw"].get("responses", []) if isinstance(r, dict)]
    detail = client.get("/v1/apis/shopify").json()
    assert detail["sections"] == {"auth": 1, "triggers": 3, "webhookEndpoints": 1}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_section_tools(stack: FakeStack) -> None:
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
            sections=stack.sections,
        )
    )

    async def call(client: Client, tool: str, **args: Any) -> dict[str, Any]:
        result = await client.call_tool(tool, args)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return dict(result.structured_content)

    async with Client(server) as client:
        auth = await call(client, "list_auth_schemes", api="woocommerce")
        assert len(auth["schemes"]) == 3
        one = await call(
            client, "get_auth_scheme", api="shopify", scheme_id="oauth2-authorization-code"
        )
        assert one["scheme"]["headerName"] == "X-Shopify-Access-Token"
        none = await call(client, "list_triggers", api="woocommerce")
        assert none["present"] is False
        trig = await call(client, "get_trigger", api="shopify", key="carts/create")
        assert trig["event"]["delivery"] == "webhook"


def test_environments_are_verbatim(client: TestClient) -> None:
    env = client.get("/v1/apis/woocommerce/environments").json()
    assert env["present"] is True
    assert env["environments"][0]["key"] == "production"
    assert env["versioning"] is not None
    shop = client.get("/v1/apis/test-catalog-api/environments").json()
    assert shop["environments"][0]["servers"]["api"] == "http://127.0.0.1:18091"


def test_webhook_mechanism_is_verbatim(client: TestClient) -> None:
    shop = client.get("/v1/apis/shopify/triggers").json()
    assert len(shop["webhooks"]) == 1
    hook = shop["webhooks"][0]
    assert "carts/create" in hook["eventsAvailable"]
    assert hook["subscribe"]["endpointId"]
    woo = client.get("/v1/apis/woocommerce/triggers").json()
    assert woo["webhooks"] == []
    env = client.get("/v1/apis/shopify/environments").json()
    assert env["variablesSchema"]["properties"]["host"]["type"] == "string"


def test_vendor_mcp_section(packages: Path, tmp_path: Path) -> None:
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    pkg = tmp_path / "with-mcp"
    shutil.copytree(packages / "test-catalog", pkg)
    mcp = pkg / "connector" / "mcp"
    (mcp / "servers").mkdir(parents=True)
    (mcp / "servers" / "srv.json").write_text(json.dumps({"id": "srv", "url": "https://x/mcp"}))
    tool = mcp / "tools" / "srv" / "search"
    tool.mkdir(parents=True)
    (tool / "tool.json").write_text(json.dumps({"name": "search", "description": "Search"}))
    (tool / "input.schema.json").write_text(json.dumps({"type": "object"}))
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(pkg))
    _, section = stack.sections().mcp("test-catalog-api")
    assert section == {
        "servers": [
            {
                "id": "srv",
                "server": {"id": "srv", "url": "https://x/mcp"},
                "tools": [
                    {
                        "tool": {"name": "search", "description": "Search"},
                        "input_schema": {"type": "object"},
                        "output_schema": None,
                    }
                ],
            }
        ]
    }
    plain = FakeStack(embedder=WordEmbedder())
    plain.load(str(packages / "test-catalog"))
    assert plain.sections().mcp("test-catalog-api")[1] is None


def test_mcp_route_absent(client: TestClient) -> None:
    r = client.get("/v1/apis/woocommerce/mcp").json()
    assert (r["present"], r["note"], r["servers"]) == (False, "not in this package", [])


def test_webhook_endpoint_ids_resolve(client: TestClient) -> None:
    shop = client.get("/v1/apis/shopify/triggers").json()
    hook = shop["webhooks"][0]
    refs = shop["endpointRefs"]
    sub = hook["subscribe"]["endpointId"]
    assert refs[sub]["method"] == "POST"
    assert refs[sub]["path"].endswith("/webhooks.json")
    assert client.get(f"/v1/apis/shopify/documents/{refs[sub]['docId']}").status_code == 200
    unsub = hook["unsubscribe"]["endpointId"]
    assert refs[unsub] is None  # not in this (mini) build
    assert client.get("/v1/apis/woocommerce/triggers").json()["endpointRefs"] == {}


def test_scopes_carry_their_endpoints_and_endpoints_their_scheme(client: TestClient) -> None:
    """requiredScopes [{authId, scopes}]: the auth scheme lists the endpoints per scope; the
    endpoint document states the scheme with its scopes."""
    shop = client.get("/v1/apis/shopify/auth").json()
    details = [client.get(f"/v1/apis/shopify/auth/{x['id']}").json() for x in shop["schemes"]]
    scopes = {s["scope"]: s for d in details for s in d["scopes"]}
    op = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"
    assert scopes["read_assigned_fulfillment_orders"]["endpoints"] == [op]
    doc = client.get("/v1/apis/shopify/documents/" + op).json()
    assert doc["requiredScopes"] == [
        {"authId": "oauth2-authorization-code", "scopes": ["read_assigned_fulfillment_orders"]}
    ]
    assert doc["guides"] == []
    woo = client.get("/v1/apis/woocommerce/auth").json()  # no requiredScopes: no endpoints
    for x in woo["schemes"]:
        detail = client.get(f"/v1/apis/woocommerce/auth/{x['id']}").json()
        assert all(s["endpoints"] == [] for s in detail["scopes"])


def test_unit_documents_state_the_basis_of_each_endpoint_link(
    packages: Path, tmp_path: Path
) -> None:
    from tests.unit.infrastructure.test_package_links import _woo_with_export_links  # noqa: PLC0415
    from tests.unit.interfaces.conftest import http_deps  # noqa: PLC0415

    s = FakeStack(embedder=WordEmbedder())
    s.load(str(_woo_with_export_links(packages, tmp_path)))
    c = TestClient(create_app(http_deps(s)))
    doc = c.get("/v1/apis/woocommerce/documents/guide:authentication").json()
    get, post = (f"endpoint:{m}~/wp-json/wc/{{version}}/coupons" for m in ("GET", "POST"))
    assert doc["linkedEndpoints"] == [get, post]
    assert doc["endpointLinks"] == [
        {"endpointId": get, "linkBasis": "text"},
        {"endpointId": post, "linkBasis": "page"},
    ]
    assert c.get(f"/v1/apis/woocommerce/documents/{post}").json()["endpointLinks"] == []


def _payload_stack(packages: Path, tmp_path: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(payload_package(packages, tmp_path)))
    return s


def test_trigger_detail_carries_the_payload(packages: Path, tmp_path: Path) -> None:
    stack = _payload_stack(packages, tmp_path)
    app = create_app(
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
            sections=stack.sections,
            rate_limit_per_minute=0,
        )
    )
    http = TestClient(app)
    cart = http.get("/v1/apis/shopify/triggers/carts/create").json()
    payload = cart["payload"]
    assert payload["schemaRef"] == "carts-create.payload.schema.json"
    assert payload["schema"]["required"] == ["id"]
    assert payload["sample"] == {"id": 7, "line_items": [{"sku": "A-1"}]}
    assert payload["model"] is None
    assert [f["name"] for f in payload["fields"]] == ["id", "line_items", "line_items[].sku"]
    assert payload["fields"][0]["location"] == "body"
    assert "_payload" not in cart["event"]
    draft = http.get("/v1/apis/shopify/triggers/draft_orders/create").json()
    assert draft["payload"]["model"] == {"docId": "model:customer", "title": "Customer"}
    assert draft["payload"]["schema"] is None
    scopes = http.get("/v1/apis/shopify/triggers/app/scopes_update").json()
    assert scopes["payload"]["fields"] == []
    listed = http.get("/v1/apis/shopify/triggers").json()
    assert "payload" not in listed["items"][0]


@pytest.mark.anyio
async def test_mcp_get_trigger_carries_the_payload(packages: Path, tmp_path: Path) -> None:
    stack = _payload_stack(packages, tmp_path)
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
            sections=stack.sections,
        )
    )
    async with Client(server) as client:
        result = await client.call_tool("get_trigger", {"api": "shopify", "key": "carts/create"})
        assert not result.is_error, result.content
        trig = dict(result.structured_content or {})
        assert trig["payload"]["sample"]["id"] == 7
        assert {f["name"] for f in trig["payload"]["fields"]} >= {"id", "line_items[].sku"}
        listed = await client.call_tool("list_triggers", {"api": "shopify"})
        assert all("payload" not in t for t in (listed.structured_content or {})["triggers"])
