"""PATH_NOT_IN_FETCH, SCALAR_FROM_OBJECT and ARRAY_FOR_SINGLE: shape errors become refusals."""

from typing import Any

from plume.domain.models.canonical_model import parse_draft
from plume.domain.models.validation import Oracle, validate

SHAPES = {
    "region": (frozenset({"object"}), ("region", "region_code", "region_id")),
    "country": (frozenset({"CountryRef"}), ("iso", "name")),  # a $ref'd model
    "tags": (frozenset({"array"}), ()),
    "status": (frozenset({"string"}), ()),
    "amount": (frozenset({"object", "string"}), ("value",)),  # scalar somewhere: fine
}
FETCH = {"GET /orders/{id}": frozenset({"order.id", "order.status", "order.tags"})}


def _oracle() -> Oracle:
    return Oracle(
        doc_text=lambda _a, _d: "anything",
        field_exists=lambda _a, p: p in SHAPES or p in {"variations[].sku"},
        endpoint_exists=lambda _a, call: call in FETCH or call == "GET /products",
        fetch_fields=lambda _a, call: FETCH.get(call),
        path_shape=lambda _a, p: SHAPES.get(p, (frozenset(), ())),
    )


def _codes(name: str, ftype: str, path: str, **src: Any) -> list[tuple[str, str]]:
    source = {"paths": [path], "evidence": [{"doc_id": "m", "quote": "anything"}], **src}
    field = {"name": name, "type": ftype, "description": "d", "sources": {"a": source}}
    draft = parse_draft({"name": "Order", "description": "d", "fields": [field]})
    return [(i.code, i.message) for i in validate(draft, frozenset({"a"}), _oracle())]


def test_scalar_from_object_lists_the_sub_fields() -> None:
    [(code, message)] = _codes("region", "string", "region")
    assert code == "SCALAR_FROM_OBJECT"
    assert "map one of its fields: region, region_code, region_id" in message
    [(code, message)] = _codes("country", "string", "country")
    assert code == "SCALAR_FROM_OBJECT"
    assert message.endswith("iso, name")


def test_scalars_and_containers_pass() -> None:
    assert _codes("status", "string", "status") == []
    assert _codes("amount", "decimal", "amount") == []  # the API states a scalar too
    assert _codes("region", "object", "region") == []  # an object canonical field


def test_a_list_for_a_single_value_needs_a_conversion() -> None:
    [(code, _)] = _codes("tag", "string", "tags")
    assert code == "ARRAY_FOR_SINGLE"
    assert _codes("tag", "string", "tags", conversion={"kind": "array-vs-single"}) == []
    assert _codes("tags", "array", "tags") == []


def test_fetch_must_return_the_path() -> None:
    assert _codes("status", "string", "status", fetch="GET /orders/{id}") == []
    [(code, message)] = _codes("sku", "string", "variations[].sku", fetch="GET /orders/{id}")
    assert code == "PATH_NOT_IN_FETCH"
    assert "not in the response of GET /orders/{id}" in message
    assert _codes("sku", "string", "variations[].sku", fetch="GET /products") == []  # unknown
