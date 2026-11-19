"""A relation can start inside a member: Shipment's lines[].order_line_id -> Order line.id."""

from typing import Any

from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.model_set import parse_set_draft, validate_set
from plume.domain.models.validation import Oracle

EV = [{"doc_id": "d", "quote": "the shipment lines of the order"}]


def _leaf(name: str) -> dict[str, Any]:
    return {"name": name, "type": "string", "description": "d",
            "sources": {"a": {"paths": [name], "evidence": EV}}}  # fmt: skip


SHIPMENT = parse_draft({"name": "Shipment", "description": "d", "fields": [
    _leaf("id"),
    {"name": "lines", "type": "array", "description": "d", "fields": [_leaf("order_line_id")]},
]})  # fmt: skip
ORDER_LINE = parse_draft({"name": "Order line", "description": "d", "fields": [_leaf("id")]})


def _issues(field: str) -> list[str]:
    draft = parse_set_draft({
        "name": "Fulfilment", "description": "d",
        "members": [{"concept": "Shipment", "model_id": "m1"},
                    {"concept": "Order line", "model_id": "m2"}],
        "relations": [{"id": "r", "from": "Shipment", "to": "Order line", "kind": "reference",
                       "cardinality": "n:m", "ref": {"field": field, "key": "id"},
                       "confirmed": True,
                       "sources": {"a": {"as": "nested", "paths": ["lines"], "evidence": EV}}}],
    })  # fmt: skip
    oracle = Oracle(
        doc_text=lambda _a, _d: "the shipment lines of the order",
        field_exists=lambda _a, _p: True,
        endpoint_exists=lambda _a, _c: True,
    )
    members = {"Shipment": SHIPMENT, "Order line": ORDER_LINE}
    return [i.code for i in validate_set(draft, members, frozenset({"a"}), oracle)]


def test_a_relation_from_a_nested_field() -> None:
    assert _issues("lines[].order_line_id") == []
    assert _issues("lines.order_line_id") == []  # the [] may be left out
    assert _issues("lines[].nope") == ["RELATION_FIELD_NOT_FOUND"]
