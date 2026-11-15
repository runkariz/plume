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
    assert keys["orders/create"]["delivery"] == "webhook"
    assert keys["orders/create"]["description"] is None  # absent in the package: null
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
    assert detail["sections"] == {"auth": 1, "triggers": 3, "webhookEndpoints": 0}


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
        trig = await call(client, "get_trigger", api="shopify", key="orders/create")
        assert trig["event"]["delivery"] == "webhook"
