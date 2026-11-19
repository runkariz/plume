"""Nested objects in canonical models: parsing, canonical paths, validation, coverage."""

from datetime import UTC, datetime
from typing import Any

import pytest

from plume.domain.models.canonical_model import DraftFormatError, parse_draft
from plume.domain.models.snapshot import ModelSnapshot, PinnedInput, draft_json
from plume.domain.models.validation import Oracle, validate

EV = [{"doc_id": "d", "quote": "documented field of the order"}]


def _leaf(name: str, path: str | None = None, api: str = "a") -> dict[str, Any]:
    sources = {api: {"paths": [{"path": path}], "evidence": EV}} if path else {}
    return {"name": name, "type": "string", "sources": sources}


def _draft(*fields: dict[str, Any]) -> dict[str, Any]:
    return {"name": "Order", "fields": list(fields)}


NESTED = _draft(
    _leaf("id", "id"),
    {
        "name": "lines",
        "type": "array",
        "sources": {},
        "fields": [
            _leaf("sku", "lines[].sku"),
            {
                "name": "price",
                "type": "object",
                "fields": [_leaf("amount", "lines[].price.amount"), _leaf("currency")],
            },
        ],
    },
)


def test_canonical_paths_and_leaves() -> None:
    d = parse_draft(NESTED)
    assert [p for p, _ in d.walk()] == [
        "id",
        "lines",
        "lines[].sku",
        "lines[].price",
        "lines[].price.amount",
        "lines[].price.currency",
    ]
    assert [p for p, _ in d.leaves()] == [
        "id",
        "lines[].sku",
        "lines[].price.amount",
        "lines[].price.currency",
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_draft({"name": "a", "type": "string", "fields": [_leaf("b")]}), "only object or array"),
        (_draft({"name": "a", "type": "object", "fields": [_leaf("b.c")]}), "not a valid field"),
        (
            _draft({"name": "a", "type": "object", "fields": [_leaf("b"), _leaf("b")]}),
            "duplicate field 'b'",
        ),
        (
            _draft(
                {
                    "name": "a",
                    "type": "object",
                    "fields": [
                        {
                            "name": "b",
                            "type": "object",
                            "fields": [{"name": "c", "type": "object", "fields": [_leaf("d")]}],
                        }
                    ],
                }
            ),
            "at most 3 levels",
        ),
        (
            _draft({"name": "a", "type": "object", "fields": [_leaf(f"f{i}") for i in range(200)]}),
            "nested ones included",
        ),
    ],
)
def test_invalid_nesting_is_refused(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(DraftFormatError, match=message):
        parse_draft(raw)


def test_validation_reports_canonical_paths() -> None:
    documented = {"id", "lines[].sku"}
    oracle = Oracle(
        doc_text=lambda api, doc: "this is a documented field of the order",
        field_exists=lambda api, path: path in documented,
        endpoint_exists=lambda api, call: False,
    )
    issues = validate(parse_draft(NESTED), frozenset({"a"}), oracle)
    assert [(i.code, i.field) for i in issues] == [
        ("FIELD_NOT_FOUND", "lines[].price.amount"),
        ("NO_SOURCES", "lines[].price.currency"),
    ]  # the containers (lines, lines[].price) need no sources of their own


def test_coverage_counts_leaves_and_containers_follow_children() -> None:
    draft = parse_draft(NESTED)
    snap = ModelSnapshot(
        "m-x", "s", "Order", (PinnedInput("a", "b1"), PinnedInput("b", "b2")), draft,
        datetime(2026, 11, 16, tzinfo=UTC), 1,
    )  # fmt: skip
    support = snap.support("a")
    assert support["lines"] == "derived"  # mapped only through its sub-fields
    assert support["lines[].price"] == "derived"
    assert support["lines[].price.currency"] == "unsupported"
    assert snap.coverage() == {"a": (3, 4), "b": (0, 4)}


def test_serialisation_round_trips_and_flat_models_keep_their_shape() -> None:
    nested = parse_draft(NESTED)
    assert parse_draft(draft_json(nested)) == nested
    flat = parse_draft(_draft(_leaf("id", "id")))
    assert "fields" not in draft_json(flat)["fields"][0]  # unchanged JSON -> unchanged ids
