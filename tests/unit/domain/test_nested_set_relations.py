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


def _issues(field: str, source_path: str = "lines") -> list[str]:
    draft = parse_set_draft({
        "name": "Fulfilment", "description": "d",
        "members": [{"concept": "Shipment", "model_id": "m1"},
                    {"concept": "Order line", "model_id": "m2"}],
        "relations": [{"id": "r", "from": "Shipment", "to": "Order line", "kind": "reference",
                       "cardinality": "n:m", "ref": {"field": field, "key": "id"},
                       "confirmed": True,
                       "sources": {"a": {"as": "nested", "paths": [source_path],
                                         "evidence": EV}}}],
    })  # fmt: skip
    oracle = Oracle(
        doc_text=lambda _a, _d: "the shipment lines of the order",
        field_exists=lambda _a, p: p == "lines",
        endpoint_exists=lambda _a, _c: True,
    )
    members = {"Shipment": SHIPMENT, "Order line": ORDER_LINE}
    return [i.code for i in validate_set(draft, members, frozenset({"a"}), oracle)]


def test_a_relation_from_a_nested_field() -> None:
    assert _issues("lines[].order_line_id") == []
    assert _issues("lines.order_line_id") == []  # the [] may be left out
    assert _issues("lines[].nope") == ["RELATION_FIELD_NOT_FOUND"]


def test_a_list_source_path_may_end_in_brackets() -> None:
    assert _issues("lines[].order_line_id", "lines[]") == []  # set-g3: order_lines[] refused
    assert _issues("lines[].order_line_id", "nope[]") == ["FIELD_NOT_FOUND"]


DOC = (
    "- `line_items[]` (array): The order's line items, one per product bought.\n"
    "- `meta_data[].id` (integer): Meta ID.\n"
    "- `shipping_lines[]` (array): Shipping lines"
)
TEXTS = {
    "line_items": ("The order's line items, one per product bought.",
                   "- `line_items[]` (array): The order's line items, one per product bought."),
    "shipping_lines": ("Shipping lines", "- `shipping_lines[]` (array): Shipping lines"),
}  # fmt: skip


def _relation_codes(path: str, evidence: dict[str, Any], as_: str = "nested") -> list[str]:
    src: dict[str, Any] = {"as": as_, "paths": [path], "evidence": [evidence]}
    if as_ == "sub_resource":
        src = {"as": as_, "paths": [], "fetch": "GET /orders/{id}/lines", "evidence": [evidence]}
    draft = parse_set_draft({
        "name": "Orders", "description": "d",
        "members": [{"concept": "Shipment", "model_id": "m1"},
                    {"concept": "Order line", "model_id": "m2"}],
        "relations": [{"id": "r", "from": "Shipment", "to": "Order line", "kind": "reference",
                       "ref": {"field": "lines[].order_line_id", "key": "id"},
                       "cardinality": "n:m", "confirmed": True, "sources": {"a": src}}],
    })  # fmt: skip
    oracle = Oracle(
        doc_text=lambda _a, _d: DOC,
        field_exists=lambda _a, p: p in TEXTS,
        endpoint_exists=lambda _a, _c: True,
        field_texts=lambda _a, _d, p: TEXTS.get(p.removesuffix("[]")),
    )
    members = {"Shipment": SHIPMENT, "Order line": ORDER_LINE}
    return [i.code for i in validate_set(draft, members, frozenset({"a"}), oracle)]


def test_relation_evidence_follows_the_field_evidence_rules() -> None:
    """set-g1 (3): woo line_items[] was cited with "Meta ID." (another field's quote);
    set-g4 (2): relation evidence had no noQuote form and no short-quote check."""
    good = {"doc_id": "d", "quote": "The order's line items, one per product bought."}
    assert _relation_codes("line_items[]", good) == []
    other = {"doc_id": "d", "quote": "Meta ID."}
    assert _relation_codes("line_items[]", other) == ["QUOTE_NOT_ON_FIELD"]
    one_word = {"doc_id": "d", "noQuote": "the description is two words"}
    assert _relation_codes("shipping_lines[]", one_word) == []
    assert _relation_codes("line_items[]", one_word) == ["NO_QUOTE_NOT_ALLOWED"]
    endpoint_quote = {"doc_id": "d", "quote": "The order's line items, one per product bought."}
    assert _relation_codes("", endpoint_quote, "sub_resource") == []
    assert _relation_codes("", one_word, "sub_resource") == ["NO_QUOTE_NOT_ALLOWED"]
