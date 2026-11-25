"""A model's document lists the endpoints that use it (used_by): fields whose type is the model
($ref, or stream's x-kariz-model on an inline copy, treated exactly like a $ref), plus the
operations a bundled response title names (x-plume-returned-by). linked_endpoints stays for
knowledge units."""

import json
import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plume.interfaces import payloads
from plume.interfaces.http.app import create_app
from tests.fakes.stack import FakeStack
from tests.unit.interfaces.conftest import http_deps

FOLDER = "get-insights"
INSIGHTS = {  # stream's inline copy of model:address, marked
    "type": "object",
    "properties": {
        "data": {
            "type": "array",
            "items": {
                "type": "object", "title": "Address", "x-kariz-model": "address.schema.json",
                "properties": {"city": {"type": "string"}, "zip": {"type": "string"}},
            },
        },
    },
}  # fmt: skip


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> FakeStack:
    from tests.conftest import PACKAGES  # noqa: PLC0415

    dst = tmp_path_factory.mktemp("used") / "shopify"
    shutil.copytree(PACKAGES / "shopify-mini", dst)
    d = dst / "connector" / "endpoints" / FOLDER
    (d / "responses").mkdir(parents=True)
    (d / "responses" / "200.schema.json").write_text(json.dumps(INSIGHTS))
    (d / "request.json").write_text(json.dumps({
        "endpointId": FOLDER, "name": "Insights", "method": "GET",
        "url": "{{app_env.servers.api}}/{ad_set_id}/insights", "resource": "Insights",
        "bodyType": "NONE", "responses": [{"statusCode": 200, "contentType": "application/json",
                                           "contentContractRef": "responses/200.schema.json"}],
    }))  # fmt: skip
    pay = dst / "connector" / "endpoints" / "post-pay"
    pay.mkdir()
    money = {"$ref": "../../models/money.schema.json"}
    body = {"type": "object", "properties": {"amount": money}}
    (pay / "body.schema.json").write_text(json.dumps(body))
    (pay / "request.json").write_text(json.dumps({
        "endpointId": "post-pay", "name": "Pay", "method": "POST",
        "url": "{{app_env.servers.api}}/payments", "resource": "Payment",
        "bodyType": "JSON", "bodyContractRef": "body.schema.json", "responses": [],
    }))  # fmt: skip
    s = FakeStack()
    s.load(str(dst))
    return s


def _doc(stack: FakeStack, doc_id: str) -> dict[str, Any]:
    return payloads.document_payload(stack.get_document().execute("shopify", doc_id))


def test_a_marked_inline_copy_links_like_a_ref(stack: FakeStack) -> None:
    endpoint = _doc(stack, "endpoint:GET~/{ad_set_id}/insights")
    by_name = {f["name"]: f for f in endpoint["fields"]}
    assert by_name["data"]["model_id"] == "model:address"
    assert "data[].city" in by_name  # the inline schema is still walked
    model = _doc(stack, "model:address")
    uses = {u["doc_id"]: u for u in model["used_by"]}
    insights = uses["endpoint:GET~/{ad_set_id}/insights"]
    assert (insights["where"], insights["basis"]) == (["response"], "ref")
    assert model["used_by_total"] == len(model["used_by"])
    assert model["linked_endpoints"] == []


def test_ref_users_are_listed_and_other_kinds_have_none(stack: FakeStack) -> None:
    model = _doc(stack, "model:money")
    assert model["used_by"] == [
        {"doc_id": "endpoint:POST~/payments", "where": ["body"], "basis": "ref"}]  # fmt: skip
    assert _doc(stack, "endpoint:GET~/{ad_set_id}/insights")["used_by"] == []


def test_http_document_has_used_by(stack: FakeStack) -> None:
    client = TestClient(create_app(http_deps(stack)))
    body = client.get("/v1/apis/shopify/documents/model:address").json()
    assert body["usedByTotal"] == 1
    assert {"docId", "where", "basis"} <= set(body["usedBy"][0])
