"""x-kariz-conflicts beyond whole-endpoint disagreements (Meta Commerce 27d):
- kind "condition" in request.json (one vendor sentence, "Required if item_id is not
  provided"): shown as a condition on that field, not a disagreement; check_call notes it when
  the field is sent;
- a property-level conflict in a model (transaction_type: SALE/REFUND vs six reason codes):
  lifted to the document with its field, and find_fact notes it on that field."""

import json
import shutil
from typing import Any

import pytest

from plume.domain.knowledge.document import (
    Conflict,
    ConflictStatement,
    conflict_concerns,
    conflicts_of,
)
from plume.interfaces import payloads
from tests.fakes.stack import FakeStack

FOLDER = "post-refunds"
CONDITION = {"kind": "condition", "limit": "field retailer_id required",
             "statements": [{"quote": "Required if item_id is not provided.",
                             "where": "description"}]}  # fmt: skip
RESPONSE_ITEM = {"limit": "item_id type", "field": "items[].item_id", "where": "response:200",
                 "statements": [{"where": "inline schema", "quote": "item_id: string"},
                                {"where": "model", "quote": "item_id: integer"}]}  # fmt: skip
TRANSACTION = {"limit": "transaction_type values", "statements": [
    {"where": "page", "quote": "Allowed values are: SALE or REFUND."},
    {"where": "page", "quote": "transaction_type Reason code for the transaction"}]}  # fmt: skip


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> FakeStack:
    from tests.conftest import PACKAGES  # noqa: PLC0415

    dst = tmp_path_factory.mktemp("cond") / "shopify"
    shutil.copytree(PACKAGES / "shopify-mini", dst)
    d = dst / "connector" / "endpoints" / FOLDER
    d.mkdir()
    item = {"type": "object", "properties": {"retailer_id": {"type": "string"},
                                             "item_id": {"type": "string"}}}  # fmt: skip
    body = {"type": "object", "properties": {"items": {"type": "array", "items": item}}}
    (d / "body.schema.json").write_text(json.dumps(body))
    (d / "request.json").write_text(json.dumps({
        "endpointId": FOLDER, "name": "Refund", "method": "POST",
        "url": "{{app_env.servers.api}}/orders/{order_id}/refunds", "resource": "Refund",
        "bodyType": "JSON", "bodyContractRef": "body.schema.json", "responses": [],
        "x-kariz-conflicts": [CONDITION, RESPONSE_ITEM],
    }))  # fmt: skip
    model = {"title": "TransactionDetail", "type": "object", "properties": {
        "transaction_type": {"type": "string", "enum": ["SALE", "REFUND"],
                             "x-kariz-conflicts": [TRANSACTION]}}}  # fmt: skip
    (dst / "connector" / "models" / "transaction-detail.schema.json").write_text(json.dumps(model))
    s = FakeStack()
    s.load(str(dst))
    return s


def _doc(stack: FakeStack, doc_id: str) -> dict[str, Any]:
    return payloads.document_payload(stack.get_document().execute("shopify", doc_id))


def test_a_condition_is_shown_as_a_condition_on_its_field(stack: FakeStack) -> None:
    c, response = _doc(stack, "endpoint:POST~/orders/{order_id}/refunds")["conflicts"]
    assert (c["kind"], c["field"], c["where"]) == ("condition", "items[].retailer_id", None)
    assert (response["field"], response["where"]) == ("items[].item_id", "response:200")
    assert c["text"] == (
        "Condition on items[].retailer_id (required only in this case):\n"
        '- description: "Required if item_id is not provided."'
    )


def test_check_call_notes_a_sent_conditional_field(stack: FakeStack) -> None:
    sent = ["items[].retailer_id", "items[].item_id"]
    call = stack.check_call().execute("shopify", "POST", "/orders/1/refunds", sent)
    r = payloads.check_call_payload(call)
    notes = {p["name"]: p["note"] for p in r["params"]}
    assert notes["items[].retailer_id"].startswith(
        "Condition on items[].retailer_id (required only in this case):"
    )
    assert not notes["items[].item_id"]  # its conflict is placed in the response


def test_a_property_conflict_is_lifted_with_its_field(stack: FakeStack) -> None:
    [c] = _doc(stack, "model:transaction-detail")["conflicts"]
    assert (c["kind"], c["field"]) == ("conflict", "transaction_type")
    assert c["text"].startswith("The docs state different values for transaction_type values:")
    [m] = [x for x in stack.find_fact().execute("shopify", "transaction_type").matches
           if x.owner_id == "model:transaction-detail"]  # fmt: skip
    assert m.note is not None
    assert "Allowed values are: SALE or REFUND." in m.note


def test_conflicts_of_rules() -> None:
    lone = {"limit": "x", "statements": [{"where": "a", "quote": "q"}]}
    assert conflicts_of({"x-kariz-conflicts": [lone]}) == ()  # a disagreement needs two
    [c] = conflicts_of({"x-kariz-conflicts": [CONDITION]})
    assert (c.kind, c.field) == ("condition", "retailer_id")
    nested = Conflict("y", (ConflictStatement("a", "q"),), "conflict", "data[].transaction_type")
    assert conflict_concerns(nested, "data[].transaction_type")
    assert conflict_concerns(nested, "transaction_type")
    assert not conflict_concerns(nested, "type")


def test_the_producers_field_and_where_win_over_the_fallbacks() -> None:
    """Stream's explicit field is used as given (no suffix match, no limit pattern); its
    item-level where is kept."""
    explicit = {**CONDITION, "field": "retailer_id", "where": "body"}
    [c] = conflicts_of({"x-kariz-conflicts": [explicit]}, ["items[].retailer_id"])
    assert (c.field, c.place) == ("retailer_id", "body")
    [bare] = conflicts_of({"x-kariz-conflicts": [CONDITION]}, ["items[].retailer_id"])
    assert bare.field == "items[].retailer_id"  # fallback: the pattern, then the suffix match
    placed = Conflict("t", (ConflictStatement("a", "q"),), "conflict", "end_time", "response:200")
    assert conflict_concerns(placed, "end_time")
    assert not conflict_concerns(placed, "end_time", request=True)
