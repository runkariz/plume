import json

from fastapi.testclient import TestClient

from plume.interfaces.http.app import create_app
from tests.fakes.stack import FakeStack
from tests.unit.interfaces.conftest import http_deps

ASSIGNED = "endpoint:GET~/admin/api/{version}/assigned_fulfillment_orders.json"


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_list_and_detail(client: TestClient) -> None:
    items = client.get("/v1/apis").json()["items"]
    assert [i["id"] for i in items] == ["shopify", "test-catalog-api"]
    shop = items[0]
    assert shop["endpoints"] == 8
    assert shop["category"] == "e-commerce"
    assert shop["status"] == {"kind": "ready", "recallAt5": None}
    assert shop["logo"]["text"] == "S"
    assert shop["docsAsOf"]

    detail = client.get("/v1/apis/shopify").json()
    assert detail["tag"] == "latest"
    assert detail["isLive"] is True
    assert detail["index"]["build"].startswith("b-")
    assert detail["index"]["dimensions"] == 768
    assert detail["quality"] is None
    assert "claude mcp add --transport http plume" in detail["connect"]["claudeCode"]


def test_errors(client: TestClient) -> None:
    r = client.get("/v1/apis/nope")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"
    assert client.get("/v1/apis/shopify?version=nope").status_code == 404
    assert client.post("/v1/apis/shopify/search", json={"query": ""}).status_code == 422
    r = client.post("/v1/apis/shopify/find-fact", json={"name": "x", "owner": "model:nope"})
    assert r.status_code == 404


def test_items(client: TestClient) -> None:
    r = client.get("/v1/apis/shopify/items", params={"kind": "endpoint", "limit": 2}).json()
    assert r["total"] == 8
    assert len(r["items"]) == 2
    assert r["items"][0]["method"]
    assert client.get("/v1/apis/shopify/items", params={"kind": "widget"}).status_code == 422


def test_search_and_payload(client: TestClient) -> None:
    r = client.post(
        "/v1/apis/shopify/search", json={"query": "assigned fulfillment orders", "topK": 3}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["id"] == ASSIGNED
    assert {"denseRank", "textRank", "denseScore", "textScore", "fused"} <= set(body["results"][0])
    assert [t["label"] for t in body["trace"]][-1] == "fuse (RRF)"
    payload = json.loads(body["claudePayload"])
    assert payload["results"][0]["doc_id"] == ASSIGNED
    assert payload["build"] == body["build"]


def test_ask_returns_passages(client: TestClient) -> None:
    r = client.post("/v1/apis/shopify/ask", json={"question": "How do I list products?"}).json()
    assert r["question"] == "How do I list products?"
    assert r["passages"]
    assert {"id", "title", "quote", "sourceUrl"} <= set(r["passages"][0])


def test_document(client: TestClient) -> None:
    r = client.get("/v1/apis/shopify/documents/model:customer").json()
    assert r["title"] == "Customer"
    assert r["complete"] is False
    assert r["fields"]
    by_name = {f["name"]: f for f in r["fields"]}
    assert by_name["default_address"]["modelId"] == "model:address"  # $ref'd model
    assert by_name["email"]["modelId"] is None
    doc = client.get(f"/v1/apis/shopify/documents/{ASSIGNED}").json()
    assert doc["scopes"] == ["read_assigned_fulfillment_orders"]


def test_find_fact(client: TestClient) -> None:
    r = client.post("/v1/apis/shopify/find-fact", json={"name": "since_id"}).json()
    assert r["found"] is True
    assert r["matches"][0]["evidence"]["anchor"].endswith("/properties/since_id")
    absent = client.post(
        "/v1/apis/test-catalog-api/find-fact", json={"name": "loyalty_points"}
    ).json()
    assert absent["found"] is False
    assert absent["complete"] is True
    assert absent["checked"] == {"endpoints": 2, "models": 3}


def test_check_call(client: TestClient) -> None:
    r = client.post(
        "/v1/apis/shopify/check-call",
        json={"method": "GET", "path": "/admin/api/2026-10/products/1.json", "params": ["fields"]},
    ).json()
    assert r["verdict"] == "documented"
    assert r["matched"]["path"] == "/admin/api/{version}/products/{product_id}.json"
    assert r["paramChecks"] == [{"name": "fields", "found": True, "where": "query"}]
    unknown = {"method": "GET", "path": "/admin/api/2026-10/products.json", "bodyFields": ["x"]}
    assert client.post("/v1/apis/shopify/check-call", json=unknown).status_code == 422
    named = {"method": "GET", "path": "/admin/api/2026-10/products/1.json", "query": ["fields"]}
    assert client.post("/v1/apis/shopify/check-call", json=named).json()["verdict"] == "documented"


def test_builds_and_diff(client: TestClient) -> None:
    builds = client.get("/v1/apis/shopify/builds").json()["items"]
    assert builds[0]["tags"] == ["latest"]
    assert builds[0]["status"] == "sealed"
    b = builds[0]["id"]
    d = client.get("/v1/apis/shopify/diff", params={"from": b, "to": "latest"}).json()
    assert d["added"] == []
    assert d["unchanged"] == builds[0]["items"]
    assert client.get("/v1/apis/nope/builds").status_code == 404


def test_rate_limit(stack: FakeStack) -> None:
    client = TestClient(create_app(http_deps(stack, rate=2)))
    assert client.get("/v1/apis").status_code == 200
    assert client.get("/v1/apis").status_code == 200
    r = client.get("/v1/apis")
    assert r.status_code == 429
    assert r.headers["retry-after"]
    assert client.get("/health").status_code == 200  # exempt


def test_cors(client: TestClient) -> None:
    r = client.options(
        "/v1/apis",
        headers={"Origin": "http://127.0.0.1:18473", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:18473"
