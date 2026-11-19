"""Operations (read / set / adjust ...): parsed, validated against the endpoints, scored
against gold operations."""

from typing import Any

import pytest

from plume.domain.models.canonical_model import DraftFormatError, parse_draft
from plume.domain.models.model_eval import (
    CORRECT,
    INVENTED,
    MISSED,
    NOT_AVAILABLE_CORRECT,
    WRONG,
    score,
)
from plume.domain.models.model_gold import parse_gold
from plume.domain.models.snapshot import draft_json
from plume.domain.models.validation import Oracle, validate

QUOTE = "Sets the inventory level for an item at a location."
ENDPOINTS = {
    "shop": {"POST /inventory_levels/set.json": {"available", "inventory_item_id"},
             "POST /inventory_levels/adjust.json": {"available_adjustment"}},
    "woo": {"PUT /products/{id}": {"stock_quantity"}},
}  # fmt: skip


def _src(endpoint: str, fields: list[str]) -> dict[str, Any]:
    return {"endpoint": endpoint, "fields": fields, "semantics": "absolute",
            "evidence": [{"doc_id": "e", "quote": QUOTE}]}  # fmt: skip


def _draft(*ops: dict[str, Any]) -> Any:
    ev = [{"doc_id": "e", "quote": QUOTE}]
    field = {"name": "id", "type": "string", "description": "d",
             "sources": {"shop": {"paths": ["id"], "evidence": ev}}}  # fmt: skip
    return parse_draft({"name": "Inventory", "description": "d", "fields": [field],
                        "operations": list(ops)})  # fmt: skip


def _oracle() -> Oracle:
    return Oracle(
        doc_text=lambda _a, _d: QUOTE,
        field_exists=lambda _a, _p: True,
        endpoint_exists=lambda api, call: call in ENDPOINTS.get(api, {}),
        call_fields=lambda api, call: frozenset(ENDPOINTS.get(api, {}).get(call, ())) or None,
    )


SET = {"name": "set absolute stock", "kind": "set", "sources": {
    "shop": _src("POST /inventory_levels/set.json", ["available"]),
    "woo": _src("PUT /products/{id}", ["stock_quantity"])}}  # fmt: skip


def test_operations_parse_and_serialise_only_when_present() -> None:
    draft = _draft(SET)
    assert [(o.name, o.kind, [a for a, _ in o.sources]) for o in draft.operations] == [
        ("set absolute stock", "set", ["shop", "woo"])
    ]
    assert draft_json(draft)["operations"][0]["sources"]["shop"]["fields"] == ["available"]
    assert "operations" not in draft_json(_draft())
    with pytest.raises(DraftFormatError, match="kind must be one of"):
        _draft({"name": "x", "kind": "teleport", "sources": {}})


def _codes(draft: Any) -> list[str]:
    return [i.code for i in validate(draft, frozenset({"shop", "woo"}), _oracle())]


def test_operations_are_validated() -> None:
    codes = _codes
    assert codes(_draft(SET)) == []
    bad_endpoint = {"name": "x", "kind": "set", "sources": {"shop": _src("POST /nope", [])}}
    assert codes(_draft(bad_endpoint)) == ["ENDPOINT_NOT_FOUND"]
    wrong = _src("POST /inventory_levels/set.json", ["quantity"])
    bad_field = {"name": "x", "kind": "set", "sources": {"shop": wrong}}
    assert codes(_draft(bad_field)) == ["OPERATION_FIELD_NOT_FOUND"]


GOLD = {
    "schema": "plume.model-gold.v1", "concept": "Inventory", "apis": ["shop", "woo"],
    "fields": [{"name": "id", "apis": {"shop": {"paths": ["id"]}}}],
    "operations": [
        {"name": "set absolute stock", "kind": "set", "apis": {
            "shop": {"endpoints": ["POST /inventory_levels/set.json"]},
            "woo": {"endpoints": ["PUT /products/{product_id}"]}}},
        {"name": "adjust by a delta", "kind": "adjust", "apis": {
            "shop": {"endpoints": ["POST /inventory_levels/adjust.json"]},
            "woo": {"notAvailable": True}}},
        {"name": "read stock", "kind": "read", "apis": {
            "shop": {"endpoints": ["GET /inventory_levels.json"]}}},
    ],
}  # fmt: skip


def test_operations_are_scored() -> None:
    [gold] = parse_gold(GOLD)
    adjust_wrong = {"name": "adjust by a delta", "kind": "adjust", "sources": {
        "shop": _src("POST /inventory_levels/set.json", []),  # exists, but it's the set call
        "woo": _src("POST /stock/delta", [])}}  # fmt: skip
    draft = _draft(SET, adjust_wrong)
    result = score(draft, gold, ("shop", "woo"), lambda _a, _p: True,
                   lambda api, call: call in ENDPOINTS.get(api, {}))  # fmt: skip
    cells = {(r.field, r.api): r.result for r in result.operations}
    assert cells == {
        ("set absolute stock", "shop"): CORRECT,
        ("set absolute stock", "woo"): CORRECT,  # {id} = {product_id}
        ("adjust by a delta", "shop"): WRONG,
        ("adjust by a delta", "woo"): INVENTED,  # gold: not available, and no such endpoint
        ("read stock", "shop"): MISSED,
    }
    ops: Any = result.as_dict()["operations"]
    assert ops["precision"] == round(2 / 4, 4)
    assert ops["recall"] == round(2 / 4, 4)
    only_set = score(_draft(SET), gold, ("shop", "woo"), lambda _a, _p: True)
    assert {(r.field, r.api): r.result for r in only_set.operations}[
        ("adjust by a delta", "woo")
    ] == NOT_AVAILABLE_CORRECT
