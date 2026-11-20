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
    "customer_id": (frozenset({"integer"}), ()),
    "salutation": (frozenset({"Salutation", "string"}), ()),  # a $ref'd enum model
    "billing": (frozenset({"object"}), ("city",)),
    "line_items": (frozenset({"array"}), ("sku",)),
    "country_iso_code": (frozenset({"string"}), ()),
}
COUNTRIES = tuple(f"C{i:03d}" for i in range(250))  # Mirakl: ~250 ISO alpha-3 codes
ENUMS = {"status": ("pending", "processing", "completed", "cancelled"),
         "country_iso_code": COUNTRIES}  # fmt: skip
FETCH = {"GET /orders/{id}": frozenset({"order.id", "order.status", "order.tags"})}


def _oracle() -> Oracle:
    return Oracle(
        doc_text=lambda _a, _d: "anything documented about this field here",
        field_exists=lambda _a, p: p in SHAPES or p in {"variations[].sku"},
        endpoint_exists=lambda _a, call: call in FETCH or call == "GET /products",
        fetch_fields=lambda _a, call: FETCH.get(call),
        path_shape=lambda _a, p: SHAPES.get(p, (frozenset(), ())),
        path_enum=lambda _a, p, docs: ENUMS.get(p) if "m" in docs else None,
    )


def _codes(name: str, ftype: str, path: str, **src: Any) -> list[tuple[str, str]]:
    quote = "anything documented about this field"
    source = {"paths": [path], "evidence": [{"doc_id": "m", "quote": quote}], **src}
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


def test_a_list_field_needs_a_list() -> None:
    [(code, message)] = _codes("lines", "array", "customer_id")
    assert code == "SINGLE_FOR_ARRAY"
    assert "customer_id is a single integer" in message
    assert _codes("lines", "array", "line_items") == []
    assert _codes("lines", "array", "customer_id", conversion={"kind": "cardinality"}) == []
    assert [c for c, _ in _codes("addresses", "array", "salutation")] == ["SINGLE_FOR_ARRAY"]
    assert [c for c, _ in _codes("addresses", "array", "billing")] == ["SINGLE_FOR_ARRAY"]


def test_enum_maps_cover_the_api_enum() -> None:
    full = {"pending": "OPEN", "processing": "OPEN", "completed": "DONE", "cancelled": "VOID"}
    assert _codes("state", "string", "status", conversion={"kind": "enum", "map": full}) == []
    part = {"kind": "enum", "map": {"pending": "OPEN", "completed": "DONE"}}
    [(code, message)] = _codes("state", "string", "status", conversion=part)
    assert code == "ENUM_MAP_INCOMPLETE"
    assert "leaves processing, cancelled" in message
    marked = {**part, "unmapped": ["processing", "cancelled"]}
    assert _codes("state", "string", "status", conversion=marked) == []
    wrong = {"kind": "enum", "map": {**full, "shipped": "DONE"}}
    [(code, message)] = _codes("state", "string", "status", conversion=wrong)
    assert code == "ENUM_KEY_UNKNOWN"
    assert "no value shipped" in message


def test_a_code_list_is_a_code_system_conversion() -> None:
    """set-g1 (2): Mirakl country_iso_code (~250 alpha-3 codes) demanded a 250-entry map."""
    import pytest  # noqa: PLC0415

    from plume.domain.models.canonical_model import DraftFormatError  # noqa: PLC0415

    one = {"kind": "enum", "map": {"C000": "AA"}}
    [(code, message)] = _codes("country", "string", "country_iso_code", conversion=one)
    assert code == "ENUM_MAP_INCOMPLETE"
    assert "and 209 more" in message
    assert "code-system" in message
    iso = {"kind": "code-system", "format": "ISO 3166-1 alpha-3 -> alpha-2"}
    assert _codes("country", "string", "country_iso_code", conversion=iso) == []
    with pytest.raises(DraftFormatError, match="code-system conversion needs format"):
        _codes("country", "string", "country_iso_code", conversion={"kind": "code-system"})
    [(_, short)] = _codes("state", "string", "status",
                          conversion={"kind": "enum", "map": {"pending": "OPEN"}})  # fmt: skip
    assert "code-system" not in short
